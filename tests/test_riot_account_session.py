from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlencode

import pytest
import requests

from peaks.adapters.riot.account_session import (
    ACCOUNT_CALLBACK_URL,
    AUTHENTICATOR_SESSION_URL,
    MAX_PAGE_BYTES,
    MAX_PROMPT_BYTES,
    MAX_SESSION_STATE_LENGTH,
    RIOT_AUTH_ISSUER,
    RiotAccountSessionChallengeError,
    RiotAccountSessionError,
    RiotAccountSessionHttpError,
    acquire_riot_account_session,
)

STATE = "generated-account-state"
AUTHORIZE = "https://auth.riotgames.com/authorize?" + urlencode({
    "client_id": "accountodactyl-prod",
    "redirect_uri": ACCOUNT_CALLBACK_URL,
    "response_type": "code",
    "scope": "openid email profile",
    "acr_values": "urn:riot:gold",
    "state": STATE,
})
CALLBACK = ACCOUNT_CALLBACK_URL + "?" + urlencode({"code": "CODE-SECRET", "state": STATE})
HANDOFF_QUERY = urlencode({
    "client_id": "accountodactyl-prod", "security_profile": "high",
    "method": "riot_identity", "redirect_uri": AUTHORIZE,
})
HANDOFF = "https://authenticate.riotgames.com/login?" + HANDOFF_QUERY
FRONTEND = "https://authenticate.riotgames.com/?" + HANDOFF_QUERY


class FakeResponse:
    def __init__(
        self,
        status: int,
        location: str | None = None,
        cookies: tuple[tuple[str, str, str], ...] = (),
        body: bytes = b"<html></html>",
    ) -> None:
        self.status_code = status
        self.headers = {"Location": location} if location is not None else {}
        self.cookies = cookies
        self.body = body
        self.closed = False

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.closed = True

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        for start in range(0, len(self.body), chunk_size):
            yield self.body[start:start + chunk_size]


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.cookies = requests.cookies.RequestsCookieJar()
        self.trust_env = True
        self.requests: list[tuple[str, str, dict[str, Any], str]] = []
        self.closed = False

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        prepared = requests.Request(method, url).prepare()
        cookie_header = requests.cookies.get_cookie_header(self.cookies, prepared) or ""
        self.requests.append((method, url, kwargs, cookie_header))
        response = self.responses[len(self.requests) - 1]
        for name, value, domain in response.cookies:
            self.cookies.set(name, value, domain=domain, path="/", secure=True)
        return response

    def close(self) -> None:
        self.closed = True


def _responses() -> list[FakeResponse]:
    return [
        FakeResponse(302, "/log-in"),
        FakeResponse(302, AUTHORIZE, (("state", STATE, "account.riotgames.com"),)),
        FakeResponse(302, CALLBACK, (("ssid", "ROTATED-SSO", "auth.riotgames.com"),)),
        FakeResponse(302, "/", (
            ("account_session", "ACCOUNT-SECRET", "account.riotgames.com"),
            ("a12l-csrf-prod", "CSRF-SECRET", "account.riotgames.com"),
        )),
        FakeResponse(200),
    ]


def _frontend_responses(prompt: object | None = None) -> list[FakeResponse]:
    base = _responses()
    payload = {"type": "success", "success": {"redirect_url": AUTHORIZE}} if prompt is None else prompt
    return [*base[:2], FakeResponse(303, HANDOFF),
        FakeResponse(302, FRONTEND, (("authenticator.sid", "PROMPT-SECRET", "authenticate.riotgames.com"),)),
        FakeResponse(200), FakeResponse(200, body=json.dumps(payload).encode()), *base[2:]]


def test_sso_exchange_keeps_cookie_hosts_separate_and_returns_ephemeral_session() -> None:
    session = FakeSession(_responses())
    session.cookies.set("other_account", "STALE-SECRET", domain="account.riotgames.com")

    result = acquire_riot_account_session({"ssid": "SSO-SECRET", "sub": "owned-id"}, session=session)

    assert session.trust_env is False
    assert result.account_cookies["account_session"] == "ACCOUNT-SECRET"
    assert result.csrf_token == "CSRF-SECRET"
    assert dict(result.sso_cookies) == {"ssid": "ROTATED-SSO", "sub": "owned-id"}
    assert "ssid" not in result.account_cookies
    assert len(session.requests) == 5
    for method, url, kwargs, sent_cookies in session.requests:
        assert method == "GET"
        assert kwargs["allow_redirects"] is False
        assert kwargs["verify"] is True
        assert kwargs["stream"] is True
        assert "STALE-SECRET" not in sent_cookies
        if url.startswith("https://account.riotgames.com/"):
            assert "SSO-SECRET" not in sent_cookies
            assert "ROTATED-SSO" not in sent_cookies
        else:
            assert "SSO-SECRET" in sent_cookies
            assert "ACCOUNT-SECRET" not in sent_cookies
    assert not list(session.cookies)
    assert all(response.closed for response in session.responses)
    assert "SECRET" not in repr(result)


