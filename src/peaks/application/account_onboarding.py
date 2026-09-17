"""Authenticate and identify a Riot account without asking for a Riot ID.

When the exact VALORANT game process is active, onboarding uses the verified
Riot Client lockfile and its local entitlement token.  Otherwise it opens the
short-lived headed browser flow.  Access tokens stay inside this service and
are never included in results, representations, or error messages.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Protocol

from peaks.adapters.riot.browser_login import login_riot_account
from peaks.adapters.riot.client import RiotClientHTTP
from peaks.adapters.riot.discovery import (
    DiscoveryResult,
    RiotLockfile,
    discover_riot_client,
    running_process_names,
)
from peaks.adapters.riot.session_import import (
    ALLOWED_COOKIE_NAMES,
    MAX_REFRESH_TOKEN_LENGTH,
    AuthenticatedRiotIdentity,
    RiotSessionImporter,
)

VALORANT_PROCESS_NAME = "VALORANT-Win64-Shipping.exe"
RIOT_ENTITLEMENTS_PATH = "/entitlements/v1/token"
DEFAULT_LOCAL_RETRY_ATTEMPTS = 3
DEFAULT_LOCAL_RETRY_DELAY_SECONDS = 0.2
LOGGER = logging.getLogger(__name__)

AccountOnboardingSource = Literal["local_client", "browser"]
_COOKIE_VALUE_RE = re.compile(r"^[A-Za-z0-9._~+/=-]+$")


class AccountOnboardingError(RuntimeError):
    """Base class for safe account-onboarding failures."""


class AccountOnboardingUnavailableError(AccountOnboardingError):
    """Raised when an expected local or browser authentication source is unavailable."""


class AccountOnboardingCancelledError(AccountOnboardingError):
    """Raised when browser authentication is cancelled, closed, or times out."""


class AccountIdentityMismatchError(AccountOnboardingError):
    """Raised when two authoritative Riot session subjects do not match."""


class _LocalClient(Protocol):
    def get_json(self, endpoint: str, *, params: Mapping[str, object] | None = None) -> Any: ...

    def close(self) -> None: ...


class _SessionImporter(Protocol):
    def import_current_session(self) -> Any: ...

    def mint_access_token(self, cookies: Mapping[str, str]) -> str: ...

    def fetch_identity(self, access_token: str) -> AuthenticatedRiotIdentity: ...

    def close(self) -> None: ...


def _copy_browser_cookies(cookies: object) -> Mapping[str, str]:
    """Validate and freeze the same narrow cookie schema as the importer."""

    if not isinstance(cookies, Mapping):
        raise AccountOnboardingError("Riot browser sign-in returned invalid session cookies")
    copied: dict[str, str] = {}
    for name, value in cookies.items():
        if not isinstance(name, str) or name not in ALLOWED_COOKIE_NAMES:
            raise AccountOnboardingError(
                "Riot browser sign-in returned unsupported session cookies"
            )
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 4096
            or not _COOKIE_VALUE_RE.fullmatch(value)
        ):
            raise AccountOnboardingError("Riot browser sign-in returned invalid session cookies")
        copied[name] = value
    if "ssid" not in copied:
        raise AccountOnboardingError("Riot browser sign-in returned incomplete session cookies")
    return MappingProxyType(copied)


@dataclass(frozen=True, slots=True)
class AccountOnboardingResult:
    """Sanitized account identity and the source that authenticated it.

    Cookies and any offline refresh token go directly to the encrypted account
    store and stay out of ``repr``. Local-client onboarding includes them only
    after the settings session was independently imported and identity-bound.
    """

    identity: AuthenticatedRiotIdentity
    source: AccountOnboardingSource
    cookies: Mapping[str, str] | None = field(default=None, repr=False)
    refresh_token: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.identity, AuthenticatedRiotIdentity):
            raise ValueError("identity must be an authenticated Riot identity")
        if self.source not in {"local_client", "browser"}:
            raise ValueError("source is invalid")
        if self.refresh_token is not None and _bounded_text(
            self.refresh_token, max_length=MAX_REFRESH_TOKEN_LENGTH,
        ) is None:
            raise ValueError("refresh token is invalid")
        if self.cookies is None:
            if self.source == "browser" or self.refresh_token is not None:
                raise ValueError("browser onboarding requires cookies")
            return
        try:
            copied = _copy_browser_cookies(self.cookies)
        except AccountOnboardingError as exc:
            raise ValueError("browser onboarding cookies are invalid") from exc
        object.__setattr__(self, "cookies", copied)


def _close_safely(resource: object | None) -> None:
    close = getattr(resource, "close", None)
    if callable(close):
        with suppress(Exception):
            close()


def _is_exact_valorant_process(names: Iterable[str]) -> bool:
    expected = VALORANT_PROCESS_NAME.casefold()
    return any(isinstance(name, str) and name.casefold() == expected for name in names)


def _bounded_text(value: object, *, max_length: int) -> str | None:
    if not isinstance(value, str) or not value or len(value) > max_length:
        return None
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        return None
    return value


class AccountOnboardingService:
    """Choose the safe Riot account-authentication path for one user action."""

    def __init__(
        self,
        *,
        process_names_provider: Callable[[], Iterable[str]] = running_process_names,
        discovery_provider: Callable[[], DiscoveryResult] = discover_riot_client,
        local_client_factory: Callable[[RiotLockfile], _LocalClient] = RiotClientHTTP,
        importer_factory: Callable[[], _SessionImporter] = RiotSessionImporter,
        browser_login: Callable[[], Mapping[str, str] | None] = login_riot_account,
        local_retry_attempts: int = DEFAULT_LOCAL_RETRY_ATTEMPTS,
        local_retry_delay: float = DEFAULT_LOCAL_RETRY_DELAY_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        if not 1 <= local_retry_attempts <= 10:
            raise ValueError("local_retry_attempts must be between 1 and 10")
        if not 0 <= local_retry_delay <= 2:
            raise ValueError("local_retry_delay must be between 0 and 2 seconds")
        self._process_names_provider = process_names_provider
        self._discovery_provider = discovery_provider
        self._local_client_factory = local_client_factory
        self._importer_factory = importer_factory
        self._browser_login = browser_login
        self._local_retry_attempts = local_retry_attempts
        self._local_retry_delay = float(local_retry_delay)
        self._sleep = sleep
        self._logger = logger or LOGGER

    def add_account(self) -> AccountOnboardingResult:
        """Authenticate the active account without accepting user-supplied identity text."""

        self._logger.info("account_onboarding.start")
        try:
            process_names = tuple(self._process_names_provider())
        except Exception as exc:
            self._logger.warning(
                "account_onboarding.process_detection.failed error_type=%s",
                type(exc).__name__,
            )
            raise AccountOnboardingUnavailableError(
                "Could not determine whether VALORANT is running"
            ) from None
        valorant_active = _is_exact_valorant_process(process_names)
        self._logger.info(
            "account_onboarding.process_detection.complete valorant_active=%s",
            valorant_active,
        )
        if valorant_active:
            return self._add_from_local_client()
        return self._add_from_browser()

    # A product-neutral alias is useful to non-UI callers.
    onboard = add_account

    def _verified_lockfile(self) -> RiotLockfile:
        for attempt in range(self._local_retry_attempts):
            try:
                result = self._discovery_provider()
            except Exception as exc:
                self._logger.warning(
                    "account_onboarding.local.discovery.failed attempt=%s error_type=%s",
                    attempt + 1,
                    type(exc).__name__,
                )
                result = None
            # Normal discovery sets ``executable`` only after binding the
            # lockfile PID to a live RiotClientServices.exe at a resolved Riot
            # installation path.  Requiring all fields fails closed if a stale
            # or unverified result reaches this service.
            if (
                isinstance(result, DiscoveryResult)
                and result.supported
                and result.process_running
                and result.lockfile is not None
                and isinstance(result.executable, Path)
            ):
                self._logger.info(
                    "account_onboarding.local.discovery.verified attempt=%s",
                    attempt + 1,
                )
                return result.lockfile
            self._logger.info(
                "account_onboarding.local.discovery.pending attempt=%s supported=%s "
                "process_running=%s lockfile_present=%s executable_verified=%s",
                attempt + 1,
                bool(getattr(result, "supported", False)),
                bool(getattr(result, "process_running", False)),
                getattr(result, "lockfile", None) is not None,
                isinstance(getattr(result, "executable", None), Path),
            )
            if attempt + 1 < self._local_retry_attempts:
                self._sleep(self._local_retry_delay)
        raise AccountOnboardingUnavailableError(
            "VALORANT is running, but its verified Riot lockfile is unavailable"
        )

    def _add_from_local_client(self) -> AccountOnboardingResult:
        self._logger.info("account_onboarding.local.start")
        lockfile = self._verified_lockfile()
        client: _LocalClient | None = None
        importer: _SessionImporter | None = None
        access_token = ""
        try:
            client = self._local_client_factory(lockfile)
            self._logger.info("account_onboarding.local.entitlements.request")
            payload = client.get_json(RIOT_ENTITLEMENTS_PATH)
            if not isinstance(payload, Mapping):
                raise AccountOnboardingError("Riot local session returned invalid account data")
            access_token = _bounded_text(payload.get("accessToken"), max_length=8192) or ""
            subject = _bounded_text(payload.get("subject"), max_length=256)
            if not access_token or subject is None:
                raise AccountOnboardingError("Riot local session returned incomplete account data")

            importer = self._importer_factory()
            identity = importer.fetch_identity(access_token)
            if not isinstance(identity, AuthenticatedRiotIdentity):
                raise AccountOnboardingError("Riot returned invalid account identity data")
            if identity.puuid != subject:
                raise AccountIdentityMismatchError(
                    "Riot local session identity does not match the active account"
                )
            self._logger.info("account_onboarding.local.identity.verified")
            cookies, refresh_token = self._try_import_session_authorization(importer, expected_puuid=subject)
            self._logger.info(
                "account_onboarding.local.complete reusable_session_saved=%s",
                cookies is not None,
            )
            return AccountOnboardingResult(
                identity=identity,
                source="local_client",
                cookies=cookies,
                refresh_token=refresh_token,
            )
        except AccountOnboardingError:
            raise
        except Exception as exc:
            self._logger.warning(
                "account_onboarding.local.failed error_type=%s", type(exc).__name__
            )
            raise AccountOnboardingError(
                "Could not authenticate the active VALORANT account"
            ) from None
        finally:
            access_token = ""
            _close_safely(importer)
            _close_safely(client)

    def _try_import_session_authorization(
        self,
        importer: _SessionImporter,
        *,
        expected_puuid: str,
    ) -> tuple[Mapping[str, str] | None, str | None]:
        """Best-effort capture of a reusable session for local onboarding.

        Lockfile credentials and entitlements tokens cannot be reused after
        Riot Client exits.  A cookie bundle is returned only when the separate
        private-settings import succeeds and its freshly minted token resolves
        to the same authoritative PUUID as the active lockfile session.
        """

        import_current = getattr(importer, "import_current_session", None)
        if not callable(import_current):
            self._logger.info(
                "account_onboarding.local.session_capture.unavailable reason=no_importer"
            )
            return None, None
        self._logger.info("account_onboarding.local.session_capture.start")
        try:
            bound_import = getattr(importer, "import_durable_session_for_identity", None)
            if not callable(bound_import):
                bound_import = getattr(importer, "import_session_for_identity", None)
            imported = bound_import(expected_puuid) if callable(bound_import) else import_current()
            imported_puuid = str(getattr(imported, "puuid", "") or "")
            imported_access_token = str(getattr(imported, "access_token", "") or "")
            if imported_puuid != expected_puuid or not imported_access_token:
                raise AccountIdentityMismatchError(
                    "Riot Client settings session does not match the active account"
                )
            imported_identity = importer.fetch_identity(imported_access_token)
            if (
                not isinstance(imported_identity, AuthenticatedRiotIdentity)
                or imported_identity.puuid != expected_puuid
            ):
                raise AccountIdentityMismatchError(
                    "Riot Client settings session does not match the active account"
                )
            cookies = _copy_browser_cookies(getattr(imported, "cookies", None))
            refresh_token = getattr(imported, "refresh_token", None)
        except AccountIdentityMismatchError:
            self._logger.warning("account_onboarding.local.session_capture.identity_mismatch")
            raise
        except Exception as exc:
            self._logger.info(
                "account_onboarding.local.session_capture.unavailable error_type=%s",
                type(exc).__name__,
            )
            return None, None
        self._logger.info(
            "account_onboarding.local.session_capture.complete cookie_count=%s",
            len(cookies),
        )
        return cookies, refresh_token

    def _add_from_browser(self) -> AccountOnboardingResult:
        self._logger.info("account_onboarding.browser.start")
        try:
            browser_cookies = self._browser_login()
        except Exception as exc:
            self._logger.warning(
                "account_onboarding.browser.capture.failed error_type=%s",
                type(exc).__name__,
            )
            raise AccountOnboardingUnavailableError("Riot browser sign-in failed") from None
        if browser_cookies is None:
            self._logger.info("account_onboarding.browser.cancelled")
            raise AccountOnboardingCancelledError(
                "Riot browser sign-in was cancelled, closed, or timed out"
            )
        cookies = _copy_browser_cookies(browser_cookies)
        self._logger.info(
            "account_onboarding.browser.capture.complete cookie_count=%s", len(cookies)
        )

        importer: _SessionImporter | None = None
        access_token = ""
        refresh_token = None
        try:
            importer = self._importer_factory()
            refresh = getattr(importer, "mint_durable_authorization", None)
            if not callable(refresh):
                refresh = getattr(importer, "refresh_authorization", None)
            if callable(refresh):
                authorization = refresh(cookies)
                access_token = str(getattr(authorization, "access_token", "") or "")
                cookies = _copy_browser_cookies(
                    getattr(authorization, "cookies", None)
                )
                refresh_token = getattr(authorization, "refresh_token", None)
            else:
                access_token = importer.mint_access_token(cookies)
            identity = importer.fetch_identity(access_token)
            if not isinstance(identity, AuthenticatedRiotIdentity):
                raise AccountOnboardingError("Riot returned invalid account identity data")
            cookie_subject = cookies.get("sub")
            if cookie_subject is not None and cookie_subject != identity.puuid:
                raise AccountIdentityMismatchError(
                    "Riot browser session identity does not match its account subject"
                )
            self._logger.info("account_onboarding.browser.identity.verified")
            return AccountOnboardingResult(
                identity=identity,
                source="browser",
                cookies=cookies,
                refresh_token=refresh_token,
            )
        except AccountOnboardingError:
            raise
        except Exception as exc:
            self._logger.warning(
                "account_onboarding.browser.failed error_type=%s", type(exc).__name__
            )
            raise AccountOnboardingError(
                "Could not authenticate the Riot browser session"
            ) from None
        finally:
            access_token = ""
            _close_safely(importer)


def onboard_account(**kwargs: Any) -> AccountOnboardingResult:
    """Convenience wrapper for a single account-onboarding action."""

    return AccountOnboardingService(**kwargs).add_account()


__all__ = [
    "RIOT_ENTITLEMENTS_PATH",
    "VALORANT_PROCESS_NAME",
    "AccountIdentityMismatchError",
    "AccountOnboardingCancelledError",
    "AccountOnboardingError",
    "AccountOnboardingResult",
    "AccountOnboardingService",
    "AccountOnboardingSource",
    "AccountOnboardingUnavailableError",
    "onboard_account",
]
