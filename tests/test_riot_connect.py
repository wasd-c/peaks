from __future__ import annotations

import logging

import pytest

from peaks.adapters.riot.qr import QRParseError, parse_qr_text
from peaks.application.riot_connect import (
    AccountBindingError,
    ApprovalRequired,
    CredentialsUnavailable,
    OwnedAccountCredentials,
    QRApprovalService,
    RiotConnectHTTPError,
    RiotQRApprovalService,
    SessionDetailsRequired,
    SessionExpired,
)


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: object | None = None) -> None:
        self.status_code = status_code
        self.payload = payload if payload is not None else {}
        self.closed = False

    def json(self) -> object:
        return self.payload

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, responses: list[FakeResponse] | None = None) -> None:
        self.responses = responses or [FakeResponse()]
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self.trust_env = True
        self.closed = False
        self.cookies = FakeCookieJar()

    def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


class FakeCookieJar:
    def __init__(self) -> None:
        self.clear_calls = 0

    def clear(self) -> None:
        self.clear_calls += 1


def test_access_token_approval_is_explicit_and_forces_remember_false() -> None:
    session = FakeSession([FakeResponse(payload={"puuid": "owned-puuid"}), FakeResponse()])
    service = RiotQRApprovalService(session=session)
    credentials = OwnedAccountCredentials(puuid="owned-puuid", access_token="access-secret")
    with pytest.raises(ApprovalRequired):
        service.approve("suuid-1:eu", credentials, user_approved=False)
    service.session_info(
        "suuid-1:eu",
        access_token="access-secret",
        selected_account_puuid="owned-puuid",
    )
    result = service.approve("suuid-1:eu", credentials, user_approved=True)
    assert result.method == "session"
    method, url, kwargs = session.calls[1]
    assert method == "POST"
    assert url == "https://authenticate.riotgames.com/api/v1/session/authentication"
    assert kwargs["allow_redirects"] is False
    assert kwargs["verify"] is True
    assert kwargs["stream"] is True
    assert kwargs["json"] == {"suuid": "suuid-1", "cluster": "eu", "remember": False}
    headers = kwargs["headers"]
    assert isinstance(headers, dict) and headers["Authorization"] == "Bearer access-secret"
    assert session.trust_env is False


def test_qr_credentials_require_an_identity_bound_reusable_session() -> None:
    with pytest.raises(CredentialsUnavailable, match="reusable Riot session"):
        OwnedAccountCredentials(puuid="owned-puuid")


def test_session_info_is_read_only_and_sanitized() -> None:
    session = FakeSession([FakeResponse(payload={"puuid": "owned-puuid", "geolocation": {"city": "Paris", "country": "FR"}, "device": "Riot Client", "token": "do-not-return"})])
    service = QRApprovalService(session=session)
    details = service.session_info(
        "suuid-1:eu",
        access_token="access-secret",
        selected_account_puuid="owned-puuid",
    )
    assert details.location == "Paris, FR"
    assert details.device == "Riot Client"
    assert not hasattr(details, "token")
    assert session.calls[0][0] == "GET"
    assert session.calls[0][2]["allow_redirects"] is False


def test_qr_urls_are_https_and_allowlisted() -> None:
    assert parse_qr_text(
        "https://qr.riotgames.com/login?suuid=suuid-1&cluster=eu"
    ).as_tuple() == ("suuid-1", "eu")
    assert parse_qr_text(
        "https://qrlogin.riotgames.com/riotmobile/?cluster=ec1&suuid=suuid-2"
        "&timestamp=1787858983848&utm_source=riotclient&utm_medium=client"
        "&utm_campaign=qrlogin-riotmobile"
    ).as_tuple() == ("suuid-2", "ec1")
    with pytest.raises(QRParseError):
        parse_qr_text("http://qr.riotgames.com/login?suuid=suuid-1&cluster=eu")
    with pytest.raises(QRParseError):
        parse_qr_text("https://example.invalid/login?suuid=suuid-1&cluster=eu")
    with pytest.raises(QRParseError):
        parse_qr_text("https://qr.riotgames.com:443/login?suuid=suuid-1&cluster=eu")
    with pytest.raises(QRParseError):
        parse_qr_text(
            "https://qrlogin.riotgames.com/not-riotmobile?suuid=suuid-1&cluster=eu"
        )


