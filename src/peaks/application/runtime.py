"""Runtime composition for authenticated Riot search and local game detection.

Local client credentials remain inside the adapters; renderer profiles contain
only normalized identity, rank, and match data.
"""

from __future__ import annotations

import base64
import logging
import platform
import re
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from peaks.adapters.riot.redaction import redact_player
from peaks.domain.regions import normalize_valorant_region

if TYPE_CHECKING:
    from peaks.adapters.riot.valorant import (
        ValorantCoregame,
        ValorantMatchSummary,
        ValorantPregame,
        ValorantRank,
    )
    from peaks.adapters.riot.valorant_presence import ValorantPresence

LOGGER = logging.getLogger(__name__)

_REGIONS: dict[str, tuple[str, str]] = {
    "BR": ("americas", "br1"),
    "EUNE": ("europe", "eun1"),
    "EUW": ("europe", "euw1"),
    "JP": ("asia", "jp1"),
    "KR": ("asia", "kr"),
    "LAN": ("americas", "la1"),
    "LAS": ("americas", "la2"),
    "ME": ("europe", "me1"),
    "NA": ("americas", "na1"),
    "OCE": ("sea", "oc1"),
    "PH": ("sea", "ph2"),
    "RU": ("europe", "ru"),
    "SG": ("sea", "sg2"),
    "TH": ("sea", "th2"),
    "TR": ("europe", "tr1"),
    "TW": ("sea", "tw2"),
    "VN": ("sea", "vn2"),
}


def _split_riot_id(value: str) -> tuple[str, str]:
    game_name, separator, tag_line = value.partition("#")
    if not separator or not game_name.strip() or not tag_line.strip():
        raise ValueError("Enter a complete Riot ID: Player#TAG")
    return game_name.strip(), tag_line.strip()


def _queue_rank(entries: Any, preferred: str) -> Any | None:
    for entry in entries or ():
        if str(getattr(entry, "queue_type", "")) == preferred:
            return entry
    return None


def _rank_label(rank: Any | None, *, valorant: bool = False) -> str:
    if rank is None:
        return "Unranked"
    tier = str(getattr(rank, "tier", "UNRANKED")).replace("_", " ").title()
    division = str(getattr(rank, "rank", "")).strip()
    points = int(getattr(rank, "league_points", 0))
    suffix = "RR" if valorant else "LP"
    return " ".join(part for part in (tier, division) if part) + f" · {points} {suffix}"


