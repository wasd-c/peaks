"""Bounded, memory-only enrichment from authenticated VALORANT client services.

Only subjects observed in the authenticated roster or an owned history page
enter this cache. No provider payload, credential or raw party identifier is
retained. Match statistics and recent-history aggregates remain separate.
"""

from __future__ import annotations

import re
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from threading import RLock
from typing import Any
from urllib.parse import quote

from .client import RiotClientError
from .valorant import (
    ValorantClient,
    ValorantMatchPlayer,
    ValorantMatchSummary,
    ValorantRank,
    _bounded_season_id,
    _bounded_subjects,
    _known_rank_tier,
    _mapping_bool,
    _safe_riot_id,
    latest_competitive_update_season,
    parse_competitive_updates_rank,
    parse_match_details,
    parse_match_history,
    parse_rank,
)

_ROMAN_ACTS = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6"}


@dataclass(frozen=True)
class SeasonCatalog:
    labels: Mapping[str, str] = field(default_factory=dict)
    active_id: str | None = None


def _date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def parse_season_catalog(payload: object) -> SeasonCatalog:
    """Use names and containing date ranges; never infer labels from map order."""

    values = payload.get("Seasons") if isinstance(payload, Mapping) else None
    if not isinstance(values, list):
        return SeasonCatalog()
    rows = [row for row in values[:512] if isinstance(row, Mapping)]
    parents = [row for row in rows if str(row.get("Type", "")).lower() in {"episode", "season"}]
    labels: dict[str, str] = {}
    active: list[str] = []
    for row in rows:
        season_id = _bounded_season_id(row.get("ID"))
        if season_id is None or str(row.get("Type", "")).lower() != "act":
            continue
        if row.get("IsActive") is True:
            active.append(season_id)
        name = str(row.get("Name", "")).strip().upper()
        name = re.sub(
            r"\bACT\s+(VI|IV|V|III|II|I)\b",
            lambda match: f"ACT {_ROMAN_ACTS[match.group(1)]}",
            name,
        )
        direct = re.fullmatch(r"(E[1-9]\d?|V\d{2})\s*:?\s*A(?:CT)?\s*([1-6])", name)
        if direct:
            labels[season_id] = f"{direct.group(1)}:A{direct.group(2)}"
            continue
        act = re.fullmatch(r"ACT\s*([1-6])", name)
        start, end = _date(row.get("StartTime")), _date(row.get("EndTime"))
        if act is None or start is None or end is None:
            continue
        containing = [
            parent
            for parent in parents
            if (
                (begin := _date(parent.get("StartTime"))) is not None
                and (finish := _date(parent.get("EndTime"))) is not None
                and begin <= start < end <= finish
            )
        ]
        if len(containing) != 1:
            continue
        parent_name = str(containing[0].get("Name", "")).strip().upper()
        episode = re.fullmatch(r"EPISODE\s*0?([1-9]\d?)", parent_name)
        year = re.fullmatch(r"(?:(?:SEASON|EPISODE)\s+)?(?:20|V)(\d{2})", parent_name)
        if year:
            labels[season_id] = f"V{year.group(1)}:A{act.group(1)}"
        elif episode and start.year < 2025:
            labels[season_id] = f"E{int(episode.group(1))}:A{act.group(1)}"
    return SeasonCatalog(labels, active[0] if len(active) == 1 else None)


@dataclass
class RequestBudget:
    remaining: int = 18
    clock: Callable[[], float] = time.monotonic
    seconds: float = 8.0
    deadline: float = field(init=False)

    def __post_init__(self) -> None:
        self.deadline = self.clock() + self.seconds

    def take(self) -> bool:
        if self.remaining <= 0 or self.clock() >= self.deadline:
            return False
        self.remaining -= 1
        return True


