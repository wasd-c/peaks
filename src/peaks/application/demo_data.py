"""Deterministic, non-sensitive data used for screenshots and UI smoke tests.

The production application never inserts these records. Set ``PEAKS_DEMO=1``
to exercise every page without a Riot account or API key.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

DEMO_PIN = "2580"
DEMO_TOTP_SEED = "JBSWY3DPEHPK3PXP"


def _rank(
    game: str,
    tier: str,
    rating: str,
    peak: str,
    icon: str = "",
) -> dict[str, Any]:
    return {
        "game": game,
        "tier": tier,
        "rating": rating,
        "peak": peak,
        "icon": icon,
    }


def demo_accounts() -> list[dict[str, Any]]:
    return [
        {
            "id": "own-aureline",
            "puuid": "demo-puuid-aureline",
            "riotId": "Aurélïne#EUW",
            "region": "EUW",
            "owned": True,
            "connected": True,
            "initials": "AU",
            "accent": "#A8CEFF",
            "lastUpdated": "just now",
            "totpAvailable": True,
            "ranks": [
                _rank("League", "Diamond IV", "62 LP", "Master"),
                _rank("VALORANT", "Ascendant 2", "74 RR", "Immortal 1"),
                _rank("TFT", "Emerald II", "31 LP", "Diamond IV"),
            ],
            "matches": _matches("valorant"),
        },
        {
            "id": "own-peaks",
            "puuid": "demo-puuid-peaks",
            "riotId": "peaks#0001",
            "region": "EUW",
            "owned": True,
            "connected": False,
            "initials": "PK",
            "accent": "#C7B6FF",
            "lastUpdated": "8 min ago",
            "totpAvailable": True,
            "ranks": [
                _rank("League", "Emerald I", "94 LP", "Diamond II"),
                _rank("VALORANT", "Diamond 3", "41 RR", "Ascendant 3"),
            ],
            "matches": _matches("league"),
        },
        {
            "id": "own-serein",
            "puuid": "demo-puuid-serein",
            "riotId": "serein#quiet",
            "region": "NA",
            "owned": True,
            "connected": True,
            "initials": "SE",
            "accent": "#F1C998",
            "lastUpdated": "yesterday",
            "totpAvailable": False,
            "ranks": [
                _rank("League", "Platinum II", "17 LP", "Emerald III"),
                _rank("VALORANT", "Gold 2", "88 RR", "Platinum 3"),
                _rank("TFT", "Unranked", "No placements", "Gold I"),
            ],
            "matches": _matches("tft"),
        },
    ]


def _valorant_match_teams() -> list[dict[str, Any]]:
    return [
        {
            "name": "Your team",
            "score": 13,
            "won": True,
            "players": [
                {
                    "name": "Aurélïne#EUW",
                    "riotId": "Aurélïne#EUW",
                    "agent": "Omen",
                    "rank": "Ascendant 2",
                    "rankTier": 22,
                    "score": "24 / 13 / 6",
                    "stats": {
                        "kills": 24,
                        "deaths": 13,
                        "assists": 6,
                        "combatScore": 318,
                        "headshots": 19,
                        "bodyshots": 39,
                        "legshots": 3,
                        "damage": 4_982,
                    },
                    "self": True,
                    "hidden": False,
                },
                {
                    "name": "dusk#EU",
                    "riotId": "dusk#EU",
                    "agent": "Sova",
                    "rank": "Diamond 3",
                    "rankTier": 20,
                    "score": "18 / 14 / 11",
                    "stats": {
                        "kills": 18,
                        "deaths": 14,
                        "assists": 11,
                        "combatScore": 244,
                        "headshots": 12,
                        "bodyshots": 34,
                        "legshots": 2,
                        "damage": 3_916,
                    },
                    "hidden": False,
                },
                {
                    "name": "Hidden player 3",
                    "agent": "Jett",
                    "rank": "Ascendant 1",
                    "rankTier": 21,
                    "score": "16 / 15 / 4",
                    "stats": {"kills": 16, "deaths": 15, "assists": 4},
                    "hidden": True,
                },
            ],
        },
        {
            "name": "Opponents",
            "score": 8,
            "won": False,
            "players": [
                {
                    "name": "nova#ACE",
                    "riotId": "nova#ACE",
                    "agent": "Reyna",
                    "rank": "Ascendant 3",
                    "rankTier": 23,
                    "score": "21 / 17 / 3",
                    "stats": {
                        "kills": 21,
                        "deaths": 17,
                        "assists": 3,
                        "combatScore": 286,
                        "headshots": 16,
                        "bodyshots": 31,
                        "legshots": 4,
                        "damage": 4_221,
                    },
                    "hidden": False,
                },
                {
                    "name": "calm#000",
                    "riotId": "calm#000",
                    "agent": "Cypher",
                    "rank": "Diamond 2",
                    "rankTier": 19,
                    "score": "12 / 19 / 8",
                    "stats": {"kills": 12, "deaths": 19, "assists": 8},
                    "hidden": False,
                },
            ],
        },
    ]


def _matches(game: str) -> list[dict[str, Any]]:
    if game == "valorant":
        return [
            {
                "id": "v-1",
                "game": "VALORANT",
                "result": "Victory",
                "score": "13 — 8",
                "mode": "Competitive",
                "map": "Abyss",
                "played": "42 min ago",
                "delta": "+21 RR",
                "performance": "24 / 13 / 6 · 31% HS",
                "positive": True,
                "teams": _valorant_match_teams(),
            },
            {
                "id": "v-2",
                "game": "VALORANT",
                "result": "Defeat",
                "score": "10 — 13",
                "mode": "Competitive",
                "map": "Ascent",
                "played": "3h ago",
                "delta": "-16 RR",
                "performance": "18 / 17 / 4 · 24% HS",
                "positive": False,
                "teams": _valorant_match_teams(),
            },
            {
                "id": "v-3",
                "game": "VALORANT",
                "result": "Victory",
                "score": "13 — 4",
                "mode": "Competitive",
                "map": "Lotus",
                "played": "yesterday",
                "delta": "+24 RR",
                "performance": "21 / 9 / 10 · 28% HS",
                "positive": True,
                "teams": _valorant_match_teams(),
            },
        ]
    if game == "tft":
        return [
            {
                "id": "t-1",
                "game": "TFT",
                "result": "2nd place",
                "score": "Top 4",
                "mode": "Ranked",
                "map": "Current set",
                "played": "2d ago",
                "delta": "+31 LP",
                "performance": "Level 9 · 5-cost board",
                "positive": True,
            }
        ]
    return [
        {
            "id": "l-1",
            "game": "League",
            "result": "Victory",
            "score": "32 — 21",
            "mode": "Ranked Solo",
            "map": "Summoner's Rift",
            "played": "1h ago",
            "delta": "+24 LP",
            "performance": "8 / 2 / 11 · 7.8 CS/min",
            "positive": True,
        },
        {
            "id": "l-2",
            "game": "League",
            "result": "Defeat",
            "score": "19 — 28",
            "mode": "Ranked Solo",
            "map": "Summoner's Rift",
            "played": "5h ago",
            "delta": "-18 LP",
            "performance": "4 / 7 / 9 · 6.9 CS/min",
            "positive": False,
        },
    ]


def demo_followed() -> list[dict[str, Any]]:
    return [
        {
            "id": "follow-tenz",
            "riotId": "quietly#EUW",
            "region": "EUW",
            "games": ["League", "VALORANT"],
            "currentRank": "Immortal 2 · 112 RR",
            "peakRank": "Radiant #418",
            "lastGame": "18 min ago",
            "lastUpdated": "Live cache",
            "followed": True,
            "initials": "QU",
        },
        {
            "id": "follow-lumen",
            "riotId": "lumen#soft",
            "region": "NA",
            "games": ["League", "TFT"],
            "currentRank": "Master · 184 LP",
            "peakRank": "Grandmaster · 421 LP",
            "lastGame": "6h ago",
            "lastUpdated": "12 min ago",
            "followed": True,
            "initials": "LU",
        },
        {
            "id": "follow-nori",
            "riotId": "nori#000",
            "region": "AP",
            "games": ["VALORANT"],
            "currentRank": "Ascendant 1 · 33 RR",
            "peakRank": "Immortal 1",
            "lastGame": "3d ago",
            "lastUpdated": "1h ago",
            "followed": True,
            "initials": "NO",
        },
    ]


def demo_search_history() -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    return [
        {
            "id": "history-1",
            "query": "quietly#EUW",
            "region": "EUW",
            "game": "All games",
            "when": "12 min ago",
            "searchedAt": (now - timedelta(minutes=12)).isoformat(),
        },
        {
            "id": "history-2",
            "query": "lumen#soft",
            "region": "NA",
            "game": "League",
            "when": "yesterday",
            "searchedAt": (now - timedelta(days=1)).isoformat(),
        },
    ]


def demo_current_match() -> dict[str, Any]:
    return {
        "game": "VALORANT",
        "mode": "Competitive",
        "map": "Abyss",
        "elapsed": "18:42",
        "status": "Live from Riot Client",
        "streamerMode": True,
        "privacyNote": "Streamer mode respected — hidden identities stay hidden.",
        "teams": [
            {
                "name": "Your team",
                "score": "8",
                "players": [
                    {
                        "name": "Aurélïne#EUW",
                        "riotId": "Aurélïne#EUW",
                        "agent": "Omen",
                        "rank": "Ascendant 2",
                        "score": "17 / 9 / 5",
                        "self": True,
                        "hidden": False,
                    },
                    {
                        "name": "Ally 2",
                        "agent": "Jett",
                        "rank": "Hidden",
                        "score": "15 / 11 / 2",
                        "self": False,
                        "hidden": True,
                    },
                    {
                        "name": "dusk#EU",
                        "riotId": "dusk#EU",
                        "agent": "Sova",
                        "rank": "Diamond 3",
                        "score": "11 / 8 / 9",
                        "self": False,
                        "hidden": False,
                    },
                ],
            },
            {
                "name": "Opponents",
                "score": "6",
                "players": [
                    {
                        "name": "Opponent 1",
                        "agent": "Reyna",
                        "rank": "Hidden",
                        "score": "16 / 10 / 3",
                        "self": False,
                        "hidden": True,
                    },
                    {
                        "name": "Opponent 2",
                        "agent": "Cypher",
                        "rank": "Hidden",
                        "score": "9 / 12 / 7",
                        "self": False,
                        "hidden": True,
                    },
                    {
                        "name": "Opponent 3",
                        "agent": "Viper",
                        "rank": "Hidden",
                        "score": "7 / 13 / 6",
                        "self": False,
                        "hidden": True,
                    },
                ],
            },
        ],
    }


def search_demo(query: str, region: str, game: str) -> list[dict[str, Any]]:
    normalized = query.strip() or "summoner#tag"
    initials = "".join(part[:1] for part in normalized.replace("#", " ").split())[:2].upper()
    return [
        {
            "id": f"search-{normalized.lower()}-{region.lower()}",
            "riotId": normalized,
            "region": region,
            "games": [game] if game != "All games" else ["League", "VALORANT", "TFT"],
            "currentRank": "Diamond IV · 62 LP" if game != "VALORANT" else "Ascendant 1 · 48 RR",
            "peakRank": "Master" if game != "VALORANT" else "Immortal 1",
            "lastGame": "2h ago",
            "lastUpdated": "Demo data",
            "followed": False,
            "initials": initials or "RI",
        }
    ]
