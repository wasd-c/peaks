"""Confirmation-gated Riot Mobile TOTP enrollment.

Preparation exchanges a saved SSO session (or uses the explicit browser flow),
binds it to the selected account, and checks factors without changing Riot state.
Only :meth:`confirm` calls the enable endpoint.  Once Riot returns a valid
seed, the caller-provided encrypted persistence callback runs *before*
verification so a partial verification failure cannot discard the only copy.
"""

from __future__ import annotations

import logging
import secrets
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from threading import RLock, Timer
from typing import Protocol

from peaks.adapters.riot.account_session import (
    RiotAccountSessionError,
    acquire_riot_account_session,
)
from peaks.adapters.riot.browser_login import (
    RiotAccountBrowserSession,
    login_riot_account_for_mfa,
)
from peaks.adapters.riot.mfa import (
    RiotAccountIdentity,
    RiotMfaClient,
    RiotMfaError,
    RiotMfaFactor,
    RiotMfaHttpError,
    factor_is_enabled,
)
from peaks.adapters.riot.session_import import (
    AuthenticatedRiotIdentity,
    RiotSessionImporter,
)
from peaks.adapters.riot.totp import parse_seed

LOGGER = logging.getLogger(__name__)
DEFAULT_CONFIRMATION_TTL_SECONDS = 300.0


class RiotMobileTotpSetupError(RuntimeError):
    """Base class for safe setup failures."""


class RiotMobileTotpSetupCancelledError(RiotMobileTotpSetupError):
    """The temporary browser was closed or timed out."""


class RiotMobileTotpIdentityMismatchError(RiotMobileTotpSetupError):
    """The browser session is not the selected Peaks account."""


class RiotMobileTotpPrerequisiteError(RiotMobileTotpSetupError):
    """The selected account cannot safely begin enrollment."""


class RiotMobileTotpConfirmationError(RiotMobileTotpSetupError):
    """The explicit confirmation is invalid or expired."""


class RiotMobileTotpPersistenceError(RiotMobileTotpSetupError):
    """Riot issued a seed, but Peaks could not preserve it encrypted."""


class _SessionImporter(Protocol):
    def mint_access_token(self, cookies: Mapping[str, str]) -> str: ...

    def fetch_identity(self, access_token: str) -> AuthenticatedRiotIdentity: ...

    def close(self) -> None: ...


class _MfaClient(Protocol):
    def refresh_csrf_token(self, cookies: Mapping[str, str]) -> str: ...

    def fetch_identity(
        self,
        cookies: Mapping[str, str],
        csrf_token: str,
    ) -> RiotAccountIdentity: ...

    def fetch_factors(
        self,
        cookies: Mapping[str, str],
        csrf_token: str,
    ) -> tuple[RiotMfaFactor, ...]: ...

    def enable_riot_mobile(
        self,
        cookies: Mapping[str, str],
        csrf_token: str,
    ) -> str: ...

    def verify_riot_mobile(self, bearer_token: str, seed: str) -> None: ...

    def close(self) -> None: ...


