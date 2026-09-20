"""Bounded cache of already-sanitized public profile presentation data."""

from __future__ import annotations

import json
import time
from typing import Any

MAX_PROFILES = 200
MAX_AGE_SECONDS = 90 * 86400
PROFILE_FIELDS = frozenset({'id', 'riotId', 'region', 'games', 'ranks', 'peakRanks', 'currentRank', 'peakRank', 'lastUpdated', 'lastGame', 'initials', 'level', 'leagueLevel', 'valorantLevel', 'leagueRegion', 'valorantRegion', 'valorantAct', 'matches'})


def cached_profile(database: Any, riot_id: str, *, now: float | None = None) -> dict[str, Any] | None:
    current = time.time() if now is None else now
    key = riot_id.strip().casefold()
    if '#' not in key or len(key) > 128:
        return None
    row = database._execute('SELECT profile_json, updated_at FROM player_profile_cache WHERE profile_key=?', (key,)).fetchone()
    if row is None or row['updated_at'] < current - MAX_AGE_SECONDS:
        return None
    value: dict[str, Any] = json.loads(row['profile_json'])
    return value


def remember_profile(database: Any, profile: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
    current = time.time() if now is None else now
    key = str(profile.get('riotId', '')).strip().casefold()
    if '#' not in key or len(key) > 128:
        return profile
    with database._lock:
        old = cached_profile(database, key, now=current) or {}
        if old.get('id') and profile.get('id') and old['id'] != profile['id']:
            old = {}  # A reused Riot ID must never inherit another PUUID's data.
        clean = {name: value for name, value in old.items() if name in PROFILE_FIELDS}
        clean.update({name: value for name, value in profile.items() if name in PROFILE_FIELDS and value is not None})
        ranks = {rank['game']: rank for rank in old.get('ranks', [])}
        ranks.update({rank['game']: rank for rank in profile.get('ranks', [])})
        clean['ranks'] = list(ranks.values())
        matches = {(match['game'], match['id']): match for match in old.get('matches', []) if match.get('id')}
        for match in profile.get('matches', []):
            if match.get('id'):
                previous = matches.get((match['game'], match['id']), {})
                matches[(match['game'], match['id'])] = {**previous, **{name: value for name, value in match.items() if value is not None and (name != 'teams' or value)}}
        # Keep an independent page for every game instead of letting VALORANT
        # evict all League/TFT history from the shared identity.
        recent: list[dict[str, Any]] = []
        for game in ('VALORANT', 'League of Legends', 'Teamfight Tactics'):
            recent.extend(sorted((match for match in matches.values() if match['game'] == game), key=lambda item: item.get('playedAtTimestamp') or 0, reverse=True)[:20])
        clean['matches'] = recent
        clean['games'] = list(dict.fromkeys([*old.get('games', []), *profile.get('games', []), *(match['game'] for match in recent)]))
        observations = list(old.get('activity', {}).get('ranks', []))
        for rank in profile.get('ranks', []):
            if type(rank.get('rating')) is not int:
                continue
            value = {name: rank.get(name) for name in ('game', 'tier', 'division', 'rating')}
            last = next((entry for entry in reversed(observations) if entry['game'] == rank['game']), None)
            if last is None or any(last.get(name) != item for name, item in value.items()):
                observations.append({**value, 'observedAt': current * 1000})
        clean['activity'] = {'matches': recent, 'ranks': observations[-200:], 'connectionDays': [], 'identities': []}
        clean['cachedAt'] = current * 1000
        encoded = json.dumps(clean, ensure_ascii=False)
        if len(encoded) > 2_000_000:
            return profile
        database._execute('INSERT INTO player_profile_cache(profile_key, updated_at, profile_json) VALUES (?, ?, ?) ON CONFLICT(profile_key) DO UPDATE SET updated_at=excluded.updated_at, profile_json=excluded.profile_json', (key, current, encoded))
        database._execute('DELETE FROM player_profile_cache WHERE updated_at < ?', (current - MAX_AGE_SECONDS,))
        database._execute('DELETE FROM player_profile_cache WHERE profile_key NOT IN (SELECT profile_key FROM player_profile_cache ORDER BY updated_at DESC LIMIT ?)', (MAX_PROFILES,))
        return clean
