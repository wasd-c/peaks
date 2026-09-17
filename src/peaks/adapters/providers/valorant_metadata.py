"""Official/public Valorant metadata and capability declarations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Protocol, cast
from urllib.parse import urlsplit

import requests

if TYPE_CHECKING:
    from .riot_api import AccountRouting, RiotApiClient, ValorantMatchHistory

VALORANT_API_BASE_URL: Final[str] = "https://valorant-api.com"
VALORANT_API_ALLOWED_HOSTS: Final[frozenset[str]] = frozenset({"valorant-api.com"})
VALORANT_ASSET_ALLOWED_HOSTS: Final[frozenset[str]] = frozenset(
    {"valorant-api.com", "media.valorant-api.com"}
)
DEFAULT_TIMEOUT_SECONDS: Final[float] = 10.0
DEFAULT_MAX_RESPONSE_BYTES: Final[int] = 8 * 1024 * 1024
DEFAULT_CACHE_TTL_SECONDS: Final[float] = 86_400.0


class MetadataSession(Protocol):
    def get(self, url: str, **kwargs: Any) -> requests.Response: ...


class MetadataCache(Protocol):
    def get(self, key: str) -> object | None: ...
    def set(self, key: str, value: object, ttl_seconds: float) -> None: ...


class ValorantMetadataError(RuntimeError):
    """A bounded HTTP or malformed-response error from valorant-api.com."""

    def __init__(self, message: str, *, status_code: int | None = None, path: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.path = path


def _safe_asset_url(value: Any) -> str | None:
    """Keep only HTTPS URLs hosted by the known Valorant asset service."""

    if not isinstance(value, str) or not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in VALORANT_ASSET_ALLOWED_HOSTS:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if parsed.username or parsed.password or port is not None:
        return None
    return value


@dataclass(frozen=True, slots=True)
class ValorantApiLimitations:
    """The public API capability boundary shown to the UI."""

    provider: str = "Riot Games Developer API"
    official_api_available: bool = True
    rank_history: bool = False
    match_history: bool = True
    current_match: bool = False
    requires_production_key: bool = True
    requires_rso_opt_in: bool = True
    reason: str = (
        "Riot documents VAL-MATCH-V1 matchlists and VAL-RANKED-V1 leaderboards, "
        "but Personal Key Applications are unsupported. Player data requires "
        "a production API/RSO opt-in; no per-player rank or current-match "
        "endpoint is documented."
    )

    def supports(self, feature: str) -> bool:
        return bool(getattr(self, feature, False))


class UnsupportedValorantApiError(RuntimeError):
    """Raised when a feature is not offered by Riot's documented public API."""

    def __init__(self, feature: str, limitations: ValorantApiLimitations) -> None:
        self.feature = feature
        self.limitations = limitations
        super().__init__(f"Valorant official API does not expose {feature}")


def valorant_official_limitations() -> ValorantApiLimitations:
    return ValorantApiLimitations()


class ValorantOfficialProvider:
    """Explicit public-API boundary; no private client or tracker fallback."""

    def __init__(
        self,
        limitations: ValorantApiLimitations | None = None,
        *,
        riot_client: RiotApiClient | None = None,
    ) -> None:
        self.limitations = limitations or valorant_official_limitations()
        self._riot_client = riot_client

    def get_rank_history(self, *_: Any, **__: Any) -> None:
        raise UnsupportedValorantApiError("Valorant rank history", self.limitations)

    def get_match_history(
        self,
        puuid: str,
        *,
        routing: str | AccountRouting = "americas",
    ) -> ValorantMatchHistory:
        if self._riot_client is None:
            raise UnsupportedValorantApiError(
                "Valorant match history without a production API/RSO client", self.limitations
            )
        return self._riot_client.get_valorant_match_history(puuid, routing=routing)

    def get_current_match(self, *_: Any, **__: Any) -> None:
        raise UnsupportedValorantApiError("Valorant current match", self.limitations)


