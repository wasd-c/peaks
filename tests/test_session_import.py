from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest
import requests
from requests.cookies import RequestsCookieJar

from peaks.adapters.riot.session_import import (
    ALLOWED_COOKIE_NAMES,
    RIOT_AUTHORIZATION_URL,
    AuthenticatedRiotIdentity,
    ImportedRiotSession,
    RefreshedRiotAuthorization,
    RiotSessionImporter,
    SessionAuthorizationError,
    SessionAuthorizationHTTPError,
    SessionReauthenticationRequired,
    SessionSettingsError,
    UnsupportedPlatformError,
)

COOKIE_VALUES = {
    "ssid": "ssid-value",
    "clid": "clid-value",
    "csid": "csid-value",
    "tdid": "tdid-value",
    "sub": "puuid-value",
}


def _settings_yaml(cookies: dict[str, str] | None = None, *, extra: str = "") -> str:
    values = cookies or COOKIE_VALUES
    entries = "\n".join(
        f"          - name: {name}\n            value: {value}" for name, value in values.items()
    )
    return (
        "riot-login:\n"
        "  persist:\n"
        "    session:\n"
        "      cookies:\n"
        f"{entries}\n"
        f"{extra}"
    )


def _write_settings(local_app_data: Path, text: str) -> Path:
    path = local_app_data / "Riot Games" / "Riot Client" / "Data" / "RiotGamesPrivateSettings.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status_code: int = 200,
        content_length: int | None = None,
        chunk_size: int = 32,
        cookies: RequestsCookieJar | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        self.chunk_size = chunk_size
        self.cookies = cookies or RequestsCookieJar()
        self.closed = False

    def iter_content(self, *, chunk_size: int) -> list[bytes]:
        size = min(chunk_size, self.chunk_size)
        return [self._body[index : index + size] for index in range(0, len(self._body), size)]

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self.trust_env = True
        self.closed = False

    def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        return self.response

    def close(self) -> None:
        self.closed = True


def _success_response() -> FakeResponse:
    return FakeResponse(
        b'{"type":"response","response":{"parameters":{"uri":'
        b'"http://localhost/redirect#access_token=token.value_123&scope=openid"}}}',
    )


def _importer(tmp_path: Path, session: FakeSession) -> RiotSessionImporter:
    local = tmp_path / "LocalAppData"
    _write_settings(local, _settings_yaml())
    return RiotSessionImporter(
        session=session,
        platform_name="Windows",
        env={"LOCALAPPDATA": str(local)},
    )


def test_import_current_session_reads_exact_file_and_mints_fresh_token(tmp_path: Path) -> None:
    session = FakeSession(_success_response())
    importer = _importer(tmp_path, session)

    result = importer.import_current_session()

    assert isinstance(result, ImportedRiotSession)
    assert result.puuid == "puuid-value"
    assert dict(result.cookies) == COOKIE_VALUES
    assert result.access_token == "token.value_123"
    assert "token.value_123" not in repr(result)
    assert "ssid-value" not in repr(result)
    with pytest.raises(TypeError):
        result.cookies["ssid"] = "changed"  # type: ignore[index]
    assert session.trust_env is False
    assert len(session.calls) == 1
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == RIOT_AUTHORIZATION_URL
    assert kwargs["allow_redirects"] is False
    assert kwargs["verify"] is True
    assert kwargs["stream"] is True
    assert kwargs["cookies"] == COOKIE_VALUES
    assert kwargs["json"] == {
        "client_id": "ritoplus",
        "nonce": "1",
        "redirect_uri": "http://localhost/redirect",
        "response_type": "token id_token",
        "scope": "openid account link ban lol summoner offline_access "
        "riot://riot.authenticator/session.auth",
    }


def test_authorization_merges_allowlisted_cookie_rotations(tmp_path: Path) -> None:
    rotated = RequestsCookieJar()
    rotated.set("ssid", "rotated-ssid", domain=".riotgames.com", path="/")
    rotated.set("ccid", "rotated-ccid", domain="auth.riotgames.com", path="/api")
    rotated.set("asid", "wrong-host", domain="example.invalid", path="/")
    rotated.set("unexpected", "ignored", domain="auth.riotgames.com", path="/")
    session = FakeSession(
        FakeResponse(
            _success_response()._body,
            cookies=rotated,
        )
    )
    importer = _importer(tmp_path, session)

    authorization = importer.refresh_authorization(COOKIE_VALUES)

    assert isinstance(authorization, RefreshedRiotAuthorization)
    assert authorization.access_token == "token.value_123"
    assert dict(authorization.cookies) == {
        **COOKIE_VALUES,
        "ssid": "rotated-ssid",
        "ccid": "rotated-ccid",
    }
    assert "rotated-ssid" not in repr(authorization)
    assert "wrong-host" not in repr(authorization)


