from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from peaks.adapters.riot.browser_login import (
    RIOT_ACCOUNT_URL,
    login_riot_account,
    login_riot_account_for_mfa,
)
from peaks.adapters.riot.discovery import DiscoveryResult, parse_lockfile
from peaks.adapters.riot.session_import import AuthenticatedRiotIdentity
from peaks.application.account_onboarding import (
    RIOT_ENTITLEMENTS_PATH,
    AccountIdentityMismatchError,
    AccountOnboardingCancelledError,
    AccountOnboardingResult,
    AccountOnboardingService,
    AccountOnboardingUnavailableError,
)


class FakeLocalClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.endpoints: list[str] = []
        self.closed = False

    def get_json(self, endpoint: str, *, params: Mapping[str, object] | None = None) -> object:
        assert params is None
        self.endpoints.append(endpoint)
        return self.payload

    def close(self) -> None:
        self.closed = True


class FakeImporter:
    def __init__(self, identity: AuthenticatedRiotIdentity, *, minted_token: str) -> None:
        self.identity = identity
        self.minted_token = minted_token
        self.minted_cookies: dict[str, str] | None = None
        self.identity_tokens: list[str] = []
        self.closed = False

    def mint_access_token(self, cookies: Mapping[str, str]) -> str:
        self.minted_cookies = dict(cookies)
        return self.minted_token

    def fetch_identity(self, access_token: str) -> AuthenticatedRiotIdentity:
        self.identity_tokens.append(access_token)
        return self.identity

    def close(self) -> None:
        self.closed = True


class CapturingImporter(FakeImporter):
    def __init__(
        self,
        identity: AuthenticatedRiotIdentity,
        *,
        imported_puuid: str,
        cookies: Mapping[str, str],
    ) -> None:
        super().__init__(identity, minted_token="unused")
        self.imported = SimpleNamespace(
            puuid=imported_puuid,
            cookies=dict(cookies),
            access_token="IMPORTED-TOKEN-SECRET",
        )

    def import_current_session(self) -> Any:
        return self.imported


def _unexpected() -> Any:
    raise AssertionError("unexpected dependency call")


def test_active_valorant_retries_verified_lockfile_and_binds_entitlement_subject() -> None:
    lockfile = parse_lockfile("Riot Client:314:54321:LOCKFILE-SECRET:https")
    missing = DiscoveryResult(True, True, None, None, "lockfile is still starting")
    verified = DiscoveryResult(
        True,
        True,
        lockfile,
        Path("C:/Riot Games/Riot Client/RiotClientServices.exe"),
        "verified",
    )
    discoveries = iter((missing, verified))
    client = FakeLocalClient({"accessToken": "ACCESS-TOKEN-SECRET", "subject": "account-puuid"})
    importer = FakeImporter(
        AuthenticatedRiotIdentity("account-puuid", "Peak", "EUW"),
        minted_token="unused",
    )
    delays: list[float] = []

    result = AccountOnboardingService(
        process_names_provider=lambda: {"valorant-win64-shipping.EXE"},
        discovery_provider=lambda: next(discoveries),
        local_client_factory=lambda discovered: client if discovered is lockfile else _unexpected(),
        importer_factory=lambda: importer,
        browser_login=_unexpected,
        local_retry_attempts=2,
        local_retry_delay=0.01,
        sleep=delays.append,
    ).add_account()

    assert result == AccountOnboardingResult(
        identity=AuthenticatedRiotIdentity("account-puuid", "Peak", "EUW"),
        source="local_client",
    )
    assert result.cookies is None
    assert client.endpoints == [RIOT_ENTITLEMENTS_PATH]
    assert importer.identity_tokens == ["ACCESS-TOKEN-SECRET"]
    assert delays == [0.01]
    assert client.closed and importer.closed
    assert "ACCESS-TOKEN-SECRET" not in repr(result)
    assert "LOCKFILE-SECRET" not in repr(result)