def _relative_timestamp(milliseconds: Any) -> str:
    try:
        timestamp = datetime.fromtimestamp(float(milliseconds) / 1_000, UTC)
    except (TypeError, ValueError, OverflowError):
        return "No recent game"
    seconds = max(0, int((datetime.now(UTC) - timestamp).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3_600:
        return f"{seconds // 60} min ago"
    if seconds < 86_400:
        return f"{seconds // 3_600}h ago"
    return f"{seconds // 86_400}d ago"


class RiotSearchService:
    """Player search with local LCU lookup and optional official enrichment."""

    LOCAL_CLIENT_ERROR = "LOCAL_RIOT_CLIENT_UNAVAILABLE"

    def __init__(
        self, *, local_client_factory: Callable[[], Any] | None = None,
        riot_client_factory: Callable[[], Any] | None = None,
        valorant_profile_reader: Callable[[str], dict[str, Any] | None] | None = None,
    ) -> None:
        self._client: Any | None = None
        self._local_client_factory = local_client_factory
        self._riot_client_factory = riot_client_factory
        self._valorant_profile_reader = valorant_profile_reader
        self._valorant_search_service: CurrentGameService | None = None

    def set_api_key(self, api_key: str) -> None:
        from peaks.adapters.providers.riot_api import RiotApiClient

        self._client = RiotApiClient(api_key)

    def clear_api_key(self) -> None:
        """Drop the in-memory Riot client when the vault is locked."""

        close = getattr(self._client, "close", None)
        if callable(close):
            close()
        self._client = None
        self._valorant_search_service = None

    def _with_valorant_profile(
        self, results: list[dict[str, Any]], requested: str,
    ) -> list[dict[str, Any]]:
        if requested not in {"all", "all games", "valorant"}:
            return results
        for result in results:
            subject = result.get("puuid")
            if not isinstance(subject, str) or not subject:
                continue
            try:
                reader = self._valorant_profile_reader
                if reader is None:
                    if self._valorant_search_service is None:
                        self._valorant_search_service = CurrentGameService()
                    reader = self._valorant_search_service.valorant_player_snapshot
                snapshot = reader(subject)
            except Exception as error:
                LOGGER.info("search.valorant.unavailable error_type=%s", type(error).__name__)
                continue
            if not snapshot:
                continue
            result["games"] = ["VALORANT", *[
                game for game in result.get("games", []) if str(game).lower() != "valorant"
            ]]
            result["ranks"] = [*snapshot.get("ranks", []), *[
                rank for rank in result.get("ranks", [])
                if str(rank.get("game", "")).lower() != "valorant"
            ]]
            result["matches"] = [*snapshot.get("matches", []), *[
                match for match in result.get("matches", [])
                if str(match.get("game", "")).lower() != "valorant"
            ]][:20]
            result["currentRank"] = snapshot.get("currentRank", "Rank unavailable")
            result["peakRank"] = snapshot.get("peakRank", "Rank unavailable")
            for key in ("level", "region", "peakRankSeason"):
                if key in snapshot:
                    result[key] = snapshot[key]
            result.pop("valorantStatus", None)
            result["lastUpdated"] = "Just now"
            LOGGER.info(
                "search.valorant.complete rank_count=%s match_count=%s",
                len(snapshot.get("ranks", [])), len(snapshot.get("matches", [])),
            )
        return results

    def _local_search_player(
        self,
        query: str,
        *,
        region: str,
        requested: str,
    ) -> list[dict[str, Any]]:
        """Resolve identity and independent ranked queues through validated LCU."""

        game_name, tag_line = _split_riot_id(query)
        factory = self._local_client_factory
        if factory is None:
            from peaks.adapters.riot.league import LeagueClient

            factory = LeagueClient.from_discovery
        local_client: Any | None = None
        ranks: list[dict[str, Any]] = []
        entries: tuple[Any, ...] = ()
        warnings: list[str] = []
        try:
            local_client = factory()
            lookup = getattr(local_client, "lookup_summoner", None)
            if not callable(lookup):
                raise RuntimeError("Local Riot player lookup is unavailable")
            profile = lookup(game_name, tag_line, expected_region=region)
            if profile is not None:
                fetch_ranks = getattr(local_client, "ranked_stats", None)
                try:
                    resolved = fetch_ranks(profile.puuid) if callable(fetch_ranks) else None
                    if resolved is not None:
                        entries = tuple(resolved)
                    else:
                        warnings.append("Rank data is unavailable from the signed-in client.")
                except Exception:
                    warnings.append("Rank data is temporarily unavailable from the signed-in client.")
        except Exception:
            # Do not surface transport details or local paths across IPC. The
            # stable marker lets the renderer choose allowlisted copy.
            raise RuntimeError(
                f"{self.LOCAL_CLIENT_ERROR}: Open League of Legends or TFT{f' in {region}' if region else ''}, "
                "sign in, and keep the client open while searching."
            ) from None
        finally:
            close = getattr(local_client, "close", None) if local_client is not None else None
            if callable(close):
                close()
        if profile is None:
            return []

        # A resolved summoner establishes a League profile. TFT is added only
        # when its own standard queue was actually returned, never from a
        # selected game or a Double Up / Hyper Roll rank.
        games = ["League"]
        for entry in entries:
            game = "TFT" if entry.queue_type == "RANKED_TFT" else "League"
            ranks.append(self._rank_view(entry, game))
            if game not in games:
                games.append(game)
        tft_requested = requested in {"tft", "teamfight tactics"}
        preferred = "RANKED_TFT" if tft_requested else "RANKED_SOLO_5x5"
        current = next((entry for entry in entries if entry.queue_type == preferred), None)
        if requested == "valorant":
            current = None
        if tft_requested and "TFT" in games:
            games = ["TFT", *[game for game in games if game != "TFT"]]
        rank_status = _rank_label(current) if current is not None else "Rank unavailable"
        riot_id = str(getattr(profile, "riot_id", "") or f"{game_name}#{tag_line}")
        resolved_name, _, _ = riot_id.partition("#")
        result: dict[str, Any] = {
            "id": str(getattr(profile, "puuid", "")),
            "riotId": riot_id,
            "region": str(getattr(profile, "region", None) or region or "GLOBAL"),
            "games": games,
            "currentRank": rank_status,
            "lastUpdated": "Just now",
            "followed": False,
            "owned": False,
            "initials": resolved_name[:2].upper(),
            "puuid": str(getattr(profile, "puuid", "")),
            "ranks": ranks,
            "matches": [],
            "valorantStatus": "Requires Riot-approved player opt-in",
            "warnings": warnings,
        }
        level = getattr(profile, "level", None)
        if isinstance(level, int) and not isinstance(level, bool):
            result["level"] = level
        return [result]

    def _riot_client_search_player(self, query: str) -> list[dict[str, Any]]:
        from peaks.adapters.riot.player_lookup import RiotPlayerLookup

        game_name, tag_line = _split_riot_id(query)
        client: Any = None
        try:
            client = (self._riot_client_factory or RiotPlayerLookup.from_discovery)()
            identity = client.lookup_player(game_name, tag_line)
        except Exception:
            raise RuntimeError(
                f"{self.LOCAL_CLIENT_ERROR}: Sign in to Riot Client, League of Legends, "
                "or TFT and keep the client open while searching."
            ) from None
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        if identity is None:
            return []
        return [{
            "id": identity.puuid,
            "puuid": identity.puuid,
            "riotId": identity.riot_id,
            "region": "GLOBAL",
            "games": [],
            "ranks": [],
            "matches": [],
            "currentRank": "Rank unavailable",
            "lastUpdated": "Just now",
            "initials": identity.game_name[:2].upper(),
            "owned": False,
            "followed": False,
        }]

    @staticmethod
    def _is_not_found(error: Exception) -> bool:
        """Riot uses 404 for accounts that have not played a game/queue."""

        return getattr(error, "status_code", None) == 404

    @staticmethod
    def _safe_provider_error(error: Exception, fallback: str) -> str:
        """Return a user-facing provider error without secrets or URLs."""

        status = getattr(error, "status_code", None)
        if status == 401 or status == 403:
            return f"{fallback}: Riot API authorization is unavailable"
        if status == 429:
            return f"{fallback}: Riot API rate limit reached"
        text = str(error).strip()
        lowered = text.lower()
        if any(
            secret in lowered
            for secret in (
                "token",
                "authorization",
                "cookie",
                "password",
                "api-key",
                "api_key",
                "secret",
                "credential",
            )
        ):
            return fallback
        # Provider paths are useful for diagnostics, but URLs and response
        # bodies should never be surfaced by the desktop UI.
        text = re.sub(r"https?://[^\s]+", "", text, flags=re.IGNORECASE).strip()
        return text[:120] if text else fallback

    @staticmethod
    def _rank_view(rank: Any, game: str) -> dict[str, Any]:
        tier = str(getattr(rank, "tier", "UNRANKED")).replace("_", " ").title()
        division = str(getattr(rank, "rank", "")).strip()
        points = int(getattr(rank, "league_points", 0))
        return {
            "game": game,
            "tier": " ".join(part for part in (tier, division) if part),
            "rating": points,
            "peak": None,
            "icon": "",
        }

    @staticmethod
    def _valorant_rank_view() -> dict[str, Any]:
        unavailable = "Requires approved VALORANT RSO"
        return {
            "game": "VALORANT",
            "tier": unavailable,
            "rating": "—",
            "peak": unavailable,
            "icon": "",
        }

    @staticmethod
    def _participant_riot_id(participant: Mapping[str, Any]) -> str | None:
        game_name = str(
            participant.get("riotIdGameName")
            or participant.get("gameName")
            or ""
        ).strip()
        tag_line = str(
            participant.get("riotIdTagline")
            or participant.get("tagLine")
            or ""
        ).strip()
        candidate = f"{game_name}#{tag_line}" if game_name and tag_line else ""
        if (
            not candidate
            or len(candidate) > 256
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in candidate)
        ):
            return None
        return candidate

    @classmethod
    def _public_match_teams(
        cls,
        game: str,
        participants: object,
        *,
        puuid: str,
        duos: bool = False,
    ) -> list[dict[str, Any]]:
        if not isinstance(participants, list):
            return []
        bounded = [item for item in participants[:20] if isinstance(item, Mapping)]
        own = next((item for item in bounded if item.get("puuid") == puuid), None)
        own_team_id = own.get("teamId") if isinstance(own, Mapping) else None
        grouped: dict[str, list[dict[str, Any]]] = {}
        team_order: list[str] = []
        duo_members: dict[int, list[int]] = {}
        if game == "TFT" and duos:
            for index, participant in enumerate(bounded):
                pair = participant.get("partner_group_id", participant.get("partnerGroupId"))
                if isinstance(pair, int) and not isinstance(pair, bool) and 1 <= pair <= 255:
                    duo_members.setdefault(pair, []).append(index)
        valid_pairs = {key: values for key, values in duo_members.items() if len(values) == 2}
        if len(valid_pairs) > 4:
            valid_pairs = {}
        pair_labels = {index: f"Duo {number}" for number, indices in enumerate(valid_pairs.values(), start=1) for index in indices}
        for index, participant in enumerate(bounded, start=1):
            team_id = pair_labels.get(index - 1, "Unassigned players") if game == "TFT" and duos else "Lobby" if game != "League" else str(participant.get("teamId") or "Players")
            if team_id not in grouped:
                grouped[team_id] = []
                team_order.append(team_id)
            riot_id = cls._participant_riot_id(participant)
            is_self = participant.get("puuid") == puuid
            if game == "League":
                kills = participant.get("kills")
                deaths = participant.get("deaths")
                assists = participant.get("assists")
                minions = sum(
                    value
                    for value in (
                        participant.get("totalMinionsKilled"),
                        participant.get("neutralMinionsKilled"),
                    )
                    if isinstance(value, int) and not isinstance(value, bool)
                )
                stats = {
                    "kills": kills,
                    "deaths": deaths,
                    "assists": assists,
                    "damage": participant.get("totalDamageDealtToChampions"),
                    "gold": participant.get("goldEarned"),
                    "minions": minions,
                    "vision": participant.get("visionScore"),
                    "level": participant.get("champLevel"),
                }
                character = str(participant.get("championName") or "Champion unavailable")
                score = (
                    f"{kills} / {deaths} / {assists}"
                    if all(isinstance(value, int) for value in (kills, deaths, assists))
                    else None
                )
            else:
                placement = participant.get("placement")
                stats = {
                    "placement": placement,
                    "level": participant.get("level"),
                    "damage": participant.get("totalDamageToPlayers"),
                    "playersEliminated": participant.get("playersEliminated"),
                }
                character = "TFT tactician"
                score = f"#{placement}" if isinstance(placement, int) else None
            grouped[team_id].append(
                {
                    "name": riot_id or f"Player {index}",
                    "riotId": riot_id,
                    "agent": character,
                    "score": score,
                    "stats": {
                        key: value
                        for key, value in stats.items()
                        if isinstance(value, (int, float)) and not isinstance(value, bool)
                    },
                    "self": is_self,
                    "hidden": riot_id is None,
                }
            )
        views: list[dict[str, Any]] = []
        for index, team_id in enumerate(team_order, start=1):
            players = grouped[team_id]
            is_own_team = game == "League" and str(own_team_id) == team_id
            name = (
                team_id if game == "TFT" and duos else "Lobby"
                if game != "League"
                else "Your team"
                if is_own_team
                else "Opponents"
                if len(team_order) == 2
                else f"Team {index}"
            )
            kills = sum(
                int(player.get("stats", {}).get("kills", 0)) for player in players
            )
            team_won = next(
                (
                    bool(participant.get("win"))
                    for participant in bounded
                    if (
                        "Lobby" if game != "League" else str(participant.get("teamId") or "Players")
                    )
                    == team_id
                    and "win" in participant
                ),
                None,
            )
            views.append(
                {
                    "name": name,
                    "score": kills if game == "League" else None,
                    "won": team_won,
                    "players": players,
                    **({"grouping": "duo" if team_id.startswith("Duo ") else "unassigned"} if game == "TFT" and duos else {}),
                }
            )
        return views

    @staticmethod
    def _match_view(
        game: str,
        match_id: str,
        *,
        info: dict[str, Any] | None = None,
        puuid: str = "",
        played_at: float | int | None = None,
    ) -> dict[str, Any]:
        """Normalize a public match detail to the controller's row shape."""

        detail = info or {}
        from peaks.adapters.riot.league import is_tft_double_up

        duos = game == "TFT" and is_tft_double_up(
            detail.get("queue_id", detail.get("queueId")),
            str(detail.get("tft_game_type") or detail.get("tftGameType") or detail.get("gameType") or ""),
        )
        participants = detail.get("participants", [])
        player = next(
            (
                item
                for item in participants
                if isinstance(item, dict) and item.get("puuid") == puuid
            ),
            {},
        )
        result = "unknown"
        kills = deaths = assists = None
        if game == "League":
            if isinstance(player, dict) and "win" in player:
                result = "win" if bool(player.get("win")) else "loss"
            kills = player.get("kills") if isinstance(player, dict) else None
            deaths = player.get("deaths") if isinstance(player, dict) else None
            assists = player.get("assists") if isinstance(player, dict) else None
            queue = detail.get("queueId") or detail.get("gameMode") or "Unknown queue"
            map_name = detail.get("mapId") or "Unknown map"
        else:
            placement = player.get("placement") if isinstance(player, dict) else None
            if isinstance(placement, int):
                result = "top_4" if placement <= 4 else "placement"
            queue = "Double Up" if duos else detail.get("tft_game_type") or detail.get("tftGameType") or detail.get("gameType") or "Unknown queue"
            map_name = detail.get("gameVariation") or "Unknown map"
        played = float(played_at) if isinstance(played_at, (int, float)) else None
        played_label = (
            _relative_timestamp(played * 1_000) if played is not None else "No recent game"
        )
        teams = RiotSearchService._public_match_teams(
            game,
            participants,
            puuid=puuid,
            duos=duos,
        )
        return {
            "id": match_id,
            "game": game.lower().replace("league", "league_of_legends"),
            "result": result,
            "queue": str(queue),
            # These aliases are intentionally presentation-only.  The
            # canonical snake_case fields remain available to persistence and
            # account refresh code, while the search detail view can render a
            # row without another controller-specific conversion step.
            "mode": str(queue),
            "map_name": str(map_name),
            "map": str(map_name),
            "played_at": played,
            "playedAt": played_label,
            "played": played_label,
            "kills": kills,
            "deaths": deaths,
            "assists": assists,
            "rank_delta": None,
            "metadata": {"teams": teams, **({"teamMode": "duos"} if duos else {})},
        }

    def _match_rows(
        self,
        game: str,
        puuid: str,
        *,
        routing: str,
        count: int = 20,
    ) -> list[dict[str, Any]]:
        """Fetch at most ``count`` IDs and details, tolerating 404s."""

        if self._client is None:
            return []
        limit = max(1, min(int(count), 20))
        try:
            if game == "League":
                history = self._client.get_league_match_history(puuid, routing=routing, count=limit)
                fetch = self._client.get_league_match
            else:
                history = self._client.get_tft_match_history(puuid, routing=routing, count=limit)
                fetch = self._client.get_tft_match
        except Exception as error:
            if self._is_not_found(error):
                return []
            raise RuntimeError(
                self._safe_provider_error(error, f"{game} match history unavailable")
            ) from None

        rows: list[dict[str, Any]] = []
        for reference in tuple(getattr(history, "match_ids", ()))[:limit]:
            try:
                detail = fetch(reference, routing=routing)
            except Exception as error:
                if self._is_not_found(error):
                    continue
                # One bad match must not discard the rest of a bounded page.
                continue
            info = getattr(detail, "info", {})
            if not isinstance(info, dict):
                info = {}
            timestamp = info.get("gameEndTimestamp") or info.get("gameStartTimestamp")
            if isinstance(timestamp, (int, float)) and timestamp > 10_000_000_000:
                timestamp = timestamp / 1_000
            rows.append(
                self._match_view(game, reference, info=info, puuid=puuid, played_at=timestamp)
            )
        return rows

    def _overview_for_account(
        self,
        account: Any,
        *,
        region_label: str,
        account_route: str,
        platform_route: str,
    ) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("Riot API client is not configured")
        client = self._client
        puuid = str(account.puuid)
        ranks: list[dict[str, Any]] = []
        warnings: list[str] = []
        league_available = True
        try:
            league_entries = client.get_league_ranks(puuid, routing=platform_route)
            league_rank = _queue_rank(league_entries, "RANKED_SOLO_5x5")
        except Exception as error:
            league_rank = None
            league_available = self._is_not_found(error)
            if not self._is_not_found(error):
                warnings.append(self._safe_provider_error(error, "League rank unavailable"))
        league_view = (
            self._rank_view(league_rank, "League")
            if league_rank is not None
            else {
                "game": "League",
                "tier": "Unranked",
                "rating": "—",
                "peak": "Unranked",
                "icon": "",
            }
        )
        if league_available:
            ranks.append(league_view)

        try:
            tft_entries = client.get_tft_ranks(puuid, routing=platform_route)
            tft_rank = _queue_rank(tft_entries, "RANKED_TFT")
        except Exception as error:
            tft_rank = None
            if not self._is_not_found(error):
                warnings.append(self._safe_provider_error(error, "TFT rank unavailable"))
        # Riot returns an empty rank list for accounts that never played TFT;
        # omit TFT entirely in that case.
        if tft_rank is not None:
            ranks.append(self._rank_view(tft_rank, "TFT"))
        ranks.append(self._valorant_rank_view())

        matches: list[dict[str, Any]] = []
        try:
            matches.extend(self._match_rows("League", puuid, routing=account_route, count=20))
        except RuntimeError as error:
            warnings.append(str(error))
        if tft_rank is not None:
            try:
                matches.extend(self._match_rows("TFT", puuid, routing=account_route, count=20))
            except RuntimeError as error:
                warnings.append(str(error))
        # Keep account rows bounded even when both game histories are present.
        matches = matches[:20]
        result = {
            "id": puuid,
            "riotId": f"{account.game_name}#{account.tag_line}",
            "region": region_label,
            "owned": True,
            "connected": False,
            "initials": account.game_name[:2].upper(),
            "accent": "#A8CEFF",
            "games": [rank["game"] for rank in ranks],
            "lastUpdated": "Official Riot API",
            "totpAvailable": False,
            "ranks": ranks,
            "matches": matches,
            "puuid": puuid,
            "valorantStatus": "Requires approved VALORANT RSO",
        }
        if warnings:
            result["warnings"] = warnings[:3]
        return result

    def search_player(self, query: str, *, region: str = "", game: str = "all") -> list[dict[str, Any]]:
        region_label = region.strip().upper()
        routes = _REGIONS.get(region_label)
        if region_label and routes is None:
            raise ValueError("Choose a supported Riot platform region")
        requested = game.strip().lower()
        if requested not in {
            "all games",
            "all",
            "league",
            "league of legends",
            "tft",
            "teamfight tactics",
            "valorant",
        }:
            raise ValueError("Choose League, TFT, VALORANT, or All Games")
        local_available = False
        local_error: RuntimeError | None = None
        try:
            local_results = self._local_search_player(
                query,
                region=region_label,
                requested=requested,
            )
            if local_results:
                return self._with_valorant_profile(local_results, requested)
            local_available = True
        except RuntimeError as error:
            local_error = error
        try:
            return self._with_valorant_profile(self._riot_client_search_player(query), requested)
        except RuntimeError as error:
            if local_available:
                return []
            if self._client is None or routes is None:
                # Preserve an explicitly selected legacy region in useful
                # error copy, but query-only searches never guess a shard.
                raise (local_error if region_label and local_error else error) from None
        account_route, platform_route = routes
        game_name, tag_line = _split_riot_id(query)
        try:
            account = self._client.get_account_by_riot_id(
                game_name, tag_line, routing=account_route
            )
        except Exception as error:
            raise RuntimeError(self._safe_provider_error(error, "Player lookup failed")) from None
        all_games = requested in {"all games", "all"}
        use_league = all_games or requested in {"league", "league of legends"}
        use_tft = all_games or requested in {"tft", "teamfight tactics"}
        use_valorant = all_games or requested == "valorant"
        games: list[str] = []
        warnings: list[str] = []
        matches: list[dict[str, Any]] = []
        league_rank: Any | None = None
        tft_rank: Any | None = None
        league_available = False
        tft_available = False

        if use_league:
            games.append("League")
            try:
                ranks = self._client.get_league_ranks(account.puuid, routing=platform_route)
                league_rank = _queue_rank(ranks, "RANKED_SOLO_5x5")
                league_available = True
            except Exception as error:
                league_available = self._is_not_found(error)
                if not self._is_not_found(error):
                    warnings.append(self._safe_provider_error(error, "League rank unavailable"))
            try:
                matches.extend(
                    self._match_rows("League", account.puuid, routing=account_route, count=10)
                )
            except RuntimeError as error:
                warnings.append(str(error))

        if use_tft:
            try:
                tft_ranks = self._client.get_tft_ranks(account.puuid, routing=platform_route)
                tft_rank = _queue_rank(tft_ranks, "RANKED_TFT")
                tft_available = True
            except Exception as error:
                tft_available = self._is_not_found(error)
                if not self._is_not_found(error):
                    warnings.append(self._safe_provider_error(error, "TFT rank unavailable"))
            # Riot's ranked TFT response is the reliable signal that the
            # player has a TFT profile.  Do not imply public TFT history for
            # an account Riot reports as unplayed.
            if tft_rank is not None:
                games.append("TFT")
                try:
                    matches.extend(
                        self._match_rows("TFT", account.puuid, routing=account_route, count=10)
                    )
                except RuntimeError as error:
                    warnings.append(str(error))

        if use_valorant:
            games.append("VALORANT")

        # League and TFT pages are fetched independently.  Merge them into a
        # single newest-first history before limiting the response so the
        # shared detail view does not privilege whichever game was requested
        # first.
        matches.sort(
            key=lambda match: (
                float(match.get("played_at", 0) or 0) if isinstance(match, dict) else 0
            ),
            reverse=True,
        )

        # The detail surface is shared by owned and searched identities.  It
        # always has League and VALORANT panels, while TFT appears only when
        # Riot returned a ranked TFT entry.  No public VALORANT rank/history
        # endpoint is guessed or scraped here.
        rank_views: list[dict[str, Any]] = []
        if league_rank is not None:
            rank_views.append(self._rank_view(league_rank, "League"))
        elif league_available:
            rank_views.append(
                {
                    "game": "League",
                    "tier": "Unranked",
                    "rating": "—",
                    "peak": "Unranked",
                    "icon": "",
                }
            )
        if tft_rank is not None:
            rank_views.append(self._rank_view(tft_rank, "TFT"))
        rank_views.append(self._valorant_rank_view())

        if requested in {"tft", "teamfight tactics"}:
            current_rank = _rank_label(tft_rank) if tft_available else "Rank unavailable"
        elif requested == "valorant":
            current_rank = "Requires approved VALORANT RSO"
        elif league_rank is not None:
            current_rank = _rank_label(league_rank)
        elif tft_rank is not None:
            current_rank = _rank_label(tft_rank)
        else:
            current_rank = "Unranked" if league_available or tft_available else "Rank unavailable"
        if matches:
            first_match = matches[0]
            played_value = first_match.get("playedAt") or first_match.get("played")
            if not played_value:
                timestamp = first_match.get("played_at")
                played_value = (
                    _relative_timestamp(float(timestamp) * 1_000)
                    if isinstance(timestamp, (int, float))
                    else "No recent game"
                )
            last_game = str(played_value)
        else:
            last_game = "No recent game"

        result = {
            "id": account.puuid,
            "riotId": f"{account.game_name}#{account.tag_line}",
            "region": region_label,
            "games": games,
            "currentRank": current_rank,
            "peakRank": "Tracked after watching",
            "lastGame": last_game,
            "lastUpdated": "Official Riot API",
            "followed": False,
            "owned": False,
            "initials": account.game_name[:2].upper(),
            "puuid": account.puuid,
            "ranks": rank_views,
            "matches": matches[:20],
            "valorantStatus": "Requires approved VALORANT RSO",
        }
        if warnings:
            result["warnings"] = warnings[:3]
        return [result]

    def account_overview(self, riot_id: str, region: str) -> dict[str, Any]:
        """Return one controller-shaped account snapshot from official APIs.

        League and VALORANT are always represented.  TFT is represented only
        when Riot returns a ranked TFT entry.  Public VALORANT rank/current
        match data remains explicitly unavailable without approved RSO.
        """

        if self._client is None:
            raise RuntimeError("Live account overview needs a Riot Developer API key in Settings")
        region_label = region.strip().upper()
        routes = _REGIONS.get(region_label)
        if routes is None:
            raise ValueError("League and TFT account refresh needs a supported platform region")
        account_route, platform_route = routes
        game_name, tag_line = _split_riot_id(riot_id)
        try:
            account = self._client.get_account_by_riot_id(
                game_name, tag_line, routing=account_route
            )
        except Exception as error:
            raise RuntimeError(self._safe_provider_error(error, "Player lookup failed")) from None
        return self._overview_for_account(
            account,
            region_label=region_label,
            account_route=account_route,
            platform_route=platform_route,
        )


class CurrentGameService:
    """Windows-first League/TFT detector with privacy-first normalization.

    VALORANT parsing and endpoints live in the adapters, but the distributed
    app does not pretend an undocumented GLZ session is available on macOS or
    without a running authenticated Windows Riot client.
    """

    def __init__(self, *, retry_sleep: Callable[[float], None] = time.sleep) -> None:
        self._last_client_status: dict[str, Any] = {
            "detected": False,
            "label": "Riot Client not detected",
            "path": "",
            "game": "",
        }
        self._valorant_agents: dict[str, str] | None = None
        self._valorant_live_match_id: str | None = None
        self._valorant_live_observed_at_ms = 0
        self._valorant_live_names: dict[str, str] = {}
        self._valorant_live_ranks: dict[str, Any] = {}
        self._valorant_enrichment_key: tuple[str, str] | None = None
        self._valorant_enrichment: Any = None
        self._last_valorant_snapshot_failure: str | None = None
        self._last_session_game: str | None = None
        self._last_session_phase: str | None = None
        self._league_rank_cache: dict[tuple[str, str, str], tuple[float, Any]] = {}
        self._league_profile_cache: dict[tuple[str, str], tuple[float, Any]] = {}
        self._tft_duo_assignments: dict[str, Any] | None = None
        self.detection_available = False
        # Internal identity binding for owned-account refresh; never projected.
        self.active_account_puuid: str | None = None
        self._retry_sleep = retry_sleep

    @property
    def client_status(self) -> dict[str, Any]:
        return dict(self._last_client_status)

    @property
    def valorant_snapshot_failure(self) -> str | None:
        """Return a safe diagnostic code for the most recent owned read."""

        return self._last_valorant_snapshot_failure

    def detect(self) -> dict[str, Any] | None:
        self.detection_available = False
        self.active_account_puuid = None
        if platform.system() != "Windows":
            self._last_client_status = {
                "detected": False,
                "label": "Riot local integration is available on Windows",
                "path": "",
                "game": "",
            }
            return None

        from peaks.adapters.riot.discovery import discover_riot_client
        from peaks.adapters.riot.league import LeagueClient

        discovery = discover_riot_client()
        self._last_client_status = {
            "detected": bool(discovery.process_running or discovery.available),
            "label": discovery.reason,
            "path": str(discovery.executable or ""),
            "game": "",
        }
        league_client = LeagueClient.from_discovery()
        try:
            session_reader = getattr(league_client, "current_session", league_client.current_game)
            league_session = session_reader()
            league_available = bool(league_session or getattr(league_client, "activity_available", False))
            league = self._league_session_view(league_session, league_client) if league_session else None
        finally:
            closer = getattr(league_client, "close", None)
            if callable(closer):
                closer()
        # A client left open in its party lobby must not mask the other game.
        selected: dict[str, Any] | None
        if league and league.get("phase") == "live" and self._last_session_game != "VALORANT":
            selected = league
        else:
            valorant = self._detect_valorant(discovery)
            valorant_available = self.detection_available
            previous_available = league_available if self._last_session_game in {"League", "TFT"} else valorant_available
            if self._last_session_phase in {"live", "pregame", "readycheck"} and not previous_available:
                # Another client's idle lobby is not evidence that the
                # observed match ended when its own telemetry goes missing.
                self.detection_available = False
                return None
            priority = {"live": 4, "pregame": 3, "readycheck": 3, "matchmaking": 2, "lobby": 1}
            selected = max(
                (candidate for candidate in (league, valorant) if candidate),
                key=lambda candidate: (priority.get(candidate.get("phase", ""), 0), candidate.get("game") == self._last_session_game),
                default=None,
            )
            if selected is None:
                self.detection_available = league_available if self._last_session_game in {"League", "TFT"} else valorant_available if self._last_session_game == "VALORANT" else league_available or valorant_available
                return None
        self.detection_available = True
        self._last_session_game = str(selected["game"])
        self._last_session_phase = str(selected.get("phase", ""))
        self._last_client_status["game"] = selected["game"]
        if selected is league:
            self.active_account_puuid = getattr(league_session, "own_puuid", None)
        return selected

    def _league_session_view(self, session: Any, client: Any) -> dict[str, Any]:
        game_label = "TFT" if session.game == "tft" else "League"
        phase = getattr(session, "phase", "live")
        own_puuid = getattr(session, "own_puuid", None)
        now = time.monotonic()
        duos = session.game == "tft" and getattr(session, "team_mode", None) == "duos"
        members = self._tft_duo_roster(session, now) if duos else session.players
        game_time = session.game_time
        if session.game == "tft" and phase == "live" and own_puuid:
            from peaks.adapters.riot.tft_telemetry import read_tft_match

            selves = [index for index, member in enumerate(members) if member.is_self and not member.hidden and member.puuid == own_puuid]
            if len(selves) == 1:
                visible_puuids = tuple(
                    member.puuid if not member.hidden and (member.name or "").strip().casefold() not in {"", "anonymous", "hidden player", "unknown player"} else None
                    for member in members
                )
                telemetry = read_tft_match(getattr(session, "game_id", None), getattr(session, "queue_id", None), own_puuid, visible_puuids)
                if telemetry is not None:
                    members = tuple(
                        replace(
                            member,
                            stats={**snapshot.stats(telemetry.observed_at), **member.stats},
                            team=f"duo:{snapshot.duo}" if duos and snapshot.duo is not None else member.team,
                        ) if snapshot is not None else member
                        for member, snapshot in zip(members, telemetry.players, strict=True)
                    )
                    if game_time is None:
                        game_time = telemetry.game_time
        if not duos:
            self._tft_duo_assignments = None
        self._league_profile_cache = {key: item for key, item in self._league_profile_cache.items() if key[0] == own_puuid and now - item[0] < 300}
        roster = []
        profile_reader = getattr(client, "session_player_profile", None)
        profile_budget = 4
        for member in members:
            name = (member.name or "").strip()
            private = member.hidden or name.casefold() in {"anonymous", "hidden player", "unknown player"}
            if own_puuid and member.puuid and not private and callable(profile_reader) and ("#" not in name or member.account_level is None):
                key = (own_puuid, member.puuid)
                if key not in self._league_profile_cache and profile_budget > 0:
                    profile_budget -= 1
                    try:
                        profile = profile_reader(member)
                    except Exception:
                        profile = None
                    self._league_profile_cache[key] = (now, profile)
                profile = self._league_profile_cache.get(key, (0, None))[1]
                if profile:
                    member = replace(member, name=profile.riot_id, account_level=profile.level if profile.level is not None else member.account_level)
            roster.append(member)
        players = self._safe_players(roster)
        self._league_rank_cache = {key: item for key, item in self._league_rank_cache.items() if key[0] == own_puuid and now - item[0] < 90}
        rank_reader = getattr(client, "ranked_stats", None)
        rank_queue = "RANKED_TFT_DOUBLE_UP" if duos else "RANKED_TFT" if session.game == "tft" else "RANKED_SOLO_5x5"
        rank_budget = 4
        for source, player in zip(session.players, players, strict=True):
            puuid = getattr(source, "puuid", None)
            if not own_puuid or not puuid or player["hidden"] or not callable(rank_reader):
                continue
            rank_key = (own_puuid, puuid, rank_queue)
            if rank_key not in self._league_rank_cache and rank_budget > 0:
                rank_budget -= 1
                try:
                    ranks = rank_reader(puuid, owned=puuid == own_puuid, **({"queue_types": frozenset({rank_queue})} if duos else {}))
                except Exception:
                    ranks = None
                self._league_rank_cache[rank_key] = (now, ranks)
            queues = self._league_rank_cache.get(rank_key, (0, None))[1]
            ranked = _queue_rank(queues, rank_queue)
            if ranked:
                player["rank"] = f"{ranked.tier.title()} {ranked.rank}".strip()
        if session.game == "tft":
            for player in players:
                if duos:
                    group = re.fullmatch(r"duo:([0-3])", player["team"])
                    player["team"] = f"Duo {int(group[1]) + 1}" if group else "Unassigned players"
                else:
                    player["team"] = "Players" if phase == "live" else "Your party"
        status = {"lobby": "Party lobby", "matchmaking": "Searching for a match", "readycheck": "Match found", "pregame": "Champion select", "live": "Match in progress"}[phase]
        teams = self._teams(players)
        if duos:
            for team in teams:
                team["grouping"] = "duo" if re.fullmatch(r"Duo [1-4]", team["name"]) else "unassigned"
        if game_label == "League" and phase == "live":
            for team in teams:
                kills = [player["stats"].get("kills") for player in team["players"]]
                if kills and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in kills):
                    team["score"] = sum(kills)
        result = {
            "game": game_label, "phase": phase,
            "mode": session.game_mode or ("TFT" if game_label == "TFT" else "League"),
            "status": status,
            "streamerMode": any(player["hidden"] for player in players),
            "privacyNote": "Streamer mode respected — hidden identities stay hidden.",
            "freeForAll": session.game == "tft" and phase == "live" and not duos,
            **({"teamMode": "duos"} if duos else {}),
            "teams": teams,
        }
        if session.map_name:
            result["map"] = {"Map11": "Summoner's Rift", "Map12": "Howling Abyss", "Map22": "Teamfight Tactics"}.get(session.map_name, session.map_name)
        if game_time is not None:
            result["elapsed"] = self._format_elapsed(game_time)
        for source_key, target_key in (("game_id", "id"), ("queue_id", "queue"), ("party_size", "partySize"), ("party_max", "partyMax")):
            if source_key == "game_id" and phase not in {"live", "pregame"}:
                continue
            value = getattr(session, source_key, None)
            if value is not None:
                result[target_key] = str(value) if source_key in {"game_id", "queue_id"} else value
        return result

    def _tft_duo_roster(self, session: Any, now: float) -> tuple[Any, ...]:
        """Carry explicit lobby pairings into this match, never list positions."""
        members = tuple(session.players)
        owner = getattr(session, "own_puuid", None)
        scope = (owner, getattr(session, "queue_id", None))
        phase = getattr(session, "phase", "live")
        match_id = getattr(session, "game_id", None)
        groups: dict[str, list[str]] = {}
        for member in members:
            if member.puuid and not member.hidden and re.fullmatch(r"duo:[0-3]", member.team or ""):
                groups.setdefault(member.team, []).append(member.puuid)
        assignments = {subject: group for group, subjects in groups.items() if len(subjects) <= 2 for subject in subjects}
        if not owner:
            self._tft_duo_assignments = None
            return members
        if phase in {"lobby", "matchmaking", "readycheck"}:
            self._tft_duo_assignments = {"scope": scope, "at": now, "match": None, "members": assignments}
            return members
        cached = self._tft_duo_assignments
        if cached and (cached["scope"] != scope or not match_id or cached["match"] not in {None, match_id} or (cached["match"] is None and now - cached["at"] > 120)):
            cached = None
            self._tft_duo_assignments = None
        inherited: dict[str, str] = {}
        if cached and owner in {member.puuid for member in members}:
            cached["match"] = match_id
            present = {member.puuid for member in members if not member.hidden}
            old_groups: dict[str, list[str]] = {}
            for subject, group in cached["members"].items():
                old_groups.setdefault(group, []).append(subject)
            for group, subjects in old_groups.items():
                if len(subjects) == 2 and set(subjects) <= present and group not in groups and not set(subjects).intersection(assignments):
                    inherited.update(dict.fromkeys(subjects, group))
        if match_id:
            self._tft_duo_assignments = {"scope": scope, "at": now, "match": match_id, "members": {**inherited, **assignments}}
        return tuple(replace(member, team=inherited[member.puuid]) if member.puuid in inherited else member for member in members)

    def owned_valorant_rank(self, puuid: str) -> Any | None:
        """Read the signed-in Windows account's VALORANT rank.

        This is intentionally separate from current-game detection.  The
        local PD/MMR endpoint can answer while no match is active, but it is a
        private service and only safe when the entitlement subject returned by
        the authenticated Riot Client exactly matches the account PUUID the
        caller supplied.  No public lookup or reverse resolution is attempted.

        ``None`` is returned for unsupported platforms, an unavailable client,
        an identity mismatch, an incomplete VALORANT log, or a failed request.
        Consequently callers cannot accidentally display a private-service
        failure as a real ``Unranked`` result.
        """

        if not self._valid_owned_puuid(puuid) or platform.system() != "Windows":
            return None
        from peaks.adapters.riot.discovery import discover_riot_client

        discovery = discover_riot_client()
        if discovery.lockfile is None:
            return None
        with self._open_valorant_client(discovery) as authenticated:
            if authenticated is None:
                return None
            client, subject = authenticated
            # Strict equality is deliberate: a caller must never use the
            # signed-in client's token to query an arbitrary PUUID.
            if subject != puuid:
                return None
            return client.rank_optional()

    # Explicit alias for callers that prefer the read operation's verb.
    get_owned_valorant_rank = owned_valorant_rank

    def owned_valorant_snapshot(self, puuid: str, *, priority_match_id: str | None = None) -> dict[str, Any] | None:
        """Read the signed-in account's rank and bounded recent match list.

        The entitlement subject is compared with ``puuid`` before either
        private endpoint is queried.  The result deliberately contains no
        access token, entitlement token, raw provider payload, or other
        players' identifiers.
        """

        self._last_valorant_snapshot_failure = None
        supported = platform.system() == "Windows"
        valid_account = self._valid_owned_puuid(puuid)
        LOGGER.info(
            "current_game.owned_snapshot.start supported=%s valid_account=%s",
            supported,
            valid_account,
        )
        if not valid_account or not supported:
            self._last_valorant_snapshot_failure = "precondition"
            LOGGER.info("current_game.owned_snapshot.unavailable reason=precondition")
            return None
        from peaks.adapters.riot.discovery import discover_riot_client

        discovery = discover_riot_client()
        if discovery.lockfile is None:
            self._last_valorant_snapshot_failure = "lockfile"
            LOGGER.info("current_game.owned_snapshot.unavailable reason=lockfile")
            return None
        with self._open_valorant_client(discovery) as authenticated:
            if authenticated is None:
                if self._last_valorant_snapshot_failure is None:
                    self._last_valorant_snapshot_failure = "authentication"
                LOGGER.info("current_game.owned_snapshot.unavailable reason=authentication")
                return None
            client, subject = authenticated
            if subject != puuid:
                self._last_valorant_snapshot_failure = "identity_mismatch"
                LOGGER.warning("current_game.owned_snapshot.unavailable reason=identity_mismatch")
                return None
            level: int | None = None
            level_reader = getattr(client, "account_level_optional", None)
            if callable(level_reader):
                try:
                    level = level_reader()
                except Exception as exc:
                    LOGGER.info(
                        "current_game.owned_snapshot.level_unavailable error_type=%s",
                        type(exc).__name__,
                    )
            rank = client.rank_optional()
            if priority_match_id:
                client.priority_match_id = priority_match_id
            matches = client.match_history(limit=20)
        if level is None and rank is None and not matches:
            self._last_valorant_snapshot_failure = "no_data"
            LOGGER.info("current_game.owned_snapshot.unavailable reason=no_data")
            return None

        snapshot = self._valorant_snapshot_view(level, rank, matches)
        routing = getattr(self, "_valorant_enrichment_key", None)
        if routing and routing[0] == puuid:
            route = re.fullmatch(r"https://pd\.([a-z0-9-]+)\.a\.pvp\.net/?", routing[1])
            region = normalize_valorant_region(route.group(1)) if route else None
            if region:
                snapshot["valorantRegion"] = region
        LOGGER.info(
            "current_game.owned_snapshot.complete level_available=%s rank_count=%s match_count=%s",
            level is not None, len(snapshot["ranks"]), len(snapshot["matches"]),
        )
        self._last_valorant_snapshot_failure = None
        return snapshot

    def valorant_player_snapshot(self, puuid: str) -> dict[str, Any] | None:
        """Read an exact searched identity using the current client's shard.

        Search has already resolved the Riot ID. Its player perspective stays
        separate from signed-in account snapshots and live-match caches.
        """
        if platform.system() != "Windows" or not self._valid_owned_puuid(puuid):
            return None
        from peaks.adapters.riot.discovery import discover_riot_client

        with self._open_valorant_client(discover_riot_client()) as authenticated:
            if authenticated is None:
                return None
            client, _ = authenticated
            profile = client.player_profile(puuid, limit=10)
        if profile is None:
            return None
        snapshot = self._valorant_snapshot_view(profile.level, profile.rank, profile.matches)
        if profile.rank is not None:
            if profile.rank.current_available:
                snapshot["currentRank"] = profile.rank.name
            if profile.rank.peak_tier >= 3:
                snapshot["peakRank"] = profile.rank.peak_name
                if profile.rank.peak_season:
                    snapshot["peakRankSeason"] = profile.rank.peak_season
        if self._valorant_enrichment_key:
            route = re.fullmatch(r"https://pd\.([a-z0-9-]+)\.a\.pvp\.net/?", self._valorant_enrichment_key[1])
            if route:
                snapshot["region"] = route.group(1).upper()
        return snapshot

    def _valorant_snapshot_view(
        self, level: int | None, rank: ValorantRank | None,
        matches: tuple[ValorantMatchSummary, ...],
    ) -> dict[str, Any]:
        """Shared sanitized presentation for owned and explicitly searched profiles."""
        ranks: list[dict[str, Any]] = []
        if rank is not None and rank.current_available:
            ranks.append(
                {
                    "game": "valorant",
                    "tier": rank.name,
                    "rating": rank.rr,
                    "peak_tier": rank.peak_name,
                }
            )
        from peaks.adapters.riot.valorant import rank_name
        from peaks.adapters.riot.valorant_enrichment import rank_presentation

        agent_names = self._valorant_agent_names()
        rows: list[dict[str, Any]] = []
        for match in matches:
            played_at: str | None = None
            if match.started_at_ms is not None:
                try:
                    played_at = datetime.fromtimestamp(match.started_at_ms / 1_000, UTC).isoformat()
                except (OSError, OverflowError, ValueError):
                    played_at = None
            team_views: list[dict[str, Any]] = []
            own_statistics: dict[str, Any] = {}
            hidden_index = 0
            player_index = 0
            for team in match.teams:
                members: list[dict[str, Any]] = []
                for player in team.players:
                    player_index += 1
                    if player.hidden:
                        hidden_index += 1
                    if player.hidden:
                        name = f"Hidden player {hidden_index}"
                    elif player.riot_id:
                        name = player.riot_id
                    else:
                        name = f"Player {player_index}"
                    statistics: dict[str, Any] = {
                        key: value
                        for key, value in {
                            "kills": player.kills,
                            "deaths": player.deaths,
                            "assists": player.assists,
                            "combatScore": player.combat_score,
                            "roundsPlayed": player.rounds_played,
                            "roundsAnalyzed": player.rounds_analyzed,
                            "headshots": player.headshots,
                            "bodyshots": player.bodyshots,
                            "legshots": player.legshots,
                            "damage": player.damage,
                        }.items()
                        if value is not None
                    }
                    if player.weapon_usage is not None:
                        statistics["weaponUsage"] = [
                            {"weapon": weapon, "kills": kills}
                            for weapon, kills in player.weapon_usage
                        ]
                    if player.round_kills is not None:
                        statistics["roundKills"] = list(player.round_kills)
                    if player.self:
                        own_statistics = statistics
                    score = (
                        f"{player.kills} / {player.deaths} / {player.assists}"
                        if player.kills is not None
                        and player.deaths is not None
                        and player.assists is not None
                        else None
                    )
                    members.append(
                        {
                            "name": name,
                            "riotId": player.riot_id,
                            "agent": agent_names.get(
                                str(player.character_id or "").lower(),
                                "Agent unavailable",
                            ),
                            "rank": rank_name(player.competitive_tier),
                            "rankTier": player.competitive_tier,
                            "score": score,
                            "stats": statistics,
                            "self": player.self,
                            "hidden": player.hidden,
                            **({"accountLevel": player.account_level} if player.account_level is not None else {}),
                            **({"partyId": player.party_id} if player.party_id else {}),
                            **rank_presentation(player.current_rank),
                            **({"overallStats": dict(player.overall_stats)} if player.overall_stats else {}),
                            "statsLoading": player.stats_loading and not player.hidden,
                        }
                    )
                team_views.append(
                    {
                        "name": team.name,
                        "score": team.score,
                        "won": team.won,
                        "players": members,
                    }
                )
            rows.append(
                {
                    "match_id": match.match_id,
                    "game": "valorant",
                    "played_at": played_at,
                    "result": match.result,
                    "queue": match.queue_id,
                    "map_name": self._valorant_map_name(match.map_id),
                    "duration_seconds": match.duration_seconds,
                    "kills": own_statistics.get("kills"),
                    "deaths": own_statistics.get("deaths"),
                    "assists": own_statistics.get("assists"),
                    "metadata": {
                        "score": (
                            f"{match.own_score}-{match.opponent_score}"
                            if not match.free_for_all
                            and match.own_score is not None
                            and match.opponent_score is not None
                            else None
                        ),
                        "teams": team_views,
                        "freeForAll": match.free_for_all,
                        **({"enrichmentPending": True} if match.enrichment_pending else {}),
                    },
                }
            )
        snapshot: dict[str, Any] = {"ranks": ranks, "matches": rows}
        if level is not None:
            snapshot["level"] = level
        return snapshot

    refresh_owned_valorant_account = owned_valorant_snapshot

    def owned_league_snapshot(self, puuid: str) -> dict[str, Any] | None:
        """Read League/TFT queues only for the exact signed-in owned identity."""
        if platform.system() != "Windows" or not self._valid_owned_puuid(puuid):
            return None
        from peaks.adapters.riot.league import LeagueClient

        client = LeagueClient.from_discovery()
        try:
            profile = client.current_profile(puuid)
            if profile is None:
                return None
            queues = client.ranked_stats(puuid, owned=True)
            snapshot: dict[str, Any] = {
                "ranks": [RiotSearchService._rank_view(entry, "TFT" if entry.queue_type == "RANKED_TFT" else "League") for entry in queues or ()],
            }
            if profile.level is not None:
                snapshot["level"] = profile.level
            return snapshot or None
        except Exception as exc:
            LOGGER.info("current_game.owned_league.unavailable error_type=%s", type(exc).__name__)
            return None
        finally:
            client.close()

    def owned_league_platform_region(self, puuid: str) -> str | None:
        """Return the active owned account's authoritative League/TFT shard.

        The League local client is used only after its lockfile PID is bound to
        a live League client owner in the Riot installation. The current
        summoner PUUID must then exactly match ``puuid`` before the platform
        value is read. Riot ID tags and locale/IP are never used as guesses.
        """

        supported = platform.system() == "Windows"
        valid_account = self._valid_owned_puuid(puuid)
        LOGGER.info(
            "current_game.owned_region.start supported=%s valid_account=%s",
            supported,
            valid_account,
        )
        if not supported or not valid_account:
            LOGGER.info("current_game.owned_region.unavailable reason=precondition")
            return None

        from peaks.adapters.riot.client import RiotClientHTTP
        from peaks.adapters.riot.discovery import discover_verified_league_lockfile
        from peaks.adapters.riot.league import (
            CURRENT_SUMMONER_PATH,
            REGION_LOCALE_PATH,
            normalize_platform_region,
        )

        lockfile = discover_verified_league_lockfile()
        if lockfile is None:
            LOGGER.info("current_game.owned_region.unavailable reason=lockfile")
            return None
        try:
            with RiotClientHTTP(lockfile) as client:
                summoner = client.get_json(CURRENT_SUMMONER_PATH)
                if not isinstance(summoner, dict) or summoner.get("puuid") != puuid:
                    LOGGER.info("current_game.owned_region.unavailable reason=identity_mismatch")
                    return None
                region_locale = client.get_json(REGION_LOCALE_PATH)
        except Exception as exc:
            LOGGER.info(
                "current_game.owned_region.unavailable reason=local_request error_type=%s",
                type(exc).__name__,
            )
            return None
        if not isinstance(region_locale, dict):
            LOGGER.info("current_game.owned_region.unavailable reason=region_payload")
            return None
        region = normalize_platform_region(region_locale.get("region"))
        if region is None:
            LOGGER.info("current_game.owned_region.unavailable reason=unsupported_region")
            return None
        LOGGER.info("current_game.owned_region.complete region=%s", region.casefold())
        return region

    @staticmethod
    def _valid_owned_puuid(puuid: object) -> bool:
        return (
            isinstance(puuid, str)
            and bool(puuid)
            and puuid == puuid.strip()
            and len(puuid) <= 256
            and not any(ord(char) < 0x20 or ord(char) == 0x7F for char in puuid)
        )

    @staticmethod
    def _valid_valorant_client_version(value: object) -> bool:
        return isinstance(value, str) and re.fullmatch(
            r"[a-z0-9][a-z0-9._-]{0,127}", value, re.I
        ) is not None

    @classmethod
    def _valorant_product_version(cls, payload: object) -> str | None:
        """Return the one active VALORANT product-session version.

        Riot's local endpoint can include Riot Client and game sessions. Only
        an exact VALORANT product record is relevant; ambiguous active records
        fail closed so an unrelated/stale version never becomes an authenticated
        remote-service header.
        """

        if not isinstance(payload, Mapping):
            return None
        versions: list[str] = []
        terminal_phases = {
            "",
            "none",
            "null",
            "complete",
            "completed",
            "failed",
            "stopped",
            "terminated",
        }
        for value in payload.values():
            if not isinstance(value, Mapping):
                continue
            if str(value.get("productId") or "").casefold() != "valorant":
                continue
            phase = str(value.get("phase") or "").casefold()
            if phase in terminal_phases:
                continue
            version = value.get("version")
            if not cls._valid_valorant_client_version(version):
                return None
            versions.append(cast(str, version))
        return versions[0] if len(versions) == 1 else None

    @staticmethod
    def _has_active_valorant_product_session(payload: object) -> bool | None:
        """Distinguish an idle Riot service from an active VALORANT session."""

        if not isinstance(payload, Mapping):
            return None
        terminal_phases = {
            "",
            "none",
            "null",
            "complete",
            "completed",
            "failed",
            "stopped",
            "terminated",
        }
        for value in payload.values():
            if not isinstance(value, Mapping):
                continue
            if str(value.get("productId") or "").casefold() != "valorant":
                continue
            phase = str(value.get("phase") or "").casefold()
            if phase not in terminal_phases:
                return True
        return False

    @contextmanager
    def _open_valorant_client(self, discovery: Any) -> Iterator[tuple[Any, str] | None]:
        """Open a short-lived authenticated VALORANT service client.

        The lockfile password, entitlements, and access token stay inside
        this context and are discarded when the remote transport is closed.
        No credential-bearing client is returned to the UI or persisted.
        """

        if getattr(discovery, "lockfile", None) is None:
            self._last_valorant_snapshot_failure = "lockfile"
            LOGGER.info("current_game.valorant_auth.unavailable reason=lockfile")
            yield None
            return
        from peaks.adapters.riot.client import RiotClientHTTP
        from peaks.adapters.riot.discovery import valorant_log_path
        from peaks.adapters.riot.valorant import ValorantClient, ValorantRemoteHTTP

        try:
            local = RiotClientHTTP(discovery.lockfile)
        except Exception as exc:
            self._last_valorant_snapshot_failure = "local_client"
            LOGGER.info(
                "current_game.valorant_auth.unavailable reason=local_client error_type=%s",
                type(exc).__name__,
            )
            yield None
            return
        product_sessions: object = None
        product_sessions_known = False
        entitlements: object = None
        entitlements_error: Exception | None = None
        try:
            try:
                product_sessions = local.get_json("/product-session/v1/external-sessions")
                product_sessions_known = True
            except Exception as exc:
                # The log still carries a compatible version fallback. A
                # product-session failure must not discard valid entitlements.
                LOGGER.info(
                    "current_game.valorant_auth.product_session_unavailable error_type=%s",
                    type(exc).__name__,
                )
            if not (
                product_sessions_known
                and self._has_active_valorant_product_session(product_sessions) is False
            ):
                for attempt in range(3):
                    try:
                        entitlements = local.get_json("/entitlements/v1/token")
                        entitlements_error = None
                        break
                    except Exception as exc:
                        entitlements_error = exc
                        if (
                            getattr(exc, "detail_code", None) == "entitlements_not_ready"
                            and attempt < 2
                        ):
                            LOGGER.info(
                                "current_game.valorant_auth.entitlements_retry attempt=%s",
                                attempt + 2,
                            )
                            self._retry_sleep(0.25 * (attempt + 1))
                            continue
                        break
        finally:
            local.close()
        if (
            product_sessions_known
            and self._has_active_valorant_product_session(product_sessions) is False
        ):
            self._last_valorant_snapshot_failure = "valorant_session_inactive"
            LOGGER.info(
                "current_game.valorant_auth.unavailable reason=valorant_session_inactive"
            )
            yield None
            return
        if entitlements_error is not None:
            status_code = getattr(entitlements_error, "status_code", None)
            detail_code = getattr(entitlements_error, "detail_code", None)
            reason = (
                "entitlements_not_ready"
                if detail_code == "entitlements_not_ready"
                else "entitlements"
            )
            self._last_valorant_snapshot_failure = reason
            LOGGER.info(
                "current_game.valorant_auth.unavailable reason=%s error_type=%s status=%s",
                reason,
                type(entitlements_error).__name__,
                status_code if isinstance(status_code, int) else "unknown",
            )
            yield None
            return
        if entitlements is None:
            self._last_valorant_snapshot_failure = "entitlements"
            LOGGER.info(
                "current_game.valorant_auth.unavailable reason=entitlements "
                "error_type=MissingPayload",
            )
            yield None
            return
        if not isinstance(entitlements, dict):
            self._last_valorant_snapshot_failure = "entitlements_payload"
            LOGGER.info("current_game.valorant_auth.unavailable reason=entitlements_payload")
            yield None
            return
        access_token = entitlements.get("accessToken")
        entitlements_token = entitlements.get("token")
        subject = entitlements.get("subject")
        if not self._valid_owned_puuid(subject):
            self._last_valorant_snapshot_failure = "subject"
            LOGGER.info("current_game.valorant_auth.unavailable reason=subject")
            yield None
            return
        if not self._valid_secret_text(access_token) or not self._valid_secret_text(
            entitlements_token
        ):
            self._last_valorant_snapshot_failure = "credentials"
            LOGGER.info("current_game.valorant_auth.unavailable reason=credentials")
            yield None
            return
        # The validators above establish bounded strings.  Keep the casts
        # local so credential-bearing values never widen this context's
        # public result type.
        access_token_text = cast(str, access_token)
        entitlements_token_text = cast(str, entitlements_token)
        subject_text = cast(str, subject)
        pd_url, glz_url, log_client_version = self._valorant_log_service_parts(
            valorant_log_path()
        )
        if pd_url is None or glz_url is None:
            self._last_valorant_snapshot_failure = "service_routes"
            LOGGER.info("current_game.valorant_auth.unavailable reason=service_routes")
            yield None
            return
        client_version = self._valorant_product_version(product_sessions) or log_client_version
        if not self._valid_valorant_client_version(client_version):
            self._last_valorant_snapshot_failure = "service_version"
            LOGGER.info("current_game.valorant_auth.unavailable reason=service_version")
            yield None
            return
        client_version_text = cast(str, client_version)
        platform_payload = base64.b64encode(
            b'{"platformType":"PC","platformOS":"Windows","platformOSVersion":"10.0.22631","platformChipset":"Unknown"}'
        ).decode("ascii")
        try:
            remote = ValorantRemoteHTTP(
                pd_url=pd_url,
                glz_url=glz_url,
                headers={
                    "Authorization": f"Bearer {access_token_text}",
                    "X-Riot-Entitlements-JWT": entitlements_token_text,
                    "X-Riot-ClientPlatform": platform_payload,
                    "X-Riot-ClientVersion": client_version_text,
                },
            )
        except Exception as exc:
            self._last_valorant_snapshot_failure = "remote_client"
            LOGGER.info(
                "current_game.valorant_auth.unavailable reason=remote_client error_type=%s",
                type(exc).__name__,
            )
            yield None
            return
        try:
            self._last_valorant_snapshot_failure = None
            LOGGER.debug("current_game.valorant_auth.ready")
            from peaks.adapters.riot.valorant_enrichment import ValorantEnrichmentCache

            cache_key = (subject_text, pd_url)
            if self._valorant_enrichment_key != cache_key:
                self._valorant_enrichment_key = cache_key
                self._valorant_enrichment = ValorantEnrichmentCache()
            client = ValorantClient(remote, subject_text)
            client.enrichment = self._valorant_enrichment
            yield client, subject_text
        finally:
            remote.close()

    @staticmethod
    def _valid_secret_text(value: object) -> bool:
        return (
            isinstance(value, str)
            and bool(value)
            and len(value) <= 8_192
            and not any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
        )

    def _detect_valorant(self, discovery: Any) -> dict[str, Any] | None:
        self.detection_available = False
        self.active_account_puuid = None
        with self._open_valorant_client(discovery) as authenticated:
            if authenticated is None:
                return None
            client, puuid = authenticated
            match = client.detect()
            self.detection_available = match is not None or bool(
                getattr(client, "activity_available", False)
            )
            self.active_account_puuid = puuid
            own_rank = client.rank() if match is not None else None
            if match is None:
                self._valorant_live_match_id = None
                self._valorant_live_observed_at_ms = 0
                self._valorant_live_names.clear()
                self._valorant_live_ranks.clear()
                return self._valorant_lobby_view(client, puuid)
            if match.match_id != self._valorant_live_match_id:
                self._valorant_live_match_id = match.match_id
                self._valorant_live_observed_at_ms = int(time.time() * 1_000)
                self._valorant_live_names.clear()
                self._valorant_live_ranks.clear()

            own_team_id = next((player.team_id for player in match.players if player.subject == puuid), None)
            own_team_subjects = tuple(player.subject for player in match.players if own_team_id and player.team_id == own_team_id)
            party = None
            party_reader = getattr(client, "own_party", None)
            if callable(party_reader):
                try:
                    party = party_reader(own_team_subjects=own_team_subjects)
                except Exception as exc:
                    LOGGER.debug("current_game.valorant_party.unavailable error_type=%s", type(exc).__name__)
            presence = self._own_valorant_presence(discovery, puuid, match, bool(getattr(party, "owner_in_own_team", False)))
            party_size = party.size if party is not None else presence.party_size
            party_max = presence.party_max if party_size == presence.party_size else None
            if party_max is None and party is not None:
                party_max = party.maximum

            if own_rank is not None:
                self._valorant_live_ranks[puuid] = own_rank

            # Riot's match payload is the privacy authority. Never send an
            # Incognito subject to the display-name service. Cache successful
            # lookups for this match so the 15-second activity poll does not
            # repeatedly query an unchanged roster.
            visible_subjects = tuple(
                player.subject for player in match.players if not player.incognito
            )
            missing_names = tuple(
                subject
                for subject in visible_subjects
                if subject not in self._valorant_live_names
            )
            name_resolver = getattr(client, "player_names", None)
            if missing_names and callable(name_resolver):
                try:
                    resolved_names = name_resolver(missing_names)
                    if isinstance(resolved_names, Mapping):
                        self._valorant_live_names.update(
                            {
                                str(subject): str(name)
                                for subject, name in resolved_names.items()
                                if subject in missing_names
                                and isinstance(name, str)
                                and name
                                and len(name) <= 256
                                and not any(ord(character) < 0x20 for character in name)
                            }
                        )
                except Exception as exc:
                    LOGGER.info(
                        "current_game.valorant_names.unavailable error_type=%s",
                        type(exc).__name__,
                    )

            roster_subjects = tuple(player.subject for player in match.players)
            missing_ranks = tuple(
                subject
                for subject in roster_subjects
                if subject not in self._valorant_live_ranks
            )
            rank_resolver = getattr(client, "live_player_ranks", None)
            if missing_ranks and callable(rank_resolver):
                try:
                    resolved_ranks = rank_resolver(missing_ranks)
                    if isinstance(resolved_ranks, Mapping):
                        self._valorant_live_ranks.update(
                            {
                                str(subject): rank
                                for subject, rank in resolved_ranks.items()
                                if subject in missing_ranks
                            }
                        )
                except Exception as exc:
                    LOGGER.info(
                        "current_game.valorant_ranks.unavailable error_type=%s",
                        type(exc).__name__,
                    )
            live_names = dict(self._valorant_live_names)
            live_ranks = dict(self._valorant_live_ranks)
            live_profiles: Mapping[str, Any] = {}
            profile_resolver = getattr(client, "live_player_profiles", None)
            if callable(profile_resolver):
                try:
                    profiles = profile_resolver(visible_subjects)
                    if isinstance(profiles, Mapping):
                        live_profiles = {subject: profile for subject, profile in profiles.items() if subject in visible_subjects and isinstance(profile, Mapping)}
                except Exception as exc:
                    LOGGER.info("current_game.valorant_profiles.unavailable error_type=%s", type(exc).__name__)
        from peaks.adapters.riot.valorant import is_free_for_all

        phase = "live" if type(match).__name__ == "ValorantCoregame" else "pregame"
        queue_id = match.queue_id or presence.queue_id
        free_for_all = match.free_for_all or is_free_for_all(queue_id, match.mode_id)
        agent_names = self._valorant_agent_names()
        hidden_count = 0
        privacy_mode = False
        teams: dict[str, list[dict[str, Any]]] = {}
        for index, player in enumerate(match.players, start=1):
            is_self = player.subject == puuid
            if player.incognito:
                hidden_count += 1
                privacy_mode = True
            fallback_name = "You" if is_self else f"Player {index}"
            display_name = live_names.get(player.subject) or fallback_name
            placeholder = f"Hidden player {hidden_count}" if player.incognito else fallback_name
            safe_player = redact_player(
                {
                    "subject": player.subject,
                    "display_name": display_name,
                    "team_id": player.team_id,
                    "character_id": player.character_id,
                    "player_card_id": player.player_card_id,
                    "Incognito": player.incognito,
                    "isSelf": is_self,
                },
                streamer_mode=False,
                is_self=is_self,
                placeholder=placeholder,
            )
            redacted = bool(safe_player.get("redacted"))
            name = str(safe_player.get("display_name") or placeholder)
            player_rank = live_ranks.get(player.subject)
            teams.setdefault("Free for all" if free_for_all else player.team_id or "Players", []).append(
                {
                    "name": name,
                    "riotId": name if not redacted and "#" in name else None,
                    "agent": agent_names.get(
                        str(player.character_id or "").lower(), "Agent not selected"
                    ),
                    "rank": (str(getattr(player_rank, "name", "") or "") or None) if getattr(player_rank, "current_available", True) else None,
                    "rankTier": int(getattr(player_rank, "tier", 0) or 0),
                    "score": "—",
                    "self": is_self,
                    "hidden": redacted,
                    "accountLevel": player.account_level,
                    "partyId": player.party_id,
                    **(dict(live_profiles.get(player.subject, {})) if not redacted else {}),
                }
            )
        map_name = self._valorant_map_name(match.map_id)
        mode = queue_id or match.mode_id or ("In game" if phase == "live" else "Agent select")
        team_scores: dict[str, int] = {}
        own_teams = {player.team_id for player in match.players if player.subject == puuid and player.team_id}
        if phase == "live" and not free_for_all and len(teams) == 2 and len(own_teams) == 1 and presence.ally_score is not None and presence.enemy_score is not None:
            own_team = next(iter(own_teams))
            if own_team in teams:
                team_scores = {team: presence.ally_score if team == own_team else presence.enemy_score for team in teams}
        return {
            "id": match.match_id,
            "phase": phase,
            "game": "VALORANT",
            "mode": mode,
            **({"queue": queue_id} if queue_id else {}),
            **({"modeId": match.mode_id} if match.mode_id else {}),
            "freeForAll": free_for_all,
            "map": map_name,
            "elapsed": "Live",
            **({"partySize": party_size} if party_size is not None else {}),
            **({"partyMax": party_max} if party_max is not None else {}),
            "status": "Live from the authenticated local Riot Client",
            "streamerMode": privacy_mode,
            "privacyNote": (
                "Riot privacy respected — only players marked incognito stay hidden."
                if privacy_mode
                else "Riot privacy respected — no player in this roster is marked incognito."
            ),
            "teams": [
                {
                    "name": team if team in {"Blue", "Red", "Players", "Free for all"} else f"Team {index}",
                    "score": team_scores.get(team, "—"),
                    "players": members,
                }
                for index, (team, members) in enumerate(teams.items(), start=1)
            ],
        }

    def _valorant_lobby_view(self, client: Any, puuid: str) -> dict[str, Any] | None:
        from peaks.adapters.riot.valorant import rank_name

        reader = getattr(client, "own_party", None)
        if not callable(reader):
            return None
        try:
            party = reader()
        except Exception as exc:
            LOGGER.debug("current_game.valorant_party.unavailable error_type=%s", type(exc).__name__)
            return None
        if party is None or party.phase not in {"lobby", "matchmaking", "readycheck"} or not party.members:
            return None
        self.detection_available = True
        visible = tuple(member.puuid for member in party.members if not member.incognito)
        names: Mapping[str, Any] = {}
        profiles: Mapping[str, Any] = {}
        for method, target in (("player_names", "names"), ("live_player_profiles", "profiles")):
            resolver = getattr(client, method, None)
            if not callable(resolver) or not visible:
                continue
            try:
                values = resolver(visible)
                if isinstance(values, Mapping):
                    if target == "names":
                        names = values
                    else:
                        profiles = values
            except Exception as exc:
                LOGGER.debug("current_game.valorant_party.enrichment_unavailable error_type=%s", type(exc).__name__)
        teams: dict[str, list[dict[str, Any]]] = {}
        for index, member in enumerate(party.members, start=1):
            hidden = member.incognito
            name = names.get(member.puuid)
            if not isinstance(name, str) or not name.strip() or len(name) > 256 or any(ord(char) < 0x20 or ord(char) == 0x7F for char in name):
                name = "You" if member.puuid == puuid else f"Player {index}"
            if hidden:
                name = f"Hidden player {index}"
            profile = profiles.get(member.puuid)
            group = {"teamOne": "Blue", "teamTwo": "Red", "teamSpectate": "Spectators", "teamOneCoaches": "Blue coaches", "teamTwoCoaches": "Red coaches"}.get(member.team, "Your party")
            teams.setdefault(group, []).append({
                **(dict(profile) if not hidden and isinstance(profile, Mapping) else {}),
                "name": name,
                "riotId": name if not hidden and "#" in name else None,
                "self": member.puuid == puuid, "hidden": hidden,
                "rank": rank_name(member.competitive_tier) if member.competitive_tier is not None else None,
                "accountLevel": member.account_level if not member.account_level_hidden else None,
                "leader": member.is_owner,
                **({"ready": member.is_ready} if member.is_ready is not None else {}),
                "partyId": "party-1" if party.size > 1 else None,
            })
        result: dict[str, Any] = {
            "game": "VALORANT", "phase": party.phase,
            "mode": party.queue_id or ("Custom" if party.mode_id else "Party"),
            "partySize": party.size,
            "status": {"lobby": "Party lobby", "matchmaking": "Searching for a match", "readycheck": "Match found"}[party.phase],
            "streamerMode": any(member.incognito for member in party.members),
            "teams": [{"name": team, "players": members} for team, members in teams.items()],
        }
        if party.maximum is not None:
            result["partyMax"] = party.maximum
        if party.queue_id:
            result["queue"] = party.queue_id
        if party.mode_id:
            result["modeId"] = party.mode_id
        if party.map_id:
            result["map"] = self._valorant_map_name(party.map_id)
        if party.phase == "matchmaking" and party.queue_started_at:
            try:
                started = datetime.fromisoformat(party.queue_started_at.replace("Z", "+00:00"))
                if started.tzinfo is not None:
                    result["elapsed"] = self._format_elapsed((datetime.now(UTC) - started).total_seconds())
            except ValueError:
                pass
        return result

    def _own_valorant_presence(self, discovery: Any, puuid: str, match: ValorantCoregame | ValorantPregame, party_owner_in_own_team: bool = False) -> ValorantPresence:
        from peaks.adapters.riot.client import RiotClientHTTP
        from peaks.adapters.riot.valorant_presence import ValorantPresence, parse_own_presence

        lockfile = getattr(discovery, "lockfile", None)
        if lockfile is None:
            return ValorantPresence()
        try:
            # discovery already verified PID/executable, and puuid came from
            # this lockfile's entitlement session. Friend rows are discarded by
            # the parser; raw presence/private JWTs never leave this read.
            with RiotClientHTTP(lockfile, timeout=2.0) as local:
                payload = local.get_json("/chat/v4/presences")
            return parse_own_presence(
                payload,
                subject=puuid,
                match_id=match.match_id,
                map_id=match.map_id,
                phase="live" if type(match).__name__ == "ValorantCoregame" else "pregame",
                observed_at_ms=self._valorant_live_observed_at_ms,
                now_ms=int(time.time() * 1_000),
                party_owner_in_own_team=party_owner_in_own_team,
            )
        except Exception as exc:
            LOGGER.debug("current_game.valorant_presence.unavailable error_type=%s", type(exc).__name__)
            return ValorantPresence()

    @classmethod
    def _valorant_service_info(
        cls,
        path: Path | None,
        *,
        client_version: str | None = None,
    ) -> tuple[str, str, str] | None:
        pd_url, glz_url, log_client_version = cls._valorant_log_service_parts(path)
        version = client_version or log_client_version
        if (
            pd_url is None
            or glz_url is None
            or not cls._valid_valorant_client_version(version)
        ):
            return None
        return pd_url, glz_url, cast(str, version)

    @staticmethod
    def _valorant_log_service_parts(
        path: Path | None,
    ) -> tuple[str | None, str | None, str | None]:
        """Read bounded routing/version facts from ShooterGame.log.

        Product-session metadata is authoritative for the live build version;
        the log version returned here exists only for compatibility/fallback.
        """

        if path is None:
            return None, None, None
        try:
            with path.open("rb") as stream:
                stream.seek(0, 2)
                size = stream.tell()
                # Riot writes the client version once near process startup,
                # while the current PD/GLZ routing hosts continue to appear
                # throughout play.  Reading only the tail therefore stops
                # working as soon as a busy ShooterGame.log grows past the
                # tail window.  Keep the read bounded, but combine a small
                # startup window with the newest service traffic.  Head is
                # placed first so ``matches[-1]`` still selects current hosts
                # (and a newer version line, if Riot emits one later).
                tail_bytes = 8 * 1024 * 1024
                head_bytes = 1024 * 1024
                chunks: tuple[bytes, ...]
                if size <= tail_bytes:
                    stream.seek(0)
                    chunks = (stream.read(tail_bytes),)
                else:
                    stream.seek(0)
                    head = stream.read(head_bytes)
                    stream.seek(max(0, size - tail_bytes))
                    tail = stream.read(tail_bytes)
                    chunks = (head, tail)
                text = b"\n".join(chunks).decode("utf-8", errors="ignore")
        except OSError:
            return None, None, None
        pd_matches = re.findall(r"https://pd\.([a-z0-9-]+)\.a\.pvp\.net", text, re.I)
        if not pd_matches:
            pd_matches = re.findall(
                r"https://[^\s]+\.([a-z0-9-]+)\.a\.pvp\.net/account-xp", text, re.I
            )
        glz_matches = re.findall(r"https://(glz-[a-z0-9-]+\.[a-z0-9-]+\.a\.pvp\.net)", text, re.I)
        # This value becomes an HTTP header.  Accept only Riot's documented
        # token-like build format rather than arbitrary log text.
        version_matches = re.findall(
            r"CI server version:\s*([a-z0-9][a-z0-9._-]{0,127})",
            text,
            re.I,
        )
        pd_url = f"https://pd.{pd_matches[-1].lower()}.a.pvp.net" if pd_matches else None
        glz_url = f"https://{glz_matches[-1]}" if glz_matches else None
        client_version = version_matches[-1] if version_matches else None
        return pd_url, glz_url, client_version

    def _valorant_agent_names(self) -> dict[str, str]:
        if self._valorant_agents is not None:
            return self._valorant_agents
        try:
            from peaks.adapters.providers.valorant_metadata import ValorantMetadataClient

            assets = ValorantMetadataClient().get_agent_assets(playable_only=True)
            self._valorant_agents = {asset.uuid.lower(): asset.display_name for asset in assets}
        except Exception:
            self._valorant_agents = {}
        return self._valorant_agents

    @staticmethod
    def _valorant_map_name(map_id: str | None) -> str:
        if not map_id:
            return "Unknown map"
        parts = [part for part in map_id.replace("\\", "/").split("/") if part]
        if not parts:
            return "Unknown map"
        candidate = parts[-1]
        if len(parts) >= 2 and candidate.casefold() == parts[-2].casefold():
            candidate = parts[-2]
        return candidate.replace("_", " ").title()

    @staticmethod
    def _safe_players(values: Any) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        hidden_index = 0
        for value in values or ():
            data = (
                asdict(cast(Any, value))
                if is_dataclass(value) and not isinstance(value, type)
                else dict(value)
            )
            raw_name = str(data.get("name") or "").strip()
            privacy_marker = bool(data.get("hidden")) or not raw_name or raw_name.casefold() in {
                "anonymous",
                "hidden player",
                "unknown player",
            }
            if privacy_marker:
                hidden_index += 1
            source_player = {
                "name": raw_name or None,
                "champion": data.get("champion"),
                "Incognito": privacy_marker,
            }
            if data.get("summoner_id"):
                source_player["summoner_id"] = data["summoner_id"]
            safe_player = redact_player(
                source_player,
                placeholder=f"Hidden player {hidden_index or 1}",
            )
            hidden = bool(safe_player.get("redacted"))
            records.append(
                {
                    "name": str(
                        safe_player.get("display_name")
                        or safe_player.get("name")
                        or "Hidden player"
                    ),
                    "riotId": raw_name if not hidden and "#" in raw_name else None,
                    "agent": safe_player.get("champion"),
                    "rank": None,
                    "score": "—",
                    "self": data.get("is_self") is True,
                    "hidden": hidden,
                    "team": str(data.get("team") or "Unknown"),
                    "accountLevel": data.get("account_level"),
                    "stats": dict(data.get("stats") or {}),
                    **({"ready": data["ready"]} if isinstance(data.get("ready"), bool) else {}),
                    **({"leader": data["is_leader"]} if isinstance(data.get("is_leader"), bool) else {}),
                    **({"role": data["role"]} if data.get("role") else {}),
                }
            )
        return records

    @staticmethod
    def _teams(players: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for player in players:
            grouped.setdefault(player.pop("team", "Unknown"), []).append(player)
        return [
            {"name": team, "score": None, "players": members} for team, members in grouped.items()
        ]

    @staticmethod
    def _format_elapsed(seconds: float | None) -> str:
        if seconds is None:
            return "—"
        total = max(0, int(seconds))
        return f"{total // 60}:{total % 60:02d}"