def _catalog_rank(
    payload: Mapping[str, Any], season_id: str | None, catalog: SeasonCatalog
) -> ValorantRank:
    rank = parse_rank(payload, season_id, season_labels=catalog.labels)
    skills = payload.get("QueueSkills")
    competitive = skills.get("competitive") if isinstance(skills, Mapping) else None
    seasons = (
        competitive.get("SeasonalInfoBySeasonID") if isinstance(competitive, Mapping) else None
    )
    # Without a season label, old Immortal/Radiant indices overlap today's
    # Ascendant/Immortal indices. Do not publish a potentially wrong peak.
    if isinstance(seasons, Mapping) and rank.peak_tier < 27:
        for key, row in seasons.items():
            if key in catalog.labels or key == season_id or not isinstance(row, Mapping):
                continue
            candidates = [row.get("CompetitiveTier")]
            wins = row.get("WinsByTier")
            if isinstance(wins, Mapping):
                candidates.extend(
                    tier
                    for tier, count in wins.items()
                    if isinstance(count, (int, float)) and not isinstance(count, bool) and count > 0
                )
            if any(
                21 <= tier <= 24
                for value in candidates
                if (tier := _known_rank_tier(value)) is not None
            ):
                return replace(rank, peak_tier=0, peak_name="Unranked", season_id=None)
    return replace(rank, peak_season=catalog.labels.get(rank.season_id or ""))


@dataclass(frozen=True, repr=False)
class CompletedMatch:
    summary: ValorantMatchSummary
    # This private association stays in memory, never in a presentation DTO.
    contexts: tuple[tuple[str, ValorantMatchPlayer], ...] = ()


