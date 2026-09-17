"""Interactive Riot sign-in through a short-lived headed Patchright browser.

The browser is used when VALORANT is not active, or when an explicit connection
action cannot import reusable client cookies. Peaks polls the browser cookie jar
over Patchright and never evaluates code in the Riot page. A login
is complete only after both Riot SSO (``ssid``) and the account site's CSRF
cookie are present.  Normal onboarding discards account cookies and returns
only the exact SSO allowlist.  The separately named MFA function retains the
account-host jar in memory for its explicit, confirmation-gated setup service.

Patchright is imported inside :func:`login_riot_account` so systems that can
use the local VALORANT client do not need to import or initialize a browser.
The browser profile lives in a temporary directory that is removed before the
function returns.  Nothing in this module enables or changes MFA.
"""

from __future__ import annotations

import logging
import re
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from .session_import import ALLOWED_COOKIE_NAMES

LOGGER = logging.getLogger(__name__)

RIOT_ACCOUNT_URL = "https://account.riotgames.com/"
RIOT_ACCOUNT_HOST = "account.riotgames.com"
RIOT_AUTH_HOST = "auth.riotgames.com"
RIOT_AUTH_URL = f"https://{RIOT_AUTH_HOST}/"
ACCOUNT_CSRF_COOKIE_NAME = "a12l-csrf-prod"
DEFAULT_LOGIN_TIMEOUT_SECONDS = 600.0
DEFAULT_POLL_INTERVAL_SECONDS = 1.5
MAX_BROWSER_COOKIES = 64
MAX_COOKIE_NAME_LENGTH = 128
MAX_COOKIE_VALUE_LENGTH = 4096
_COOKIE_NAME_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")


class RiotBrowserLoginError(RuntimeError):
    """Raised when the isolated browser login cannot be started or completed."""


class RiotBrowserUnavailableError(RiotBrowserLoginError):
    """Raised when Patchright browser support is not installed."""


def _freeze_cookie_jar(cookies: Mapping[str, str]) -> Mapping[str, str]:
    if not isinstance(cookies, Mapping) or not 0 < len(cookies) <= MAX_BROWSER_COOKIES:
        raise ValueError("browser cookie jar is invalid")
    copied: dict[str, str] = {}
    for name, value in cookies.items():
        if (
            not isinstance(name, str)
            or not 0 < len(name) <= MAX_COOKIE_NAME_LENGTH
            or not _COOKIE_NAME_RE.fullmatch(name)
        ):
            raise ValueError("browser cookie name is invalid")
        if (
            not isinstance(value, str)
            or not value
            or len(value) > MAX_COOKIE_VALUE_LENGTH
            or ";" in value
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        ):
            raise ValueError("browser cookie value is invalid")
        copied[name] = value
    return MappingProxyType(copied)


@dataclass(frozen=True, slots=True)
class RiotAccountBrowserSession:
    """Ephemeral account-site session used only by explicit MFA enrollment.

    Account cookies and the CSRF value are hidden from representations.  The
    caller must keep this object in memory and discard it when the confirmation
    window expires; it is intentionally not serializable.
    """

    account_cookies: Mapping[str, str] = field(repr=False)
    sso_cookies: Mapping[str, str] = field(repr=False)
    csrf_token: str = field(repr=False)

    def __post_init__(self) -> None:
        account_cookies = _freeze_cookie_jar(self.account_cookies)
        sso_cookies = _freeze_cookie_jar(self.sso_cookies)
        if "ssid" not in sso_cookies:
            raise ValueError("browser SSO session is incomplete")
        if account_cookies.get(ACCOUNT_CSRF_COOKIE_NAME) != self.csrf_token:
            raise ValueError("browser account session is incomplete")
        object.__setattr__(self, "account_cookies", account_cookies)
        object.__setattr__(self, "sso_cookies", sso_cookies)


def _domain_matches(cookie_domain: object, host: str) -> bool:
    if not isinstance(cookie_domain, str):
        return False
    domain = cookie_domain.lstrip(".").casefold()
    expected = host.casefold()
    return bool(domain) and (expected == domain or expected.endswith(f".{domain}"))


