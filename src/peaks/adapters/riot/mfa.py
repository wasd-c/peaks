"""Narrow client for explicit Riot Mobile TOTP enrollment.

These are private Riot account endpoints and may change without notice.  The
client accepts no user-controlled URLs, never logs response bodies or
credentials, and exposes only the operations needed by the confirmation-gated
application service.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Protocol, cast

import requests

from .totp import generate_totp, parse_seed

RIOT_ACCOUNT_USER_URL = "https://account.riotgames.com/api/account/v1/user"
RIOT_MFA_FACTORS_URL = "https://account.riotgames.com/api/mfa/v2/factors"
RIOT_MOBILE_ENABLE_URL = "https://account.riotgames.com/api/mfa/v2/factors/riotmobile/enable"
RIOT_MOBILE_VERIFY_URL = "https://api.account.riotgames.com/mfa/v1/factor/riotmobile/verify"
RIOT_ACCOUNT_ORIGIN = "https://account.riotgames.com"
RIOT_ACCOUNT_PAGE_URL = f"{RIOT_ACCOUNT_ORIGIN}/"
RIOT_ACCOUNT_HOST = "account.riotgames.com"
DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_JSON_BYTES = 512 * 1024
MAX_ACCOUNT_PAGE_BYTES = 2 * 1024 * 1024
MAX_IDENTITY_LENGTH = 256
MAX_BEARER_TOKEN_LENGTH = 8192
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)
_BROWSER_CLIENT_HINT = (
    '"Not;A=Brand";v="8", "Chromium";v="151", "Google Chrome";v="151"'
)
_COOKIE_NAME_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")


class RiotMfaError(RuntimeError):
    """Base class for presentation-safe enrollment failures."""


class RiotMfaHttpError(RiotMfaError):
    """A fixed Riot endpoint returned a non-success status."""

    def __init__(self, operation: str, status_code: int) -> None:
        self.operation = operation
        self.status_code = status_code
        super().__init__(f"Riot {operation} failed (HTTP {status_code})")


class _Response(Protocol):
    status_code: int
    content: bytes

    def iter_content(self, chunk_size: int) -> Any: ...

    def close(self) -> None: ...


class _HttpSession(Protocol):
    cookies: Any

    def request(self, method: str, url: str, **kwargs: Any) -> _Response: ...

    def close(self) -> None: ...


def _bounded_text(value: object, label: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise RiotMfaError(f"Riot returned invalid {label}")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise RiotMfaError(f"Riot returned invalid {label}")
    return value


@dataclass(frozen=True, slots=True)
class RiotAccountIdentity:
    puuid: str = field(repr=False)
    game_name: str = field(repr=False)
    tag_line: str = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "puuid",
            _bounded_text(self.puuid, "account identifier", max_length=MAX_IDENTITY_LENGTH),
        )
        object.__setattr__(
            self,
            "game_name",
            _bounded_text(self.game_name, "game name", max_length=128),
        )
        object.__setattr__(
            self,
            "tag_line",
            _bounded_text(self.tag_line, "tag line", max_length=128),
        )

    @property
    def riot_id(self) -> str:
        return f"{self.game_name}#{self.tag_line}"


@dataclass(frozen=True, slots=True)
class RiotMfaFactor:
    name: str
    status: str


def factor_is_enabled(factors: Sequence[RiotMfaFactor], name: str) -> bool:
    expected = name.casefold()
    return any(
        factor.name.casefold() == expected and factor.status.casefold() == "enabled"
        for factor in factors
    )


class _CsrfMetaParser(HTMLParser):
    """Extract exactly one account-page CSRF meta value without retaining HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "meta":
            return
        values = {name.casefold(): value for name, value in attrs}
        if str(values.get("name") or "").casefold() != "csrf-token":
            return
        content = values.get("content")
        if isinstance(content, str):
            self.values.append(content)