class ValorantEnrichmentCache:
    """One authenticated owner/shard's bounded sanitized cache, reused by polls."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._entries: OrderedDict[tuple[str, str], tuple[float, Any]] = OrderedDict()
        self._lock = RLock()

    def _get(self, kind: str, key: str) -> tuple[bool, Any]:
        with self._lock:
            entry = self._entries.get((kind, key))
            if entry is None:
                return False, None
            if entry[0] <= self.clock():
                self._entries.pop((kind, key), None)
                return False, None
            self._entries.move_to_end((kind, key))
            return True, entry[1]

    def _put(self, kind: str, key: str, value: Any, ttl: float) -> None:
        with self._lock:
            self._entries[(kind, key)] = (self.clock() + ttl, value)
            self._entries.move_to_end((kind, key))
            while len(self._entries) > 512:
                self._entries.popitem(last=False)

    def catalog(self, client: ValorantClient, budget: RequestBudget) -> SeasonCatalog:
        found, cached = self._get("catalog", "seasons")
        if found:
            return cached if isinstance(cached, SeasonCatalog) else SeasonCatalog()
        if not budget.take():
            return SeasonCatalog()
        try:
            parsed = parse_season_catalog(client._get_json("shared", "/content-service/v3/content"))
        except RiotClientError:
            parsed = SeasonCatalog()
        self._put("catalog", "seasons", parsed, 21_600 if parsed.labels else 60)
        return parsed

    def profile(
        self, client: ValorantClient, subject: str, catalog: SeasonCatalog, budget: RequestBudget
    ) -> ValorantRank | None:
        found, cached = self._get("rank", subject)
        if found:
            return cached if isinstance(cached, ValorantRank) else None
        if not budget.take():
            return None
        path = quote(subject, safe="")
        rank: ValorantRank | None = None
        primary: Mapping[str, Any] | None = None
        try:
            payload = client._get_json("pd", f"/mmr/v1/players/{path}")
            if isinstance(payload, Mapping):
                skills = payload.get("QueueSkills")
                competitive = skills.get("competitive") if isinstance(skills, Mapping) else None
                seasons = (
                    competitive.get("SeasonalInfoBySeasonID")
                    if isinstance(competitive, Mapping)
                    else None
                )
                if isinstance(seasons, Mapping):
                    primary = payload
                    rank = _catalog_rank(payload, catalog.active_id, catalog)
                    update = payload.get("LatestCompetitiveUpdate")
                    latest_id = (
                        _bounded_season_id(update.get("SeasonID"))
                        if isinstance(update, Mapping)
                        else None
                    )
                    resolved = (
                        catalog.active_id is not None or latest_id in seasons or len(seasons) == 1
                    )
                    rank = replace(rank, current_available=resolved)
        except RiotClientError:
            pass
        if rank is None or not rank.current_available:
            if not budget.take():
                return rank
            try:
                updates = client._get_json(
                    "pd",
                    f"/mmr/v1/players/{path}/competitiveupdates?startIndex=0&endIndex=20&queue=competitive",
                )
                if isinstance(updates, Mapping):
                    update_season = catalog.active_id or latest_competitive_update_season(updates)
                    recent = parse_competitive_updates_rank(updates, update_season, limit=20)
                    # A page of recent updates is not proof of a career peak.
                    if recent is not None and primary is not None:
                        rank = _catalog_rank(primary, update_season, catalog)
                        rank = replace(
                            rank,
                            tier=recent.tier,
                            name=recent.name,
                            rr=recent.rr,
                            peak_season=catalog.labels.get(rank.season_id or ""),
                        )
                    elif recent is not None:
                        rank = replace(
                            recent,
                            peak_tier=0,
                            peak_name="Unranked",
                            season_id=None,
                            peak_season=None,
                        )
            except RiotClientError:
                pass
        self._put("rank", subject, rank, 300 if rank is not None else 60)
        return rank

    def completed(
        self,
        client: ValorantClient,
        match: ValorantMatchSummary,
        budget: RequestBudget,
        *,
        resolve_names: bool = False,
    ) -> CompletedMatch | None:
        found, cached = self._get("match", match.match_id)
        if found:
            if isinstance(cached, CompletedMatch):
                return self._hydrate_names(client, cached, budget) if resolve_names else cached
            return None
        if not budget.take():
            return None
        try:
            details = client._get_json(
                "pd", f"/match-details/v1/matches/{quote(match.match_id, safe='')}"
            )
        except RiotClientError:
            self._put("match", match.match_id, None, 30)
            return None
        if not isinstance(details, Mapping):
            self._put("match", match.match_id, None, 30)
            return None
        info = details.get("matchInfo", details.get("MatchInfo", {}))
        if isinstance(info, Mapping) and (
            _mapping_bool(info, "isCompleted", "IsCompleted") is False
            or info.get("matchId", info.get("MatchID", match.match_id)) != match.match_id
        ):
            return None
        contexts: list[tuple[str, ValorantMatchPlayer]] = []
        summary = parse_match_details(
            details, puuid=client.puuid, fallback=match, contexts=contexts
        )
        completed = CompletedMatch(summary, tuple(contexts))
        self._put("match", match.match_id, completed, 86_400)
        return self._hydrate_names(client, completed, budget) if resolve_names else completed

    def _hydrate_names(
        self, client: ValorantClient, match: CompletedMatch, budget: RequestBudget
    ) -> CompletedMatch:
        candidates = tuple(dict.fromkeys(
            subject for subject, player in match.contexts if _safe_riot_id(player.riot_id) is None
        ))
        names = {
            subject: name
            for subject in candidates
            if (name := _safe_riot_id(self._get("name", subject)[1])) is not None
        }
        missing = tuple(subject for subject in candidates if not self._get("name", subject)[0])
        if missing and budget.take():
            resolved = client.player_names(missing)
            for subject in missing:
                name = _safe_riot_id(resolved.get(subject))
                if name is not None:
                    names[subject] = name
                    self._put("name", subject, name, 86_400)
                    self._put("name_pending", subject, False, 86_400)
                    self._put("name_attempts", subject, 0, 300)
                    continue
                attempts = int(self._get("name_attempts", subject)[1] or 0) + 1
                pending = attempts < 3
                self._put("name", subject, None, 15 if pending else 300)
                self._put("name_pending", subject, pending, 300)
                self._put("name_attempts", subject, attempts, 300)
        replacements = {}
        for subject, player in match.contexts:
            name = _safe_riot_id(player.riot_id) or names.get(subject)
            if player.hidden or player.riot_id != name:
                # Completed reports no longer inherit live incognito flags.
                # Missing names stay absent while lookup retries; a historical
                # privacy placeholder must never masquerade as a real Riot ID.
                replacements[id(player)] = replace(player, riot_id=name, hidden=False)
        if not replacements:
            return match
        summary = replace(
            match.summary,
            teams=tuple(
                replace(
                    team,
                    players=tuple(replacements.get(id(player), player) for player in team.players),
                )
                for team in match.summary.teams
            ),
        )
        hydrated = CompletedMatch(
            summary,
            tuple(
                (subject, replacements.get(id(player), player))
                for subject, player in match.contexts
            ),
        )
        self._put("match", summary.match_id, hydrated, 86_400)
        return hydrated

    def identity_pending(self, match: CompletedMatch) -> bool:
        """Keep deferred/temporary name failures retryable, with a finite cap."""

        return any(
            _safe_riot_id(player.riot_id) is None
            and (
                not self._get("name", subject)[0]
                or bool(self._get("name_pending", subject)[1])
            )
            for subject, player in match.contexts
        )

    def owned_history_match(self, match_id: str) -> ValorantMatchSummary | None:
        """Return only a match observed on this owner's authenticated history."""

        _, cached = self._get("owned_history_match", match_id)
        return cached if isinstance(cached, ValorantMatchSummary) else None

    def remember_owned_history_match(self, match: ValorantMatchSummary) -> None:
        """Avoid rescanning old history pages during an open report's retries."""

        self._put("owned_history_match", match.match_id, match, 300)

    def overall(
        self, client: ValorantClient, subject: str, budget: RequestBudget
    ) -> Mapping[str, Any] | None:
        found, cached = self._get("overall", subject)
        if found:
            return cached if isinstance(cached, Mapping) else None
        if not budget.take():
            return None
        try:
            payload = client._get_json(
                "pd",
                f"/match-history/v1/history/{quote(subject, safe='')}?startIndex=0&endIndex=5&queue=competitive",
            )
        except RiotClientError:
            self._put("overall", subject, None, 60)
            self._put("overall_pending", subject, False, 60)
            return None
        matches = parse_match_history(payload, limit=5) if isinstance(payload, Mapping) else ()
        samples: list[tuple[ValorantMatchPlayer, bool | None]] = []
        complete = True
        for match in matches:
            completed = self.completed(client, match, budget)
            if completed is None:
                # Deferred work is pending; a completed negative lookup is not.
                # Otherwise an inaccessible match keeps the card spinning forever.
                complete = complete and self._get("match", match.match_id)[0]
                continue
            player = next((row for key, row in completed.contexts if key == subject), None)
            if player is None or any(
                number is None for number in (player.kills, player.deaths, player.assists)
            ):
                continue
            team = next((team for team in completed.summary.teams if player in team.players), None)
            samples.append((player, team.won if team else None))
        stats = aggregate_recent_stats(samples)
        # Partial fetches are retried quickly; a complete sample is reusable.
        self._put("overall", subject, stats, 300 if complete else 15)
        self._put("overall_pending", subject, not complete, 300)
        return stats

    def _stats_pending(self, subject: str) -> bool:
        rank_found, _ = self._get("rank", subject)
        overall_found, _ = self._get("overall", subject)
        _, overall_pending = self._get("overall_pending", subject)
        return not rank_found or not overall_found or bool(overall_pending)

    def _enrich(self, match: CompletedMatch) -> ValorantMatchSummary:
        subjects = {id(player): subject for subject, player in match.contexts}
        teams = []
        pending = self.identity_pending(match)
        for team in match.summary.teams:
            players = []
            for player in team.players:
                subject = subjects.get(id(player), "")
                if not subject:
                    players.append(player)
                    continue
                _, rank = self._get("rank", subject)
                _, overall = self._get("overall", subject)
                stats_loading = not player.hidden and self._stats_pending(subject)
                pending = pending or stats_loading
                players.append(replace(player, current_rank=rank, overall_stats=overall, stats_loading=stats_loading))
            teams.append(replace(team, players=tuple(players)))
        return replace(match.summary, teams=tuple(teams), enrichment_pending=pending)

    def match_history(
        self,
        client: ValorantClient,
        matches: tuple[ValorantMatchSummary, ...],
        *,
        priority_match_id: str | None = None,
    ) -> tuple[ValorantMatchSummary, ...]:
        # A priority ID can only reorder an already authorized own-history page.
        ordered = sorted(matches, key=lambda match: match.match_id != priority_match_id)
        detail_budget = RequestBudget(remaining=30, clock=self.clock, seconds=12)
        completed = {
            match.match_id: self.completed(client, match, detail_budget, resolve_names=True)
            for match in ordered
        }
        subjects = list(
            dict.fromkeys(
                subject
                for match in completed.values()
                if match is not None
                for subject, _ in match.contexts
            )
        )
        prioritized = completed.get(priority_match_id or "")
        if prioritized is not None:
            # An open report gets its complete roster before spending its
            # request allowance on unrelated older reports.
            subjects = list(dict.fromkeys(subject for subject, _ in prioritized.contexts))
        budget = RequestBudget(remaining=24 if priority_match_id else 18, clock=self.clock)
        catalog = self.catalog(client, budget)
        rank_allowance = min(20 if priority_match_id else 12, budget.remaining)
        initial = budget.remaining
        for subject in subjects:
            found, _ = self._get("rank", subject)
            if not found and initial - budget.remaining >= rank_allowance:
                break
            self.profile(client, subject, catalog, budget)
        attempts = 0
        for subject in subjects:
            found, _ = self._get("overall", subject)
            if not found:
                self.overall(client, subject, budget)
                attempts += 1
                if attempts >= 2:
                    break
        return tuple(
            self._enrich(item)
            if (item := completed.get(match.match_id)) is not None
            else replace(match, enrichment_pending=not self._get("match", match.match_id)[0])
            for match in matches
        )

    def live_profiles(self, client: ValorantClient, subjects: object) -> dict[str, dict[str, Any]]:
        """Caller provides only visible roster subjects, never hidden players."""

        allowed = _bounded_subjects(subjects)
        budget = RequestBudget(clock=self.clock)
        catalog = self.catalog(client, budget)
        for subject in allowed:
            self.profile(client, subject, catalog, budget)
        attempts = 0
        for subject in allowed:
            found, _ = self._get("overall", subject)
            if not found:
                self.overall(client, subject, budget)
                attempts += 1
                if attempts >= 2:
                    break
        result = {}
        for subject in allowed:
            _, rank = self._get("rank", subject)
            _, overall = self._get("overall", subject)
            result[subject] = {
                **rank_presentation(rank),
                **({"overallStats": dict(overall)} if overall else {}),
                "statsLoading": self._stats_pending(subject),
            }
        return result


