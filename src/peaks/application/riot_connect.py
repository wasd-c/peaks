"""Explicitly approved Riot QR-login actions.

This module is intentionally small and does not discover accounts, launch a
client, or approve anything by itself. QR approval requires a fresh
``session_info`` proof bound to the same selected-account bearer session.
Authenticator seeds are deliberately not accepted here: Riot's TOTP
verification route handles a different MFA challenge type, not Riot Client QR
sessions. Credentials are accepted from the application's secret store and are
never included in representations, logs, or errors.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urlparse

from peaks.adapters.riot.client import requests_module
from peaks.adapters.riot.qr import QRLoginPayload, QRParseError, parse_qr_text

LOGGER = logging.getLogger(__name__)

AUTHENTICATE_ORIGIN = "https://authenticate.riotgames.com"
QR_SESSION_INFO_PATH = "/api/v1/session/info"
QR_SESSION_AUTH_PATH = "/api/v1/session/authentication"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_SESSION_TTL_SECONDS = 60.0
DEFAULT_MAX_RESPONSE_BYTES = 512 * 1024
MAX_PENDING_SESSION_PROOFS = 128


class RiotConnectError(RuntimeError):
    """Base class for safe QR-connect failures."""


class ApprovalRequired(RiotConnectError):
    """Raised when an operation was not explicitly approved by the user."""


class SessionDetailsRequired(RiotConnectError):
    """Raised when Riot has not freshly described the QR login request."""


class SessionExpired(RiotConnectError):
    """Raised when the confirmation window for a QR login has elapsed."""


class AccountBindingError(RiotConnectError):
    """Raised when the approval credentials differ from the selected account proof."""


class CredentialsUnavailable(RiotConnectError):
    """Raised when the selected owned account has no usable credential path."""


class RiotConnectTransportError(RiotConnectError):
    """Raised when Riot authentication cannot be reached or parsed."""


class RiotConnectHTTPError(RiotConnectError):
    """Raised for a non-success Riot authentication response."""

    def __init__(self, operation: str, status_code: int) -> None:
        self.operation = operation
        self.status_code = status_code
        super().__init__(f"Riot {operation} request failed (HTTP {status_code})")


def _safe_opaque(value: str, field_name: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    value = value.strip()
    if not value or len(value) > max_length or any(ord(char) < 0x20 for char in value):
        raise ValueError(f"{field_name} is invalid")
    return value


@dataclass(frozen=True, slots=True)
class OwnedAccountCredentials:
    """Secrets retrieved for one owned Riot account.

    A Riot Client QR challenge is approved only with the short-lived access
    token minted from that account's identity-bound reusable session.
    """

    puuid: str | None = None
    access_token: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        puuid = self.puuid
        if puuid is not None:
            object.__setattr__(self, "puuid", _safe_opaque(puuid, "puuid", max_length=256))
        if self.access_token is not None:
            object.__setattr__(
                self,
                "access_token",
                _safe_opaque(self.access_token, "access token", max_length=4096),
            )
        if not self.puuid or not self.access_token:
            raise CredentialsUnavailable("owned account has no reusable Riot session")


@dataclass(frozen=True, slots=True)
class QRSessionDetails:
    """The non-sensitive fields needed for the confirmation prompt."""

    suuid: str
    cluster: str
    location: str | None = None
    device: str | None = None
    requested: str | None = None

    @classmethod
    def from_payload(cls, qr: QRLoginPayload, payload: object) -> QRSessionDetails:
        if not isinstance(payload, Mapping):
            return cls(qr.suuid, qr.cluster)

        def text(*keys: str) -> str | None:
            for key in keys:
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:256]
            return None

        location = text("location", "geolocation", "geo")
        if location is None:
            geo = payload.get("geolocation")
            if isinstance(geo, Mapping):
                city = geo.get("city") if isinstance(geo.get("city"), str) else None
                country = geo.get("country") if isinstance(geo.get("country"), str) else None
                location = ", ".join(part for part in (city, country) if part) or None
        return cls(
            qr.suuid,
            qr.cluster,
            location,
            text("device", "device_name", "client", "client_name"),
            text("requested", "requested_at", "created_at", "timestamp"),
        )


@dataclass(frozen=True, slots=True)
class QRApprovalResult:
    """Sanitized outcome of one approved login action."""

    method: str
    status_code: int


@dataclass(frozen=True, slots=True)
class _SessionProof:
    """Private, short-lived authorization proof for one QR request.

    The proof is deliberately not returned to QML or serialized.  The QR
    payload identifies an unclaimed login request; the authenticated session
    used to inspect it identifies the selected account that may approve it.
    Both the selected PUUID and bearer-token fingerprint must agree at
    approval time.
    """

    details: QRSessionDetails
    selected_account_identity: str
    access_token_fingerprint: bytes = field(repr=False)
    expires_at: float


def _token_fingerprint(access_token: str) -> bytes:
    """Return a non-reversible binding for a high-entropy bearer token."""

    return hashlib.sha256(access_token.encode("utf-8")).digest()


def _coerce_qr(value: QRLoginPayload | str | tuple[str, str]) -> QRLoginPayload:
    if isinstance(value, QRLoginPayload):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        try:
            return parse_qr_text(f"{value[0]}:{value[1]}")
        except (QRParseError, TypeError) as exc:
            raise QRParseError("invalid QR payload") from exc
    if isinstance(value, str):
        return parse_qr_text(value)
    raise QRParseError("invalid QR payload")


class RiotQRApprovalService:
    """Confirmation-gated Riot QR authentication service.

    The transport is injected so unit tests can use fixtures and the desktop
    application can reuse its configured HTTP session.  Redirects are always
    disabled and external TLS verification is always enabled.
    """

    def __init__(
        self,
        *,
        session: Any | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        session_ttl: float = DEFAULT_SESSION_TTL_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        clock: Any = time.monotonic,
        logger: logging.Logger | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if session_ttl <= 0:
            raise ValueError("session_ttl must be positive")
        if not 0 < max_response_bytes <= 4 * 1024 * 1024:
            raise ValueError("max_response_bytes must be between 1 and 4194304")
        session_value: Any = session
        if session_value is None and requests_module is not None:
            session_value = requests_module.Session()
        if session_value is None:
            raise RiotConnectTransportError("HTTP transport is unavailable")
        self._session = session_value
        if hasattr(self._session, "trust_env"):
            self._session.trust_env = False
        self.timeout = float(timeout)
        self.session_ttl = float(session_ttl)
        self.max_response_bytes = int(max_response_bytes)
        if not callable(clock):
            raise ValueError("clock must be callable")
        self._clock = clock
        self._logger = logger or LOGGER
        self._proof_lock = threading.Lock()
        self._session_proofs: dict[tuple[str, str], _SessionProof] = {}

    @staticmethod
    def _url(path: str, *, query: dict[str, str] | None = None) -> str:
        # Keep the origin literal and HTTPS-only.  ``_request`` never follows
        # redirects, so a compromised DNS/proxy cannot move approval to an
        # attacker-controlled host through a 30x response.
        origin = urlparse(AUTHENTICATE_ORIGIN)
        if (
            origin.scheme.lower() != "https"
            or origin.hostname is None
            or origin.hostname.lower() != "authenticate.riotgames.com"
            or origin.port is not None
            or origin.path not in {"", "/"}
            or origin.username
            or origin.password
        ):
            raise ValueError("Riot authentication origin is not allowlisted")
        if path not in {QR_SESSION_INFO_PATH, QR_SESSION_AUTH_PATH}:
            raise ValueError("Riot authentication path is not allowlisted")
        if query:
            return f"{AUTHENTICATE_ORIGIN}{path}?{urlencode(query)}"
        return f"{AUTHENTICATE_ORIGIN}{path}"

    @staticmethod
    def _headers(access_token: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Peaks/0.1 Riot QR approval",
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        return headers

    def _request(
        self,
        operation: str,
        path: str,
        *,
        access_token: str | None = None,
        query: dict[str, str] | None = None,
        body: dict[str, object] | None = None,
    ) -> Any:
        url = self._url(path, query=query)
        diagnostic_operation = {
            "session info": "session_info",
            "session approval": "session_approval",
        }.get(operation, "unknown")
        try:
            response = self._session.request(
                "POST" if body is not None else "GET",
                url,
                headers=self._headers(access_token),
                json=body,
                timeout=self.timeout,
                allow_redirects=False,
                verify=True,
                stream=True,
            )
        except Exception as exc:
            self._logger.debug("riot_qr.request.failed operation=%s", diagnostic_operation)
            raise RiotConnectTransportError("Riot authentication is unavailable") from exc
        status_code = getattr(response, "status_code", None)
        if not isinstance(status_code, int) or status_code < 200 or status_code >= 300:
            self._logger.debug(
                "riot_qr.request.rejected operation=%s status=%s", diagnostic_operation, status_code
            )
            close = getattr(response, "close", None)
            if callable(close):
                close()
            raise RiotConnectHTTPError(
                operation, status_code if isinstance(status_code, int) else 0
            )
        return response

    def _read_json(self, response: Any) -> object:
        """Read one small JSON response and always release the connection."""

        try:
            headers = getattr(response, "headers", {})
            content_length = headers.get("Content-Length") if isinstance(headers, Mapping) else None
            if content_length is not None:
                try:
                    if int(content_length) > self.max_response_bytes:
                        raise RiotConnectTransportError(
                            "Riot session details exceeded the size limit"
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
                    if total > self.max_response_bytes:
                        raise RiotConnectTransportError(
                            "Riot session details exceeded the size limit"
                        )
                    chunks.append(data)
                try:
                    return json.loads(b"".join(chunks).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RiotConnectTransportError(
                        "Riot returned invalid session details"
                    ) from exc
            # Lightweight injected transports used by tests may expose only
            # ``json()``; production requests.Response uses iter_content above.
            return response.json()
        except RiotConnectTransportError:
            raise
        except Exception as exc:
            raise RiotConnectTransportError("Riot returned invalid session details") from exc
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def close(self) -> None:
        with self._proof_lock:
            self._session_proofs.clear()
        # requests.Session owns a CookieJar.  Clear it before closing so a
        # lock/reset cannot leave imported Riot cookies resident in memory or
        # available to a reused transport.  Test transports may not expose a
        # jar, and custom jars may reject clear(), so cleanup remains best
        # effort while proof invalidation above is unconditional.
        cookies = getattr(self._session, "cookies", None)
        clear_cookies = getattr(cookies, "clear", None)
        if callable(clear_cookies):
            try:
                clear_cookies()
            except Exception:
                self._logger.debug("riot_qr.cookie_cleanup.failed")
        close = getattr(self._session, "close", None)
        if callable(close):
            close()

    def session_info(
        self,
        qr: QRLoginPayload | str | tuple[str, str],
        *,
        access_token: str,
        selected_account_puuid: str,
    ) -> QRSessionDetails:
        """Read pending session details for a confirmation prompt.

        This method is read-only; it cannot approve a login. Riot's QR is an
        unclaimed client challenge, so its response is not treated as the
        identity that owns the challenge. The trusted caller supplies the
        PUUID it already verified for ``access_token`` through Riot userinfo.
        """

        payload = _coerce_qr(qr)
        token = _safe_opaque(access_token, "access token", max_length=4096)
        selected_identity = _safe_opaque(
            selected_account_puuid,
            "selected account PUUID",
            max_length=256,
        )
        response = self._request(
            "session info",
            QR_SESSION_INFO_PATH,
            access_token=token,
            query={"suuid": payload.suuid, "cluster": payload.cluster},
        )
        body = self._read_json(response)
        details = QRSessionDetails.from_payload(payload, body)
        # Keep the authority private. The UI receives only display-safe
        # challenge details. Approval later requires the same caller-verified
        # selected identity, the same bearer token, and a fresh local window.
        now = self._clock()
        proof = _SessionProof(
            details=details,
            selected_account_identity=selected_identity,
            access_token_fingerprint=_token_fingerprint(token),
            expires_at=now + self.session_ttl,
        )
        with self._proof_lock:
            # QR scans are user-controlled input.  Prune abandoned requests
            # and cap the map so a stream of unique QR values cannot grow the
            # approval service without bound.
            for key, pending in tuple(self._session_proofs.items()):
                if pending.expires_at <= now:
                    del self._session_proofs[key]
            if len(self._session_proofs) >= MAX_PENDING_SESSION_PROOFS:
                oldest_key = min(
                    self._session_proofs,
                    key=lambda key: self._session_proofs[key].expires_at,
                )
                del self._session_proofs[oldest_key]
            self._session_proofs[payload.as_tuple()] = proof
        return details

    def approve(
        self,
        qr: QRLoginPayload | str | tuple[str, str],
        credentials: OwnedAccountCredentials,
        *,
        user_approved: bool,
    ) -> QRApprovalResult:
        """Approve exactly one QR session after an explicit user confirmation."""

        if user_approved is not True:
            raise ApprovalRequired("explicit user approval is required")
        if not isinstance(credentials, OwnedAccountCredentials):
            raise CredentialsUnavailable("owned account credentials are required")
        payload = _coerce_qr(qr)
        proof = self._consume_session_proof(payload)
        if not credentials.puuid or proof.selected_account_identity != credentials.puuid:
            raise AccountBindingError("selected account changed before QR approval")
        if not credentials.access_token or not hmac.compare_digest(
            proof.access_token_fingerprint,
            _token_fingerprint(credentials.access_token),
        ):
            raise AccountBindingError("selected Riot session changed before QR approval")
        return self._approve_with_access_token(payload, credentials.access_token)

    def _consume_session_proof(self, qr: QRLoginPayload) -> _SessionProof:
        """Atomically consume the one-shot proof for ``qr``.

        It is removed before the network approval request.  A timeout or
        server error therefore cannot be retried through this service with a
        stale confirmation; the user must scan and verify a fresh QR request.
        """

        with self._proof_lock:
            proof = self._session_proofs.pop(qr.as_tuple(), None)
        if proof is None:
            raise SessionDetailsRequired("fresh Riot session details are required before approval")
        if self._clock() >= proof.expires_at:
            raise SessionExpired("the Riot QR confirmation has expired")
        return proof

    def _approve_with_access_token(self, qr: QRLoginPayload, access_token: str) -> QRApprovalResult:
        response = self._request(
            "session approval",
            QR_SESSION_AUTH_PATH,
            access_token=access_token,
            body={"suuid": qr.suuid, "cluster": qr.cluster, "remember": False},
        )
        try:
            return QRApprovalResult("session", response.status_code)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    # Explicit aliases make the integration intent clear while retaining the
    # same mandatory ``user_approved`` gate on every approval entry point.
    get_session_info = session_info
    approve_qr = approve


# Short aliases for callers that prefer a product-oriented name.
RiotConnectService = RiotQRApprovalService
QRApprovalService = RiotQRApprovalService
AccountSecrets = OwnedAccountCredentials
