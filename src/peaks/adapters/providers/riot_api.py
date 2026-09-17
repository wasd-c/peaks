"""Typed access to Riot's documented public APIs.

Only documented HTTPS endpoints are used here.  In particular, Valorant
private client/PD/GLZ endpoints and third-party tracker endpoints are not part
of this client.  Riot API keys are user supplied (normally by the application
secret store), never embedded in source, URLs, exception messages, or logs.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Protocol, cast
from urllib.parse import quote

import requests

DEFAULT_TIMEOUT_SECONDS: Final[float] = 10.0
DEFAULT_MAX_RESPONSE_BYTES: Final[int] = 8 * 1024 * 1024
MAX_MATCH_COUNT: Final[int] = 100


class AccountRouting(StrEnum):
    """Riot account and match routing regions."""

    AMERICAS = "americas"
    ASIA = "asia"
    EUROPE = "europe"
    SEA = "sea"


class PlatformRouting(StrEnum):
    """Riot platform (shard) routing regions."""

    BR1 = "br1"
    EUN1 = "eun1"
    EUW1 = "euw1"
    JP1 = "jp1"
    KR = "kr"
    LA1 = "la1"
    LA2 = "la2"
    ME1 = "me1"
    NA1 = "na1"
    OC1 = "oc1"
    PH2 = "ph2"
    RU = "ru"
    SG2 = "sg2"
    TH2 = "th2"
    TR1 = "tr1"
    TW2 = "tw2"
    VN2 = "vn2"


LEAGUE_ROUTING_HOSTS: Final[Mapping[str, str]] = {
    AccountRouting.AMERICAS.value: "https://americas.api.riotgames.com",
    AccountRouting.ASIA.value: "https://asia.api.riotgames.com",
    AccountRouting.EUROPE.value: "https://europe.api.riotgames.com",
    AccountRouting.SEA.value: "https://sea.api.riotgames.com",
}

PLATFORM_ROUTING_HOSTS: Final[Mapping[str, str]] = {
    value: f"https://{value}.api.riotgames.com" for value in PlatformRouting
}
_RIOT_ALLOWED_HOSTS: Final[frozenset[str]] = frozenset(
    (*LEAGUE_ROUTING_HOSTS.values(), *PLATFORM_ROUTING_HOSTS.values())
)


class RiotApiSession(Protocol):
    """The small part of :class:`requests.Session` required by the client."""

    def get(self, url: str, **kwargs: Any) -> requests.Response: ...


class RiotApiError(RuntimeError):
    """An HTTP or malformed-response error from a documented Riot endpoint."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        path: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.path = path
        self.retry_after_seconds = retry_after_seconds


class RiotApiTransportError(RiotApiError):
    """A connection, timeout, or bounded-response-read failure."""


class UnsupportedRiotRegion(ValueError):
    """The caller supplied a routing region not supported by Riot."""


def _route_value(route: str | StrEnum) -> str:
    value = route.value if isinstance(route, StrEnum) else route
    return str(value).strip().lower()


