"""Import the currently signed-in Riot Client session on Windows.

Riot does not publish this interface as a supported desktop integration.  The
Riot Client private settings YAML and the ``ritoplus`` authorization request
used here are private, undocumented interfaces and can change or stop working
at any time. Keep local settings imports behind an explicit user action;
already saved authorizations may be renewed while the vault is unlocked.
This adapter is not a replacement for Riot-approved RSO.

Only a bounded, exact path is read.  Only the small cookie allowlist needed by
the authorization request is returned. Access tokens remain memory-only.
Offline authorization additionally returns a refresh token for encrypted,
identity-bound storage. All credentials stay out of representations and logs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import platform as _platform
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.parse import parse_qs, urlsplit

import requests
import yaml  # type: ignore[import-untyped]
from yaml.events import (  # type: ignore[import-untyped]
    AliasEvent,
    CollectionStartEvent,
    DocumentStartEvent,
    MappingEndEvent,
    MappingStartEvent,
    ScalarEvent,
    SequenceEndEvent,
)

from peaks.domain.regions import normalize_league_region, normalize_valorant_region

LOGGER = logging.getLogger(__name__)

RIOT_AUTHORIZATION_URL = "https://auth.riotgames.com/api/v1/authorization"
RIOT_USERINFO_URL = "https://auth.riotgames.com/userinfo"
RIOT_TOKEN_URL = "https://auth.riotgames.com/token"
RIOT_VALORANT_REGION_URL = "https://riot-geo.pas.si.riotgames.com/pas/v1/product/valorant"
RIOT_CLIENT_SETTINGS_NAME = "RiotGamesPrivateSettings.yaml"
RIOT_CLIENT_SETTINGS_RELATIVE_PATH = Path(
    "Riot Games", "Riot Client", "Data", RIOT_CLIENT_SETTINGS_NAME
)

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_SETTINGS_BYTES = 1 * 1024 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 512 * 1024
MAX_COOKIE_VALUE_LENGTH = 4096
MAX_PUUID_LENGTH = 256
MAX_ACCESS_TOKEN_LENGTH = 8192
MAX_REFRESH_TOKEN_LENGTH = 16384
# The private settings file is expected to contain a small cookie list.  Keep
# parsing limits separate from the byte limit: a small YAML document can still
# contain a very large alias-expanded graph or deeply nested collections.
MAX_YAML_DEPTH = 64
MAX_YAML_NODES = 4096
MAX_YAML_COLLECTION_ITEMS = 1024

ALLOWED_COOKIE_NAMES = frozenset(
    {"ssid", "clid", "csid", "tdid", "sub", "ccid", "asid"}
)
_TOKEN_RE = re.compile(r"^[A-Za-z0-9._~+/=-]+$")
_ACCESS_TOKEN_RE = re.compile(r"^[A-Za-z0-9._~-]+$")

# This exact body is the private ``ritoplus`` session.auth flow used by the
# Riot Client.  Do not add user-controlled URLs, scopes, or client IDs here.
_AUTHORIZATION_BODY: dict[str, str] = {
    "client_id": "ritoplus",
    "nonce": "1",
    "redirect_uri": "http://localhost/redirect",
    "response_type": "token id_token",
    "scope": "openid account link ban lol summoner offline_access "
    "riot://riot.authenticator/session.auth",
}


class RiotSessionImportError(RuntimeError):
    """Base class for safe current-session import failures."""


class UnsupportedPlatformError(RiotSessionImportError):
    """Raised when the Windows-only importer is used elsewhere."""


class SessionSettingsError(RiotSessionImportError):
    """Raised when the Riot Client private settings are unavailable/invalid."""


class SessionAuthorizationError(RiotSessionImportError):
    """Raised when Riot rejects or cannot parse the private authorization flow."""


class SessionReauthenticationRequired(SessionAuthorizationError):
    """Riot explicitly requires interactive sign-in or an MFA challenge."""

    def __init__(self, response_type: str) -> None:
        self.response_type = "multifactor" if response_type == "multifactor" else "auth"
        super().__init__("Riot requires sign-in again for this saved session")


class SessionAuthorizationHTTPError(SessionAuthorizationError):
    """Raised for a non-success response from the fixed Riot endpoint."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"Riot session authorization failed (HTTP {status_code})")


@dataclass(frozen=True, slots=True)
class AuthenticatedRiotIdentity:
    """Non-sensitive identity fields returned by Riot's userinfo endpoint."""

    puuid: str = field(repr=False)
    game_name: str | None = field(default=None, repr=False)
    tag_line: str | None = field(default=None, repr=False)
    league_region: str | None = None
    valorant_region: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "league_region", normalize_league_region(self.league_region))
        object.__setattr__(self, "valorant_region", normalize_valorant_region(self.valorant_region))
        object.__setattr__(
            self, "puuid", _validate_opaque(self.puuid, "PUUID", max_length=MAX_PUUID_LENGTH)
        )
        for field_name in ("game_name", "tag_line"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _validate_opaque(value, field_name, max_length=128),
                )