def test_active_valorant_saves_only_identity_bound_reusable_session_cookies() -> None:
    lockfile = parse_lockfile("Riot Client:314:54321:LOCKFILE-SECRET:https")
    verified = DiscoveryResult(
        True,
        True,
        lockfile,
        Path("C:/Riot Games/Riot Client/RiotClientServices.exe"),
        "verified",
    )
    client = FakeLocalClient(
        {"accessToken": "LOCAL-TOKEN-SECRET", "subject": "account-puuid"}
    )
    cookies = {"ssid": "REUSABLE-COOKIE-SECRET", "sub": "account-puuid"}
    importer = CapturingImporter(
        AuthenticatedRiotIdentity("account-puuid", "Peak", "EUW"),
        imported_puuid="account-puuid",
        cookies=cookies,
    )

    result = AccountOnboardingService(
        process_names_provider=lambda: {"VALORANT-Win64-Shipping.exe"},
        discovery_provider=lambda: verified,
        local_client_factory=lambda _lockfile: client,
        importer_factory=lambda: importer,
        browser_login=_unexpected,
    ).add_account()

    assert result.source == "local_client"
    assert dict(result.cookies or {}) == cookies
    assert importer.identity_tokens == ["LOCAL-TOKEN-SECRET", "IMPORTED-TOKEN-SECRET"]
    assert "REUSABLE-COOKIE-SECRET" not in repr(result)


def test_local_onboarding_prefers_bound_offline_import() -> None:
    class OfflineImporter(CapturingImporter):
        def import_durable_session_for_identity(self, expected: str) -> Any:
            assert expected == "account-puuid"
            self.imported.refresh_token = "DURABLE-REFRESH"
            return self.imported

        def import_current_session(self) -> Any:
            raise AssertionError("Use the identity-bound offline import")

    importer = OfflineImporter(
        AuthenticatedRiotIdentity("account-puuid", "Peak", "EUW"),
        imported_puuid="account-puuid", cookies={"ssid": "REUSABLE-COOKIE"},
    )
    verified = DiscoveryResult(
        True, True, parse_lockfile("Riot Client:314:54321:LOCKFILE-SECRET:https"),
        Path("C:/Riot Games/Riot Client/RiotClientServices.exe"), "verified",
    )
    service = AccountOnboardingService(
        process_names_provider=lambda: {"VALORANT-Win64-Shipping.exe"},
        discovery_provider=lambda: verified,
        local_client_factory=lambda _lockfile: FakeLocalClient({
            "accessToken": "LOCAL-TOKEN", "subject": "account-puuid",
        }),
        importer_factory=lambda: importer, browser_login=_unexpected,
    )

    result = service.add_account()

    assert result.refresh_token == "DURABLE-REFRESH"
    assert result.identity.puuid == "account-puuid"
    assert "DURABLE-REFRESH" not in repr(result)


def test_browser_onboarding_requests_offline_authorization_before_saving() -> None:
    class OfflineImporter(FakeImporter):
        def mint_durable_authorization(self, cookies: Mapping[str, str]) -> Any:
            assert cookies["ssid"] == "BROWSER-COOKIE"
            return SimpleNamespace(
                cookies={"ssid": "ROTATED-COOKIE", "sub": "account-puuid"},
                access_token="OFFLINE-ACCESS", refresh_token="DURABLE-REFRESH",
            )

        def mint_access_token(self, cookies: Mapping[str, str]) -> str:
            raise AssertionError("Offline credentials must be requested")

    importer = OfflineImporter(
        AuthenticatedRiotIdentity("account-puuid", "Peak", "EUW"), minted_token="unused",
    )
    result = AccountOnboardingService(
        process_names_provider=lambda: (), importer_factory=lambda: importer,
        browser_login=lambda: {"ssid": "BROWSER-COOKIE"},
    ).add_account()

    assert result.refresh_token == "DURABLE-REFRESH"
    assert result.cookies == {"ssid": "ROTATED-COOKIE", "sub": "account-puuid"}
    assert importer.identity_tokens == ["OFFLINE-ACCESS"]
    assert "DURABLE-REFRESH" not in repr(result)


