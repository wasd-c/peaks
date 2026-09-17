from __future__ import annotations

import io
import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

import pytest
import requests

from peaks.adapters.riot.browser_login import RiotAccountBrowserSession
from peaks.adapters.riot.mfa import (
    RIOT_ACCOUNT_PAGE_URL,
    RIOT_ACCOUNT_USER_URL,
    RIOT_MFA_FACTORS_URL,
    RIOT_MOBILE_ENABLE_URL,
    RIOT_MOBILE_VERIFY_URL,
    RiotAccountIdentity,
    RiotMfaClient,
    RiotMfaError,
    RiotMfaFactor,
    RiotMfaHttpError,
)
from peaks.adapters.riot.session_import import AuthenticatedRiotIdentity
from peaks.application.riot_mobile_totp_setup import (
    RiotMobileTotpConfirmationError,
    RiotMobileTotpIdentityMismatchError,
    RiotMobileTotpPrerequisiteError,
    RiotMobileTotpSetupCancelledError,
    RiotMobileTotpSetupError,
    RiotMobileTotpSetupResult,
    RiotMobileTotpSetupService,
)

SEED = "JBSWY3DPEHPK3PXP"


class FakeExpiryTimer:
    def __init__(self, delay: float, callback: Callable[[], None]) -> None:
        self.delay = delay
        self.callback = callback
        self.daemon = False
        self.started = False
        self.cancelled = False

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        if not self.cancelled:
            self.callback()


def _browser_session() -> RiotAccountBrowserSession:
    return RiotAccountBrowserSession(
        account_cookies={
            "account_session": "ACCOUNT-SECRET",
            "a12l-csrf-prod": "CSRF-SECRET",
        },
        sso_cookies={"ssid": "SSO-SECRET", "sub": "owned-puuid"},
        csrf_token="CSRF-SECRET",
    )


class FakeImporter:
    def __init__(self, identity: AuthenticatedRiotIdentity | None = None) -> None:
        self.identity = identity or AuthenticatedRiotIdentity("owned-puuid", "Peak", "EUW")
        self.closed = False
        self.tokens: list[str] = []

    def mint_access_token(self, cookies: Mapping[str, str]) -> str:
        assert dict(cookies) == {"ssid": "SSO-SECRET", "sub": "owned-puuid"}
        return "ACCESS-TOKEN-SECRET"

    def fetch_identity(self, access_token: str) -> AuthenticatedRiotIdentity:
        self.tokens.append(access_token)
        return self.identity

    def close(self) -> None:
        self.closed = True