@dataclass(frozen=True, slots=True)
class RefreshedRiotAuthorization:
    """Fresh access token, optional refresh token and reusable cookie rotations.

    Riot can rotate renewal credentials while minting an access token.
    All credentials stay out of representations and the cookie mapping
    is copied into a read-only proxy before it leaves this adapter.
    """

    access_token: str = field(repr=False)
    cookies: Mapping[str, str] = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        token = _validate_access_token(self.access_token)
        if not isinstance(self.cookies, Mapping):
            raise ValueError("cookies must be a mapping")
        copied: dict[str, str] = {}
        for name, value in self.cookies.items():
            if name not in ALLOWED_COOKIE_NAMES:
                raise ValueError("cookies contain an unsupported name")
            copied[name] = _validate_cookie_value(value, name)
        if self.refresh_token is not None:
            _validate_opaque(self.refresh_token, "refresh token", max_length=MAX_REFRESH_TOKEN_LENGTH)
        if "ssid" not in copied and self.refresh_token is None:
            raise ValueError("cookies require ssid")
        object.__setattr__(self, "access_token", token)
        object.__setattr__(self, "cookies", MappingProxyType(copied))


@dataclass(frozen=True, slots=True)
class ImportedRiotSession:
    """Sanitized result of importing one active Riot Client session.

    All credentials are hidden from ``repr``. The cookie mapping is copied
    into a read-only proxy before the result is exposed to callers.
    """

    puuid: str = field(repr=False)
    cookies: Mapping[str, str] = field(repr=False)
    access_token: str = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        puuid = _validate_opaque(self.puuid, "PUUID", max_length=MAX_PUUID_LENGTH)
        token = _validate_access_token(self.access_token)
        if self.refresh_token is not None:
            _validate_opaque(self.refresh_token, "refresh token", max_length=MAX_REFRESH_TOKEN_LENGTH)
        if not isinstance(self.cookies, Mapping):
            raise ValueError("cookies must be a mapping")
        copied: dict[str, str] = {}
        for name, value in self.cookies.items():
            if name not in ALLOWED_COOKIE_NAMES:
                raise ValueError("cookies contain an unsupported name")
            copied[name] = _validate_cookie_value(value, name)
        if "ssid" not in copied:
            raise ValueError("cookies require ssid")
        if "sub" in copied and copied["sub"] != puuid:
            raise ValueError("cookie subject does not match PUUID")
        object.__setattr__(self, "puuid", puuid)
        object.__setattr__(self, "access_token", token)
        object.__setattr__(self, "cookies", MappingProxyType(copied))