def test_complete_riot_sso_cookie_allowlist_includes_device_context() -> None:
    assert {
        "ssid",
        "clid",
        "csid",
        "tdid",
        "sub",
        "ccid",
        "asid",
    } == ALLOWED_COOKIE_NAMES


@pytest.mark.parametrize("response_type", ["auth", "multifactor"])
def test_expired_session_is_distinct_from_transport_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, response_type: str,
) -> None:
    response = FakeResponse(json.dumps({
        "type": response_type,
        "multifactor": {"email": "PRIVATE-EMAIL", "cookie": "PRIVATE-COOKIE"},
    }).encode())
    importer = _importer(tmp_path, FakeSession(response))
    importer._logger = logging.getLogger("session-reauthentication-test")

    with caplog.at_level(logging.INFO), pytest.raises(SessionReauthenticationRequired) as caught:
        importer.refresh_authorization(COOKIE_VALUES)

    assert caught.value.response_type == response_type
    assert "reauthentication_required" in caplog.text
    assert "PRIVATE-EMAIL" not in caplog.text + str(caught.value)
    assert "PRIVATE-COOKIE" not in caplog.text + str(caught.value)
    assert response.closed


def test_reusing_importer_does_not_send_another_accounts_transport_cookies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = requests.Session()
    session.cookies.set("ssid", "OTHER-ACCOUNT", domain="auth.riotgames.com", path="/")
    sent: list[str] = []

    def send(request: requests.PreparedRequest, **kwargs: Any) -> requests.Response:
        sent.append(request.headers.get("Cookie", ""))
        response = requests.Response()
        response.status_code = 200
        response._content = _success_response()._body
        response._content_consumed = True
        return response

    monkeypatch.setattr(session, "send", send)
    importer = RiotSessionImporter(session=session, platform_name="Windows")
    importer.refresh_authorization(COOKIE_VALUES)

    assert sent[0].count("ssid=") == 1
    assert "ssid=ssid-value" in sent[0]
    assert "OTHER-ACCOUNT" not in sent[0]


def test_local_import_checks_selected_subject_before_rotating_another_session(tmp_path: Path) -> None:
    session = FakeSession(_success_response())
    importer = _importer(tmp_path, session)

    with pytest.raises(SessionSettingsError, match="another account"):
        importer.import_session_for_identity("different-puuid")

    assert session.calls == []


@pytest.mark.parametrize("source", ["cookies", "local_client"])
def test_pkce_code_exchange_and_offline_refresh_do_not_require_browser_cookies(
    tmp_path: Path, source: str,
) -> None:
    class CodeSession(FakeSession):
        def __init__(self) -> None:
            super().__init__(_success_response())
            self.challenge = ""
            self.cookies = RequestsCookieJar()

        def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
            self.calls.append((method, url, kwargs))
            if url == RIOT_AUTHORIZATION_URL:
                body = kwargs["json"]
                assert body["response_type"] == "code"
                assert body["code_challenge_method"] == "S256"
                self.challenge = body["code_challenge"]
                uri = "http://localhost/redirect?" + urlencode({"code": "ONE-USE-CODE", "state": body["state"]})
                return FakeResponse(json.dumps({"type": "response", "response": {"parameters": {"uri": uri}}}).encode())
            assert url == "https://auth.riotgames.com/token"
            data = kwargs["data"]
            if data["grant_type"] == "authorization_code":
                challenge = base64.urlsafe_b64encode(hashlib.sha256(data["code_verifier"].encode()).digest()).decode().rstrip("=")
                assert challenge == self.challenge
                assert data["code"] == "ONE-USE-CODE"
                return FakeResponse(b'{"access_token":"FIRST-TOKEN","refresh_token":"OFFLINE-SECRET"}')
            assert data["refresh_token"] == "OFFLINE-SECRET"
            assert "cookies" not in kwargs
            assert not list(self.cookies)
            return FakeResponse(b'{"access_token":"NEW-TOKEN","refresh_token":"ROTATED-OFFLINE-SECRET"}')

    session = CodeSession()
    importer = _importer(tmp_path, session)
    authorization = (
        importer.import_durable_session_for_identity("puuid-value")
        if source == "local_client" else importer.mint_durable_authorization(COOKIE_VALUES)
    )
    assert authorization.refresh_token == "OFFLINE-SECRET"
    session.cookies.set("ssid", "EXPIRED-COOKIE")
    renewed = importer.refresh_from_token(authorization.refresh_token, {})

    assert renewed.access_token == "NEW-TOKEN"
    assert renewed.refresh_token == "ROTATED-OFFLINE-SECRET"
    assert dict(renewed.cookies) == {}
    assert "OFFLINE-SECRET" not in repr(renewed)
    assert "NEW-TOKEN" not in repr(renewed)