@pytest.mark.parametrize("destination", [
    "https://evil.example/authorize",
    "http://auth.riotgames.com/authorize",
    "https://auth.riotgames.com:443/authorize",
    "https://auth.riotgames.com.evil.example/authorize",
    "https://account.riotgames.com@evil.example/",
    "https://user:password@account.riotgames.com/",
    "https://account.riotgames.com/log-out",
    "https://account.riotgames.com/\\evil.example",
    "https://account.riotgames.com/\n",
    "https://account.riotgames.com/#CODE-SECRET",
    "https://account.riotgames.com/?redirect=https://evil.example",
])
def test_untrusted_redirects_are_rejected_before_request(destination: str) -> None:
    session = FakeSession([FakeResponse(302, destination)])
    with pytest.raises(RiotAccountSessionError) as caught:
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert len(session.requests) == 1
    assert destination not in str(caught.value)
    assert not list(session.cookies)
    assert session.responses[0].closed


@pytest.mark.parametrize("replacement", [
    AUTHORIZE.replace("accountodactyl-prod", "other-client"),
    AUTHORIZE.replace("urn%3Ariot%3Agold", "urn%3Ariot%3Asilver"),
    AUTHORIZE.replace("response_type=code", "response_type=token"),
    AUTHORIZE.replace("https%3A%2F%2Faccount.riotgames.com%2Foauth2%2Flog-in", "https%3A%2F%2Fevil.example"),
    AUTHORIZE + "&state=duplicate",
])
def test_only_account_oauth_request_with_high_assurance_is_accepted(replacement: str) -> None:
    session = FakeSession([FakeResponse(302, replacement)])
    with pytest.raises(RiotAccountSessionError):
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert len(session.requests) == 1


@pytest.mark.parametrize("callback", [
    CALLBACK.replace(STATE, "wrong-state"),
    CALLBACK + "&state=duplicate",
    CALLBACK + "&code=duplicate",
    CALLBACK + "&redirect=https://evil.example",
    ACCOUNT_CALLBACK_URL + "?code=CODE-SECRET",
    ACCOUNT_CALLBACK_URL + "?state=" + STATE,
])
def test_callback_state_and_code_are_checked_before_visiting(callback: str) -> None:
    responses = _responses()
    responses[2] = FakeResponse(302, callback)
    session = FakeSession(responses)
    with pytest.raises(RiotAccountSessionError):
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert len(session.requests) == 3


def test_unsolicited_callback_is_rejected() -> None:
    session = FakeSession([FakeResponse(302, CALLBACK)])
    with pytest.raises(RiotAccountSessionError, match="could not be verified"):
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert len(session.requests) == 1


@pytest.mark.parametrize("via_frontend", [False, True])
def test_rfc9207_riot_issuer_is_accepted_on_bound_oauth_callback(via_frontend: bool) -> None:
    from peaks.diagnostic_policy import sanitize_diagnostic_message

    callback = CALLBACK + "&" + urlencode({"iss": RIOT_AUTH_ISSUER})
    responses = _frontend_responses() if via_frontend else _responses()
    responses[-3].headers["Location"] = callback
    output = io.StringIO()
    diagnostic = logging.Logger("issuer-test", level=logging.INFO)
    diagnostic.addHandler(logging.StreamHandler(output))
    session = FakeSession(responses)
    result = acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session, logger=diagnostic)
    assert result.csrf_token == "CSRF-SECRET"
    lines = output.getvalue().splitlines()
    assert "riot_account_session.callback has_issuer=True has_error=False has_session_state=False" in lines
    assert all(sanitize_diagnostic_message(line) == line for line in lines)
    assert "CODE-SECRET" not in output.getvalue()
    assert "https://" not in output.getvalue()