def _validate_opaque(value: object, label: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise ValueError(f"{label} is invalid")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError(f"{label} is invalid")
    return value


def _validate_cookie_value(value: object, name: str) -> str:
    value_text = _validate_opaque(value, f"cookie {name}", max_length=MAX_COOKIE_VALUE_LENGTH)
    # A cookie value will be handed to requests as a Cookie value.  Reject
    # separators even though control-character validation already blocks the
    # usual header-injection cases.
    if ";" in value_text or "," in value_text:
        raise ValueError(f"cookie {name} is invalid")
    if not _TOKEN_RE.fullmatch(value_text):
        raise ValueError(f"cookie {name} is invalid")
    return value_text


def _validate_access_token(value: object) -> str:
    token = _validate_opaque(value, "access token", max_length=MAX_ACCESS_TOKEN_LENGTH)
    if not _ACCESS_TOKEN_RE.fullmatch(token):
        raise ValueError("access token is invalid")
    return token


@dataclass(slots=True)
class _YamlCollectionState:
    kind: str
    child_count: int = 0


def _validate_yaml_shape(text: str) -> None:
    """Validate YAML parser events before PyYAML constructs Python objects.

    ``yaml.safe_load`` blocks Python-object constructors, but it still accepts
    anchors and aliases and has no application-specific depth or collection
    limits.  The Riot settings file only needs ordinary scalars, sequences,
    and mappings, so reject anchors/aliases and bound the event stream first.
    The production path runs this before ``yaml.safe_load``.  An explicitly
    injected loader remains untouched so tests and fixtures can provide their
    own deterministic parser behavior.
    """

    depth = 0
    node_count = 0
    document_count = 0
    # Mapping children alternate between keys and values, while sequence
    # children are individual values.
    collections: list[_YamlCollectionState] = []

    for event in yaml.parse(text, Loader=yaml.SafeLoader):
        if isinstance(event, DocumentStartEvent):
            document_count += 1
            if document_count > 1:
                raise yaml.YAMLError("multiple YAML documents are not supported")

        if isinstance(event, AliasEvent) or getattr(event, "anchor", None) is not None:
            raise yaml.YAMLError("YAML anchors and aliases are not supported")

        if isinstance(event, (CollectionStartEvent,)):
            node_count += 1
            if node_count > MAX_YAML_NODES:
                raise yaml.YAMLError("YAML document contains too many nodes")
            if collections:
                collections[-1].child_count += 1
            depth += 1
            if depth > MAX_YAML_DEPTH:
                raise yaml.YAMLError("YAML document is too deeply nested")
            kind = "mapping" if isinstance(event, MappingStartEvent) else "sequence"
            collections.append(_YamlCollectionState(kind))
            continue

        # Scalar events are the remaining YAML nodes.  Count them before the
        # loader can materialize strings or add them to a collection.
        if isinstance(event, ScalarEvent):
            node_count += 1
            if node_count > MAX_YAML_NODES:
                raise yaml.YAMLError("YAML document contains too many nodes")
            if collections:
                collections[-1].child_count += 1

        if isinstance(event, (MappingEndEvent, SequenceEndEvent)):
            if not collections:
                raise yaml.YAMLError("invalid YAML collection boundaries")
            collection = collections.pop()
            limit = MAX_YAML_COLLECTION_ITEMS * (2 if collection.kind == "mapping" else 1)
            if collection.child_count > limit:
                raise yaml.YAMLError("YAML collection contains too many items")
            depth -= 1

    if document_count != 1:
        raise yaml.YAMLError("YAML document is empty")


def _as_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SessionSettingsError(f"Riot session settings have an invalid {label} section")
    return value


def _is_link_like(path: Path) -> bool:
    """Return whether a path is a symlink or Windows junction/reparse point."""

    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(callable(is_junction) and is_junction())


def _extract_cookie_data(document: object) -> tuple[str, dict[str, str]]:
    """Extract only the allowlisted cookies from the known YAML shape."""

    root = _as_mapping(document, "root")
    riot_login = _as_mapping(root.get("riot-login"), "riot-login")
    persist = _as_mapping(riot_login.get("persist"), "persist")
    session = _as_mapping(persist.get("session"), "session")
    entries = session.get("cookies")
    if not isinstance(entries, list) or not entries:
        raise SessionSettingsError("Riot session settings contain no session cookies")

    cookies: dict[str, str] = {}
    for entry in entries:
        item = _as_mapping(entry, "cookie")
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or name not in ALLOWED_COOKIE_NAMES:
            # Unknown cookies can be added by Riot over time.  They are
            # intentionally ignored rather than copied into the auth request.
            continue
        if name in cookies:
            raise SessionSettingsError("Riot session settings contain duplicate cookies")
        try:
            cookies[name] = _validate_cookie_value(value, name)
        except ValueError as exc:
            raise SessionSettingsError("Riot session settings contain an invalid cookie") from exc

    if "ssid" not in cookies:
        raise SessionSettingsError("Riot session settings require an ssid cookie")

    # ``sub`` is the normal subject cookie.  A few client builds have exposed
    # the same subject in session.puuid, so accept that explicit field only as a
    # fallback and never copy it into the cookie jar.
    puuid = cookies.get("sub")
    if puuid is None:
        candidate = session.get("puuid")
        if candidate is None:
            candidate = persist.get("puuid")
        try:
            puuid = _validate_opaque(candidate, "PUUID", max_length=MAX_PUUID_LENGTH)
        except ValueError as exc:
            raise SessionSettingsError("Riot session settings require a sub or PUUID") from exc
    if puuid is None:
        raise SessionSettingsError("Riot session settings require a sub or PUUID")
    if "sub" in cookies and puuid != cookies["sub"]:
        raise SessionSettingsError("Riot session subject is inconsistent")
    return puuid, cookies


class RiotSessionImporter:
    """Windows-only importer for the active Riot Client session."""

    def __init__(
        self,
        *,
        session: Any | None = None,
        platform_name: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_settings_bytes: int = DEFAULT_MAX_SETTINGS_BYTES,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        yaml_loader: Any = yaml.safe_load,
        logger: logging.Logger | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if not 0 < max_settings_bytes <= DEFAULT_MAX_SETTINGS_BYTES:
            raise ValueError("max_settings_bytes must be between 1 and 1048576")
        if not 0 < max_response_bytes <= 4 * 1024 * 1024:
            raise ValueError("max_response_bytes must be between 1 and 4194304")
        if not callable(yaml_loader):
            raise ValueError("yaml_loader must be callable")
        self._session = session if session is not None else requests.Session()
        if hasattr(self._session, "trust_env"):
            self._session.trust_env = False
        self._platform_name = platform_name
        self._env = env
        self.timeout = float(timeout)
        self.max_settings_bytes = int(max_settings_bytes)
        self.max_response_bytes = int(max_response_bytes)
        self._yaml_loader = yaml_loader
        self._logger = logger or LOGGER
        # One authorization only; ID and geo tokens never leave this adapter.
        self._region_authorization: tuple[bytes, str] | None = None

    @property
    def supported(self) -> bool:
        return (self._platform_name or _platform.system()).casefold() == "windows"

    def settings_path(self) -> Path:
        """Return the exact private settings path after boundary validation."""

        self._logger.info("riot_session.settings.validate_start supported=%s", self.supported)
        if not self.supported:
            raise UnsupportedPlatformError("Riot Client session import requires Windows")
        environment = self._env
        if environment is None:
            import os

            environment = os.environ
        local_app_data = environment.get("LOCALAPPDATA")
        if not isinstance(local_app_data, str) or not local_app_data:
            raise SessionSettingsError("LOCALAPPDATA is unavailable")
        local_root = Path(local_app_data)
        if not local_root.is_absolute():
            raise SessionSettingsError("LOCALAPPDATA is invalid")
        if _is_link_like(local_root):
            raise SessionSettingsError("LOCALAPPDATA is invalid")
        try:
            local_resolved = local_root.resolve(strict=True)
            riot_root = (local_resolved / "Riot Games").resolve(strict=False)
            candidate = local_resolved / RIOT_CLIENT_SETTINGS_RELATIVE_PATH
            parent = local_resolved
            for part in RIOT_CLIENT_SETTINGS_RELATIVE_PATH.parts[:-1]:
                parent = parent / part
                if _is_link_like(parent):
                    raise SessionSettingsError("Riot Client settings path is outside LOCALAPPDATA")
            resolved = candidate.resolve(strict=True)
        except SessionSettingsError:
            raise
        except (OSError, RuntimeError) as exc:
            raise SessionSettingsError("Riot Client settings path is unavailable") from exc
        try:
            resolved.relative_to(riot_root)
        except ValueError as exc:
            raise SessionSettingsError("Riot Client settings path is outside LOCALAPPDATA") from exc
        if _is_link_like(candidate) or not candidate.is_file():
            raise SessionSettingsError("Riot Client settings file is unavailable")
        try:
            if candidate.stat().st_size > self.max_settings_bytes:
                raise SessionSettingsError("Riot Client settings file is too large")
        except OSError as exc:
            raise SessionSettingsError("Riot Client settings file is unavailable") from exc
        self._logger.info("riot_session.settings.available")
        return candidate

    def _read_cookies(self) -> tuple[str, dict[str, str]]:
        self._logger.info("riot_session.cookies.read_start")
        path = self.settings_path()
        try:
            with path.open("rb") as handle:
                raw = handle.read(self.max_settings_bytes + 1)
        except (OSError, ValueError) as exc:
            raise SessionSettingsError("Riot Client settings file is unavailable") from exc
        if len(raw) > self.max_settings_bytes:
            raise SessionSettingsError("Riot Client settings file is too large")
        try:
            text = raw.decode("utf-8-sig")
            # ``yaml.safe_load`` is the production default.  Keep callers'
            # injectable loaders usable for deterministic tests and fixtures;
            # production callers cannot replace this dependency through the
            # file contents or any user-controlled value.
            if self._yaml_loader is yaml.safe_load:
                _validate_yaml_shape(text)
            document = self._yaml_loader(text)
        except (UnicodeError, yaml.YAMLError, RecursionError, ValueError, TypeError) as exc:
            raise SessionSettingsError("Riot Client settings are invalid") from exc
        puuid, cookies = _extract_cookie_data(document)
        self._logger.info("riot_session.cookies.read_complete cookie_count=%s", len(cookies))
        return puuid, cookies

    def _read_response_body(self, response: Any) -> bytes:
        try:
            headers = getattr(response, "headers", {})
            content_length = headers.get("Content-Length") if isinstance(headers, Mapping) else None
            if content_length is not None:
                try:
                    if int(content_length) > self.max_response_bytes:
                        raise SessionAuthorizationError("Riot authorization response is too large")
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
                        raise SessionAuthorizationError("Riot authorization response is too large")
                    chunks.append(data)
                return b"".join(chunks)
            content = getattr(response, "content", None)
            if isinstance(content, (bytes, bytearray, memoryview)):
                body = bytes(content)
                if len(body) > self.max_response_bytes:
                    raise SessionAuthorizationError("Riot authorization response is too large")
                return body
            raise SessionAuthorizationError("Riot returned an unreadable authorization response")
        except SessionAuthorizationError:
            raise
        except Exception as exc:
            raise SessionAuthorizationError("Riot authorization response could not be read") from exc
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _token_from_uri(uri: object) -> str:
        if not isinstance(uri, str) or len(uri) > 32 * 1024:
            raise SessionAuthorizationError("Riot returned an invalid authorization URI")
        parsed = urlsplit(uri)
        if (
            parsed.scheme.lower() != "http"
            or parsed.hostname is None
            or parsed.hostname.casefold() != "localhost"
            or parsed.port is not None
            or parsed.username
            or parsed.password
            or parsed.path != "/redirect"
            or parsed.query
            or not parsed.fragment
        ):
            raise SessionAuthorizationError("Riot returned an invalid authorization URI")
        try:
            fragment = parse_qs(parsed.fragment, keep_blank_values=True, strict_parsing=True)
        except ValueError as exc:
            raise SessionAuthorizationError("Riot returned an invalid authorization URI") from exc
        values = fragment.get("access_token", [])
        if len(values) != 1:
            raise SessionAuthorizationError("Riot authorization token is missing")
        try:
            return _validate_access_token(values[0])
        except ValueError as exc:
            raise SessionAuthorizationError("Riot authorization token is invalid") from exc

    @staticmethod
    def _cookie_applies_to_authorization(cookie: object) -> bool:
        """Return whether a response cookie applies to the fixed auth endpoint."""

        domain = str(getattr(cookie, "domain", "") or "").lstrip(".").casefold()
        auth_host = "auth.riotgames.com"
        if domain and domain != auth_host and not auth_host.endswith(f".{domain}"):
            return False

        path = str(getattr(cookie, "path", "") or "/")
        target = "/api/v1/authorization"
        if not path.startswith("/") or not target.startswith(path):
            return False
        if target != path and not path.endswith("/") and target[len(path) : len(path) + 1] != "/":
            return False

        expired = getattr(cookie, "is_expired", None)
        return not (callable(expired) and expired())

    def _response_cookie_updates(self, response: object) -> dict[str, str]:
        """Extract only effective allowlisted rotations from one Riot response."""

        jar = getattr(response, "cookies", None)
        if jar is None:
            return {}
        try:
            candidates = list(jar)
        except (TypeError, ValueError):
            return {}

        # Apply broad-domain/path cookies first so the most specific cookie for
        # this exact endpoint wins, matching normal browser selection.
        candidates.sort(
            key=lambda cookie: (
                len(str(getattr(cookie, "domain", "") or "").lstrip(".")),
                len(str(getattr(cookie, "path", "") or "/")),
            )
        )
        updates: dict[str, str] = {}
        for cookie in candidates:
            name = getattr(cookie, "name", None)
            value = getattr(cookie, "value", None)
            if (
                not isinstance(name, str)
                or name not in ALLOWED_COOKIE_NAMES
                or not isinstance(value, str)
                or not value
                or not self._cookie_applies_to_authorization(cookie)
            ):
                continue
            try:
                updates[name] = _validate_cookie_value(value, name)
            except ValueError as exc:
                raise SessionAuthorizationError(
                    "Riot returned an invalid session cookie"
                ) from exc
        return updates

    def _refresh_authorization(
        self, cookies: Mapping[str, str]
    ) -> RefreshedRiotAuthorization:
        uri, refreshed_cookies = self._request_authorization(cookies, _AUTHORIZATION_BODY)
        token = self._token_from_uri(uri)
        if isinstance(uri, str):
            values = parse_qs(urlsplit(uri).fragment).get("id_token", [])
            self._remember_region_authorization(token, values[0] if len(values) == 1 else None)
        return RefreshedRiotAuthorization(token, refreshed_cookies)

    def _request_authorization(
        self, cookies: Mapping[str, str], authorization_body: Mapping[str, str]
    ) -> tuple[object, dict[str, str]]:
        self._region_authorization = None
        if not isinstance(cookies, Mapping) or "ssid" not in cookies:
            raise SessionSettingsError("Riot session cookies are incomplete")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Peaks/0.1 Riot session import",
        }
        self._logger.info(
            "riot_session.authorization.start cookie_count=%s", len(cookies)
        )
        # requests otherwise merges its previous response jar with the explicit
        # cookies below. A local import followed by browser sign-in can then send
        # duplicate credentials, including cookies belonging to another account.
        transport_cookies = getattr(self._session, "cookies", None)
        clear_cookies = getattr(transport_cookies, "clear", None)
        if callable(clear_cookies):
            clear_cookies()
        try:
            response = self._session.request(
                "POST",
                RIOT_AUTHORIZATION_URL,
                headers=headers,
                cookies=dict(cookies),
                json=dict(authorization_body),
                timeout=self.timeout,
                allow_redirects=False,
                verify=True,
                stream=True,
            )
        except Exception as exc:
            self._logger.warning(
                "riot_session.authorization.transport_failed error_type=%s",
                type(exc).__name__,
            )
            raise SessionAuthorizationError("Riot session authorization is unavailable") from exc
        status_code = getattr(response, "status_code", None)
        if not isinstance(status_code, int) or not 200 <= status_code < 300:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            self._logger.info(
                "riot_session.authorization.rejected status=%s",
                status_code if isinstance(status_code, int) else 0,
            )
            raise SessionAuthorizationHTTPError(status_code if isinstance(status_code, int) else 0)
        try:
            cookie_updates = self._response_cookie_updates(response)
        except SessionAuthorizationError:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            raise
        body = self._read_response_body(response)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SessionAuthorizationError("Riot returned invalid authorization data") from exc
        response_type = payload.get("type") if isinstance(payload, Mapping) else None
        if response_type in ("auth", "multifactor"):
            self._logger.info(
                "riot_session.authorization.reauthentication_required response_type=%s",
                response_type,
            )
            raise SessionReauthenticationRequired(str(response_type))
        if not isinstance(payload, Mapping) or response_type != "response":
            self._logger.warning("riot_session.authorization.invalid_response")
            raise SessionAuthorizationError("Riot did not authorize the current session")
        response_data = payload.get("response")
        if not isinstance(response_data, Mapping):
            raise SessionAuthorizationError("Riot returned invalid authorization data")
        parameters = response_data.get("parameters")
        if not isinstance(parameters, Mapping):
            raise SessionAuthorizationError("Riot returned invalid authorization data")
        refreshed_cookies = dict(cookies)
        refreshed_cookies.update(cookie_updates)
        self._logger.info(
            "riot_session.authorization.complete rotated_cookie_count=%s",
            len(cookie_updates),
        )
        return parameters.get("uri"), refreshed_cookies

    @staticmethod
    def _code_from_uri(uri: object, expected_state: str) -> str:
        if not isinstance(uri, str) or len(uri) > DEFAULT_MAX_RESPONSE_BYTES:
            raise SessionAuthorizationError("Riot returned an invalid authorization URI")
        parsed = urlsplit(uri)
        if (
            parsed.scheme != "http" or parsed.netloc != "localhost"
            or parsed.path != "/redirect" or parsed.fragment
        ):
            raise SessionAuthorizationError("Riot returned an invalid authorization URI")
        params = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=20)
        states, codes = params.get("state", []), params.get("code", [])
        if len(states) != 1 or not hmac.compare_digest(states[0], expected_state):
            raise SessionAuthorizationError("Riot authorization state did not match")
        if len(codes) != 1:
            raise SessionAuthorizationError("Riot authorization code is missing")
        return _validate_opaque(codes[0], "authorization code", max_length=MAX_REFRESH_TOKEN_LENGTH)

    def _exchange_token(
        self, form: Mapping[str, str], cookies: Mapping[str, str],
        *, previous_refresh_token: str | None = None,
    ) -> RefreshedRiotAuthorization:
        self._region_authorization = None
        try:
            response = self._session.request(
                "POST", RIOT_TOKEN_URL,
                headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
                data=dict(form), timeout=self.timeout, allow_redirects=False, verify=True, stream=True,
            )
        except Exception as exc:
            raise SessionAuthorizationError("Riot token renewal is unavailable") from exc
        status = getattr(response, "status_code", 0)
        try:
            updates = self._response_cookie_updates(response)
        except SessionAuthorizationError:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            raise
        body = self._read_response_body(response)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SessionAuthorizationError("Riot returned invalid token data") from exc
        if not isinstance(payload, Mapping):
            raise SessionAuthorizationError("Riot returned invalid token data")
        if not isinstance(status, int) or not 200 <= status < 300:
            error = payload.get("error")
            safe_error = error if error in ("invalid_grant", "invalid_client", "unauthorized_client", "invalid_scope") else "other"
            self._logger.info("riot_session.token.rejected status=%s reason=%s", status, safe_error)
            if previous_refresh_token is not None and error == "invalid_grant":
                raise SessionReauthenticationRequired("auth")
            raise SessionAuthorizationHTTPError(status if isinstance(status, int) else 0)
        token = payload.get("access_token")
        if not isinstance(token, str):
            raise SessionAuthorizationError("Riot token response has no access token")
        refresh_token = payload.get("refresh_token", previous_refresh_token)
        if refresh_token is not None and not isinstance(refresh_token, str):
            raise SessionAuthorizationError("Riot returned an invalid refresh token")
        result = RefreshedRiotAuthorization(token, {**cookies, **updates}, refresh_token)
        self._remember_region_authorization(result.access_token, payload.get("id_token"))
        self._logger.info(
            "riot_session.token.complete refresh_token_issued=%s grant=%s",
            bool(refresh_token), "refresh_token" if previous_refresh_token else "authorization_code",
        )
        return result

    def mint_durable_authorization(self, cookies: Mapping[str, str]) -> RefreshedRiotAuthorization:
        """Request an offline authorization with a one-use, PKCE-bound code."""
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
        state = secrets.token_urlsafe(24)
        uri, rotated = self._request_authorization(self._validate_session_cookies(cookies), {
            **_AUTHORIZATION_BODY, "response_type": "code", "response_mode": "query",
            "nonce": secrets.token_urlsafe(24), "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256",
        })
        try:
            code = self._code_from_uri(uri, state)
            return self._exchange_token({
                "grant_type": "authorization_code", "client_id": "ritoplus",
                "redirect_uri": "http://localhost/redirect", "code": code, "code_verifier": verifier,
            }, rotated)
        except (SessionAuthorizationError, ValueError) as exc:
            # Some Riot clients do not permit code exchange. Keep the current
            # account usable and retain the cookies rotated by the code request.
            # This fallback must never be advertised as an offline authorization.
            self._logger.warning(
                "riot_session.offline_authorization.unavailable error_type=%s", type(exc).__name__,
            )
            return self._refresh_authorization(rotated)

    def refresh_from_token(
        self, refresh_token: str, cookies: Mapping[str, str],
    ) -> RefreshedRiotAuthorization:
        """Renew after offline time without needing an unexpired browser cookie."""
        refresh_token = _validate_opaque(refresh_token, "refresh token", max_length=MAX_REFRESH_TOKEN_LENGTH)
        # Refresh authentication uses the dedicated credential, never ambient SSO.
        clear = getattr(getattr(self._session, "cookies", None), "clear", None)
        if callable(clear):
            clear()
        return self._exchange_token({
            "grant_type": "refresh_token", "client_id": "ritoplus", "refresh_token": refresh_token,
        }, cookies, previous_refresh_token=refresh_token)

    @staticmethod
    def _validate_session_cookies(cookies: Mapping[str, str]) -> dict[str, str]:
        validated: dict[str, str] = {}
        if not isinstance(cookies, Mapping):
            raise SessionSettingsError("Riot session cookies are invalid")
        for name, value in cookies.items():
            if name not in ALLOWED_COOKIE_NAMES:
                raise SessionSettingsError("Riot session cookies contain an unsupported name")
            try:
                validated[name] = _validate_cookie_value(value, name)
            except ValueError as exc:
                raise SessionSettingsError(
                    "Riot session cookies contain an invalid value"
                ) from exc
        if "ssid" not in validated:
            raise SessionSettingsError("Riot session cookies require an ssid cookie")
        return validated

    def refresh_authorization(
        self, cookies: Mapping[str, str]
    ) -> RefreshedRiotAuthorization:
        """Mint a token and return Riot's safely merged cookie rotations."""

        return self._refresh_authorization(self._validate_session_cookies(cookies))

    def mint_access_token(self, cookies: Mapping[str, str]) -> str:
        """Mint a fresh token from an already validated cookie mapping.

        This is public so a caller that stores encrypted cookies can refresh a
        short-lived token on demand rather than persisting it longer than
        needed.  The mapping is validated again before any network request.
        """

        return self.refresh_authorization(cookies).access_token

    def _remember_region_authorization(self, access_token: str, id_token: object) -> None:
        self._region_authorization = None
        if (
            isinstance(id_token, str) and 0 < len(id_token) <= MAX_REFRESH_TOKEN_LENGTH
            and _ACCESS_TOKEN_RE.fullmatch(id_token)
        ):
            self._region_authorization = (hashlib.sha256(access_token.encode()).digest(), id_token)

    def _fetch_valorant_region(self, access_token: str, puuid: str) -> str | None:
        authorization, self._region_authorization = self._region_authorization, None
        if authorization is None or not hmac.compare_digest(
            authorization[0], hashlib.sha256(access_token.encode()).digest(),
        ):
            return None
        id_token = authorization[1]
        try:
            # This claim is only a consistency check. Identity comes from the
            # authenticated userinfo response; Riot verifies the token pair.
            parts = id_token.split(".")
            if len(parts) != 3:
                return None
            claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
            if not isinstance(claims, dict) or claims.get("sub") != puuid:
                return None
            clear = getattr(getattr(self._session, "cookies", None), "clear", None)
            if callable(clear):
                clear()
            response = self._session.request(
                "PUT", RIOT_VALORANT_REGION_URL,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                json={"id_token": id_token}, timeout=min(self.timeout, 5.0),
                allow_redirects=False, verify=True, stream=True,
            )
            status = getattr(response, "status_code", 0)
            body = self._read_response_body(response)
            if status != 200:
                self._logger.info(
                    "riot_session.region.unavailable game=valorant status=%s",
                    status if isinstance(status, int) else 0,
                )
                return None
            payload = json.loads(body)
            affinities = payload.get("affinities") if isinstance(payload, dict) else None
            return normalize_valorant_region(affinities.get("live")) if isinstance(affinities, dict) else None
        except Exception as exc:
            # Optional metadata must never prevent cookie rotation or sign-in.
            self._logger.info(
                "riot_session.region.unavailable game=valorant error_type=%s", type(exc).__name__,
            )
            return None

    def fetch_identity(self, access_token: str) -> AuthenticatedRiotIdentity:
        """Fetch an authoritative, redacted identity for account binding.

        The userinfo endpoint is also private/undocumented.  It is deliberately
        separate from :meth:`import_current` so callers can require explicit
        consent before the additional network request and compare its ``sub``
        to the selected account's stored PUUID.
        """

        try:
            token = _validate_access_token(access_token)
        except ValueError as exc:
            raise SessionAuthorizationError("Riot access token is invalid") from exc
        self._logger.info("riot_session.identity.start")
        try:
            response = self._session.request(
                "GET",
                RIOT_USERINFO_URL,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "Peaks/0.1 Riot session import",
                },
                timeout=self.timeout,
                allow_redirects=False,
                verify=True,
                stream=True,
            )
        except Exception as exc:
            self._logger.warning(
                "riot_session.identity.transport_failed error_type=%s",
                type(exc).__name__,
            )
            raise SessionAuthorizationError("Riot account identity is unavailable") from exc
        status_code = getattr(response, "status_code", None)
        if not isinstance(status_code, int) or not 200 <= status_code < 300:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            self._logger.info(
                "riot_session.identity.rejected status=%s",
                status_code if isinstance(status_code, int) else 0,
            )
            raise SessionAuthorizationHTTPError(status_code if isinstance(status_code, int) else 0)
        body = self._read_response_body(response)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SessionAuthorizationError("Riot returned invalid account identity data") from exc
        if not isinstance(payload, Mapping):
            raise SessionAuthorizationError("Riot returned invalid account identity data")
        subject = payload.get("sub")
        if not isinstance(subject, str):
            subject = payload.get("puuid")
        if not isinstance(subject, str):
            raise SessionAuthorizationError("Riot account identity is missing")
        account_payload = payload.get("acct")
        if not isinstance(account_payload, Mapping):
            account_payload = payload
        game_name = account_payload.get("gameName", account_payload.get("game_name"))
        tag_line = account_payload.get("tagLine", account_payload.get("tag_line"))
        league_payload = payload.get("lol")
        league_regions = {
            region for region in (
                normalize_league_region(payload.get("cpid")),
                normalize_league_region(league_payload.get("cpid")) if isinstance(league_payload, Mapping) else None,
            ) if region is not None
        }
        try:
            identity = AuthenticatedRiotIdentity(
                puuid=subject,
                game_name=game_name if isinstance(game_name, str) else None,
                tag_line=tag_line if isinstance(tag_line, str) else None,
                league_region=next(iter(league_regions)) if len(league_regions) == 1 else None,
            )
        except ValueError as exc:
            raise SessionAuthorizationError("Riot returned invalid account identity data") from exc
        identity = AuthenticatedRiotIdentity(
            identity.puuid, identity.game_name, identity.tag_line, identity.league_region,
            self._fetch_valorant_region(token, identity.puuid),
        )
        self._logger.info(
            "riot_session.region.complete league=%s valorant=%s",
            identity.league_region or "unknown", identity.valorant_region or "unknown",
        )
        self._logger.info("riot_session.identity.complete")
        return identity

    def import_current_session(self) -> ImportedRiotSession:
        """Read the current Riot session and mint a fresh access token."""

        return self._import_session(expected_puuid=None)

    def import_session_for_identity(self, expected_puuid: str) -> ImportedRiotSession:
        """Reject a different local account before rotating its credentials."""
        expected = _validate_opaque(expected_puuid, "PUUID", max_length=MAX_PUUID_LENGTH)
        return self._import_session(expected_puuid=expected)

    def import_durable_session_for_identity(self, expected_puuid: str) -> ImportedRiotSession:
        """Import a matching local account with an offline renewal credential."""
        expected = _validate_opaque(expected_puuid, "PUUID", max_length=MAX_PUUID_LENGTH)
        return self._import_session(expected_puuid=expected, durable=True)

    def _import_session(
        self, *, expected_puuid: str | None, durable: bool = False,
    ) -> ImportedRiotSession:

        self._logger.info("riot_session.import.start")
        puuid, cookies = self._read_cookies()
        if expected_puuid is not None and puuid != expected_puuid:
            raise SessionSettingsError("The local Riot session belongs to another account")
        authorization = (
            self.mint_durable_authorization(cookies) if durable
            else self._refresh_authorization(cookies)
        )
        imported = ImportedRiotSession(
            puuid=puuid,
            cookies=authorization.cookies,
            access_token=authorization.access_token,
            refresh_token=authorization.refresh_token,
        )
        self._logger.info(
            "riot_session.import.complete cookie_count=%s", len(authorization.cookies)
        )
        return imported

    import_current = import_current_session

    def close(self) -> None:
        self._region_authorization = None
        close = getattr(self._session, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> RiotSessionImporter:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()


def import_current_riot_session(**kwargs: Any) -> ImportedRiotSession:
    """Convenience wrapper for one isolated current-session import."""

    with RiotSessionImporter(**kwargs) as importer:
        return importer.import_current_session()


def mint_access_token(cookies: Mapping[str, str], **kwargs: Any) -> str:
    """Mint a fresh token from encrypted, previously imported cookies."""

    with RiotSessionImporter(**kwargs) as importer:
        return importer.mint_access_token(cookies)


def refresh_authorization(
    cookies: Mapping[str, str], **kwargs: Any
) -> RefreshedRiotAuthorization:
    """Mint a token and retain Riot's allowlisted cookie rotations."""

    with RiotSessionImporter(**kwargs) as importer:
        return importer.refresh_authorization(cookies)


# Product-oriented alias for callers that want to make the Windows boundary
# explicit at the call site.
RiotClientSessionImporter = RiotSessionImporter


__all__ = [
    "ALLOWED_COOKIE_NAMES",
    "RIOT_AUTHORIZATION_URL",
    "RIOT_CLIENT_SETTINGS_NAME",
    "RIOT_CLIENT_SETTINGS_RELATIVE_PATH",
    "RIOT_USERINFO_URL",
    "AuthenticatedRiotIdentity",
    "ImportedRiotSession",
    "RefreshedRiotAuthorization",
    "RiotClientSessionImporter",
    "RiotSessionImportError",
    "RiotSessionImporter",
    "SessionAuthorizationError",
    "SessionAuthorizationHTTPError",
    "SessionReauthenticationRequired",
    "SessionSettingsError",
    "UnsupportedPlatformError",
    "import_current_riot_session",
    "mint_access_token",
    "refresh_authorization",
]