def test_active_valorant_rejects_mismatched_reusable_settings_session() -> None:
    lockfile = parse_lockfile("Riot Client:314:54321:LOCKFILE-SECRET:https")
    verified = DiscoveryResult(
        True,
        True,
        lockfile,
        Path("C:/Riot Games/Riot Client/RiotClientServices.exe"),
        "verified",
    )
    importer = CapturingImporter(
        AuthenticatedRiotIdentity("account-puuid", "Peak", "EUW"),
        imported_puuid="different-puuid",
        cookies={"ssid": "REUSABLE-COOKIE-SECRET", "sub": "different-puuid"},
    )
    service = AccountOnboardingService(
        process_names_provider=lambda: {"VALORANT-Win64-Shipping.exe"},
        discovery_provider=lambda: verified,
        local_client_factory=lambda _lockfile: FakeLocalClient(
            {"accessToken": "LOCAL-TOKEN-SECRET", "subject": "account-puuid"}
        ),
        importer_factory=lambda: importer,
        browser_login=_unexpected,
    )

    with pytest.raises(AccountIdentityMismatchError, match="settings session"):
        service.add_account()


def test_similar_process_name_does_not_select_local_client() -> None:
    cookies = {"ssid": "ssid-value", "clid": "clid-value"}
    importer = FakeImporter(
        AuthenticatedRiotIdentity("browser-puuid"),
        minted_token="BROWSER-TOKEN-SECRET",
    )

    result = AccountOnboardingService(
        process_names_provider=lambda: {"helper-VALORANT-Win64-Shipping.exe"},
        discovery_provider=_unexpected,
        local_client_factory=lambda _lockfile: _unexpected(),
        importer_factory=lambda: importer,
        browser_login=lambda: cookies,
    ).add_account()

    assert result.source == "browser"
    assert result.identity.puuid == "browser-puuid"
    assert dict(result.cookies or {}) == cookies
    assert importer.minted_cookies == cookies
    assert importer.identity_tokens == ["BROWSER-TOKEN-SECRET"]
    assert importer.closed
    assert "ssid-value" not in repr(result)
    assert "BROWSER-TOKEN-SECRET" not in repr(result)
    with pytest.raises(TypeError):
        assert result.cookies is not None
        result.cookies["ssid"] = "changed"  # type: ignore[index]


def test_active_valorant_fails_closed_when_lockfile_is_not_verified() -> None:
    unverified = DiscoveryResult(True, True, None, None, "PID could not be verified")
    delays: list[float] = []
    browser_calls = 0

    def browser_login() -> Mapping[str, str] | None:
        nonlocal browser_calls
        browser_calls += 1
        return {"ssid": "must-not-be-used"}

    service = AccountOnboardingService(
        process_names_provider=lambda: {"VALORANT-Win64-Shipping.exe"},
        discovery_provider=lambda: unverified,
        local_client_factory=lambda _lockfile: _unexpected(),
        importer_factory=_unexpected,
        browser_login=browser_login,
        local_retry_attempts=3,
        local_retry_delay=0.02,
        sleep=delays.append,
    )

    with pytest.raises(AccountOnboardingUnavailableError, match="verified Riot lockfile"):
        service.add_account()
    assert browser_calls == 0
    assert delays == [0.02, 0.02]


