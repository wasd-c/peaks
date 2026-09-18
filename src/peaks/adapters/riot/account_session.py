"""Exchange an existing Riot SSO session for an ephemeral account-site session.

This follows the account site's OAuth redirects without opening a browser. It
does not sign in, answer an authentication challenge, or change MFA settings.
Account cookies stay in memory and may only be used after identity binding.
"""

from __future__ import annotations

import hmac
import json
import logging
from collections.abc import Mapping
from contextlib import suppress
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urljoin, urlsplit

import requests

from .browser_login import (
    ACCOUNT_CSRF_COOKIE_NAME,
    RIOT_ACCOUNT_HOST,
    RIOT_ACCOUNT_URL,
    RIOT_AUTH_HOST,
    RiotAccountBrowserSession,
    _freeze_cookie_jar,
)
from .session_import import ALLOWED_COOKIE_NAMES

ACCOUNT_CALLBACK_URL = "https://account.riotgames.com/oauth2/log-in"
ACCOUNT_CLIENT_ID = "accountodactyl-prod"
RIOT_AUTH_ISSUER = "https://auth.riotgames.com"
MAX_REDIRECTS = 8
MAX_LOCATION_BYTES = 16 * 1024
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_PROMPT_BYTES = 512 * 1024
MAX_SESSION_STATE_LENGTH = 4096
AUTHENTICATOR_HOST = "authenticate.riotgames.com"
AUTHENTICATOR_SESSION_URL = "https://authenticate.riotgames.com/api/v1/login"
LOGGER = logging.getLogger(__name__)


class RiotAccountSessionError(RuntimeError):
    """Safe, credential-free account session failure."""


class RiotAccountSessionChallengeError(RiotAccountSessionError):
    """Riot requires renewed authentication or an additional identity check."""


class RiotAccountSessionHttpError(RiotAccountSessionError):
    """Riot rejected an HTTP request; this does not prove the SSO is expired."""

    def __init__(self, *, status_code: int, browser_challenge: bool = False) -> None:
        self.status_code = status_code
        self.browser_challenge = browser_challenge
        super().__init__(
            "Riot blocked the account connection. Please try again later"
            if browser_challenge else "Riot could not complete the account connection. Please try again"
        )


class _HttpSession(Protocol):
    cookies: Any

    def request(self, method: str, url: str, **kwargs: Any) -> Any: ...

    def close(self) -> None: ...


def _parsed_url(url: str) -> Any:
    if (
        not isinstance(url, str)
        or len(url) > MAX_LOCATION_BYTES
        or "\\" in url
        or any(ord(character) <= 0x20 or ord(character) == 0x7F for character in url)
    ):
        raise RiotAccountSessionError("Riot returned an invalid account sign-in redirect")
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme == "https"
            and parsed.port is None
            and not parsed.username
            and not parsed.password
            and not parsed.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise RiotAccountSessionError("Riot returned an invalid account sign-in redirect")
    return parsed


def _query(url: Any) -> dict[str, list[str]]:
    try:
        return parse_qs(url.query, keep_blank_values=True, strict_parsing=True, max_num_fields=32)
    except ValueError:
        raise RiotAccountSessionError("Riot returned an invalid account sign-in redirect") from None


def _value(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key, ())
    if len(values) != 1 or not values[0]:
        raise RiotAccountSessionError("Riot returned an invalid account sign-in redirect")
    value = values[0]
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise RiotAccountSessionError("Riot returned an invalid account sign-in redirect")
    return value


def _request_stage(url: str) -> str:
    """Fixed diagnostic labels only; never log OAuth URLs or query values."""

    parsed = urlsplit(url)
    if parsed.hostname == AUTHENTICATOR_HOST:
        return (
            "authenticator_session" if parsed.path == "/api/v1/login"
            else "authenticator_login" if parsed.path == "/login"
            else "authenticator_page"
        )
    if parsed.hostname == RIOT_AUTH_HOST:
        return "account_authorize"
    if parsed.path == "/oauth2/log-in":
        return "account_callback"
    if parsed.path == "/log-in":
        return "account_login"
    return "account_home"


def _redirect_target(parsed: Any) -> str:
    """Describe only known destinations, never arbitrary host/path content."""

    if parsed.hostname == RIOT_ACCOUNT_HOST and parsed.path in {"/", "/log-in", "/oauth2/log-in"}:
        return _request_stage(parsed.geturl())
    if parsed.hostname == RIOT_AUTH_HOST and parsed.path == "/authorize":
        return "account_authorize"
    if parsed.hostname == AUTHENTICATOR_HOST and parsed.path in {"/", "/login"}:
        return _request_stage(parsed.geturl())
    return "unknown"