def test_refresh_retains_credential_when_riot_does_not_rotate_it() -> None:
    session = FakeSession(FakeResponse(b'{"access_token":"FRESH-ACCESS"}'))
    importer = RiotSessionImporter(session=session, platform_name="Windows")

    result = importer.refresh_from_token("STILL-VALID-REFRESH", {})

    assert result.refresh_token == "STILL-VALID-REFRESH"
    assert result.access_token == "FRESH-ACCESS"
    assert session.response.closed


def test_revoked_refresh_token_is_reported_without_returning_credentials(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse(b'{"error":"invalid_grant","detail":"PRIVATE-REFRESH"}', status_code=400))
    importer = _importer(tmp_path, session)
    with pytest.raises(SessionReauthenticationRequired) as caught:
        importer.refresh_from_token("PRIVATE-REFRESH", {})
    assert "PRIVATE-REFRESH" not in str(caught.value)


@pytest.mark.parametrize("uri", [
    "http://attacker.invalid/redirect?code=SECRET&state=expected",
    "http://localhost/redirect?code=SECRET&state=other",
    "http://localhost/redirect?code=SECRET&code=SECOND&state=expected",
    "http://localhost/redirect#code=SECRET&state=expected",
])
def test_offline_authorization_code_is_bound_to_callback_and_state(uri: str) -> None:
    with pytest.raises(SessionAuthorizationError):
        RiotSessionImporter._code_from_uri(uri, "expected")


def test_off_windows_and_missing_localappdata_fail_closed(tmp_path: Path) -> None:
    session = FakeSession(_success_response())
    with pytest.raises(UnsupportedPlatformError):
        RiotSessionImporter(
            session=session,
            platform_name="Darwin",
            env={"LOCALAPPDATA": str(tmp_path)},
        ).import_current_session()
    assert not session.calls

    with pytest.raises(SessionSettingsError):
        RiotSessionImporter(session=session, platform_name="Windows", env={}).settings_path()


def test_settings_path_rejects_relative_root_and_symlink_outside_root(tmp_path: Path) -> None:
    with pytest.raises(SessionSettingsError):
        RiotSessionImporter(platform_name="Windows", env={"LOCALAPPDATA": "relative"}).settings_path()

    local = tmp_path / "LocalAppData"
    outside = tmp_path / "outside.yaml"
    outside.write_text(_settings_yaml(), encoding="utf-8")
    target = local / "Riot Games" / "Riot Client" / "Data" / "RiotGamesPrivateSettings.yaml"
    target.parent.mkdir(parents=True)
    try:
        target.symlink_to(outside)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege is unavailable")
        raise
    importer = RiotSessionImporter(platform_name="Windows", env={"LOCALAPPDATA": str(local)})
    with pytest.raises(SessionSettingsError):
        importer.settings_path()

    local_with_linked_riot = tmp_path / "LocalAppDataLinked"
    outside_root = tmp_path / "outside-root"
    _write_settings(outside_root, _settings_yaml())
    local_with_linked_riot.mkdir()
    (local_with_linked_riot / "Riot Games").symlink_to(outside_root / "Riot Games")
    linked_importer = RiotSessionImporter(
        platform_name="Windows", env={"LOCALAPPDATA": str(local_with_linked_riot)}
    )
    with pytest.raises(SessionSettingsError):
        linked_importer.settings_path()


def test_settings_file_is_regular_and_bounded(tmp_path: Path) -> None:
    local = tmp_path / "LocalAppData"
    path = _write_settings(local, _settings_yaml())
    path.unlink()
    path.mkdir()
    importer = RiotSessionImporter(platform_name="Windows", env={"LOCALAPPDATA": str(local)})
    with pytest.raises(SessionSettingsError):
        importer.settings_path()

    path.rmdir()
    path.write_bytes(b"x" * (1 * 1024 * 1024 + 1))
    with pytest.raises(SessionSettingsError, match="too large"):
        importer.settings_path()