@pytest.mark.parametrize("issuer_query", [
    urlencode({"iss": "https://evil.example"}),
    urlencode({"iss": "http://auth.riotgames.com"}),
    urlencode({"iss": RIOT_AUTH_ISSUER + "/"}),
    urlencode({"iss": RIOT_AUTH_ISSUER + "?extra=value"}),
    urlencode({"iss": RIOT_AUTH_ISSUER + ".evil.example"}),
    "iss=",
    urlencode({"iss": RIOT_AUTH_ISSUER}) + "&iss=https%3A%2F%2Fauth.riotgames.com",
    urlencode({"iss": RIOT_AUTH_ISSUER}) + "&redirect=https://evil.example",
])
def test_invalid_duplicate_or_extra_issuer_callback_fields_are_rejected(issuer_query: str) -> None:
    responses = _responses()
    responses[2].headers["Location"] = CALLBACK + "&" + issuer_query
    session = FakeSession(responses)
    with pytest.raises(RiotAccountSessionError, match="could not be verified"):
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert len(session.requests) == 3
    assert not list(session.cookies)


def test_valid_issuer_cannot_replace_oauth_state_binding() -> None:
    responses = _responses()
    responses[2].headers["Location"] = CALLBACK.replace(STATE, "wrong-state") + "&" + urlencode({"iss": RIOT_AUTH_ISSUER})
    output = io.StringIO()
    diagnostic = logging.Logger("issuer-state-test", level=logging.INFO)
    diagnostic.addHandler(logging.StreamHandler(output))
    session = FakeSession(responses)
    with pytest.raises(RiotAccountSessionError, match="could not be verified"):
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session, logger=diagnostic)
    assert len(session.requests) == 3
    assert "reason=callback_state" in output.getvalue()
    assert "wrong-state" not in output.getvalue()


@pytest.mark.parametrize("include_issuer", [False, True])
def test_openid_session_state_is_forwarded_only_with_original_oauth_state(include_issuer: bool) -> None:
    from peaks.diagnostic_policy import sanitize_diagnostic_message

    parameters = {"session_state": "OPAQUE-SESSION-SECRET.hash"}
    if include_issuer:
        parameters["iss"] = RIOT_AUTH_ISSUER
    callback = CALLBACK + "&" + urlencode(parameters)
    responses = _responses()
    responses[2].headers["Location"] = callback
    output = io.StringIO()
    diagnostic = logging.Logger("session-state-test", level=logging.INFO)
    diagnostic.addHandler(logging.StreamHandler(output))
    session = FakeSession(responses)
    result = acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session, logger=diagnostic)
    assert result.csrf_token == "CSRF-SECRET"
    assert session.requests[3][1] == callback
    assert "has_session_state=True" in output.getvalue()
    assert "OPAQUE-SESSION-SECRET" not in output.getvalue()
    assert all(sanitize_diagnostic_message(line) == line for line in output.getvalue().splitlines())


@pytest.mark.parametrize("value", ["", "with space", "with\ttab", "with\x00control", "with\x80control", "x" * (MAX_SESSION_STATE_LENGTH + 1)], ids=["empty", "space", "tab", "null", "c1-control", "oversized"])
def test_invalid_openid_session_state_is_rejected_before_callback(value: str) -> None:
    responses = _responses()
    responses[2].headers["Location"] = CALLBACK + "&" + urlencode({"session_state": value})
    session = FakeSession(responses)
    with pytest.raises(RiotAccountSessionError, match="could not be verified"):
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert len(session.requests) == 3


@pytest.mark.parametrize("callback", [
    CALLBACK + "&session_state=first&session_state=second",
    CALLBACK.replace(STATE, "wrong-state") + "&session_state=" + STATE,
])
def test_session_state_cannot_be_duplicated_or_used_as_oauth_state(callback: str) -> None:
    responses = _responses()
    responses[2].headers["Location"] = callback
    session = FakeSession(responses)
    with pytest.raises(RiotAccountSessionError, match="could not be verified"):
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert len(session.requests) == 3