def _read_body(response: Any, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        size += len(chunk)
        if size > limit:
            raise RiotAccountSessionError("Riot account page exceeded the size limit")
        chunks.append(bytes(chunk))
    return b"".join(chunks)


def _validate_authenticator_handoff(
    parsed: Any,
    authorization_query: dict[str, list[str]] | None,
) -> None:
    """Constrain the frontend context to the same account OAuth request."""

    query = _query(parsed)
    allowed_keys = {
        "client_id", "redirect_uri", "security_profile", "method", "platform",
        "acr_values", "response_type", "scope", "state", "locale", "login_state", "remember",
    }
    if (
        parsed.path not in {"/login", "/"}
        or authorization_query is None
        or not set(query).issubset(allowed_keys)
        or any(len(values) != 1 for values in query.values())
        or _value(query, "client_id") != ACCOUNT_CLIENT_ID
        or _value(query, "security_profile") != "high"
        or _value(query, "method") not in {"riot_identity", "login_state", "rso"}
    ):
        raise RiotAccountSessionError("Riot returned an invalid account sign-in redirect")
    redirect = _parsed_url(_value(query, "redirect_uri"))
    if (
        redirect.hostname != RIOT_AUTH_HOST
        or redirect.path != "/authorize"
        or _query(redirect) != authorization_query
    ):
        raise RiotAccountSessionError("Riot returned an invalid account sign-in redirect")
    for key in ("acr_values", "client_id", "response_type", "scope", "state"):
        if key in query and query[key] != authorization_query.get(key):
            raise RiotAccountSessionError("Riot returned an invalid account sign-in redirect")


def _effective_cookies(session: _HttpSession, host: str) -> dict[str, str]:
    """Read root-path, unexpired cookies for one exact HTTPS host."""

    cookies = sorted(
        session.cookies,
        key=lambda cookie: len(str(getattr(cookie, "domain", "")).lstrip(".")),
    )
    result: dict[str, str] = {}
    for cookie in cookies:
        domain = str(getattr(cookie, "domain", "")).lstrip(".").lower()
        if domain not in {host, "riotgames.com"}:
            continue
        if getattr(cookie, "path", "/") != "/" or cookie.is_expired():
            continue
        if host == RIOT_AUTH_HOST and cookie.name not in ALLOWED_COOKIE_NAMES:
            continue
        if host == RIOT_ACCOUNT_HOST and cookie.name in ALLOWED_COOKIE_NAMES:
            continue
        result[cookie.name] = cookie.value
    return result


def acquire_riot_account_session(
    reusable_sso_cookies: Mapping[str, str],
    *,
    session: _HttpSession | None = None,
    timeout: float = 15.0,
    logger: logging.Logger | None = None,
) -> RiotAccountBrowserSession:
    """Use saved SSO cookies; stop if Riot asks for any interactive proof.

    The same freshly created HTTP session retains the account site's OAuth
    state cookie. Every redirect is validated *before* its request. Only the
    matching account callback can complete the exchange; a login page or a
    challenge cannot be mistaken for a usable session.
    """

    if not 0 < timeout <= 60:
        raise ValueError("timeout must be between 0 and 60 seconds")
    try:
        cookies = _freeze_cookie_jar(reusable_sso_cookies)
        if "ssid" not in cookies or any(name not in ALLOWED_COOKIE_NAMES for name in cookies):
            raise ValueError("incomplete session")
    except (TypeError, ValueError):
        raise RiotAccountSessionError("Reconnect this account in Peaks before enabling MFA") from None

    http = cast(_HttpSession, session or requests.Session())
    if hasattr(http, "trust_env"):
        http.trust_env = False
    expected_state: str | None = None
    authorization_query: dict[str, list[str]] | None = None
    callback_seen = False
    authenticator_seen = False
    prompt_read = False
    resume_authorization = False
    url = RIOT_ACCOUNT_URL
    diagnostic = logger or LOGGER
    try:
        http.cookies.clear()
        for name, value in cookies.items():
            http.cookies.set(name, value, domain=RIOT_AUTH_HOST, path="/", secure=True)
        for _ in range(MAX_REDIRECTS + 1):
            with http.request(
                "GET",
                url,
                headers={
                    "Accept": "application/json" if url == AUTHENTICATOR_SESSION_URL else "text/html,application/xhtml+xml",
                    "User-Agent": "Peaks/0.3 Riot account session",
                    "Cache-Control": "no-cache",
                },
                allow_redirects=False,
                stream=True,
                verify=True,
                timeout=timeout,
            ) as response:
                stage = _request_stage(url)
                diagnostic.info(
                    "riot_account_session.response stage=%s status=%s",
                    stage,
                    response.status_code,
                )
                if response.status_code >= 400:
                    browser_challenge = response.headers.get("cf-mitigated") == "challenge"
                    diagnostic.warning(
                        "riot_account_session.rejected stage=%s status=%s reason=%s",
                        stage,
                        response.status_code,
                        "browser_challenge" if browser_challenge else "http_rejected",
                    )
                    raise RiotAccountSessionHttpError(
                        status_code=response.status_code,
                        browser_challenge=browser_challenge,
                    )
                location: object = None
                if url == AUTHENTICATOR_SESSION_URL:
                    if response.status_code != 200 or prompt_read:
                        raise RiotAccountSessionError("Riot account sign-in could not be completed")
                    prompt_read = True
                    try:
                        prompt = json.loads(_read_body(response, MAX_PROMPT_BYTES))
                    except (ValueError, UnicodeError):
                        raise RiotAccountSessionError("Riot returned an invalid account session") from None
                    kind = prompt.get("type") if isinstance(prompt, Mapping) else None
                    diagnostic.info(
                        "riot_account_session.prompt prompt=%s",
                        kind if kind in {"auth", "re-auth", "multifactor", "success", "error"} else "unknown",
                    )
                    if kind in {"auth", "re-auth", "multifactor"}:
                        raise RiotAccountSessionChallengeError(
                            "Riot requires a verification code before changing MFA. Use Refresh Riot sign-in from this account's connection menu."
                            if kind == "multifactor" else
                            "Riot requires a fresh sign-in before changing MFA. Use Refresh Riot sign-in from this account's connection menu."
                        )
                    success = prompt.get("success") if isinstance(prompt, Mapping) and kind == "success" else None
                    if not isinstance(success, Mapping):
                        raise RiotAccountSessionError("Riot account sign-in could not be completed")
                    location = success.get("redirect_url")
                    resume_authorization = True
                elif response.status_code == 200 and urlsplit(url).hostname == AUTHENTICATOR_HOST:
                    if urlsplit(url).path != "/" or not authenticator_seen or prompt_read:
                        raise RiotAccountSessionError("Riot account sign-in could not be completed")
                    _read_body(response, MAX_PAGE_BYTES)
                    url = AUTHENTICATOR_SESSION_URL
                    continue
                elif response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")

                if location is not None or response.status_code in {301, 302, 303, 307, 308}:
                    if not isinstance(location, str) or not location:
                        raise RiotAccountSessionError("Riot returned an invalid account sign-in redirect")
                    # Validate the original string too: urljoin normalizes some
                    # control characters which must never enter navigation.
                    if len(location) > MAX_LOCATION_BYTES or "\\" in location or any(
                        ord(character) <= 0x20 or ord(character) == 0x7F for character in location
                    ):
                        raise RiotAccountSessionError("Riot returned an invalid account sign-in redirect")
                    next_url = urljoin(url, location)
                    parsed = _parsed_url(next_url)
                    diagnostic.info(
                        "riot_account_session.redirect stage=%s target=%s",
                        stage,
                        _redirect_target(parsed),
                    )
                    if parsed.hostname == AUTHENTICATOR_HOST:
                        if prompt_read or callback_seen:
                            raise RiotAccountSessionError("Riot account sign-in could not be completed")
                        try:
                            _validate_authenticator_handoff(parsed, authorization_query)
                        except RiotAccountSessionError:
                            diagnostic.warning(
                                "riot_account_session.rejected stage=%s status=%s reason=frontend_context",
                                stage,
                                response.status_code,
                            )
                            raise
                        if not authenticator_seen and parsed.path != "/login":
                            raise RiotAccountSessionError("Riot returned an invalid account sign-in redirect")
                        authenticator_seen = True
                        diagnostic.info(
                            "riot_account_session.handoff stage=%s status=%s",
                            stage,
                            response.status_code,
                        )
                    elif parsed.hostname == RIOT_AUTH_HOST and parsed.path == "/authorize":
                        query = _query(parsed)
                        if callback_seen or (expected_state is not None and not resume_authorization):
                            raise RiotAccountSessionError("Riot account sign-in could not be completed")
                        if resume_authorization and query != authorization_query:
                            raise RiotAccountSessionError("Riot account sign-in could not be verified")
                        if (
                            _value(query, "client_id") != ACCOUNT_CLIENT_ID
                            or _value(query, "redirect_uri") != ACCOUNT_CALLBACK_URL
                            or _value(query, "response_type") != "code"
                            or _value(query, "acr_values") != "urn:riot:gold"
                        ):
                            raise RiotAccountSessionError("Riot returned an invalid account sign-in redirect")
                        expected_state = _value(query, "state")
                        authorization_query = query
                        resume_authorization = False
                    elif parsed.hostname == RIOT_ACCOUNT_HOST and parsed.path == "/oauth2/log-in":
                        query = _query(parsed)
                        diagnostic.info(
                            "riot_account_session.callback has_issuer=%s has_error=%s has_session_state=%s",
                            "iss" in query,
                            "error" in query,
                            "session_state" in query,
                        )
                        failure = ""
                        if not {"code", "state"}.issubset(query) or not set(query).issubset(
                            {"code", "state", "iss", "session_state"}
                        ) or any(
                            len(values) != 1 or not values[0] for values in query.values()
                        ):
                            failure = "callback_fields"
                        elif (
                            callback_seen or expected_state is None
                            or not hmac.compare_digest(_value(query, "state").encode(), expected_state.encode())
                        ):
                            failure = "callback_state"
                        # Riot advertises RFC 9207 support in its OpenID
                        # discovery metadata. Its optional issuer must match
                        # exactly; never normalize or accept another issuer.
                        elif "iss" in query and _value(query, "iss") != RIOT_AUTH_ISSUER:
                            failure = "callback_issuer"
                        # OpenID Session Management adds an opaque session
                        # state. It never substitutes for our original OAuth
                        # state and is only forwarded to Riot's fixed callback.
                        elif "session_state" in query and (
                            len(query["session_state"][0]) > MAX_SESSION_STATE_LENGTH
                            or any(
                                character.isspace() or ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F
                                for character in query["session_state"][0]
                            )
                        ):
                            failure = "callback_session_state"
                        if failure:
                            diagnostic.warning(
                                "riot_account_session.rejected stage=%s status=%s reason=%s",
                                stage,
                                response.status_code,
                                failure,
                            )
                            raise RiotAccountSessionError("Riot account sign-in could not be verified")
                        _value(query, "code")
                        callback_seen = True
                        resume_authorization = False
                    elif parsed.hostname == RIOT_ACCOUNT_HOST and parsed.path in {"/", "/log-in"}:
                        if parsed.query or resume_authorization:
                            raise RiotAccountSessionError("Riot returned an invalid account sign-in redirect")
                    else:
                        raise RiotAccountSessionError("Riot returned an invalid account sign-in redirect")
                    url = next_url
                    continue
                if response.status_code != 200 or url != RIOT_ACCOUNT_URL or not callback_seen:
                    raise RiotAccountSessionError("Riot account sign-in could not be completed")
                # Do not retain the page. Bounded consumption completes this
                # response before exporting its effective, rotated cookies.
                _read_body(response, MAX_PAGE_BYTES)
                account_cookies = _effective_cookies(http, RIOT_ACCOUNT_HOST)
                sso_cookies = _effective_cookies(http, RIOT_AUTH_HOST)
                csrf_token = account_cookies.get(ACCOUNT_CSRF_COOKIE_NAME, "")
                if not csrf_token:
                    raise RiotAccountSessionError("Riot account sign-in could not be completed")
                try:
                    return RiotAccountBrowserSession(account_cookies, sso_cookies, csrf_token)
                except ValueError:
                    raise RiotAccountSessionError("Riot returned an invalid account session") from None
        raise RiotAccountSessionError("Riot account sign-in could not be completed")
    except RiotAccountSessionError:
        raise
    except Exception:
        # Transport errors can contain request URLs, callback codes or cookie
        # data. Never chain them to a presentation or log-safe exception.
        raise RiotAccountSessionError("Could not connect to Riot to enable MFA; try again") from None
    finally:
        with suppress(Exception):
            http.cookies.clear()
        if session is None:
            with suppress(Exception):
                http.close()


__all__ = [
    "RiotAccountSessionChallengeError",
    "RiotAccountSessionError",
    "RiotAccountSessionHttpError",
    "acquire_riot_account_session",
]