class _ExpiryTimer(Protocol):
    daemon: bool

    def start(self) -> None: ...

    def cancel(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RiotMobileTotpSetupProposal:
    confirmation_id: str = field(repr=False)
    account_id: str = field(repr=False)
    riot_id: str = field(repr=False)
    expires_in_seconds: int


@dataclass(frozen=True, slots=True)
class RiotMobileTotpSetupResult:
    account_id: str = field(repr=False)
    riot_id: str = field(repr=False)
    seed_saved: bool
    verified: bool
    warning: str | None = None


@dataclass(frozen=True, slots=True)
class _PendingSetup:
    account_id: str = field(repr=False)
    expected_puuid: str = field(repr=False)
    expected_riot_id: str = field(repr=False)
    expires_at: float
    browser_session: RiotAccountBrowserSession = field(repr=False)


def _close_safely(resource: object | None) -> None:
    close = getattr(resource, "close", None)
    if callable(close):
        with suppress(Exception):
            close()


def _expected_text(value: object, label: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise RiotMobileTotpSetupError(f"The selected account has no valid {label}")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise RiotMobileTotpSetupError(f"The selected account has no valid {label}")
    return value


def _assert_identity_binding(
    *,
    expected_puuid: str,
    expected_riot_id: str,
    account_identity: RiotAccountIdentity,
    sso_identity: AuthenticatedRiotIdentity,
) -> None:
    sso_riot_id = (
        f"{sso_identity.game_name}#{sso_identity.tag_line}"
        if sso_identity.game_name and sso_identity.tag_line
        else ""
    )
    if not (
        account_identity.puuid == expected_puuid
        and sso_identity.puuid == expected_puuid
        and account_identity.riot_id == expected_riot_id
        and sso_riot_id == expected_riot_id
    ):
        raise RiotMobileTotpIdentityMismatchError(
            "The Riot browser session does not match the selected account"
        )


def _check_prerequisites(factors: tuple[RiotMfaFactor, ...]) -> None:
    if not factor_is_enabled(factors, "email"):
        raise RiotMobileTotpPrerequisiteError(
            "Enable email multi-factor authentication in Riot account security, then try again"
        )
    if factor_is_enabled(factors, "riotmobile"):
        raise RiotMobileTotpPrerequisiteError(
            "Riot Mobile authentication is already enabled; Peaks will not rotate it"
        )


def _login_with_reusable_session(
    cookies: Mapping[str, str],
) -> RiotAccountBrowserSession | None:
    return acquire_riot_account_session(cookies)


class RiotMobileTotpSetupService:
    """Own short-lived browser sessions across prepare/confirm commands."""

    def __init__(
        self,
        *,
        browser_login: Callable[[], RiotAccountBrowserSession | None] = (
            login_riot_account_for_mfa
        ),
        browser_login_with_session: Callable[
            [Mapping[str, str]], RiotAccountBrowserSession | None
        ] = _login_with_reusable_session,
        mfa_client_factory: Callable[[], _MfaClient] = RiotMfaClient,
        importer_factory: Callable[[], _SessionImporter] = RiotSessionImporter,
        confirmation_ttl: float = DEFAULT_CONFIRMATION_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
        timer_factory: Callable[[float, Callable[[], None]], _ExpiryTimer] = Timer,
        logger: logging.Logger | None = None,
    ) -> None:
        if not 30 <= confirmation_ttl <= 900:
            raise ValueError("confirmation_ttl must be between 30 and 900 seconds")
        self._browser_login = browser_login
        self._browser_login_with_session = browser_login_with_session
        self._mfa_client_factory = mfa_client_factory
        self._importer_factory = importer_factory
        self._confirmation_ttl = float(confirmation_ttl)
        self._clock = clock
        self._token_factory = token_factory
        self._timer_factory = timer_factory
        self._logger = logger or LOGGER
        self._pending: dict[str, _PendingSetup] = {}
        self._expiry_timers: dict[str, _ExpiryTimer] = {}
        self._pending_lock = RLock()

    def _discard_pending(self, confirmation_id: str) -> _PendingSetup | None:
        with self._pending_lock:
            pending = self._pending.pop(confirmation_id, None)
            timer = self._expiry_timers.pop(confirmation_id, None)
        if timer is not None:
            with suppress(Exception):
                timer.cancel()
        return pending

    def _new_expiry_timer(self, confirmation_id: str, delay: float) -> _ExpiryTimer:
        timer = self._timer_factory(
            max(0.0, delay),
            lambda: self._expire_pending(confirmation_id),
        )
        # A pending confirmation must never keep the desktop process alive.
        timer.daemon = True
        return timer

    def _expire_pending(self, confirmation_id: str) -> None:
        """Drop browser credentials at their deadline without another API call."""

        replacement: _ExpiryTimer | None = None
        with self._pending_lock:
            pending = self._pending.get(confirmation_id)
            if pending is None:
                self._expiry_timers.pop(confirmation_id, None)
                return
            remaining = pending.expires_at - self._clock()
            if remaining > 0:
                # Defend against an early/spurious timer wake-up.
                replacement = self._new_expiry_timer(confirmation_id, remaining)
                self._expiry_timers[confirmation_id] = replacement
            else:
                self._pending.pop(confirmation_id, None)
                self._expiry_timers.pop(confirmation_id, None)
        if replacement is not None:
            try:
                replacement.start()
            except Exception:
                # Fail closed if a replacement timer cannot be armed.
                self._discard_pending(confirmation_id)
        else:
            self._logger.info("riot_mobile_totp.confirmation_expired")

    def _store_pending(self, confirmation_id: str, pending: _PendingSetup) -> None:
        timer = self._new_expiry_timer(
            confirmation_id,
            pending.expires_at - self._clock(),
        )
        with self._pending_lock:
            self._pending[confirmation_id] = pending
            self._expiry_timers[confirmation_id] = timer
        try:
            timer.start()
        except Exception:
            self._discard_pending(confirmation_id)
            raise RuntimeError("Could not arm authenticator confirmation expiry") from None

    def _purge_expired(self) -> None:
        now = self._clock()
        with self._pending_lock:
            expired = tuple(
                confirmation_id
                for confirmation_id, pending in self._pending.items()
                if pending.expires_at <= now
            )
        for confirmation_id in expired:
            self._discard_pending(confirmation_id)

    def _authenticate_bound_session(
        self,
        pending: _PendingSetup,
        client: _MfaClient,
        importer: _SessionImporter,
        csrf_token: str,
    ) -> tuple[RiotAccountIdentity, str]:
        browser = pending.browser_session
        account_identity = client.fetch_identity(
            browser.account_cookies,
            csrf_token,
        )
        access_token = importer.mint_access_token(browser.sso_cookies)
        sso_identity = importer.fetch_identity(access_token)
        if not isinstance(sso_identity, AuthenticatedRiotIdentity):
            raise RiotMobileTotpSetupError("Riot returned invalid account identity data")
        _assert_identity_binding(
            expected_puuid=pending.expected_puuid,
            expected_riot_id=pending.expected_riot_id,
            account_identity=account_identity,
            sso_identity=sso_identity,
        )
        return account_identity, access_token

    def prepare(
        self,
        *,
        account_id: str,
        expected_puuid: str,
        expected_riot_id: str,
        reusable_sso_cookies: Mapping[str, str] | None = None,
    ) -> RiotMobileTotpSetupProposal:
        """Authenticate and inspect factors without changing Riot account state."""

        account_id = _expected_text(account_id, "local account ID")
        expected_puuid = _expected_text(expected_puuid, "PUUID")
        expected_riot_id = _expected_text(expected_riot_id, "Riot ID")
        self._logger.info("riot_mobile_totp.prepare.start")
        self._purge_expired()
        try:
            browser = (
                self._browser_login_with_session(reusable_sso_cookies)
                if reusable_sso_cookies is not None
                else self._browser_login()
            )
        except RiotAccountSessionError as exc:
            self._logger.warning(
                "riot_mobile_totp.prepare.session_failed error_type=%s",
                type(exc).__name__,
            )
            raise RiotMobileTotpSetupError(str(exc)) from None
        except Exception as exc:
            self._logger.warning(
                "riot_mobile_totp.prepare.browser_failed error_type=%s",
                type(exc).__name__,
            )
            raise RiotMobileTotpSetupError("Riot browser sign-in failed") from None
        if browser is None:
            self._logger.info("riot_mobile_totp.prepare.cancelled")
            raise RiotMobileTotpSetupCancelledError(
                "Riot browser sign-in was cancelled, closed, or timed out"
            )
        if not isinstance(browser, RiotAccountBrowserSession):
            raise RiotMobileTotpSetupError("Riot browser sign-in returned invalid session data")

        client: _MfaClient | None = None
        importer: _SessionImporter | None = None
        pending = _PendingSetup(
            account_id=account_id,
            expected_puuid=expected_puuid,
            expected_riot_id=expected_riot_id,
            expires_at=0.0,
            browser_session=browser,
        )
        try:
            client = self._mfa_client_factory()
            importer = self._importer_factory()
            self._logger.info("riot_mobile_totp.prepare.csrf_refresh.start")
            try:
                csrf_token = client.refresh_csrf_token(browser.account_cookies)
            except RiotMfaError as exc:
                status_code = getattr(exc, "status_code", None)
                self._logger.warning(
                    "riot_mobile_totp.prepare.csrf_refresh.failed "
                    "error_type=%s status=%s",
                    type(exc).__name__,
                    status_code if isinstance(status_code, int) else "unknown",
                )
                raise
            self._logger.info("riot_mobile_totp.prepare.csrf_refresh.complete")
            identity, _ = self._authenticate_bound_session(
                pending,
                client,
                importer,
                csrf_token,
            )
            self._logger.info("riot_mobile_totp.prepare.identity_verified")
            factors = client.fetch_factors(browser.account_cookies, csrf_token)
            _check_prerequisites(factors)
            self._logger.info(
                "riot_mobile_totp.prepare.factors_checked email_enabled=true "
                "riotmobile_enabled=false"
            )
            if identity.riot_id != expected_riot_id:
                raise RiotMobileTotpIdentityMismatchError(
                    "The Riot browser session does not match the selected account"
                )
        except RiotMobileTotpSetupError:
            raise
        except RiotMfaError as exc:
            status_code = getattr(exc, "status_code", None)
            self._logger.warning(
                "riot_mobile_totp.prepare.riot_request_failed error_type=%s status=%s",
                type(exc).__name__,
                status_code if isinstance(status_code, int) else "unknown",
            )
            raise RiotMobileTotpSetupError(str(exc)) from None
        except Exception as exc:
            self._logger.warning(
                "riot_mobile_totp.prepare.failed error_type=%s",
                type(exc).__name__,
            )
            raise RiotMobileTotpSetupError(
                "Could not inspect Riot authenticator settings"
            ) from None
        finally:
            _close_safely(importer)
            _close_safely(client)

        pending = _PendingSetup(
            account_id=account_id,
            expected_puuid=expected_puuid,
            expected_riot_id=expected_riot_id,
            expires_at=self._clock() + self._confirmation_ttl,
            browser_session=browser,
        )
        # Re-preparing an account invalidates its previous confirmation and
        # cancels that confirmation's independent expiry timer.
        with self._pending_lock:
            previous_confirmations = tuple(
                confirmation_id
                for confirmation_id, value in self._pending.items()
                if value.account_id == account_id
            )
        for previous_confirmation_id in previous_confirmations:
            self._discard_pending(previous_confirmation_id)
        confirmation_id = self._token_factory()
        if not isinstance(confirmation_id, str) or len(confirmation_id) < 32:
            raise RuntimeError("confirmation token generator returned invalid data")
        self._store_pending(confirmation_id, pending)
        self._logger.info("riot_mobile_totp.prepare.complete")
        return RiotMobileTotpSetupProposal(
            confirmation_id=confirmation_id,
            account_id=account_id,
            riot_id=expected_riot_id,
            expires_in_seconds=int(self._confirmation_ttl),
        )

    def enable(
        self,
        *,
        account_id: str,
        expected_puuid: str,
        expected_riot_id: str,
        reusable_sso_cookies: Mapping[str, str],
        persist_seed: Callable[[str], None],
    ) -> RiotMobileTotpSetupResult:
        """Enroll after an explicit Enable MFA click without opening a browser.

        Preserve the same identity/prerequisite rechecks and persist-before-
        verify ordering as the two-step flow. A missing session cannot fall
        through to interactive sign-in.
        """

        if not isinstance(reusable_sso_cookies, Mapping) or not reusable_sso_cookies.get("ssid"):
            raise RiotMobileTotpSetupError(
                "Reconnect this account in Peaks before enabling MFA"
            )
        proposal = self.prepare(
            account_id=account_id,
            expected_puuid=expected_puuid,
            expected_riot_id=expected_riot_id,
            reusable_sso_cookies=reusable_sso_cookies,
        )
        try:
            return self.confirm(
                confirmation_id=proposal.confirmation_id,
                account_id=account_id,
                persist_seed=persist_seed,
            )
        finally:
            self.cancel(proposal.confirmation_id)

    def cancel(self, confirmation_id: str) -> None:
        """Discard one pending browser session without changing Riot state."""

        if isinstance(confirmation_id, str):
            self._discard_pending(confirmation_id)

    def close(self) -> None:
        """Cancel expiry work and discard every ephemeral browser session."""

        with self._pending_lock:
            confirmation_ids = tuple(self._pending.keys() | self._expiry_timers.keys())
        for confirmation_id in confirmation_ids:
            self._discard_pending(confirmation_id)

    def confirm(
        self,
        *,
        confirmation_id: str,
        account_id: str,
        persist_seed: Callable[[str], None],
    ) -> RiotMobileTotpSetupResult:
        """Enable, persist, then verify after the user explicitly confirms."""

        self._purge_expired()
        if not isinstance(confirmation_id, str) or not isinstance(account_id, str):
            raise RiotMobileTotpConfirmationError(
                "Authenticator setup confirmation expired; start again"
            )
        pending = self._discard_pending(confirmation_id)
        if pending is None or pending.account_id != account_id:
            raise RiotMobileTotpConfirmationError(
                "Authenticator setup confirmation expired; start again"
            )
        if pending.expires_at <= self._clock():
            raise RiotMobileTotpConfirmationError(
                "Authenticator setup confirmation expired; start again"
            )

        self._logger.info("riot_mobile_totp.confirm.start")
        client: _MfaClient | None = None
        importer: _SessionImporter | None = None
        access_token = ""
        seed = ""
        try:
            client = self._mfa_client_factory()
            importer = self._importer_factory()
            self._logger.info("riot_mobile_totp.confirm.csrf_refresh.start")
            try:
                csrf_token = client.refresh_csrf_token(
                    pending.browser_session.account_cookies
                )
            except RiotMfaError as exc:
                status_code = getattr(exc, "status_code", None)
                self._logger.warning(
                    "riot_mobile_totp.confirm.csrf_refresh.failed "
                    "error_type=%s status=%s",
                    type(exc).__name__,
                    status_code if isinstance(status_code, int) else "unknown",
                )
                raise
            self._logger.info("riot_mobile_totp.confirm.csrf_refresh.complete")
            identity, access_token = self._authenticate_bound_session(
                pending,
                client,
                importer,
                csrf_token,
            )
            self._logger.info("riot_mobile_totp.confirm.identity_reverified")
            factors = client.fetch_factors(
                pending.browser_session.account_cookies,
                csrf_token,
            )
            _check_prerequisites(factors)
            self._logger.info(
                "riot_mobile_totp.confirm.factors_rechecked email_enabled=true "
                "riotmobile_enabled=false"
            )
            if identity.riot_id != pending.expected_riot_id:
                raise RiotMobileTotpIdentityMismatchError(
                    "The Riot browser session does not match the selected account"
                )

            # This is the first external mutation.  It can only run after the
            # opaque one-time confirmation has been consumed above.
            self._logger.info("riot_mobile_totp.confirm.enable_request")
            try:
                seed = parse_seed(
                    client.enable_riot_mobile(
                        pending.browser_session.account_cookies,
                        csrf_token,
                    )
                )
            except RiotMfaHttpError as exc:
                self._logger.warning(
                    "riot_mobile_totp.confirm.enable_failed error_type=%s status=%s",
                    type(exc).__name__,
                    exc.status_code,
                )
                if exc.status_code in {401, 403}:
                    raise RiotMobileTotpSetupError(
                        f"Riot rejected authenticator enrollment (HTTP {exc.status_code}). "
                        "Peaks saved nothing. Start setup again and sign in to refresh the "
                        "account session; if Riot rejects it again, check email MFA and "
                        "account security before retrying."
                    ) from None
                raise RiotMobileTotpSetupError(
                    f"Riot authenticator enrollment failed (HTTP {exc.status_code}). "
                    "Peaks saved nothing and did not verify."
                ) from None
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                self._logger.warning(
                    "riot_mobile_totp.confirm.enable_failed error_type=%s status=%s",
                    type(exc).__name__,
                    status_code if isinstance(status_code, int) else "unknown",
                )
                raise RiotMobileTotpSetupError(
                    "Riot did not return a usable authenticator secret. Peaks stored nothing "
                    "and did not verify; Riot account state may have changed, so check account "
                    "security before retrying."
                ) from None
            self._logger.info("riot_mobile_totp.confirm.enable_secret_valid")
            try:
                persist_seed(seed)
            except Exception as exc:
                self._logger.error(
                    "riot_mobile_totp.confirm.persistence_failed error_type=%s",
                    type(exc).__name__,
                )
                raise RiotMobileTotpPersistenceError(
                    "Riot issued an authenticator secret, but Peaks could not encrypt it. "
                    "Check Riot account security before retrying."
                ) from None
            self._logger.info("riot_mobile_totp.confirm.seed_persisted")

            try:
                self._logger.info("riot_mobile_totp.confirm.verify_request")
                client.verify_riot_mobile(access_token, seed)
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                self._logger.warning(
                    "riot_mobile_totp.confirm.verify_failed error_type=%s status=%s",
                    type(exc).__name__,
                    status_code if isinstance(status_code, int) else "unknown",
                )
                return RiotMobileTotpSetupResult(
                    account_id=pending.account_id,
                    riot_id=pending.expected_riot_id,
                    seed_saved=True,
                    verified=False,
                    warning=(
                        "Riot returned an authenticator secret and Peaks saved it encrypted, "
                        "but Riot verification failed. The factor may already be enabled; "
                        "use the saved code and check Riot account security before retrying."
                    ),
                )
        except RiotMobileTotpSetupError:
            raise
        except RiotMfaError as exc:
            status_code = getattr(exc, "status_code", None)
            self._logger.warning(
                "riot_mobile_totp.confirm.riot_request_failed error_type=%s status=%s",
                type(exc).__name__,
                status_code if isinstance(status_code, int) else "unknown",
            )
            raise RiotMobileTotpSetupError(str(exc)) from None
        except Exception as exc:
            self._logger.warning(
                "riot_mobile_totp.confirm.failed error_type=%s",
                type(exc).__name__,
            )
            raise RiotMobileTotpSetupError("Could not enable Riot Mobile authentication") from None
        finally:
            access_token = ""
            seed = ""
            _close_safely(importer)
            _close_safely(client)

        self._logger.info("riot_mobile_totp.confirm.complete verified=true")
        return RiotMobileTotpSetupResult(
            account_id=pending.account_id,
            riot_id=pending.expected_riot_id,
            seed_saved=True,
            verified=True,
        )


__all__ = [
    "RiotMobileTotpConfirmationError",
    "RiotMobileTotpIdentityMismatchError",
    "RiotMobileTotpPersistenceError",
    "RiotMobileTotpPrerequisiteError",
    "RiotMobileTotpSetupCancelledError",
    "RiotMobileTotpSetupError",
    "RiotMobileTotpSetupProposal",
    "RiotMobileTotpSetupResult",
    "RiotMobileTotpSetupService",
]