@pytest.mark.parametrize(
    "cookies",
    [
        {"ssid": "ssid-value"},
        {"sub": "puuid-value"},
        {"ssid": "ssid-value", "sub": "bad;cookie"},
        {"ssid": "ssid-value", "sub": "bad\nvalue"},
    ],
)
def test_invalid_cookie_schema_fails_closed(tmp_path: Path, cookies: dict[str, str]) -> None:
    local = tmp_path / "LocalAppData"
    _write_settings(local, _settings_yaml(cookies))
    importer = RiotSessionImporter(
        platform_name="Windows", env={"LOCALAPPDATA": str(local)}, session=FakeSession(_success_response())
    )
    with pytest.raises(SessionSettingsError):
        importer.import_current_session()


def test_yaml_alias_expansion_is_rejected_before_object_construction(tmp_path: Path) -> None:
    local = tmp_path / "LocalAppData"
    text = (
        "riot-login:\n"
        "  persist:\n"
        "    session:\n"
        "      cookies:\n"
        "        - &cookie\n"
        "          name: ssid\n"
        "          value: ssid-value\n"
        "        - *cookie\n"
    )
    _write_settings(local, text)
    session = FakeSession(_success_response())
    importer = RiotSessionImporter(
        platform_name="Windows", env={"LOCALAPPDATA": str(local)}, session=session
    )

    with pytest.raises(SessionSettingsError, match="invalid"):
        importer.import_current_session()
    assert not session.calls


def test_yaml_deep_nesting_is_rejected(tmp_path: Path) -> None:
    local = tmp_path / "LocalAppData"
    nested = ["      nested:"]
    indent = "        "
    for _ in range(80):
        nested.append(f"{indent}nested:")
        indent += "  "
    nested.append(f"{indent}value: too-deep")
    _write_settings(local, _settings_yaml(extra="\n".join(nested) + "\n"))
    session = FakeSession(_success_response())
    importer = RiotSessionImporter(
        platform_name="Windows", env={"LOCALAPPDATA": str(local)}, session=session
    )

    with pytest.raises(SessionSettingsError, match="invalid"):
        importer.import_current_session()
    assert not session.calls


def test_yaml_large_collection_is_rejected(tmp_path: Path) -> None:
    local = tmp_path / "LocalAppData"
    values = "\n".join(f"        - noise-{index}" for index in range(1_100))
    _write_settings(local, _settings_yaml(extra=f"      noise:\n{values}\n"))
    session = FakeSession(_success_response())
    importer = RiotSessionImporter(
        platform_name="Windows", env={"LOCALAPPDATA": str(local)}, session=session
    )

    with pytest.raises(SessionSettingsError, match="invalid"):
        importer.import_current_session()
    assert not session.calls


def test_injected_yaml_loader_remains_usable_for_fixtures(tmp_path: Path) -> None:
    local = tmp_path / "LocalAppData"
    path = _write_settings(local, "fixture input intentionally ignored by loader\n")
    calls: list[str] = []

    def fixture_loader(text: str) -> dict[str, object]:
        calls.append(text)
        return {
            "riot-login": {
                "persist": {
                    "session": {
                        "cookies": [
                            {"name": name, "value": value}
                            for name, value in COOKIE_VALUES.items()
                        ]
                    }
                }
            }
        }

    session = FakeSession(_success_response())
    result = RiotSessionImporter(
        platform_name="Windows",
        env={"LOCALAPPDATA": str(local)},
        session=session,
        yaml_loader=fixture_loader,
    ).import_current_session()

    assert calls == [path.read_bytes().decode("utf-8-sig")]
    assert result.puuid == "puuid-value"


def test_unknown_cookies_are_not_copied(tmp_path: Path) -> None:
    local = tmp_path / "LocalAppData"
    text = _settings_yaml(extra="          - name: unexpected\n            value: do-not-copy\n")
    _write_settings(local, text)
    session = FakeSession(_success_response())
    result = RiotSessionImporter(
        platform_name="Windows", env={"LOCALAPPDATA": str(local)}, session=session
    ).import_current_session()
    assert "unexpected" not in result.cookies
    assert session.calls[0][2]["cookies"] == COOKIE_VALUES