class RiotMfaClient:
    """HTTP client constrained to four fixed Riot account operations."""

    def __init__(
        self,
        *,
        session: _HttpSession | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not 0 < timeout <= 60:
            raise ValueError("timeout must be between 0 and 60 seconds")
        self._session = cast(_HttpSession, session or requests.Session())
        self._owns_session = session is None
        if hasattr(self._session, "trust_env"):
            self._session.trust_env = False
        self._timeout = float(timeout)
        self._bound_account_source: dict[str, str] | None = None

    @staticmethod
    def _validated_account_cookies(cookies: Mapping[str, str]) -> dict[str, str]:
        if not isinstance(cookies, Mapping) or not 0 < len(cookies) <= 64:
            raise RiotMfaError("Riot account session cookies are invalid")
        copied: dict[str, str] = {}
        for name, raw_value in cookies.items():
            if (
                not isinstance(name, str)
                or not 0 < len(name) <= 128
                or _COOKIE_NAME_RE.fullmatch(name) is None
            ):
                raise RiotMfaError("Riot account session cookies are invalid")
            value = _bounded_text(raw_value, "account cookie", max_length=4096)
            if ";" in value:
                raise RiotMfaError("Riot account session cookies are invalid")
            copied[name] = value
        return copied

    def _replace_account_cookie_jar(self, cookies: Mapping[str, str]) -> None:
        jar = getattr(self._session, "cookies", None)
        clear = getattr(jar, "clear", None)
        set_cookie = getattr(jar, "set", None)
        if not callable(clear) or not callable(set_cookie):
            raise RiotMfaError("Riot account session cookie support is unavailable")
        try:
            clear()
            for name, value in cookies.items():
                set_cookie(
                    name,
                    value,
                    domain=RIOT_ACCOUNT_HOST,
                    path="/",
                    secure=True,
                )
        except Exception:
            raise RiotMfaError("Could not bind the Riot account session") from None

    def _bind_account_session(self, cookies: Mapping[str, str]) -> dict[str, str]:
        copied = self._validated_account_cookies(cookies)
        self._replace_account_cookie_jar(copied)
        self._bound_account_source = copied
        return copied

    def _require_account_session(self, cookies: Mapping[str, str]) -> None:
        copied = self._validated_account_cookies(cookies)
        if self._bound_account_source is None or copied != self._bound_account_source:
            raise RiotMfaError("Riot account session must be refreshed before use")

    def _clear_account_session(self) -> None:
        self._bound_account_source = None
        jar = getattr(self._session, "cookies", None)
        clear = getattr(jar, "clear", None)
        if not callable(clear):
            raise RiotMfaError("Could not clear the Riot account session")
        try:
            clear()
        except Exception:
            raise RiotMfaError("Could not clear the Riot account session") from None

    @staticmethod
    def _read_json_body(response: _Response, operation: str) -> Any:
        try:
            headers = getattr(response, "headers", {})
            content_length = headers.get("Content-Length") if isinstance(headers, Mapping) else None
            if content_length is not None:
                try:
                    if int(content_length) > MAX_JSON_BYTES:
                        raise RiotMfaError(
                            f"Riot returned too much data while attempting {operation}"
                        )
                except (TypeError, ValueError):
                    pass
            iterator = getattr(response, "iter_content", None)
            if callable(iterator):
                chunks: list[bytes] = []
                total = 0
                for chunk in iterator(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    data = bytes(chunk)
                    total += len(data)
                    if total > MAX_JSON_BYTES:
                        raise RiotMfaError(
                            f"Riot returned too much data while attempting {operation}"
                        )
                    chunks.append(data)
                body = b"".join(chunks)
            else:
                body = bytes(response.content)
                if len(body) > MAX_JSON_BYTES:
                    raise RiotMfaError(f"Riot returned too much data while attempting {operation}")
            return json.loads(body)
        except RiotMfaError:
            raise
        except requests.RequestException:
            raise RiotMfaError(f"Could not read Riot data while attempting {operation}") from None
        except (TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            raise RiotMfaError(f"Riot returned invalid data while attempting {operation}") from None
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _account_headers(csrf_token: str) -> dict[str, str]:
        csrf = _bounded_text(csrf_token, "CSRF token", max_length=4096)
        return {
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Content-Type": "application/json",
            "csrf-token": csrf,
            "Origin": RIOT_ACCOUNT_ORIGIN,
            "Pragma": "no-cache",
            "Priority": "u=1, i",
            "Referer": f"{RIOT_ACCOUNT_ORIGIN}/",
            "Sec-CH-UA": _BROWSER_CLIENT_HINT,
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": _BROWSER_USER_AGENT,
        }

    @staticmethod
    def _account_page_headers() -> dict[str, str]:
        return {
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Priority": "u=0, i",
            "Sec-CH-UA": _BROWSER_CLIENT_HINT,
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": _BROWSER_USER_AGENT,
        }

    @staticmethod
    def _read_account_page(response: _Response) -> str:
        try:
            headers = getattr(response, "headers", {})
            content_length = headers.get("Content-Length") if isinstance(headers, Mapping) else None
            if content_length is not None:
                try:
                    if int(content_length) > MAX_ACCOUNT_PAGE_BYTES:
                        raise RiotMfaError("Riot account page exceeded the size limit")
                except (TypeError, ValueError):
                    pass
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                data = bytes(chunk)
                total += len(data)
                if total > MAX_ACCOUNT_PAGE_BYTES:
                    raise RiotMfaError("Riot account page exceeded the size limit")
                chunks.append(data)
            return b"".join(chunks).decode("utf-8")
        except RiotMfaError:
            raise
        except requests.RequestException:
            raise RiotMfaError("Could not read the Riot account page") from None
        except (TypeError, UnicodeError):
            raise RiotMfaError("Riot returned an invalid account page") from None
        finally:
            response.close()

    def refresh_csrf_token(self, cookies: Mapping[str, str]) -> str:
        """Fetch the current meta CSRF token before any account mutation."""

        source_cookies = self._bind_account_session(cookies)
        try:
            response = self._session.request(
                "GET",
                RIOT_ACCOUNT_PAGE_URL,
                timeout=self._timeout,
                allow_redirects=False,
                stream=True,
                headers=self._account_page_headers(),
            )
        except requests.RequestException:
            raise RiotMfaError("Could not refresh the Riot account session") from None
        if not 200 <= response.status_code < 300:
            response.close()
            raise RiotMfaHttpError("account session refresh", response.status_code)
        effective_cookies = dict(source_cookies)
        try:
            response_cookies = getattr(response, "cookies", ())
            for cookie in response_cookies:
                name = getattr(cookie, "name", None)
                value = getattr(cookie, "value", None)
                if name not in effective_cookies:
                    continue
                effective_cookies[name] = _bounded_text(
                    value,
                    "account cookie",
                    max_length=4096,
                )
        except (RiotMfaError, TypeError):
            response.close()
            with suppress(RiotMfaError):
                self._clear_account_session()
            raise RiotMfaError("Riot returned invalid account session cookies") from None
        parser = _CsrfMetaParser()
        try:
            parser.feed(self._read_account_page(response))
            parser.close()
        except RiotMfaError:
            raise
        except Exception:
            raise RiotMfaError("Riot returned an invalid account page") from None
        if len(parser.values) != 1:
            raise RiotMfaError("Riot account session did not provide a CSRF token")
        csrf_token = _bounded_text(parser.values[0], "CSRF token", max_length=4096)
        self._replace_account_cookie_jar(effective_cookies)
        return csrf_token

    def _request_json(
        self,
        method: str,
        url: str,
        operation: str,
        **kwargs: Any,
    ) -> Any:
        try:
            response = self._session.request(
                method,
                url,
                timeout=self._timeout,
                allow_redirects=False,
                stream=True,
                **kwargs,
            )
        except requests.RequestException:
            raise RiotMfaError(f"Could not reach Riot while attempting {operation}") from None
        if not 200 <= response.status_code < 300:
            response.close()
            raise RiotMfaHttpError(operation, response.status_code)
        return self._read_json_body(response, operation)

    def fetch_identity(
        self,
        cookies: Mapping[str, str],
        csrf_token: str,
    ) -> RiotAccountIdentity:
        self._require_account_session(cookies)
        payload = self._request_json(
            "GET",
            RIOT_ACCOUNT_USER_URL,
            "account identity lookup",
            headers=self._account_headers(csrf_token),
        )
        if not isinstance(payload, Mapping):
            raise RiotMfaError("Riot returned invalid account identity data")
        alias = payload.get("alias")
        if not isinstance(alias, Mapping):
            raise RiotMfaError("Riot returned incomplete account identity data")
        return RiotAccountIdentity(
            puuid=_bounded_text(
                payload.get("puuid") or payload.get("sub"),
                "account identifier",
                max_length=MAX_IDENTITY_LENGTH,
            ),
            game_name=_bounded_text(alias.get("game_name"), "game name", max_length=128),
            tag_line=_bounded_text(alias.get("tag_line"), "tag line", max_length=128),
        )

    def fetch_factors(
        self,
        cookies: Mapping[str, str],
        csrf_token: str,
    ) -> tuple[RiotMfaFactor, ...]:
        self._require_account_session(cookies)
        payload = self._request_json(
            "GET",
            RIOT_MFA_FACTORS_URL,
            "MFA factor lookup",
            headers=self._account_headers(csrf_token),
        )
        raw_factors = payload if isinstance(payload, list) else None
        if raw_factors is None and isinstance(payload, Mapping):
            candidate = payload.get("factors")
            raw_factors = candidate if isinstance(candidate, list) else None
        if raw_factors is None or len(raw_factors) > 32:
            raise RiotMfaError("Riot returned invalid MFA factor data")
        factors: list[RiotMfaFactor] = []
        for value in raw_factors:
            if not isinstance(value, Mapping):
                raise RiotMfaError("Riot returned invalid MFA factor data")
            name = value.get("factor")
            status = value.get("status")
            if not isinstance(name, str) or not isinstance(status, str):
                raise RiotMfaError("Riot returned invalid MFA factor data")
            if len(name) > 64 or len(status) > 64:
                raise RiotMfaError("Riot returned invalid MFA factor data")
            factors.append(RiotMfaFactor(name=name, status=status))
        return tuple(factors)

    def enable_riot_mobile(
        self,
        cookies: Mapping[str, str],
        csrf_token: str,
    ) -> str:
        self._require_account_session(cookies)
        payload = self._request_json(
            "POST",
            RIOT_MOBILE_ENABLE_URL,
            "Riot Mobile authenticator enrollment",
            headers=self._account_headers(csrf_token),
        )
        if not isinstance(payload, Mapping):
            raise RiotMfaError("Riot returned invalid authenticator enrollment data")
        secret = payload.get("secret")
        if not isinstance(secret, str):
            raise RiotMfaError("Riot returned an invalid authenticator secret")
        try:
            return parse_seed(secret)
        except (TypeError, ValueError):
            raise RiotMfaError("Riot returned an invalid authenticator secret") from None

    def verify_riot_mobile(self, bearer_token: str, seed: str) -> None:
        token = _bounded_text(
            bearer_token,
            "authorization token",
            max_length=MAX_BEARER_TOKEN_LENGTH,
        )
        otp = generate_totp(seed)
        try:
            self._clear_account_session()
            response = self._session.request(
                "POST",
                RIOT_MOBILE_VERIFY_URL,
                timeout=self._timeout,
                allow_redirects=False,
                stream=True,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"device": "Peaks Desktop", "otp": otp},
            )
        except requests.RequestException:
            raise RiotMfaError("Could not reach Riot while verifying the authenticator") from None
        finally:
            otp = ""
        try:
            if not 200 <= response.status_code < 300:
                raise RiotMfaHttpError(
                    "Riot Mobile authenticator verification",
                    response.status_code,
                )
        finally:
            response.close()

    def close(self) -> None:
        with suppress(RiotMfaError):
            self._clear_account_session()
        if self._owns_session:
            self._session.close()


__all__ = [
    "RIOT_ACCOUNT_HOST",
    "RIOT_ACCOUNT_PAGE_URL",
    "RIOT_ACCOUNT_USER_URL",
    "RIOT_MFA_FACTORS_URL",
    "RIOT_MOBILE_ENABLE_URL",
    "RIOT_MOBILE_VERIFY_URL",
    "RiotAccountIdentity",
    "RiotMfaClient",
    "RiotMfaError",
    "RiotMfaFactor",
    "RiotMfaHttpError",
    "factor_is_enabled",
]