def test_unclaimed_qr_metadata_is_not_treated_as_its_account_owner() -> None:
    session = FakeSession(
        [
            FakeResponse(
                payload={
                    "puuid": "pending-client-session",
                    "subject": "unclaimed-login-challenge",
                }
            ),
            FakeResponse(),
        ]
    )
    service = RiotQRApprovalService(session=session)
    service.session_info(
        "suuid-1:eu",
        access_token="session-secret",
        selected_account_puuid="owned-puuid",
    )
    result = service.approve(
        "suuid-1:eu",
        OwnedAccountCredentials(puuid="owned-puuid", access_token="session-secret"),
        user_approved=True,
    )
    assert result.method == "session"
    assert len(session.calls) == 2


def test_approval_requires_the_same_selected_account_binding() -> None:
    session = FakeSession([FakeResponse(payload={})])
    service = RiotQRApprovalService(session=session)
    service.session_info(
        "suuid-1:eu",
        access_token="session-secret",
        selected_account_puuid="owned-puuid",
    )
    with pytest.raises(AccountBindingError):
        service.approve(
            "suuid-1:eu",
            OwnedAccountCredentials(puuid="another-puuid", access_token="session-secret"),
            user_approved=True,
        )
    assert len(session.calls) == 1


def test_approval_requires_the_same_selected_bearer_session() -> None:
    session = FakeSession([FakeResponse(payload={})])
    service = RiotQRApprovalService(session=session)
    service.session_info(
        "suuid-1:eu",
        access_token="session-secret",
        selected_account_puuid="owned-puuid",
    )
    with pytest.raises(AccountBindingError):
        service.approve(
            "suuid-1:eu",
            OwnedAccountCredentials(puuid="owned-puuid", access_token="changed-secret"),
            user_approved=True,
        )
    assert len(session.calls) == 1


def test_session_proof_expires_and_cannot_be_replayed() -> None:
    now = [100.0]
    session = FakeSession(
        [
            FakeResponse(payload={"puuid": "owned-puuid"}),
            FakeResponse(payload={"puuid": "owned-puuid"}),
            FakeResponse(),
        ]
    )
    service = RiotQRApprovalService(session=session, session_ttl=5, clock=lambda: now[0])
    credentials = OwnedAccountCredentials(puuid="owned-puuid", access_token="access-secret")
    service.session_info(
        "suuid-1:eu",
        access_token="access-secret",
        selected_account_puuid="owned-puuid",
    )
    now[0] = 106
    with pytest.raises(SessionExpired):
        service.approve("suuid-1:eu", credentials, user_approved=True)
    assert len(session.calls) == 1

    now[0] = 107
    service.session_info(
        "suuid-1:eu",
        access_token="access-secret",
        selected_account_puuid="owned-puuid",
    )
    assert service.approve("suuid-1:eu", credentials, user_approved=True).method == "session"
    with pytest.raises(SessionDetailsRequired):
        service.approve("suuid-1:eu", credentials, user_approved=True)
    assert len(session.calls) == 3


def test_http_errors_and_logs_do_not_include_tokens_or_bodies(caplog: pytest.LogCaptureFixture) -> None:
    session = FakeSession(
        [
            FakeResponse(payload={"puuid": "owned-puuid"}),
            FakeResponse(403, {"access_token": "response-secret"}),
        ]
    )
    service = RiotQRApprovalService(session=session, logger=logging.getLogger("riot-connect-test"))
    with caplog.at_level(logging.DEBUG, logger="riot-connect-test"), pytest.raises(RiotConnectHTTPError):
        service.session_info(
            "suuid-1:eu",
            access_token="request-secret",
            selected_account_puuid="owned-puuid",
        )
        service.approve(
            "suuid-1:eu",
            OwnedAccountCredentials(puuid="owned-puuid", access_token="request-secret"),
            user_approved=True,
        )
    assert "request-secret" not in caplog.text
    assert "response-secret" not in caplog.text
    assert "403" in caplog.text


def test_close_clears_cookie_jar_and_pending_session_proofs() -> None:
    session = FakeSession([FakeResponse(payload={"puuid": "owned-puuid"})])
    service = RiotQRApprovalService(session=session)

    service.session_info(
        "suuid-1:eu",
        access_token="session-secret",
        selected_account_puuid="owned-puuid",
    )
    service.close()

    assert session.cookies.clear_calls == 1
    assert session.closed is True
    assert service._session_proofs == {}