def test_explicit_session_puuid_is_accepted_without_copying_it_as_a_cookie(tmp_path: Path) -> None:
    local = tmp_path / "LocalAppData"
    cookies = {name: value for name, value in COOKIE_VALUES.items() if name != "sub"}
    text = _settings_yaml(cookies, extra="      puuid: puuid-value\n")
    _write_settings(local, text)
    session = FakeSession(_success_response())
    result = RiotSessionImporter(
        platform_name="Windows", env={"LOCALAPPDATA": str(local)}, session=session
    ).import_current_session()
    assert result.puuid == "puuid-value"
    assert "sub" not in result.cookies
    assert "sub" not in session.calls[0][2]["cookies"]


def test_fetch_identity_returns_only_authoritative_redacted_fields(tmp_path: Path) -> None:
    response = FakeResponse(
        b'{"sub":"authoritative-puuid","acct":{"game_name":"Nora","tag_line":"EUW"},'
        b'"email":"must-not-return"}'
    )
    session = FakeSession(response)
    importer = _importer(tmp_path, session)
    identity = importer.fetch_identity("token.value_123")
    assert isinstance(identity, AuthenticatedRiotIdentity)
    assert identity.puuid == "authoritative-puuid"
    assert identity.game_name == "Nora"
    assert identity.tag_line == "EUW"
    assert "must-not-return" not in repr(identity)
    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert url == "https://auth.riotgames.com/userinfo"
    assert kwargs["headers"] == {
        "Accept": "application/json",
        "Authorization": "Bearer token.value_123",
        "User-Agent": "Peaks/0.1 Riot session import",
    }
    assert kwargs["allow_redirects"] is False
    assert kwargs["verify"] is True
    assert kwargs["stream"] is True


def test_non_success_authorization_closes_response_without_leaking_data(tmp_path: Path) -> None:
    response = FakeResponse(b'{"error":"secret-response"}', status_code=302)
    session = FakeSession(response)
    importer = _importer(tmp_path, session)
    with pytest.raises(SessionAuthorizationHTTPError) as raised:
        importer.import_current_session()
    assert raised.value.status_code == 302
    assert response.closed is True
    assert "secret-response" not in str(raised.value)


def test_response_content_length_and_stream_are_bounded(tmp_path: Path) -> None:
    response = FakeResponse(b"{}", content_length=20)
    session = FakeSession(response)
    importer = RiotSessionImporter(
        session=session,
        platform_name="Windows",
        env={"LOCALAPPDATA": str(tmp_path / "missing")},
        max_response_bytes=10,
    )
    # Create valid settings after constructing the importer so only response
    # limits, not path discovery, determine this assertion.
    _write_settings(tmp_path / "missing", _settings_yaml())
    with pytest.raises(SessionAuthorizationError, match="too large"):
        importer.import_current_session()
    assert response.closed is True

    oversized = FakeResponse(b"{" + b"x" * 32 + b"}")
    session = FakeSession(oversized)
    importer = RiotSessionImporter(
        session=session,
        platform_name="Windows",
        env={"LOCALAPPDATA": str(tmp_path / "missing2")},
        max_response_bytes=10,
    )
    _write_settings(tmp_path / "missing2", _settings_yaml())
    with pytest.raises(SessionAuthorizationError, match="too large"):
        importer.import_current_session()
    assert oversized.closed is True


@pytest.mark.parametrize(
    "uri",
    [
        "https://localhost/redirect#access_token=token.value",
        "http://evil.invalid/redirect#access_token=token.value",
        "http://localhost:80/redirect#access_token=token.value",
        "http://localhost/other#access_token=token.value",
        "http://localhost/redirect?access_token=token.value#scope=openid",
        "http://localhost/redirect#access_token=one&access_token=two",
        "http://localhost/redirect#scope=openid",
        "http://localhost/redirect#access_token=bad%0Atoken",
    ],
)
def test_access_token_uri_is_strict(tmp_path: Path, uri: str) -> None:
    body = json.dumps({"type": "response", "response": {"parameters": {"uri": uri}}}).encode()
    session = FakeSession(FakeResponse(body))
    importer = _importer(tmp_path, session)
    with pytest.raises(SessionAuthorizationError):
        importer.import_current_session()
    assert session.response.closed is True


def test_close_releases_injected_transport(tmp_path: Path) -> None:
    session = FakeSession(_success_response())
    importer = _importer(tmp_path, session)
    importer.close()
    assert session.closed is True