def test_local_and_browser_subject_mismatches_are_rejected_without_secret_leaks() -> None:
    lockfile = parse_lockfile("Riot Client:314:54321:LOCKFILE-SECRET:https")
    verified = DiscoveryResult(
        True,
        True,
        lockfile,
        Path("C:/Riot Games/Riot Client/RiotClientServices.exe"),
        "verified",
    )
    client = FakeLocalClient({"accessToken": "LOCAL-TOKEN-SECRET", "subject": "expected-puuid"})
    local_importer = FakeImporter(
        AuthenticatedRiotIdentity("different-puuid"),
        minted_token="unused",
    )
    local_service = AccountOnboardingService(
        process_names_provider=lambda: {"VALORANT-Win64-Shipping.exe"},
        discovery_provider=lambda: verified,
        local_client_factory=lambda _lockfile: client,
        importer_factory=lambda: local_importer,
        browser_login=_unexpected,
    )
    with pytest.raises(AccountIdentityMismatchError) as local_error:
        local_service.add_account()
    assert "LOCAL-TOKEN-SECRET" not in repr(local_error.value)
    assert client.closed and local_importer.closed

    browser_importer = FakeImporter(
        AuthenticatedRiotIdentity("identity-puuid"),
        minted_token="BROWSER-TOKEN-SECRET",
    )
    browser_service = AccountOnboardingService(
        process_names_provider=lambda: set(),
        discovery_provider=_unexpected,
        local_client_factory=lambda _lockfile: _unexpected(),
        importer_factory=lambda: browser_importer,
        browser_login=lambda: {"ssid": "ssid-secret", "sub": "cookie-puuid"},
    )
    with pytest.raises(AccountIdentityMismatchError) as browser_error:
        browser_service.add_account()
    assert "ssid-secret" not in repr(browser_error.value)
    assert "BROWSER-TOKEN-SECRET" not in repr(browser_error.value)
    assert browser_importer.closed


def test_closed_browser_is_reported_as_cancelled_without_importing_a_session() -> None:
    service = AccountOnboardingService(
        process_names_provider=lambda: set(),
        discovery_provider=_unexpected,
        local_client_factory=lambda _lockfile: _unexpected(),
        importer_factory=_unexpected,
        browser_login=lambda: None,
    )

    with pytest.raises(AccountOnboardingCancelledError, match="cancelled, closed, or timed out"):
        service.add_account()


class FakePage:
    def __init__(self) -> None:
        self.navigation: tuple[str, str] | None = None

    def goto(self, url: str, *, wait_until: str) -> None:
        self.navigation = (url, wait_until)


class FakeBrowserContext:
    def __init__(self, cookie_batches: list[list[dict[str, str]]]) -> None:
        self.page = FakePage()
        self.pages = [self.page]
        self.cookie_batches = cookie_batches
        self.cookie_urls: list[str] | None = None
        self.added_cookies: list[dict[str, str]] = []
        self.closed = False

    def new_page(self) -> FakePage:
        self.pages.append(self.page)
        return self.page

    def cookies(self, urls: list[str]) -> list[dict[str, str]]:
        self.cookie_urls = urls
        if len(self.cookie_batches) > 1:
            return self.cookie_batches.pop(0)
        return self.cookie_batches[0]

    def add_cookies(self, cookies: list[dict[str, str]]) -> None:
        self.added_cookies.extend(cookies)

    def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self, context: FakeBrowserContext) -> None:
        self.context = context
        self.profile_dir: Path | None = None
        self.options: dict[str, object] = {}

    def launch_persistent_context(self, profile_dir: str, **options: object) -> FakeBrowserContext:
        self.profile_dir = Path(profile_dir)
        self.options = options
        return self.context


class FakePlaywright:
    def __init__(self, chromium: FakeChromium) -> None:
        self.chromium = chromium

    def __enter__(self) -> FakePlaywright:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


def test_headed_browser_polls_auth_and_account_completion_then_returns_allowlist() -> None:
    incomplete = [
        {"domain": ".auth.riotgames.com", "name": "ssid", "value": "ssid-value"},
    ]
    complete = [
        {"domain": ".auth.riotgames.com", "name": "ssid", "value": "ssid-value"},
        {"domain": ".auth.riotgames.com", "name": "clid", "value": "clid-value"},
        {"domain": ".auth.riotgames.com", "name": "ccid", "value": "ccid-value"},
        {"domain": ".auth.riotgames.com", "name": "asid", "value": "asid-value"},
        {"domain": ".account.riotgames.com", "name": "a12l-csrf-prod", "value": "csrf"},
        {"domain": ".account.riotgames.com", "name": "account-cookie", "value": "private"},
    ]
    context = FakeBrowserContext([incomplete, complete])
    chromium = FakeChromium(context)
    playwright = FakePlaywright(chromium)

    result = login_riot_account(
        timeout=1,
        poll_interval=0.1,
        playwright_factory=lambda: playwright,
        clock=lambda: 0,
        sleep=lambda _delay: None,
    )

    assert dict(result or {}) == {
        "ssid": "ssid-value",
        "clid": "clid-value",
        "ccid": "ccid-value",
        "asid": "asid-value",
    }
    assert context.page.navigation == (RIOT_ACCOUNT_URL, "commit")
    assert context.cookie_urls == [
        "https://account.riotgames.com/",
        "https://auth.riotgames.com/",
    ]
    assert chromium.options == {"headless": False, "no_viewport": True}
    assert chromium.profile_dir is not None and not chromium.profile_dir.exists()
    assert context.closed
    with pytest.raises(TypeError):
        assert result is not None
        result["ssid"] = "changed"  # type: ignore[index]