@pytest.mark.parametrize("kind", ["auth", "re-auth", "multifactor"])
def test_actual_interactive_prompt_stops_without_submitting_credentials(kind: str) -> None:
    session = FakeSession(_frontend_responses({
        "type": kind, kind: {"private": "SECRET"},
        "success": {"redirect_url": AUTHORIZE},
    }))
    with pytest.raises(RiotAccountSessionChallengeError, match="before changing MFA") as caught:
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert len(session.requests) == 6
    assert all(method == "GET" for method, *_rest in session.requests)
    assert "SECRET" not in str(caught.value)
    assert not list(session.cookies)


def test_passive_frontend_success_resumes_same_oauth_request_without_browser() -> None:
    session = FakeSession(_frontend_responses())
    result = acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert result.csrf_token == "CSRF-SECRET"
    assert len(session.requests) == 9
    assert session.requests[5][1] == AUTHENTICATOR_SESSION_URL
    assert session.requests[5][2]["headers"]["Accept"] == "application/json"
    assert session.requests[5][2]["allow_redirects"] is False
    assert session.requests[5][2]["verify"] is True
    for method, url, _kwargs, cookies in session.requests:
        assert method == "GET"
        if url.startswith("https://authenticate.riotgames.com/"):
            assert "SSO-SECRET" not in cookies
        else:
            assert "PROMPT-SECRET" not in cookies
    assert "authenticator.sid" not in result.account_cookies
    assert "authenticator.sid" not in result.sso_cookies
    assert not list(session.cookies)


def test_passive_frontend_success_accepts_direct_callback_with_original_state() -> None:
    responses = _frontend_responses({"type": "success", "success": {"redirect_url": CALLBACK}})
    responses.pop(6)  # The success redirect already supplies the OAuth callback.
    session = FakeSession(responses)
    result = acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert result.csrf_token == "CSRF-SECRET"
    assert len(session.requests) == 8


@pytest.mark.parametrize("target", [
    "https://evil.example/", "https://account.riotgames.com/",
    CALLBACK.replace(STATE, "WRONG-STATE"),
    AUTHORIZE.replace(STATE, "WRONG-STATE"),
    AUTHORIZE + "&state=duplicate",
    "https://authenticate.riotgames.com/api/v1/login",
])
def test_passive_success_cannot_redirect_to_other_flow_or_mismatched_state(target: str) -> None:
    session = FakeSession(_frontend_responses({"type": "success", "success": {"redirect_url": target}}))
    with pytest.raises(RiotAccountSessionError):
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert len(session.requests) == 6


@pytest.mark.parametrize("target", [
    HANDOFF.replace("security_profile=high", "security_profile=low"),
    HANDOFF.replace("method=riot_identity", "method=unrecognized"),
    HANDOFF + "&state=unrelated",
    HANDOFF + "&client_id=other",
    HANDOFF.replace("/login?", "/api/v1/login?"),
    HANDOFF.replace("accountodactyl-prod", "other-client"),
    HANDOFF.replace("redirect_uri=", "unknown_uri="),
])
def test_invalid_frontend_context_is_rejected_before_following(target: str) -> None:
    responses = _frontend_responses()
    responses[2] = FakeResponse(303, target)
    session = FakeSession(responses)
    with pytest.raises(RiotAccountSessionError):
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert len(session.requests) == 3


@pytest.mark.parametrize(
    "body", [b"not-json", b"[]", b'{}', b'{"type":"success"}', b'x' * (MAX_PROMPT_BYTES + 1)],
    ids=["not-json", "array", "empty", "incomplete-success", "oversized"],
)
def test_invalid_or_oversized_frontend_response_is_not_success(body: bytes) -> None:
    responses = _frontend_responses()
    responses[5] = FakeResponse(200, body=body)
    session = FakeSession(responses)
    with pytest.raises(RiotAccountSessionError):
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert len(session.requests) == 6


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_http_rejection_is_not_reported_as_required_identity_verification(status: int) -> None:
    session = FakeSession([FakeResponse(status)])
    with pytest.raises(RiotAccountSessionHttpError, match="account connection") as caught:
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert caught.value.status_code == status
    assert not isinstance(caught.value, RiotAccountSessionChallengeError)


