"""Authenticated local Riot-client HTTP requests.

Riot's local endpoints use a self-signed certificate.  TLS verification is
disabled only for the literal loopback URL generated from a validated
lockfile; public requests are intentionally out of scope for this adapter.
"""

from __future__ import annotations

import base64
import json
import logging
import warnings
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import requests
from urllib3.exceptions import InsecureRequestWarning

from .discovery import RiotLockfile

requests_module: Any = requests

LOGGER = logging.getLogger(__name__)

# Local Riot endpoints return small JSON documents.  Keeping an explicit upper
# bound here prevents a compromised/local process from making the desktop app
# buffer an unbounded response before JSON parsing.
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class RiotClientError(RuntimeError):
    """Base exception for local-client failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail_code: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail_code = detail_code
        super().__init__(message)


class RiotClientUnavailable(RiotClientError):
    """Raised when a local request cannot reach Riot."""


def _endpoint_path(endpoint: str) -> str:
    if not isinstance(endpoint, str) or not endpoint:
        raise ValueError("endpoint must be a non-empty path")
    if not endpoint.startswith("/") or endpoint.startswith("//"):
        raise ValueError("endpoint must be an absolute local path")
    parsed = urlsplit(endpoint)
    if parsed.scheme or parsed.netloc:
        raise ValueError("absolute external URLs are not allowed")
    return endpoint


def _is_loopback_https(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme.lower() == "https" and parsed.hostname == "127.0.0.1"


def _allowlisted_error_detail(response: Any) -> str | None:
    """Classify one known Riot error without retaining arbitrary body text."""

    content = getattr(response, "content", None)
    if not isinstance(content, (bytes, bytearray, memoryview)):
        return None
    try:
        payload = json.loads(bytes(content).decode("utf-8"))
    except (UnicodeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    if (
        payload.get("errorCode") == "RPC_ERROR"
        and payload.get("message") == "Entitlements token is not ready yet"
    ):
        return "entitlements_not_ready"
    return None


def _read_bounded_response(response: Any, *, max_bytes: int) -> None:
    """Materialize at most ``max_bytes`` on a response and close its stream.

    ``requests`` responses are requested with ``stream=True`` so this helper
    can enforce the limit before JSON decoding.  Keeping the bytes on the
    response preserves the existing ``request() -> Response`` API while making
    the returned response safe to use after its underlying connection closes.
    Lightweight test doubles that only expose ``json()`` continue to work.
    """

    close = getattr(response, "close", None)
    try:
        headers = getattr(response, "headers", {})
        content_length = headers.get("Content-Length") if hasattr(headers, "get") else None
        if content_length is not None:
            try:
                if int(content_length) > max_bytes:
                    raise RiotClientError("Riot response exceeded the size limit")
            except (TypeError, ValueError):
                # A malformed length is not a reason to trust the response.
                # The streamed read below remains authoritative.
                pass

        iterator = getattr(response, "iter_content", None)
        if callable(iterator):
            chunks: list[bytes] = []
            total = 0
            try:
                for chunk in iterator(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    data = bytes(chunk)
                    total += len(data)
                    if total > max_bytes:
                        raise RiotClientError("Riot response exceeded the size limit")
                    chunks.append(data)
            except RiotClientError:
                raise
            except requests.RequestException as exc:
                raise RiotClientUnavailable("Riot response could not be read") from exc
            body = b"".join(chunks)
            # ``requests.Response.json`` reads ``_content``.  Setting these
            # fields is the supported way to retain a materialized response
            # after closing the streamed connection.
            response._content = body
            response._content_consumed = True
            return

        # Test doubles and alternate transports may expose an eagerly loaded
        # content property instead of a stream.  Do not invoke an arbitrary
        # ``json()`` method here: that could parse an unbounded body.
        content = getattr(response, "content", None)
        if isinstance(content, (bytes, bytearray, memoryview)):
            body = bytes(content)
            if len(body) > max_bytes:
                raise RiotClientError("Riot response exceeded the size limit")
            response._content = body
            response._content_consumed = True
    finally:
        if callable(close):
            close()


class RiotClientHTTP:
    """Small request wrapper that keeps lockfile credentials out of logs."""

    def __init__(
        self,
        lockfile: RiotLockfile,
        *,
        session: requests.Session | Any | None = None,
        timeout: float = 5.0,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        logger: logging.Logger | None = None,
    ) -> None:
        if not 0 < max_response_bytes <= 64 * 1024 * 1024:
            raise ValueError("max_response_bytes must be between 1 and 67108864")
        self.lockfile = lockfile
        self._session = session if session is not None else requests.Session()
        # Never honor ambient HTTP(S)_PROXY/NO_PROXY configuration for local
        # Riot traffic.  A proxy must not see lockfile-authenticated requests.
        if hasattr(self._session, "trust_env"):
            self._session.trust_env = False
        self.timeout = timeout
        self._max_response_bytes = int(max_response_bytes)
        self._logger = logger or LOGGER

    def close(self) -> None:
        """Close the underlying HTTP session."""

        close = getattr(self._session, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> RiotClientHTTP:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def _request_kwargs(self) -> dict[str, Any]:
        credentials = f"riot:{self.lockfile.password}".encode()
        token = base64.b64encode(credentials).decode("ascii")
        return {
            "headers": {
                "Authorization": f"Basic {token}",
                "Accept": "application/json",
            },
            "timeout": self.timeout,
            "stream": True,
            "allow_redirects": False,
            # The URL is generated below and verified before this exception.
            "verify": False,
        }

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        json_body: object | None = None,
        params: Mapping[str, object] | None = None,
    ) -> requests.Response:
        path = _endpoint_path(endpoint)
        url = f"{self.lockfile.base_url}{path}"
        if not _is_loopback_https(url):
            raise ValueError("local Riot requests must target https://127.0.0.1")
        kwargs = self._request_kwargs()
        diagnostic_method = (
            method.upper()
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
            else "unknown"
        )
        if json_body is not None:
            kwargs["json"] = json_body
        if params:
            kwargs["params"] = params
        try:
            # Riot's loopback service uses a self-signed certificate. Suppress
            # only that expected warning around the already hard-coded and
            # validated 127.0.0.1 request; remote transports keep verification.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", InsecureRequestWarning)
                response = self._session.request(method.upper(), url, **kwargs)
            _read_bounded_response(response, max_bytes=self._max_response_bytes)
        except RiotClientError:
            raise
        except Exception as exc:
            if requests is not None and not isinstance(exc, requests.RequestException):
                raise
            self._logger.debug("riot_local.request.failed method=%s", diagnostic_method)
            raise RiotClientUnavailable("Riot local client is unavailable") from exc
        # URL paths can contain player/match IDs; queries may contain credentials.
        self._logger.debug(
            "riot_local.request.complete method=%s status=%s",
            diagnostic_method,
            response.status_code,
        )
        return response

    def json(
        self,
        method: str,
        endpoint: str,
        *,
        json_body: object | None = None,
        params: Mapping[str, object] | None = None,
    ) -> Any:
        response = self.request(method, endpoint, json_body=json_body, params=params)
        try:
            response.raise_for_status()
        except Exception as exc:
            if requests is not None and not isinstance(exc, requests.HTTPError):
                raise
            raise RiotClientError(
                f"Riot local endpoint returned HTTP {response.status_code}",
                status_code=response.status_code,
                detail_code=_allowlisted_error_detail(response),
            ) from exc
        try:
            content = getattr(response, "content", None)
            if isinstance(content, (bytes, bytearray, memoryview)):
                return json.loads(bytes(content).decode("utf-8"))
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise RiotClientError("Riot local endpoint returned invalid JSON") from exc

    def get_json(self, endpoint: str, *, params: Mapping[str, object] | None = None) -> Any:
        return self.json("GET", endpoint, params=params)

    request_json = json


RiotClient = RiotClientHTTP
LocalRiotClient = RiotClientHTTP
