"""Exact public Riot-ID lookup through the validated, signed-in Riot Client.

The route and schema are advertised by the local client's OpenAPI catalog.
No developer key, remote bearer token, friend-list access or Riot mutation is
needed. A Riot identity by itself does not establish a game profile or shard.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .client import RiotClientError, RiotClientHTTP, RiotClientUnavailable
from .discovery import discover_riot_client

ALIAS_LOOKUP_PATH = "/player-account/aliases/v1/lookup"


@dataclass(frozen=True, slots=True)
class RiotPlayerIdentity:
    puuid: str = field(repr=False)
    game_name: str
    tag_line: str

    @property
    def riot_id(self) -> str:
        return f"{self.game_name}#{self.tag_line}"


def _safe_text(value: object, limit: int) -> str | None:
    return value if (
        isinstance(value, str) and value and len(value) <= limit
        and value == value.strip()
        and not any(ord(char) < 32 or 127 <= ord(char) < 160 for char in value)
    ) else None


def parse_alias_lookup(payload: object, game_name: str, tag_line: str) -> RiotPlayerIdentity | None:
    if not isinstance(payload, list) or len(payload) > 100:
        raise RiotClientUnavailable("Riot identity lookup returned an invalid response")
    matches: dict[str, RiotPlayerIdentity] = {}
    for row in payload:
        if not isinstance(row, Mapping) or not isinstance(row.get("alias"), Mapping):
            continue
        alias = row["alias"]
        name = _safe_text(alias.get("game_name"), 128)
        tag = _safe_text(alias.get("tag_line"), 64)
        puuid = _safe_text(row.get("puuid"), 256)
        if name and tag and puuid and name.casefold() == game_name.casefold() and tag.casefold() == tag_line.casefold():
            matches[puuid] = RiotPlayerIdentity(puuid, name, tag)
    if len(matches) > 1:
        raise RiotClientUnavailable("Riot identity lookup returned an ambiguous response")
    return next(iter(matches.values()), None)


class RiotPlayerLookup:
    def __init__(self, http: RiotClientHTTP | None = None) -> None:
        self.http = http

    @classmethod
    def from_discovery(cls) -> RiotPlayerLookup:
        discovery = discover_riot_client()
        return cls(RiotClientHTTP(discovery.lockfile) if discovery.lockfile is not None else None)

    def lookup_player(self, game_name: str, tag_line: str) -> RiotPlayerIdentity | None:
        if not _safe_text(game_name, 128) or not _safe_text(tag_line, 64):
            raise ValueError("Enter a complete Riot ID: Player#TAG")
        if self.http is None:
            raise RiotClientUnavailable("A verified signed-in Riot Client is required")
        try:
            payload = self.http.get_json(ALIAS_LOOKUP_PATH, params={"gameName": game_name, "tagLine": tag_line})
        except RiotClientError as error:
            # 404 can mean this client version lacks the route, so only an
            # actual successful empty result establishes no identity match.
            raise RiotClientUnavailable("The signed-in Riot Client lookup is unavailable") from error
        return parse_alias_lookup(payload, game_name, tag_line)

    def close(self) -> None:
        if self.http is not None:
            self.http.close()