def test_diagnostics_distinguish_browser_block_from_identity_challenge() -> None:
    from peaks.diagnostic_policy import sanitize_diagnostic_message

    output = io.StringIO()
    diagnostic = logging.Logger("account-session-test", level=logging.INFO)
    handler = logging.StreamHandler(output)
    diagnostic.addHandler(handler)
    response = FakeResponse(403)
    response.headers["cf-mitigated"] = "challenge"
    with pytest.raises(RiotAccountSessionHttpError) as caught:
        acquire_riot_account_session(
            {"ssid": "SSO-SECRET"}, session=FakeSession([response]), logger=diagnostic,
        )
    assert caught.value.browser_challenge is True
    lines = output.getvalue().splitlines()
    assert lines == [
        "riot_account_session.response stage=account_home status=403",
        "riot_account_session.rejected stage=account_home status=403 reason=browser_challenge",
    ]
    assert all(sanitize_diagnostic_message(line) == line for line in lines)
    assert "SECRET" not in output.getvalue()


def test_authorization_redirect_diagnostic_preserves_stage_without_oauth_secrets() -> None:
    from peaks.diagnostic_policy import sanitize_diagnostic_message

    output = io.StringIO()
    diagnostic = logging.Logger("account-session-test", level=logging.INFO)
    diagnostic.addHandler(logging.StreamHandler(output))
    responses = _frontend_responses({"type": "auth", "auth": {"private": "SECRET"}})
    with pytest.raises(RiotAccountSessionChallengeError):
        acquire_riot_account_session(
            {"ssid": "SSO-SECRET"}, session=FakeSession(responses), logger=diagnostic,
        )
    lines = output.getvalue().splitlines()
    assert "riot_account_session.handoff stage=account_authorize status=303" in lines
    assert lines[-1] == "riot_account_session.prompt prompt=auth"
    assert all(sanitize_diagnostic_message(line) == line for line in lines)
    assert "SECRET" not in output.getvalue()


@pytest.mark.parametrize("cookies", [{}, {"sub": "id"}, {"ssid": "x", "other": "x"}, {"ssid": "x;other=x"}])
def test_invalid_saved_cookie_input_never_makes_a_request(cookies: dict[str, str]) -> None:
    session = FakeSession([])
    with pytest.raises(RiotAccountSessionError, match="Reconnect"):
        acquire_riot_account_session(cookies, session=session)
    assert session.requests == []


def test_public_success_page_cannot_be_mistaken_for_authenticated_account() -> None:
    session = FakeSession([FakeResponse(200)])
    with pytest.raises(RiotAccountSessionError, match="could not be completed"):
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)


def test_redirect_loop_is_bounded() -> None:
    session = FakeSession([FakeResponse(302, "/") for _ in range(9)])
    with pytest.raises(RiotAccountSessionError, match="could not be completed"):
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert len(session.requests) == 9


def test_missing_csrf_cookie_and_oversized_page_fail_closed() -> None:
    responses = _responses()
    responses[3] = FakeResponse(302, "/")
    with pytest.raises(RiotAccountSessionError, match="could not be completed"):
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=FakeSession(responses))
    responses = _responses()
    responses[4] = FakeResponse(200, body=b"x" * (MAX_PAGE_BYTES + 1))
    with pytest.raises(RiotAccountSessionError, match="size limit"):
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=FakeSession(responses))


def test_transport_error_does_not_expose_secret_exception_or_leave_cookies() -> None:
    class FailingSession(FakeSession):
        def request(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
            raise requests.RequestException("failed CODE-SECRET SSO-SECRET")

    session = FailingSession([])
    with pytest.raises(RiotAccountSessionError, match="Could not connect") as caught:
        acquire_riot_account_session({"ssid": "SSO-SECRET"}, session=session)
    assert "SECRET" not in str(caught.value)
    assert caught.value.__suppress_context__ is True
    assert not list(session.cookies)


def test_default_session_is_closed_and_cleared_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from peaks.adapters.riot import account_session

    session = FakeSession(_responses())
    monkeypatch.setattr(account_session.requests, "Session", lambda: session)
    result = acquire_riot_account_session({"ssid": "SSO-SECRET"})
    assert result.csrf_token == "CSRF-SECRET"
    assert session.closed is True
    assert not list(session.cookies)


def test_default_session_is_closed_and_cleared_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from peaks.adapters.riot import account_session

    session = FakeSession([FakeResponse(503)])
    monkeypatch.setattr(account_session.requests, "Session", lambda: session)
    with pytest.raises(RiotAccountSessionError):
        acquire_riot_account_session({"ssid": "SSO-SECRET"})
    assert session.closed is True
    assert not list(session.cookies)