def _quote_segment(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return quote(value.strip(), safe="")


def _required_string(payload: Mapping[str, Any], key: str, *, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RiotApiError(f"Riot returned an invalid {context} ({key})")
    return value


def _integer(payload: Mapping[str, Any], key: str, *, default: int = 0) -> int:
    value = payload.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class RiotAccount:
    """A Riot ID resolved by ``account-v1``."""

    puuid: str
    game_name: str
    tag_line: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RiotAccount:
        return cls(
            puuid=_required_string(payload, "puuid", context="account"),
            game_name=_required_string(payload, "gameName", context="account"),
            tag_line=_required_string(payload, "tagLine", context="account"),
        )


@dataclass(frozen=True, slots=True)
class LeagueRank:
    """A League of Legends ranked queue entry from ``league-v4``."""

    queue_type: str
    tier: str
    rank: str
    league_points: int
    wins: int
    losses: int
    summoner_id: str | None = None
    puuid: str | None = None
    league_id: str | None = None
    hot_streak: bool = False
    veteran: bool = False
    fresh_blood: bool = False
    inactive: bool = False

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> LeagueRank:
        return cls(
            queue_type=str(payload.get("queueType", "")),
            tier=str(payload.get("tier", "UNRANKED")),
            rank=str(payload.get("rank", "")),
            league_points=_integer(payload, "leaguePoints"),
            wins=_integer(payload, "wins"),
            losses=_integer(payload, "losses"),
            summoner_id=payload.get("summonerId") if isinstance(payload.get("summonerId"), str) else None,
            puuid=payload.get("puuid") if isinstance(payload.get("puuid"), str) else None,
            league_id=payload.get("leagueId") if isinstance(payload.get("leagueId"), str) else None,
            hot_streak=bool(payload.get("hotStreak", False)),
            veteran=bool(payload.get("veteran", False)),
            fresh_blood=bool(payload.get("freshBlood", False)),
            inactive=bool(payload.get("inactive", False)),
        )


@dataclass(frozen=True, slots=True)
class TftRank:
    """A Teamfight Tactics ranked entry from ``tft/league-v1``."""

    queue_type: str
    tier: str
    rank: str
    league_points: int
    wins: int
    losses: int
    summoner_id: str | None = None
    puuid: str | None = None
    league_id: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> TftRank:
        return cls(
            queue_type=str(payload.get("queueType", "")),
            tier=str(payload.get("tier", "UNRANKED")),
            rank=str(payload.get("rank", "")),
            league_points=_integer(payload, "leaguePoints"),
            wins=_integer(payload, "wins"),
            losses=_integer(payload, "losses"),
            summoner_id=payload.get("summonerId") if isinstance(payload.get("summonerId"), str) else None,
            puuid=payload.get("puuid") if isinstance(payload.get("puuid"), str) else None,
            league_id=payload.get("leagueId") if isinstance(payload.get("leagueId"), str) else None,
        )


@dataclass(frozen=True, slots=True)
class MatchReference:
    """A match ID returned by a Riot match history endpoint."""

    match_id: str

    @classmethod
    def from_value(cls, value: Any) -> MatchReference:
        if not isinstance(value, str) or not value:
            raise RiotApiError("Riot returned an invalid match reference")
        return cls(match_id=value)


@dataclass(frozen=True, slots=True)
class MatchHistory:
    """A bounded, ordered match-history page."""

    matches: tuple[MatchReference, ...]
    start: int = 0
    count: int = 0

    @property
    def match_ids(self) -> tuple[str, ...]:
        return tuple(match.match_id for match in self.matches)


@dataclass(frozen=True, slots=True)
class ValorantMatchReference:
    """A VAL-MATCH-V1 match-list item."""

    match_id: str
    game_start_time_millis: int | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ValorantMatchReference:
        match_id = payload.get("matchId")
        if not isinstance(match_id, str) or not match_id:
            raise RiotApiError("Riot returned an invalid Valorant match reference")
        value = payload.get("gameStartTimeMillis")
        try:
            timestamp = int(value) if value is not None else None
        except (TypeError, ValueError):
            timestamp = None
        return cls(match_id=match_id, game_start_time_millis=timestamp)


@dataclass(frozen=True, slots=True)
class ValorantMatchHistory:
    """A VAL-MATCH-V1 match-list page."""

    matches: tuple[ValorantMatchReference, ...]
    start: int = 0
    count: int = 0

    @property
    def match_ids(self) -> tuple[str, ...]:
        return tuple(match.match_id for match in self.matches)


@dataclass(frozen=True, slots=True)
class RiotMatch:
    """Typed envelope retaining the documented match-v5/tft match payload."""

    match_id: str
    metadata: Mapping[str, Any]
    info: Mapping[str, Any]
    raw: Mapping[str, Any]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, match_id: str) -> RiotMatch:
        metadata_value = payload.get("metadata", {})
        info_value = payload.get("info", {})
        metadata = metadata_value if isinstance(metadata_value, Mapping) else {}
        info = info_value if isinstance(info_value, Mapping) else {}
        return cls(match_id=match_id, metadata=metadata, info=info, raw=payload)


class RiotApiClient:
    """Client for documented Riot account, League, TFT, and VAL APIs.

    ``api_key`` must come from the caller's secret store.  It is intentionally
    not accepted through a URL or implicitly read from an environment variable
    so that a UI can make credential ownership explicit.  The key is private
    state and this object has no logging side effects.
    """

    def __init__(
        self,
        api_key: str,
        *,
        session: RiotApiSession | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be supplied by the user")
        if not 0 < timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be between 0 and 120")
        if not 0 < max_response_bytes <= 64 * 1024 * 1024:
            raise ValueError("max_response_bytes must be between 1 and 67108864")
        self._api_key = api_key
        self._session = session or requests.Session()
        if hasattr(self._session, "trust_env"):
            # Never send a user-provided Riot key through ambient HTTP proxy
            # variables. Enterprise proxy support must be an explicit feature.
            self._session.trust_env = False
        self._timeout = float(timeout_seconds)
        self._max_response_bytes = int(max_response_bytes)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(api_key=<redacted>, timeout_seconds={self._timeout!r})"

    def close(self) -> None:
        """Release the transport and drop the live key when Peaks locks."""

        self._api_key = ""
        close = getattr(self._session, "close", None)
        if callable(close):
            close()

    def _host(self, route: str | StrEnum, hosts: Mapping[str, str]) -> str:
        value = _route_value(route)
        try:
            return hosts[value]
        except KeyError as exc:
            raise UnsupportedRiotRegion(f"unsupported Riot routing region: {value!r}") from exc

    def _request_json(
        self,
        path: str,
        *,
        host: str,
        params: Mapping[str, str | int] | None = None,
    ) -> Mapping[str, Any] | list[Any] | None:
        if not path.startswith("/") or "//" in path or "://" in path:
            raise ValueError("Riot API paths must be relative HTTPS paths")
        if host not in _RIOT_ALLOWED_HOSTS or not host.startswith("https://"):
            raise ValueError("Riot API host is outside the HTTPS allowlist")
        url = f"{host}{path}"
        headers = {"X-Riot-Token": self._api_key, "Accept": "application/json"}
        try:
            response = self._session.get(
                url,
                headers=headers,
                params=dict(params) if params else None,
                timeout=self._timeout,
                stream=True,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise RiotApiTransportError(f"Riot request failed for {path}", path=path) from exc

        try:
            status_code = int(response.status_code)
            if status_code >= 400:
                retry_after = self._retry_after(response)
                raise RiotApiError(
                    f"Riot API returned HTTP {status_code} for {path}",
                    status_code=status_code,
                    path=path,
                    retry_after_seconds=retry_after,
                )
            if status_code == 204:
                return None
            body = self._read_bounded(response, path=path)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

        if not body:
            raise RiotApiError(f"Riot API returned an empty response for {path}", path=path)
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RiotApiError(f"Riot API returned invalid JSON for {path}", path=path) from exc
        if not isinstance(decoded, (dict, list)):
            raise RiotApiError(f"Riot API returned an invalid JSON value for {path}", path=path)
        return cast(Mapping[str, Any] | list[Any], decoded)

    def _read_bounded(self, response: requests.Response, *, path: str) -> bytes:
        content_length = getattr(response, "headers", {}).get("Content-Length")
        if content_length is not None:
            try:
                if int(content_length) > self._max_response_bytes:
                    raise RiotApiTransportError(
                        f"Riot response exceeded the size limit for {path}", path=path
                    )
            except ValueError:
                pass

        chunks: list[bytes] = []
        total = 0
        iterator = getattr(response, "iter_content", None)
        if callable(iterator):
            try:
                content = iterator(chunk_size=64 * 1024)
                for chunk in content:
                    if not chunk:
                        continue
                    data = bytes(chunk)
                    total += len(data)
                    if total > self._max_response_bytes:
                        raise RiotApiTransportError(
                            f"Riot response exceeded the size limit for {path}", path=path
                        )
                    chunks.append(data)
                return b"".join(chunks)
            except RiotApiTransportError:
                raise
            except requests.RequestException as exc:
                raise RiotApiTransportError(f"Riot response read failed for {path}", path=path) from exc

        raw = getattr(response, "content", b"")
        body = bytes(raw)
        if len(body) > self._max_response_bytes:
            raise RiotApiTransportError(f"Riot response exceeded the size limit for {path}", path=path)
        return body

    @staticmethod
    def _retry_after(response: requests.Response) -> float | None:
        value = getattr(response, "headers", {}).get("Retry-After")
        if value is None:
            return None
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            return None
        return seconds if seconds >= 0 else None

    def get_account_by_riot_id(
        self,
        game_name: str,
        tag_line: str,
        *,
        routing: str | AccountRouting = AccountRouting.AMERICAS,
    ) -> RiotAccount:
        host = self._host(routing, LEAGUE_ROUTING_HOSTS)
        path = f"/riot/account/v1/accounts/by-riot-id/{_quote_segment(game_name, 'game_name')}/{_quote_segment(tag_line, 'tag_line')}"
        payload = self._request_json(path, host=host)
        if not isinstance(payload, Mapping):
            raise RiotApiError(f"Riot returned an invalid account response for {path}", path=path)
        return RiotAccount.from_payload(payload)

    def get_puuid_by_riot_id(
        self,
        game_name: str,
        tag_line: str,
        *,
        routing: str | AccountRouting = AccountRouting.AMERICAS,
    ) -> str:
        return self.get_account_by_riot_id(game_name, tag_line, routing=routing).puuid

    def get_account_by_puuid(
        self,
        puuid: str,
        *,
        routing: str | AccountRouting = AccountRouting.AMERICAS,
    ) -> RiotAccount:
        """Resolve a PUUID back to its current Riot ID via account-v1."""

        host = self._host(routing, LEAGUE_ROUTING_HOSTS)
        path = f"/riot/account/v1/accounts/by-puuid/{_quote_segment(puuid, 'puuid')}"
        payload = self._request_json(path, host=host)
        if not isinstance(payload, Mapping):
            raise RiotApiError(f"Riot returned an invalid account response for {path}", path=path)
        return RiotAccount.from_payload(payload)

    def _get_summoner_by_puuid(
        self,
        puuid: str,
        *,
        routing: str | PlatformRouting,
        game: str,
    ) -> Mapping[str, Any]:
        host = self._host(routing, PLATFORM_ROUTING_HOSTS)
        path = f"/{game}/summoner/v1/summoners/by-puuid/{_quote_segment(puuid, 'puuid')}"
        payload = self._request_json(path, host=host)
        if not isinstance(payload, Mapping):
            raise RiotApiError(f"Riot returned an invalid summoner response for {path}", path=path)
        return payload

    def get_league_ranks(
        self,
        puuid: str,
        *,
        routing: str | PlatformRouting = PlatformRouting.NA1,
    ) -> tuple[LeagueRank, ...]:
        host = self._host(routing, PLATFORM_ROUTING_HOSTS)
        path = f"/lol/league/v4/entries/by-puuid/{_quote_segment(puuid, 'puuid')}"
        payload = self._request_json(path, host=host)
        if not isinstance(payload, list):
            raise RiotApiError(f"Riot returned an invalid League rank response for {path}", path=path)
        return tuple(LeagueRank.from_payload(entry) for entry in payload if isinstance(entry, Mapping))

    def get_league_ranks_by_puuid(
        self,
        puuid: str,
        *,
        routing: str | PlatformRouting = PlatformRouting.NA1,
    ) -> tuple[LeagueRank, ...]:
        """Alias emphasizing the current PUUID-based League endpoint."""

        return self.get_league_ranks(puuid, routing=routing)

    def get_league_ranks_by_summoner_id(
        self,
        summoner_id: str,
        *,
        routing: str | PlatformRouting = PlatformRouting.NA1,
    ) -> tuple[LeagueRank, ...]:
        host = self._host(routing, PLATFORM_ROUTING_HOSTS)
        path = f"/lol/league/v4/entries/by-summoner/{_quote_segment(summoner_id, 'summoner_id')}"
        payload = self._request_json(path, host=host)
        if not isinstance(payload, list):
            raise RiotApiError(f"Riot returned an invalid League rank response for {path}", path=path)
        return tuple(LeagueRank.from_payload(entry) for entry in payload if isinstance(entry, Mapping))

    def get_league_match_history(
        self,
        puuid: str,
        *,
        routing: str | AccountRouting = AccountRouting.AMERICAS,
        start: int = 0,
        count: int = 20,
        start_time: int | None = None,
        end_time: int | None = None,
        queue: int | None = None,
        match_type: str | None = None,
    ) -> MatchHistory:
        params = self._match_history_params(
            start=start,
            count=count,
            start_time=start_time,
            end_time=end_time,
            queue=queue,
            match_type=match_type,
        )
        host = self._host(routing, LEAGUE_ROUTING_HOSTS)
        path = f"/lol/match/v5/matches/by-puuid/{_quote_segment(puuid, 'puuid')}/ids"
        payload = self._request_json(path, host=host, params=params)
        if not isinstance(payload, list):
            raise RiotApiError(f"Riot returned an invalid League match history for {path}", path=path)
        matches = tuple(MatchReference.from_value(value) for value in payload)
        return MatchHistory(matches=matches, start=start, count=len(matches))

    def get_league_match(
        self,
        match_id: str,
        *,
        routing: str | AccountRouting = AccountRouting.AMERICAS,
    ) -> RiotMatch:
        host = self._host(routing, LEAGUE_ROUTING_HOSTS)
        path = f"/lol/match/v5/matches/{_quote_segment(match_id, 'match_id')}"
        payload = self._request_json(path, host=host)
        if not isinstance(payload, Mapping):
            raise RiotApiError(f"Riot returned an invalid League match for {path}", path=path)
        return RiotMatch.from_payload(payload, match_id=match_id)

    def get_tft_ranks(
        self,
        puuid: str,
        *,
        routing: str | PlatformRouting = PlatformRouting.NA1,
    ) -> tuple[TftRank, ...]:
        host = self._host(routing, PLATFORM_ROUTING_HOSTS)
        path = f"/tft/league/v1/by-puuid/{_quote_segment(puuid, 'puuid')}"
        payload = self._request_json(path, host=host)
        if not isinstance(payload, list):
            raise RiotApiError(f"Riot returned an invalid TFT rank response for {path}", path=path)
        return tuple(TftRank.from_payload(entry) for entry in payload if isinstance(entry, Mapping))

    def get_tft_ranks_by_puuid(
        self,
        puuid: str,
        *,
        routing: str | PlatformRouting = PlatformRouting.NA1,
    ) -> tuple[TftRank, ...]:
        return self.get_tft_ranks(puuid, routing=routing)

    def get_tft_match_history(
        self,
        puuid: str,
        *,
        routing: str | AccountRouting = AccountRouting.AMERICAS,
        start: int = 0,
        count: int = 20,
    ) -> MatchHistory:
        params = self._match_history_params(start=start, count=count)
        host = self._host(routing, LEAGUE_ROUTING_HOSTS)
        path = f"/tft/match/v1/matches/by-puuid/{_quote_segment(puuid, 'puuid')}/ids"
        payload = self._request_json(path, host=host, params=params)
        if not isinstance(payload, list):
            raise RiotApiError(f"Riot returned an invalid TFT match history for {path}", path=path)
        matches = tuple(MatchReference.from_value(value) for value in payload)
        return MatchHistory(matches=matches, start=start, count=len(matches))

    def get_tft_match(
        self,
        match_id: str,
        *,
        routing: str | AccountRouting = AccountRouting.AMERICAS,
    ) -> RiotMatch:
        host = self._host(routing, LEAGUE_ROUTING_HOSTS)
        path = f"/tft/match/v1/matches/{_quote_segment(match_id, 'match_id')}"
        payload = self._request_json(path, host=host)
        if not isinstance(payload, Mapping):
            raise RiotApiError(f"Riot returned an invalid TFT match for {path}", path=path)
        return RiotMatch.from_payload(payload, match_id=match_id)

    def get_valorant_match_history(
        self,
        puuid: str,
        *,
        routing: str | AccountRouting = AccountRouting.AMERICAS,
    ) -> ValorantMatchHistory:
        """Read the documented VAL-MATCH-V1 match list.

        Riot requires a production-level VALORANT API/RSO integration for
        player data; callers should surface that access requirement to users.
        This method never uses private client endpoints or third-party trackers.
        """

        host = self._host(routing, LEAGUE_ROUTING_HOSTS)
        path = f"/val/match/v1/matchlists/by-puuid/{_quote_segment(puuid, 'puuid')}"
        payload = self._request_json(path, host=host)
        if not isinstance(payload, Mapping):
            raise RiotApiError(f"Riot returned an invalid Valorant match history for {path}", path=path)
        values = payload.get("matches", [])
        if not isinstance(values, list):
            raise RiotApiError(f"Riot returned an invalid Valorant match list for {path}", path=path)
        matches = tuple(
            ValorantMatchReference.from_payload(value) for value in values if isinstance(value, Mapping)
        )
        return ValorantMatchHistory(matches=matches, start=0, count=len(matches))

    def get_valorant_match(
        self,
        match_id: str,
        *,
        routing: str | AccountRouting = AccountRouting.AMERICAS,
    ) -> RiotMatch:
        """Read one documented VAL-MATCH-V1 match by ID."""

        host = self._host(routing, LEAGUE_ROUTING_HOSTS)
        path = f"/val/match/v1/matches/{_quote_segment(match_id, 'match_id')}"
        payload = self._request_json(path, host=host)
        if not isinstance(payload, Mapping):
            raise RiotApiError(f"Riot returned an invalid Valorant match for {path}", path=path)
        return RiotMatch.from_payload(payload, match_id=match_id)

    def get_valorant_ranked_leaderboard(
        self,
        act_id: str,
        *,
        routing: str | AccountRouting = AccountRouting.AMERICAS,
        size: int = 25,
        start_index: int = 0,
    ) -> Mapping[str, Any]:
        """Read the documented leaderboard; it is not a per-player rank API."""

        if not isinstance(size, int) or not 1 <= size <= 200:
            raise ValueError("size must be between 1 and 200")
        if not isinstance(start_index, int) or start_index < 0:
            raise ValueError("start_index must be a non-negative integer")
        host = self._host(routing, LEAGUE_ROUTING_HOSTS)
        path = f"/val/ranked/v1/leaderboards/by-act/{_quote_segment(act_id, 'act_id')}"
        payload = self._request_json(
            path,
            host=host,
            params={"size": size, "startIndex": start_index},
        )
        if not isinstance(payload, Mapping):
            raise RiotApiError(f"Riot returned an invalid Valorant leaderboard for {path}", path=path)
        return payload

    @staticmethod
    def _match_history_params(
        *,
        start: int,
        count: int,
        start_time: int | None = None,
        end_time: int | None = None,
        queue: int | None = None,
        match_type: str | None = None,
    ) -> dict[str, str | int]:
        if not isinstance(start, int) or start < 0:
            raise ValueError("start must be a non-negative integer")
        if not isinstance(count, int) or not 1 <= count <= MAX_MATCH_COUNT:
            raise ValueError(f"count must be between 1 and {MAX_MATCH_COUNT}")
        params: dict[str, str | int] = {"start": start, "count": count}
        if start_time is not None:
            if not isinstance(start_time, int) or start_time < 0:
                raise ValueError("start_time must be a non-negative Unix timestamp")
            params["startTime"] = start_time
        if end_time is not None:
            if not isinstance(end_time, int) or end_time < 0:
                raise ValueError("end_time must be a non-negative Unix timestamp")
            params["endTime"] = end_time
        if queue is not None:
            if not isinstance(queue, int) or queue < 0:
                raise ValueError("queue must be a non-negative integer")
            params["queue"] = queue
        if match_type is not None:
            if not isinstance(match_type, str) or not match_type.strip():
                raise ValueError("match_type must be a non-empty string")
            params["type"] = match_type.strip()
        return params


# Provider terminology is useful at composition boundaries, while the client
# name remains the most familiar public API for callers.
RiotApiProvider = RiotApiClient
OfficialRiotApiClient = RiotApiClient


__all__ = [
    "LEAGUE_ROUTING_HOSTS",
    "PLATFORM_ROUTING_HOSTS",
    "AccountRouting",
    "LeagueRank",
    "MatchHistory",
    "MatchReference",
    "OfficialRiotApiClient",
    "PlatformRouting",
    "RiotAccount",
    "RiotApiClient",
    "RiotApiError",
    "RiotApiProvider",
    "RiotApiTransportError",
    "RiotMatch",
    "TftRank",
    "UnsupportedRiotRegion",
    "ValorantMatchHistory",
    "ValorantMatchReference",
]