class FakeMfaClient:
    def __init__(
        self,
        *,
        identity: RiotAccountIdentity | None = None,
        factors: tuple[RiotMfaFactor, ...] | None = None,
        seed: str = SEED,
        enable_error: Exception | None = None,
        verify_error: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.identity = identity or RiotAccountIdentity("owned-puuid", "Peak", "EUW")
        self.factors = (
            factors if factors is not None else (RiotMfaFactor("email", "enabled"),)
        )
        self.seed = seed
        self.enable_error = enable_error
        self.verify_error = verify_error
        self.events = events if events is not None else []
        self.closed = False

    def refresh_csrf_token(self, cookies: Mapping[str, str]) -> str:
        assert cookies["account_session"] == "ACCOUNT-SECRET"
        self.events.append("csrf")
        return "FRESH-CSRF-SECRET"

    def fetch_identity(
        self, cookies: Mapping[str, str], csrf_token: str
    ) -> RiotAccountIdentity:
        assert cookies["account_session"] == "ACCOUNT-SECRET"
        assert csrf_token == "FRESH-CSRF-SECRET"
        self.events.append("identity")
        return self.identity

    def fetch_factors(
        self, cookies: Mapping[str, str], csrf_token: str
    ) -> tuple[RiotMfaFactor, ...]:
        assert cookies["account_session"] == "ACCOUNT-SECRET"
        assert csrf_token == "FRESH-CSRF-SECRET"
        self.events.append("factors")
        return self.factors

    def enable_riot_mobile(self, cookies: Mapping[str, str], csrf_token: str) -> str:
        assert cookies["account_session"] == "ACCOUNT-SECRET"
        assert csrf_token == "FRESH-CSRF-SECRET"
        self.events.append("enable")
        if self.enable_error is not None:
            raise self.enable_error
        return self.seed

    def verify_riot_mobile(self, bearer_token: str, seed: str) -> None:
        assert bearer_token == "ACCESS-TOKEN-SECRET"
        assert seed == SEED
        self.events.append("verify")
        if self.verify_error is not None:
            raise self.verify_error

    def close(self) -> None:
        self.closed = True


def _service(
    client: FakeMfaClient,
    *,
    importer: FakeImporter | None = None,
    browser: RiotAccountBrowserSession | None = None,
    clock: Callable[[], float] = lambda: 100,
    timer_factory: Callable[[float, Callable[[], None]], FakeExpiryTimer] = FakeExpiryTimer,
    logger: logging.Logger | None = None,
) -> RiotMobileTotpSetupService:
    return RiotMobileTotpSetupService(
        browser_login=lambda: browser if browser is not None else _browser_session(),
        mfa_client_factory=lambda: client,
        importer_factory=lambda: importer or FakeImporter(),
        confirmation_ttl=60,
        clock=clock,
        token_factory=lambda: "confirmation-token-that-is-long-enough",
        timer_factory=timer_factory,
        logger=logger,
    )


def _prepare(service: RiotMobileTotpSetupService) -> str:
    proposal = service.prepare(
        account_id="owned-puuid",
        expected_puuid="owned-puuid",
        expected_riot_id="Peak#EUW",
    )
    assert proposal.account_id == "owned-puuid"
    assert proposal.riot_id == "Peak#EUW"
    assert proposal.expires_in_seconds == 60
    return proposal.confirmation_id


def test_prepare_only_authenticates_and_checks_factors_without_mutating() -> None:
    events: list[str] = []
    client = FakeMfaClient(events=events)
    service = _service(client)

    confirmation_id = _prepare(service)

    assert confirmation_id == "confirmation-token-that-is-long-enough"
    assert events == ["csrf", "identity", "factors"]
    assert "SSO-SECRET" not in repr(service)
    assert "ACCOUNT-SECRET" not in repr(service)
    assert "CSRF-SECRET" not in repr(service)


def test_prepare_bootstraps_temporary_browser_from_reusable_sso_session() -> None:
    reused: list[dict[str, str]] = []
    client = FakeMfaClient()
    service = RiotMobileTotpSetupService(
        browser_login=lambda: (_ for _ in ()).throw(AssertionError("fresh login not expected")),
        browser_login_with_session=lambda cookies: reused.append(dict(cookies))
        or _browser_session(),
        mfa_client_factory=lambda: client,
        importer_factory=FakeImporter,
        confirmation_ttl=60,
        clock=lambda: 100,
        token_factory=lambda: "confirmation-token-that-is-long-enough",
        timer_factory=FakeExpiryTimer,
    )

    proposal = service.prepare(
        account_id="owned-puuid",
        expected_puuid="owned-puuid",
        expected_riot_id="Peak#EUW",
        reusable_sso_cookies={"ssid": "SAVED-SESSION", "sub": "owned-puuid"},
    )

    assert proposal.riot_id == "Peak#EUW"
    assert reused == [{"ssid": "SAVED-SESSION", "sub": "owned-puuid"}]
    assert client.events == ["csrf", "identity", "factors"]
    assert "SAVED-SESSION" not in repr(service)


def test_pending_browser_credentials_are_proactively_discarded_at_expiry() -> None:
    now = [100.0]
    timers: list[FakeExpiryTimer] = []

    def timer_factory(delay: float, callback: Callable[[], None]) -> FakeExpiryTimer:
        timer = FakeExpiryTimer(delay, callback)
        timers.append(timer)
        return timer

    service = _service(
        FakeMfaClient(),
        clock=lambda: now[0],
        timer_factory=timer_factory,
    )
    confirmation_id = _prepare(service)

    assert timers[0].started is True
    assert timers[0].daemon is True
    assert timers[0].delay == 60

    # An early wake-up must re-arm rather than extending or consuming the
    # confirmation. At the real deadline, no later service call is needed.
    timers[0].fire()
    assert confirmation_id in service._pending
    assert len(timers) == 2
    now[0] = 160.0
    timers[1].fire()
    assert service._pending == {}
    assert service._expiry_timers == {}

    with pytest.raises(RiotMobileTotpConfirmationError, match="expired"):
        service.confirm(
            confirmation_id=confirmation_id,
            account_id="owned-puuid",
            persist_seed=lambda _seed: None,
        )


def test_close_cancels_timer_and_discards_pending_browser_credentials() -> None:
    timers: list[FakeExpiryTimer] = []

    def timer_factory(delay: float, callback: Callable[[], None]) -> FakeExpiryTimer:
        timer = FakeExpiryTimer(delay, callback)
        timers.append(timer)
        return timer

    service = _service(FakeMfaClient(), timer_factory=timer_factory)
    _prepare(service)

    service.close()

    assert timers[0].cancelled is True
    assert service._pending == {}
    assert service._expiry_timers == {}


@pytest.mark.parametrize(
    ("factors", "message"),
    [
        ((), "Enable email multi-factor authentication"),
        (
            (RiotMfaFactor("email", "enabled"), RiotMfaFactor("riotmobile", "enabled")),
            "will not rotate",
        ),
        (
            (RiotMfaFactor("Email", "ENABLED"), RiotMfaFactor("RiotMobile", "Enabled")),
            "will not rotate",
        ),
    ],
)
def test_prepare_requires_email_mfa_and_refuses_existing_riotmobile(
    factors: tuple[RiotMfaFactor, ...], message: str
) -> None:
    client = FakeMfaClient(factors=factors)

    with pytest.raises(RiotMobileTotpPrerequisiteError, match=message):
        _prepare(_service(client))

    assert "enable" not in client.events


def test_prepare_requires_exact_puuid_and_riot_id_binding() -> None:
    client = FakeMfaClient(identity=RiotAccountIdentity("different-puuid", "Peak", "EUW"))

    with pytest.raises(RiotMobileTotpIdentityMismatchError, match="selected account"):
        _prepare(_service(client))

    assert "enable" not in client.events


def test_authenticator_identity_and_confirmation_reprs_hide_identifiers() -> None:
    identity = RiotAccountIdentity("owned-puuid", "Peak", "EUW")
    service = _service(FakeMfaClient(identity=identity))
    proposal = service.prepare(
        account_id="owned-puuid",
        expected_puuid="owned-puuid",
        expected_riot_id="Peak#EUW",
    )
    result = RiotMobileTotpSetupResult(
        account_id="owned-puuid",
        riot_id="Peak#EUW",
        seed_saved=True,
        verified=True,
    )

    for value in (identity, proposal, result):
        representation = repr(value)
        assert "owned-puuid" not in representation
        assert "Peak" not in representation
        assert "EUW" not in representation
        assert "confirmation-token" not in representation


def test_confirm_is_one_time_and_persists_seed_before_verification() -> None:
    events: list[str] = []
    client = FakeMfaClient(seed="jbsw-y3dp ehpk3pxp", events=events)
    service = _service(client)
    confirmation_id = _prepare(service)

    saved: list[str] = []

    def persist(seed: str) -> None:
        events.append("persist")
        saved.append(seed)

    result = service.confirm(
        confirmation_id=confirmation_id,
        account_id="owned-puuid",
        persist_seed=persist,
    )

    assert result == RiotMobileTotpSetupResult(
        account_id="owned-puuid",
        riot_id="Peak#EUW",
        seed_saved=True,
        verified=True,
    )
    assert saved == [SEED]
    assert events == [
        "csrf",
        "identity",
        "factors",
        "csrf",
        "identity",
        "factors",
        "enable",
        "persist",
        "verify",
    ]
    with pytest.raises(RiotMobileTotpConfirmationError, match="expired"):
        service.confirm(
            confirmation_id=confirmation_id,
            account_id="owned-puuid",
            persist_seed=persist,
        )


def test_verification_failure_retains_seed_and_returns_accurate_warning() -> None:
    events: list[str] = []
    client = FakeMfaClient(
        verify_error=RuntimeError("response body with ACCOUNT-SECRET"),
        events=events,
    )
    service = _service(client)
    confirmation_id = _prepare(service)
    saved: list[str] = []

    result = service.confirm(
        confirmation_id=confirmation_id,
        account_id="owned-puuid",
        persist_seed=lambda seed: (events.append("persist"), saved.append(seed)),
    )

    assert saved == [SEED]
    assert result.seed_saved is True
    assert result.verified is False
    assert result.warning is not None and "saved it encrypted" in result.warning
    assert events[-3:] == ["enable", "persist", "verify"]
    assert SEED not in repr(result)
    assert "ACCOUNT-SECRET" not in repr(result)


def test_invalid_enable_secret_is_not_saved_or_verified_and_reports_uncertain_state() -> None:
    events: list[str] = []
    client = FakeMfaClient(seed="invalid-0-secret", events=events)
    service = _service(client)
    confirmation_id = _prepare(service)
    saved: list[str] = []

    with pytest.raises(RiotMobileTotpSetupError, match="account state may have changed"):
        service.confirm(
            confirmation_id=confirmation_id,
            account_id="owned-puuid",
            persist_seed=saved.append,
        )

    assert saved == []
    assert events[-1] == "enable"
    assert "persist" not in events
    assert "verify" not in events


def test_enable_403_reports_session_rejection_without_claiming_a_secret() -> None:
    client = FakeMfaClient(
        enable_error=RiotMfaHttpError("Riot Mobile authenticator enrollment", 403)
    )
    log_stream = io.StringIO()
    logger = logging.Logger("tests.riot_mobile_totp.enable_403", level=logging.INFO)
    log_handler = logging.StreamHandler(log_stream)
    logger.addHandler(log_handler)
    service = _service(client, logger=logger)
    confirmation_id = _prepare(service)
    saved: list[str] = []

    try:
        with pytest.raises(RiotMobileTotpSetupError, match=r"rejected.*HTTP 403") as raised:
            service.confirm(
                confirmation_id=confirmation_id,
                account_id="owned-puuid",
                persist_seed=saved.append,
            )
    finally:
        logger.removeHandler(log_handler)
        log_handler.close()

    assert "saved nothing" in str(raised.value).lower()
    assert saved == []
    assert client.events[-1] == "enable"
    assert "verify" not in client.events
    log_text = log_stream.getvalue()
    assert "confirm.csrf_refresh.complete" in log_text
    assert "enable_failed error_type=RiotMfaHttpError status=403" in log_text
    for secret in (
        "ACCOUNT-SECRET",
        "CSRF-SECRET",
        "FRESH-CSRF-SECRET",
        "SSO-SECRET",
        "owned-puuid",
        "Peak#EUW",
    ):
        assert secret not in log_text


def test_cancelled_browser_and_cancelled_confirmation_never_enable() -> None:
    client = FakeMfaClient()
    cancelled = RiotMobileTotpSetupService(
        browser_login=lambda: None,
        mfa_client_factory=lambda: client,
        importer_factory=FakeImporter,
        confirmation_ttl=60,
    )
    with pytest.raises(RiotMobileTotpSetupCancelledError):
        _prepare(cancelled)

    service = _service(client)
    confirmation_id = _prepare(service)
    service.cancel(confirmation_id)
    with pytest.raises(RiotMobileTotpConfirmationError):
        service.confirm(
            confirmation_id=confirmation_id,
            account_id="owned-puuid",
            persist_seed=lambda _seed: None,
        )
    assert "enable" not in client.events


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode()
        self.headers = {"Content-Length": str(len(self.content))}
        self.cookies: list[FakeCookie] = []
        self.closed = False

    def json(self) -> object:
        return self.payload

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return [self.content[index : index + chunk_size] for index in range(0, len(self.content), chunk_size)]

    def close(self) -> None:
        self.closed = True


class FakeCookie:
    def __init__(self, name: str, value: str) -> None:
        self.name = name
        self.value = value


class FakeCookieJar:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def clear(self) -> None:
        self.values.clear()

    def set(self, name: str, value: str, **_kwargs: Any) -> None:
        self.values[name] = value


class FailingStreamResponse(FakeResponse):
    def iter_content(self, chunk_size: int) -> list[bytes]:
        del chunk_size
        raise requests.exceptions.ChunkedEncodingError(
            "stream detail with RESPONSE-BODY-SECRET"
        )


class FakeHttpSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self.closed = False
        self.trust_env = True
        self.cookies = FakeCookieJar()
        self.cookie_snapshots: list[dict[str, str]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append((method, url, kwargs))
        self.cookie_snapshots.append(dict(self.cookies.values))
        response = self.responses.pop(0)
        for cookie in response.cookies:
            self.cookies.set(cookie.name, cookie.value)
        return response

    def close(self) -> None:
        self.closed = True


def test_mfa_client_uses_only_fixed_endpoints_and_normalizes_enable_seed() -> None:
    account_page = FakeResponse(None)
    account_page.content = (
        b"<html><head><meta name='csrf-token' content='FRESH-CSRF-SECRET'></head></html>"
    )
    account_page.headers = {"Content-Length": str(len(account_page.content))}
    account_page.cookies = [FakeCookie("a12l-csrf-prod", "ROTATED-CSRF-COOKIE")]
    http = FakeHttpSession(
        [
            account_page,
            FakeResponse(
                {
                    "puuid": "owned-puuid",
                    "alias": {"game_name": "Peak", "tag_line": "EUW"},
                }
            ),
            FakeResponse({"factors": [{"factor": "email", "status": "enabled"}]}),
            FakeResponse({"secret": "jbsw-y3dp ehpk3pxp"}),
            FakeResponse({}),
        ]
    )
    client = RiotMfaClient(session=http)
    cookies = {
        "account_session": "ACCOUNT-SECRET",
        "a12l-csrf-prod": "CSRF-SECRET",
    }

    csrf_token = client.refresh_csrf_token(cookies)
    assert csrf_token == "FRESH-CSRF-SECRET"
    assert client.fetch_identity(cookies, csrf_token).riot_id == "Peak#EUW"
    assert client.fetch_factors(cookies, csrf_token) == (
        RiotMfaFactor("email", "enabled"),
    )
    assert client.enable_riot_mobile(cookies, csrf_token) == SEED
    client.verify_riot_mobile("ACCESS-TOKEN-SECRET", SEED)

    assert [(method, url) for method, url, _kwargs in http.requests] == [
        ("GET", RIOT_ACCOUNT_PAGE_URL),
        ("GET", RIOT_ACCOUNT_USER_URL),
        ("GET", RIOT_MFA_FACTORS_URL),
        ("POST", RIOT_MOBILE_ENABLE_URL),
        ("POST", RIOT_MOBILE_VERIFY_URL),
    ]
    assert all(request[2]["allow_redirects"] is False for request in http.requests)
    assert all(request[2]["stream"] is True for request in http.requests)
    assert all("cookies" not in request[2] for request in http.requests)
    assert http.cookie_snapshots[0]["a12l-csrf-prod"] == "CSRF-SECRET"
    assert http.cookie_snapshots[1]["a12l-csrf-prod"] == "ROTATED-CSRF-COOKIE"
    assert http.cookie_snapshots[2]["a12l-csrf-prod"] == "ROTATED-CSRF-COOKIE"
    assert http.cookie_snapshots[3]["a12l-csrf-prod"] == "ROTATED-CSRF-COOKIE"
    assert http.cookie_snapshots[4] == {}
    assert http.trust_env is False
    enable_headers = http.requests[-2][2]["headers"]
    assert enable_headers["csrf-token"] == "FRESH-CSRF-SECRET"
    assert enable_headers["User-Agent"].startswith("Mozilla/5.0")
    assert enable_headers["Sec-CH-UA-Platform"] == '"Windows"'
    assert enable_headers["Sec-Fetch-Site"] == "same-origin"
    assert http.requests[-1][2]["json"]["device"] == "Peaks Desktop"
    assert len(http.requests[-1][2]["json"]["otp"]) == 6


def test_mfa_client_rejects_ambiguous_or_oversized_csrf_page() -> None:
    ambiguous = FakeResponse(None)
    ambiguous.content = (
        b"<meta name='csrf-token' content='FIRST'>"
        b"<meta content='SECOND' name='csrf-token'>"
    )
    ambiguous.headers = {"Content-Length": str(len(ambiguous.content))}
    oversized = FakeResponse(None)
    oversized.headers = {"Content-Length": str(2 * 1024 * 1024 + 1)}
    http = FakeHttpSession([ambiguous, oversized])
    client = RiotMfaClient(session=http)

    with pytest.raises(RiotMfaError, match="did not provide"):
        client.refresh_csrf_token({"account_session": "ACCOUNT-SECRET"})
    with pytest.raises(RiotMfaError, match="size limit"):
        client.refresh_csrf_token({"account_session": "ACCOUNT-SECRET"})

    assert ambiguous.closed is True
    assert oversized.closed is True


def test_mfa_client_closes_csrf_response_with_invalid_rotated_cookie() -> None:
    response = FakeResponse(None)
    response.content = b"<meta name='csrf-token' content='FRESH-CSRF-SECRET'>"
    response.headers = {"Content-Length": str(len(response.content))}
    response.cookies = [FakeCookie("account_session", "")]
    http = FakeHttpSession([response])
    client = RiotMfaClient(session=http)

    with pytest.raises(RiotMfaError, match="invalid account session cookies"):
        client.refresh_csrf_token({"account_session": "ACCOUNT-SECRET"})

    assert response.closed is True
    assert http.cookies.values == {}


def test_mfa_client_errors_expose_status_but_never_response_body() -> None:
    account_page = FakeResponse(None)
    account_page.content = b"<meta name='csrf-token' content='FRESH-CSRF-SECRET'>"
    account_page.headers = {"Content-Length": str(len(account_page.content))}
    response = FakeResponse({"secret": "RESPONSE-BODY-SECRET"}, 403)
    http = FakeHttpSession([account_page, response])
    client = RiotMfaClient(session=http)
    cookies = {"account_session": "ACCOUNT-SECRET"}
    csrf_token = client.refresh_csrf_token(cookies)

    with pytest.raises(RiotMfaHttpError) as raised:
        client.enable_riot_mobile(cookies, csrf_token)

    assert raised.value.status_code == 403
    assert response.closed is True
    assert "RESPONSE-BODY-SECRET" not in str(raised.value)
    assert "SSO-SECRET" not in str(raised.value)


def test_mfa_client_bounds_streamed_json_and_closes_response() -> None:
    account_page = FakeResponse(None)
    account_page.content = b"<meta name='csrf-token' content='FRESH-CSRF-SECRET'>"
    account_page.headers = {"Content-Length": str(len(account_page.content))}
    response = FakeResponse({})
    response.content = b"x" * (512 * 1024 + 1)
    response.headers = {}
    http = FakeHttpSession([account_page, response])
    client = RiotMfaClient(session=http)
    cookies = {"account_session": "ACCOUNT-SECRET"}
    csrf_token = client.refresh_csrf_token(cookies)

    with pytest.raises(RiotMfaError, match="too much data"):
        client.fetch_factors(cookies, csrf_token)

    assert response.closed is True


def test_mfa_client_normalizes_midstream_json_failure() -> None:
    account_page = FakeResponse(None)
    account_page.content = b"<meta name='csrf-token' content='FRESH-CSRF-SECRET'>"
    account_page.headers = {"Content-Length": str(len(account_page.content))}
    response = FailingStreamResponse({})
    http = FakeHttpSession([account_page, response])
    client = RiotMfaClient(session=http)
    cookies = {"account_session": "ACCOUNT-SECRET"}
    csrf_token = client.refresh_csrf_token(cookies)

    with pytest.raises(RiotMfaError, match="Could not read Riot data") as raised:
        client.fetch_factors(cookies, csrf_token)

    assert "RESPONSE-BODY-SECRET" not in str(raised.value)
    assert response.closed is True