def _jar_for_host(cookies: Iterable[object], host: str) -> dict[str, str]:
    """Build the effective cookie jar for one fixed Riot host.

    Less-specific domains are applied first so a host-specific cookie wins in
    the same way it would in the browser.
    """

    relevant: list[Mapping[str, object]] = []
    for cookie in cookies:
        if isinstance(cookie, Mapping) and _domain_matches(cookie.get("domain"), host):
            relevant.append(cookie)
    relevant.sort(key=lambda cookie: len(str(cookie.get("domain", "")).lstrip(".")))
    jar: dict[str, str] = {}
    for cookie in relevant:
        name = cookie.get("name")
        value = cookie.get("value")
        if isinstance(name, str) and isinstance(value, str) and name and value:
            jar[name] = value
    return jar


def _reusable_auth_cookies(cookies: Mapping[str, str] | None) -> list[dict[str, str]]:
    """Return an exact-host Patchright cookie list for a saved SSO session.

    Reusable Riot cookies are already narrowed when they enter the encrypted
    vault.  Validate that boundary again before copying them into the temporary
    browser profile, and bind every cookie to Riot's fixed HTTPS auth origin.
    Account-site cookies are never accepted or persisted here.
    """

    if cookies is None:
        return []
    frozen = _freeze_cookie_jar(cookies)
    if any(name not in ALLOWED_COOKIE_NAMES for name in frozen):
        raise ValueError("reusable Riot session cookies are invalid")
    if "ssid" not in frozen:
        raise ValueError("reusable Riot session cookies are incomplete")
    return [
        {"name": name, "value": value, "url": RIOT_AUTH_URL}
        for name, value in frozen.items()
    ]


def _default_playwright_factory() -> Any:
    try:
        from patchright.sync_api import sync_playwright
    except ImportError as exc:
        raise RiotBrowserUnavailableError("Riot browser sign-in support is unavailable") from exc
    return sync_playwright()


