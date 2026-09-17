"""Public data providers used by Peaks.

The provider layer deliberately contains no UI or persistence concerns.  Riot
API credentials are supplied by the caller and are kept in memory by the
client; provider errors never include request headers or response bodies.
"""

from .riot_api import (
    LEAGUE_ROUTING_HOSTS,
    PLATFORM_ROUTING_HOSTS,
    AccountRouting,
    LeagueRank,
    MatchHistory,
    MatchReference,
    OfficialRiotApiClient,
    PlatformRouting,
    RiotAccount,
    RiotApiClient,
    RiotApiError,
    RiotApiProvider,
    RiotApiTransportError,
    RiotMatch,
    TftRank,
    UnsupportedRiotRegion,
    ValorantMatchHistory,
    ValorantMatchReference,
)
from .valorant_metadata import (
    UnsupportedValorantApiError,
    ValorantAgentAsset,
    ValorantApiLimitations,
    ValorantMapAsset,
    ValorantMetadataClient,
    ValorantMetadataError,
    ValorantOfficialClient,
    ValorantOfficialProvider,
    ValorantRankAsset,
    valorant_official_limitations,
)

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
    "UnsupportedValorantApiError",
    "ValorantAgentAsset",
    "ValorantApiLimitations",
    "ValorantMapAsset",
    "ValorantMatchHistory",
    "ValorantMatchReference",
    "ValorantMetadataClient",
    "ValorantMetadataError",
    "ValorantOfficialClient",
    "ValorantOfficialProvider",
    "ValorantRankAsset",
    "valorant_official_limitations",
]