def rank_presentation(rank: ValorantRank | None) -> dict[str, Any]:
    if rank is None:
        return {}
    result: dict[str, Any] = (
        {"currentRank": rank.name, "currentRankTier": rank.tier} if rank.current_available else {}
    )
    if rank.peak_tier >= 3:
        result.update(peakRank=rank.peak_name, peakRankTier=rank.peak_tier)
        if rank.peak_season:
            result["peakRankSeason"] = rank.peak_season
    return result


def aggregate_recent_stats(
    samples: list[tuple[ValorantMatchPlayer, bool | None]],
) -> dict[str, Any] | None:
    if not samples:
        return None
    fields = {
        "kills": "kills",
        "deaths": "deaths",
        "assists": "assists",
        "combatScore": "combat_score",
        "roundsPlayed": "rounds_played",
        "headshots": "headshots",
        "bodyshots": "bodyshots",
        "legshots": "legshots",
        "damage": "damage",
    }
    stats: dict[str, Any] = {
        "matchesPlayed": len(samples),
        "scope": "recent",
        "source": "authenticated-client-history",
    }
    for key, attribute in fields.items():
        values = [getattr(player, attribute) for player, _ in samples]
        if all(
            isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100_000_000
            for value in values
        ):
            stats[key] = sum(values)
    if all(won is not None for _, won in samples):
        stats["wins"] = sum(won is True for _, won in samples)
    if "kills" in stats and "deaths" in stats:
        stats["recentKda"] = [
            {"kills": player.kills, "deaths": player.deaths} for player, _ in samples
        ]
    return stats