def _capture_riot_browser_session(
    *,
    reusable_sso_cookies: Mapping[str, str] | None = None,
    cancelled: Callable[[], bool] | None = None,
    timeout: float = DEFAULT_LOGIN_TIMEOUT_SECONDS,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    playwright_factory: Callable[[], Any] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> tuple[dict[str, str], dict[str, str]] | None:
    """Capture effective account/auth cookie jars from a temporary browser."""

    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if not 0 < poll_interval <= timeout:
        raise ValueError("poll_interval must be positive and no greater than timeout")
    initial_cookies = _reusable_auth_cookies(reusable_sso_cookies)
    is_cancelled = cancelled or (lambda: False)
    factory = playwright_factory or _default_playwright_factory
    diagnostic = logger or LOGGER
    diagnostic.info("riot_browser.start")

    try:
        # A persistent context matches Riot's tested login behavior, while the
        # temporary profile makes its on-disk browser state strictly ephemeral.
        with (
            tempfile.TemporaryDirectory(prefix="peaks_riot_login_") as profile_dir,
            factory() as playwright,
        ):
            context: Any | None = None
            try:
                context = playwright.chromium.launch_persistent_context(
                    profile_dir,
                    headless=False,
                    no_viewport=True,
                )
                diagnostic.info("riot_browser.launched")
                if initial_cookies:
                    context.add_cookies(initial_cookies)
                    diagnostic.info(
                        "riot_browser.reusable_session_loaded cookie_count=%s",
                        len(initial_cookies),
                    )
                pages = list(context.pages)
                page = pages[0] if pages else context.new_page()
                with suppress(Exception):
                    page.goto(RIOT_ACCOUNT_URL, wait_until="commit")
                    # Redirect and navigation errors are common during the
                    # interactive login; cookie polling is authoritative.

                deadline = clock() + timeout
                while clock() < deadline:
                    if is_cancelled():
                        diagnostic.info("riot_browser.cancelled reason=requested")
                        return None
                    try:
                        if not context.pages:
                            diagnostic.info("riot_browser.cancelled reason=window_closed")
                            return None
                        # Ask Chromium for cookies applicable to these exact
                        # HTTPS roots. This preserves browser domain/path/
                        # secure-cookie rules before the jars are flattened.
                        cookies = context.cookies([RIOT_ACCOUNT_URL, RIOT_AUTH_URL])
                    except Exception:
                        cookies = ()

                    account = _jar_for_host(cookies, RIOT_ACCOUNT_HOST)
                    auth = _jar_for_host(cookies, RIOT_AUTH_HOST)
                    if auth.get("ssid") and account.get(ACCOUNT_CSRF_COOKIE_NAME):
                        diagnostic.info(
                            "riot_browser.authenticated account_cookie_count=%s "
                            "auth_cookie_count=%s",
                            len(account),
                            len(auth),
                        )
                        return account, auth

                    remaining = deadline - clock()
                    if remaining > 0:
                        sleep(min(poll_interval, remaining))
                diagnostic.info("riot_browser.cancelled reason=timeout")
                return None
            finally:
                if context is not None:
                    with suppress(Exception):
                        context.close()
    except RiotBrowserLoginError:
        raise
    except Exception as exc:
        diagnostic.warning("riot_browser.failed error_type=%s", type(exc).__name__)
        # Patchright errors may carry page/browser detail.  Replace them with
        # a stable message so cookies or redirect fragments cannot leak.
        raise RiotBrowserLoginError("Riot browser sign-in failed") from None


def login_riot_account(
    *,
    cancelled: Callable[[], bool] | None = None,
    timeout: float = DEFAULT_LOGIN_TIMEOUT_SECONDS,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    playwright_factory: Callable[[], Any] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> Mapping[str, str] | None:
    """Open Riot's account page and return its completed SSO cookie subset.

    ``None`` means the user cancelled, closed the browser, or reached the
    timeout.  The returned mapping contains only :data:`ALLOWED_COOKIE_NAMES`
    and is immutable.  Account-site cookies and the CSRF completion signal are
    deliberately discarded.
    """

    captured = _capture_riot_browser_session(
        cancelled=cancelled,
        timeout=timeout,
        poll_interval=poll_interval,
        playwright_factory=playwright_factory,
        clock=clock,
        sleep=sleep,
        logger=logger,
    )
    if captured is None:
        return None
    _account, auth = captured
    allowed = {
        name: auth[name]
        for name in ALLOWED_COOKIE_NAMES
        if isinstance(auth.get(name), str) and auth[name]
    }
    return MappingProxyType(allowed)


def login_riot_account_for_mfa(
    *,
    reusable_sso_cookies: Mapping[str, str] | None = None,
    cancelled: Callable[[], bool] | None = None,
    timeout: float = DEFAULT_LOGIN_TIMEOUT_SECONDS,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    playwright_factory: Callable[[], Any] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> RiotAccountBrowserSession | None:
    """Return a short-lived account session for confirmed MFA enrollment.

    Unlike :func:`login_riot_account`, this privileged variant retains the
    account-site cookie jar and CSRF token.  It must only be used by the
    confirmation-gated MFA setup service and never persisted.
    """

    captured = _capture_riot_browser_session(
        reusable_sso_cookies=reusable_sso_cookies,
        cancelled=cancelled,
        timeout=timeout,
        poll_interval=poll_interval,
        playwright_factory=playwright_factory,
        clock=clock,
        sleep=sleep,
        logger=logger,
    )
    if captured is None:
        return None
    account, auth = captured
    csrf_token = account[ACCOUNT_CSRF_COOKIE_NAME]
    allowed = {
        name: auth[name]
        for name in ALLOWED_COOKIE_NAMES
        if isinstance(auth.get(name), str) and auth[name]
    }
    return RiotAccountBrowserSession(
        account_cookies=account,
        sso_cookies=allowed,
        csrf_token=csrf_token,
    )


__all__ = [
    "ACCOUNT_CSRF_COOKIE_NAME",
    "RIOT_ACCOUNT_URL",
    "RiotAccountBrowserSession",
    "RiotBrowserLoginError",
    "RiotBrowserUnavailableError",
    "login_riot_account",
    "login_riot_account_for_mfa",
]