@dataclass(frozen=True, slots=True)
class ValorantRankAsset:
    uuid: str
    tier: int | None
    tier_name: str
    division: str
    rank_name: str
    small_icon: str | None = None
    large_icon: str | None = None
    asset_object_name: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ValorantRankAsset:
        uuid = payload.get("uuid")
        if not isinstance(uuid, str) or not uuid:
            raise ValorantMetadataError("valorant-api.com returned a rank without a UUID")
        tier_value = payload.get("tier")
        try:
            tier = int(tier_value) if tier_value is not None else None
        except (TypeError, ValueError):
            tier = None
        return cls(
            uuid=uuid,
            tier=tier,
            tier_name=str(payload.get("tierName") or ""),
            division=str(payload.get("division") or ""),
            rank_name=str(payload.get("rankName") or payload.get("tierName") or ""),
            small_icon=_safe_asset_url(payload.get("smallIcon")),
            large_icon=_safe_asset_url(payload.get("largeIcon")),
            asset_object_name=(
                payload.get("assetObjectName")
                if isinstance(payload.get("assetObjectName"), str)
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class ValorantMapAsset:
    uuid: str
    display_name: str
    display_icon: str | None = None
    list_view_icon: str | None = None
    splash: str | None = None
    stylized_background_image: str | None = None
    narrative_description: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ValorantMapAsset:
        uuid = payload.get("uuid")
        if not isinstance(uuid, str) or not uuid:
            raise ValorantMetadataError("valorant-api.com returned a map without a UUID")
        return cls(
            uuid=uuid,
            display_name=str(payload.get("displayName") or ""),
            display_icon=_safe_asset_url(payload.get("displayIcon")),
            list_view_icon=_safe_asset_url(payload.get("listViewIcon")),
            splash=_safe_asset_url(payload.get("splash")),
            stylized_background_image=_safe_asset_url(payload.get("stylizedBackgroundImage")),
            narrative_description=(
                payload.get("narrativeDescription")
                if isinstance(payload.get("narrativeDescription"), str)
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class ValorantAgentAsset:
    uuid: str
    display_name: str
    description: str | None = None
    display_icon: str | None = None
    display_icon_small: str | None = None
    full_portrait: str | None = None
    full_portrait_v2: str | None = None
    is_playable_character: bool = False
    role_name: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ValorantAgentAsset:
        uuid = payload.get("uuid")
        if not isinstance(uuid, str) or not uuid:
            raise ValorantMetadataError("valorant-api.com returned an agent without a UUID")
        role = payload.get("role")
        role_name = role.get("displayName") if isinstance(role, Mapping) else None
        return cls(
            uuid=uuid,
            display_name=str(payload.get("displayName") or ""),
            description=payload.get("description") if isinstance(payload.get("description"), str) else None,
            display_icon=_safe_asset_url(payload.get("displayIcon")),
            display_icon_small=_safe_asset_url(payload.get("displayIconSmall")),
            full_portrait=_safe_asset_url(payload.get("fullPortrait")),
            full_portrait_v2=_safe_asset_url(payload.get("fullPortraitV2")),
            is_playable_character=bool(payload.get("isPlayableCharacter", False)),
            role_name=role_name if isinstance(role_name, str) else None,
        )


class ValorantMetadataClient:
    """Bounded read-only client for public Valorant metadata assets."""

    def __init__(
        self,
        *,
        session: MetadataSession | None = None,
        cache: MetadataCache | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        if not 0 < timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be between 0 and 120")
        if not 0 < max_response_bytes <= 64 * 1024 * 1024:
            raise ValueError("max_response_bytes must be between 1 and 67108864")
        if cache_ttl_seconds < 0:
            raise ValueError("cache_ttl_seconds must be non-negative")
        self._session = session or requests.Session()
        self._cache = cache
        self._timeout = float(timeout_seconds)
        self._max_response_bytes = int(max_response_bytes)
        self._cache_ttl_seconds = float(cache_ttl_seconds)

    @staticmethod
    def _url(path: str) -> str:
        if not path.startswith("/") or "://" in path or "//" in path:
            raise ValueError("metadata paths must be relative HTTPS paths")
        url = f"{VALORANT_API_BASE_URL}{path}"
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in VALORANT_API_ALLOWED_HOSTS:
            raise ValueError("metadata URL is outside the allowlist")
        return url

    def _get_json(self, path: str) -> Mapping[str, Any] | list[Any]:
        url = self._url(path)
        cached = self._cache_get(path)
        if isinstance(cached, (dict, list)):
            return cast(Mapping[str, Any] | list[Any], cached)
        try:
            response = self._session.get(
                url,
                headers={"Accept": "application/json"},
                timeout=self._timeout,
                stream=True,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise ValorantMetadataError(f"metadata request failed for {path}", path=path) from exc
        try:
            status_code = int(response.status_code)
            if status_code >= 400:
                raise ValorantMetadataError(
                    f"valorant-api.com returned HTTP {status_code} for {path}",
                    status_code=status_code,
                    path=path,
                )
            if 300 <= status_code < 400:
                raise ValorantMetadataError(
                    f"valorant-api.com returned an unexpected redirect for {path}",
                    status_code=status_code,
                    path=path,
                )
            body = self._read_bounded(response, path=path)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValorantMetadataError(f"metadata response was invalid JSON for {path}", path=path) from exc
        if not isinstance(decoded, (dict, list)):
            raise ValorantMetadataError(f"metadata response was not an object or list for {path}", path=path)
        self._cache_set(path, decoded)
        return cast(Mapping[str, Any] | list[Any], decoded)

    def _read_bounded(self, response: requests.Response, *, path: str) -> bytes:
        headers = getattr(response, "headers", {})
        content_length = headers.get("Content-Length")
        if content_length is not None:
            try:
                if int(content_length) > self._max_response_bytes:
                    raise ValorantMetadataError(
                        f"metadata response exceeded the size limit for {path}", path=path
                    )
            except ValueError:
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
                    if total > self._max_response_bytes:
                        raise ValorantMetadataError(
                            f"metadata response exceeded the size limit for {path}", path=path
                        )
                    chunks.append(data)
                return b"".join(chunks)
            except ValorantMetadataError:
                raise
            except requests.RequestException as exc:
                raise ValorantMetadataError(f"metadata response read failed for {path}", path=path) from exc
        body = bytes(getattr(response, "content", b""))
        if len(body) > self._max_response_bytes:
            raise ValorantMetadataError(f"metadata response exceeded the size limit for {path}", path=path)
        return body

    def _cache_get(self, path: str) -> object | None:
        if self._cache is None:
            return None
        try:
            return self._cache.get(f"valorant-api:{path}")
        except Exception:
            return None

    def _cache_set(self, path: str, value: object) -> None:
        if self._cache is None:
            return
        try:
            self._cache.set(f"valorant-api:{path}", value, self._cache_ttl_seconds)
        except Exception:
            return

    @staticmethod
    def _data(payload: Mapping[str, Any] | list[Any], *, path: str) -> list[Mapping[str, Any]]:
        value: Any = payload.get("data") if isinstance(payload, Mapping) else payload
        if not isinstance(value, list):
            raise ValorantMetadataError(f"metadata response had no data list for {path}", path=path)
        return [item for item in value if isinstance(item, Mapping)]

    def get_rank_assets(self) -> tuple[ValorantRankAsset, ...]:
        path = "/v1/competitivetiers"
        payload = self._get_json(path)
        return tuple(ValorantRankAsset.from_payload(item) for item in self._data(payload, path=path))

    def get_map_assets(self) -> tuple[ValorantMapAsset, ...]:
        path = "/v1/maps"
        payload = self._get_json(path)
        return tuple(ValorantMapAsset.from_payload(item) for item in self._data(payload, path=path))

    def get_agent_assets(self, *, playable_only: bool = False) -> tuple[ValorantAgentAsset, ...]:
        path = "/v1/agents"
        payload = self._get_json(path)
        assets = tuple(ValorantAgentAsset.from_payload(item) for item in self._data(payload, path=path))
        if playable_only:
            return tuple(asset for asset in assets if asset.is_playable_character)
        return assets

    list_rank_assets = get_rank_assets
    list_map_assets = get_map_assets
    list_agent_assets = get_agent_assets


ValorantOfficialClient = ValorantOfficialProvider


__all__ = [
    "VALORANT_API_ALLOWED_HOSTS",
    "VALORANT_API_BASE_URL",
    "VALORANT_ASSET_ALLOWED_HOSTS",
    "MetadataCache",
    "UnsupportedValorantApiError",
    "ValorantAgentAsset",
    "ValorantApiLimitations",
    "ValorantMapAsset",
    "ValorantMetadataClient",
    "ValorantMetadataError",
    "ValorantOfficialClient",
    "ValorantOfficialProvider",
    "ValorantRankAsset",
    "valorant_official_limitations",
]