def test_mfa_browser_capture_keeps_only_account_host_jar_and_sso_allowlist() -> None:
    complete = [
        {"domain": ".auth.riotgames.com", "name": "ssid", "value": "ssid-value"},
        {"domain": ".auth.riotgames.com", "name": "clid", "value": "clid-value"},
        {"domain": ".auth.riotgames.com", "name": "ccid", "value": "ccid-value"},
        {"domain": ".auth.riotgames.com", "name": "asid", "value": "asid-value"},
        {"domain": ".account.riotgames.com", "name": "a12l-csrf-prod", "value": "csrf"},
        {"domain": ".account.riotgames.com", "name": "account-cookie", "value": "private"},
    ]
    context = FakeBrowserContext([complete])
    chromium = FakeChromium(context)

    result = login_riot_account_for_mfa(
        timeout=1,
        poll_interval=0.1,
        playwright_factory=lambda: FakePlaywright(chromium),
        clock=lambda: 0,
        sleep=lambda _delay: None,
    )

    assert result is not None
    assert dict(result.account_cookies) == {
        "a12l-csrf-prod": "csrf",
        "account-cookie": "private",
    }
    assert dict(result.sso_cookies) == {
        "ssid": "ssid-value",
        "clid": "clid-value",
        "ccid": "ccid-value",
        "asid": "asid-value",
    }
    assert result.csrf_token == "csrf"
    assert "ssid-value" not in repr(result)
    assert "private" not in repr(result)


def test_mfa_browser_reuses_only_allowlisted_sso_cookies_in_ephemeral_context() -> None:
    complete = [
        {"domain": ".auth.riotgames.com", "name": "ssid", "value": "saved-session"},
        {"domain": ".auth.riotgames.com", "name": "sub", "value": "owned-puuid"},
        {"domain": ".account.riotgames.com", "name": "a12l-csrf-prod", "value": "csrf"},
    ]
    context = FakeBrowserContext([complete])

    result = login_riot_account_for_mfa(
        reusable_sso_cookies={"ssid": "saved-session", "sub": "owned-puuid"},
        timeout=1,
        poll_interval=0.1,
        playwright_factory=lambda: FakePlaywright(FakeChromium(context)),
        clock=lambda: 0,
        sleep=lambda _delay: None,
    )

    assert result is not None
    assert context.added_cookies == [
        {
            "name": "ssid",
            "value": "saved-session",
            "url": "https://auth.riotgames.com/",
        },
        {
            "name": "sub",
            "value": "owned-puuid",
            "url": "https://auth.riotgames.com/",
        },
    ]
    assert "saved-session" not in repr(result)


def test_mfa_browser_rejects_non_allowlisted_reusable_cookie_before_navigation() -> None:
    context = FakeBrowserContext([[]])

    with pytest.raises(ValueError, match="cookies are invalid"):
        login_riot_account_for_mfa(
            reusable_sso_cookies={"ssid": "saved-session", "unexpected": "secret"},
            timeout=1,
            poll_interval=0.1,
            playwright_factory=lambda: FakePlaywright(FakeChromium(context)),
            clock=lambda: 0,
            sleep=lambda _delay: None,
        )

    assert context.page.navigation is None
    assert context.closed is False
