#!/usr/bin/env python3
"""Fetch the small, redistributable Riot artwork set used by Peaks.

The script intentionally uses only the Python standard library.  It resolves the
current Data Dragon patch and current Valorant competitive-tier table at fetch
time, then records those versions and the source URL for every checked-in file
in ``src/peaks/ui/assets/riot/manifest.json``.

Run from any working directory with a supported Python 3.12+ interpreter::

    python scripts/fetch_assets.py

ImageMagick (``magick``) or Pillow is used when available to keep the committed
PNGs small.  Without either optional image tool, the original PNG bytes are
retained and the manifest still records their dimensions and hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "src" / "peaks" / "ui" / "assets" / "riot"
MANIFEST_PATH = ASSET_ROOT / "manifest.json"
VALORANT_INDEX_PATH = ASSET_ROOT / "valorant" / "index.json"

DD_API = "https://ddragon.leagueoflegends.com"
LOL_RANK_ARCHIVE = "https://static.developer.riotgames.com/docs/lol/ranked-emblems-latest.zip"
VALORANT_API = "https://valorant-api.com"
ALLOWED_ASSET_HOSTS = frozenset(
    {
        "ddragon.leagueoflegends.com",
        "static.developer.riotgames.com",
        "valorant-api.com",
        "media.valorant-api.com",
    }
)
DEFAULT_MAX_DOWNLOAD_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 16 * 1024 * 1024

LOL_TIERS = (
    "Iron",
    "Bronze",
    "Silver",
    "Gold",
    "Platinum",
    "Emerald",
    "Diamond",
    "Master",
    "Grandmaster",
    "Challenger",
)
TFT_TIERS = LOL_TIERS
VALORANT_TIERS = (
    ("UNRANKED", "unranked"),
    ("IRON 1", "iron-1"),
    ("IRON 2", "iron-2"),
    ("IRON 3", "iron-3"),
    ("BRONZE 1", "bronze-1"),
    ("BRONZE 2", "bronze-2"),
    ("BRONZE 3", "bronze-3"),
    ("SILVER 1", "silver-1"),
    ("SILVER 2", "silver-2"),
    ("SILVER 3", "silver-3"),
    ("GOLD 1", "gold-1"),
    ("GOLD 2", "gold-2"),
    ("GOLD 3", "gold-3"),
    ("PLATINUM 1", "platinum-1"),
    ("PLATINUM 2", "platinum-2"),
    ("PLATINUM 3", "platinum-3"),
    ("DIAMOND 1", "diamond-1"),
    ("DIAMOND 2", "diamond-2"),
    ("DIAMOND 3", "diamond-3"),
    ("ASCENDANT 1", "ascendant-1"),
    ("ASCENDANT 2", "ascendant-2"),
    ("ASCENDANT 3", "ascendant-3"),
    ("IMMORTAL 1", "immortal-1"),
    ("IMMORTAL 2", "immortal-2"),
    ("IMMORTAL 3", "immortal-3"),
    ("RADIANT", "radiant"),
)


@dataclass(frozen=True)
class AssetSpec:
    """One source image and its stable local path."""

    asset_id: str
    game: str
    kind: str
    local_path: str
    source_url: str
    source_kind: str
    source_detail: str
    max_dimension: int
    metadata: dict[str, Any] | None = None


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def _validate_asset_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_ASSET_HOSTS
        or parsed.port is not None
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise RuntimeError("Asset URL is outside the HTTPS source allowlist")


def fetch_bytes(url: str, *, max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES) -> bytes:
    _validate_asset_url(url)
    if not 0 < max_bytes <= MAX_ARCHIVE_BYTES:
        raise ValueError("max_bytes is outside the supported download range")
    request = Request(url, headers={"User-Agent": "Peaks asset fetcher/0.1"})
    try:
        with build_opener(_RejectRedirects).open(request, timeout=60) as response:
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    if int(content_length) > max_bytes:
                        raise RuntimeError("Asset download exceeded the size limit")
                except ValueError:
                    pass
            payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise RuntimeError("Asset download exceeded the size limit")
            return bytes(payload)
    except (HTTPError, URLError) as exc:
        raise RuntimeError("Unable to fetch an allowlisted asset source") from exc


def fetch_json(url: str) -> Any:
    try:
        return json.loads(fetch_bytes(url).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid JSON returned by {url}") from exc


def png_dimensions(data: bytes) -> tuple[int, int]:
    """Read dimensions without adding Pillow to the build/runtime dependencies."""

    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise RuntimeError("source is not a valid PNG")
    width, height = struct.unpack(">II", data[16:24])
    if not width or not height:
        raise RuntimeError("PNG has invalid dimensions")
    return width, height


def image_tool() -> str | None:
    # On Windows ``convert`` is also a shell command, so only use it when the
    # ImageMagick launcher is present and ``magick`` is unavailable.
    return shutil.which("magick") or shutil.which("convert")


def optimise_png(data: bytes, destination: Path, max_dimension: int) -> bytes:
    """Resize/strip a PNG with an available image tool, or keep the original."""

    tool = image_tool()
    if tool is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="peaks-assets-") as temp_dir:
            source = Path(temp_dir) / "source.png"
            output = Path(temp_dir) / "optimised.png"
            source.write_bytes(data)
            # ``-thumbnail`` never enlarges an image and preserves transparent
            # backgrounds used by rank emblems.
            command = [
                tool,
                str(source),
                "-thumbnail",
                f"{max_dimension}x{max_dimension}>",
                "-strip",
                "-define",
                "png:compression-level=9",
                str(output),
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, timeout=90)
                optimised = output.read_bytes()
                png_dimensions(optimised)
                return optimised
            except (OSError, subprocess.SubprocessError, RuntimeError):
                pass

    try:
        from PIL import Image  # type: ignore[import-not-found]

        with Image.open(io.BytesIO(data)) as image:
            if image.format != "PNG":
                raise RuntimeError("source is not a valid PNG")
            image.load()
            image.thumbnail((max_dimension, max_dimension))
            output_buffer = io.BytesIO()
            image.save(output_buffer, format="PNG", optimize=True, compress_level=9)
            optimised = output_buffer.getvalue()
            png_dimensions(optimised)
            return optimised
    except (ImportError, OSError, RuntimeError, ValueError):
        return data


def write_asset(spec: AssetSpec, raw: bytes) -> dict[str, Any]:
    """Validate, optimise and atomically write one asset."""

    png_dimensions(raw)
    data = optimise_png(raw, ASSET_ROOT / spec.local_path, spec.max_dimension)
    width, height = png_dimensions(data)
    destination = ASSET_ROOT / spec.local_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False
    ) as temporary:
        temporary.write(data)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, destination)
    record = {
        "id": spec.asset_id,
        "game": spec.game,
        "kind": spec.kind,
        "path": spec.local_path.replace(os.sep, "/"),
        "source_url": spec.source_url,
        "source_kind": spec.source_kind,
        "source_detail": spec.source_detail,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "width": width,
        "height": height,
    }
    if spec.metadata:
        record["metadata"] = spec.metadata
    return record


def select_tft_filename(regalia: dict[str, Any], tier: str) -> str:
    try:
        filename = regalia["data"]["RANKED_TFT"][tier]["image"]["full"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"TFT regalia does not contain the {tier} tier") from exc
    if not isinstance(filename, str) or not filename:
        raise RuntimeError(f"TFT regalia does not contain the {tier} tier")
    return filename


def select_valorant_table(payload: dict[str, Any]) -> dict[str, Any]:
    tables = payload.get("data")
    if not isinstance(tables, list) or not tables:
        raise RuntimeError("Valorant API returned no competitive tier tables")
    # valorant-api.com returns tables oldest-to-newest.  Keep the newest table
    # together with its UUID in the manifest so the selection is auditable.
    table = tables[-1]
    if not isinstance(table, dict) or not isinstance(table.get("tiers"), list):
        raise RuntimeError("Valorant API returned an invalid competitive tier table")
    return table


def _valorant_uuid(record: dict[str, Any], *, label: str) -> str:
    value = record.get("uuid")
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Valorant API returned {label} without a UUID")
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise RuntimeError(f"Valorant API returned {label} with an invalid UUID") from exc


def select_playable_valorant_agents(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    records = payload.get("data")
    if not isinstance(records, list) or not records:
        raise RuntimeError("Valorant API returned no agents")
    agents: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or not record.get("isPlayableCharacter"):
            continue
        uuid = _valorant_uuid(record, label="a playable agent")
        display_name = record.get("displayName")
        display_icon = record.get("displayIcon")
        if not isinstance(display_name, str) or not display_name:
            raise RuntimeError(f"Valorant API agent {uuid} has no display name")
        if not isinstance(display_icon, str) or not display_icon:
            raise RuntimeError(f"Valorant API agent {uuid} has no display icon")
        if uuid in seen:
            raise RuntimeError(f"Valorant API returned duplicate agent UUID {uuid}")
        seen.add(uuid)
        agents.append((uuid, record))
    if not agents:
        raise RuntimeError("Valorant API returned no playable agents")
    return sorted(agents, key=lambda item: item[0])


def select_valorant_maps(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    records = payload.get("data")
    if not isinstance(records, list) or not records:
        raise RuntimeError("Valorant API returned no maps")
    maps: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError("Valorant API returned an invalid map record")
        uuid = _valorant_uuid(record, label="a map")
        display_name = record.get("displayName")
        splash = record.get("splash")
        map_url = record.get("mapUrl")
        if not isinstance(display_name, str) or not display_name:
            raise RuntimeError(f"Valorant API map {uuid} has no display name")
        if not isinstance(splash, str) or not splash:
            raise RuntimeError(f"Valorant API map {uuid} has no splash artwork")
        if not isinstance(map_url, str) or not map_url:
            raise RuntimeError(f"Valorant API map {uuid} has no map URL")
        if uuid in seen:
            raise RuntimeError(f"Valorant API returned duplicate map UUID {uuid}")
        seen.add(uuid)
        maps.append((uuid, record))
    return sorted(maps, key=lambda item: item[0])


def valorant_renderer_index(
    agents: list[tuple[str, dict[str, Any]]], maps: list[tuple[str, dict[str, Any]]]
) -> dict[str, Any]:
    return {
        "agents": [
            {
                "displayName": agent["displayName"],
                "uuid": agent_uuid,
                "path": f"valorant/agents/{agent_uuid}.png",
                "portraitPath": f"valorant/portraits/{agent_uuid}.png",
            }
            for agent_uuid, agent in agents
        ],
        "maps": [
            {
                "displayName": map_record["displayName"],
                "uuid": map_uuid,
                "path": f"valorant/maps/{map_uuid}.png",
                "mapUrl": map_record["mapUrl"],
            }
            for map_uuid, map_record in maps
        ],
    }


def valorant_agent_portrait_spec(agent_uuid: str, agent: dict[str, Any]) -> AssetSpec:
    """Keep the transparent full-body artwork separate from the small head icon."""

    portrait_url = agent.get("fullPortraitV2") or agent.get("fullPortrait")
    if not isinstance(portrait_url, str) or not portrait_url:
        raise RuntimeError(f"Valorant API agent {agent_uuid} has no full portrait")
    return AssetSpec(
        asset_id=f"valorant.agent.{agent_uuid}.full_portrait",
        game="valorant",
        kind="agent_portrait",
        local_path=f"valorant/portraits/{agent_uuid}.png",
        source_url=portrait_url,
        source_kind="valorant_api",
        source_detail=f"{VALORANT_API}/v1/agents agent={agent['displayName']} uuid={agent_uuid}",
        max_dimension=1024,
        metadata={
            "uuid": agent_uuid,
            "display_name": agent["displayName"],
            "is_playable_character": True,
        },
    )


def refresh_valorant_agent_portraits() -> int:
    """Add portraits for the currently shipped roster without refreshing other art."""

    if not MANIFEST_PATH.is_file() or not VALORANT_INDEX_PATH.is_file():
        raise RuntimeError("Fetch the complete asset set before refreshing agent portraits")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    renderer_index = json.loads(VALORANT_INDEX_PATH.read_text(encoding="utf-8"))
    agents_url = f"{VALORANT_API}/v1/agents?language=en-US&isPlayableCharacter=true"
    agents = dict(select_playable_valorant_agents(fetch_json(agents_url)))
    version = fetch_json(f"{VALORANT_API}/v1/version").get("data", {})
    if not isinstance(version, dict) or not isinstance(version.get("version"), str):
        raise RuntimeError("Valorant API returned invalid version metadata")
    specs: list[AssetSpec] = []
    for entry in renderer_index["agents"]:
        agent_uuid = _valorant_uuid(entry, label="a bundled agent")
        if agent_uuid not in agents:
            raise RuntimeError(f"Valorant API no longer contains bundled agent {agent_uuid}")
        specs.append(valorant_agent_portrait_spec(agent_uuid, agents[agent_uuid]))
    # Resolve and validate the complete selection before changing the local index.
    portraits = [write_asset(spec, fetch_bytes(spec.source_url)) for spec in specs]
    portrait_paths = {record["metadata"]["uuid"]: record["path"] for record in portraits}
    for entry in renderer_index["agents"]:
        entry["portraitPath"] = portrait_paths[entry["uuid"]]
    replaced_ids = {record["id"] for record in portraits}
    manifest["assets"] = [record for record in manifest["assets"] if record["id"] not in replaced_ids] + portraits
    manifest["selection"]["valorant_agent_portraits"] = [entry["displayName"] for entry in renderer_index["agents"]]
    manifest["sources"]["valorant_agent_portraits"] = {
        "agents_url": agents_url,
        "version": version["version"],
        "manifest_id": version.get("manifestId"),
        "refreshed_at": utc_now(),
        "note": "Riot game full-body portraits distributed by the public Valorant API media index.",
    }
    write_json_atomic(VALORANT_INDEX_PATH, renderer_index)
    write_json_atomic(MANIFEST_PATH, manifest)
    print(f"Fetched {len(portraits)} local VALORANT agent portraits")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent-portraits-only",
        action="store_true",
        help="add or refresh full-body portraits for the already bundled Valorant roster",
    )
    parser.add_argument(
        "--version",
        help="pin a Data Dragon version instead of resolving versions.json (useful for reproducible refreshes)",
    )
    args = parser.parse_args()
    if args.agent_portraits_only:
        return refresh_valorant_agent_portraits()

    ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    generated_at = utc_now()
    versions_url = f"{DD_API}/api/versions.json"
    version = args.version
    if version is None:
        versions = fetch_json(versions_url)
        if not isinstance(versions, list) or not versions or not isinstance(versions[0], str):
            raise RuntimeError("Data Dragon versions endpoint returned no versions")
        version = versions[0]

    assets: list[dict[str, Any]] = []

    # League rank emblems are provided as a first-party bundle by Riot's
    # developer portal.  Only the ten tier emblem PNGs are extracted; the
    # optional wing layers are deliberately not shipped.
    rank_zip = fetch_bytes(LOL_RANK_ARCHIVE, max_bytes=MAX_ARCHIVE_BYTES)
    try:
        archive = ZipFile(io.BytesIO(rank_zip))
    except BadZipFile as exc:
        raise RuntimeError("Riot rank emblem download was not a ZIP archive") from exc
    with archive:
        for tier in LOL_TIERS:
            member = f"Ranked Emblems Latest/Rank={tier}.png"
            try:
                member_info = archive.getinfo(member)
                if member_info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                    raise RuntimeError(f"Riot rank bundle member is too large: {member}")
                raw = archive.read(member)
            except KeyError as exc:
                raise RuntimeError(f"Riot rank bundle is missing {member}") from exc
            assets.append(
                write_asset(
                    AssetSpec(
                        asset_id=f"lol.rank.{tier.lower()}",
                        game="league_of_legends",
                        kind="rank",
                        local_path=f"lol/ranks/{tier.lower()}.png",
                        source_url=LOL_RANK_ARCHIVE,
                        source_kind="riot_developer_portal",
                        source_detail=member,
                        max_dimension=192,
                    ),
                    raw,
                )
            )

    # TFT rank art and the map/arena artwork are Data Dragon assets from the
    # same patch.  TFT's regalia JSON is the authoritative filename index.
    tft_regalia_url = f"{DD_API}/cdn/{version}/data/en_US/tft-regalia.json"
    tft_regalia = fetch_json(tft_regalia_url)
    for tier in TFT_TIERS:
        filename = select_tft_filename(tft_regalia, tier)
        source_url = f"{DD_API}/cdn/{version}/img/tft-regalia/{filename}"
        assets.append(
            write_asset(
                AssetSpec(
                    asset_id=f"tft.rank.{tier.lower()}",
                    game="teamfight_tactics",
                    kind="rank",
                    local_path=f"tft/ranks/{tier.lower()}.png",
                    source_url=source_url,
                    source_kind="data_dragon",
                    source_detail=f"tft-regalia.json:RANKED_TFT.{tier}",
                    max_dimension=192,
                ),
                fetch_bytes(source_url),
            )
        )

    artwork_specs = (
        AssetSpec(
            asset_id="lol.artwork.summoners_rift",
            game="league_of_legends",
            kind="artwork",
            local_path="artwork/lol-summoners-rift.png",
            source_url=f"{DD_API}/cdn/{version}/img/map/map11.png",
            source_kind="data_dragon",
            source_detail="map11 (Summoner's Rift)",
            max_dimension=640,
        ),
        AssetSpec(
            asset_id="tft.artwork.default_arena",
            game="teamfight_tactics",
            kind="artwork",
            local_path="artwork/tft-default-arena.png",
            source_url=f"{DD_API}/cdn/{version}/img/tft-arena/1.png",
            source_kind="data_dragon",
            source_detail="tft-arena.json:Base",
            max_dimension=640,
        ),
    )
    for spec in artwork_specs:
        assets.append(write_asset(spec, fetch_bytes(spec.source_url)))

    # Valorant metadata and artwork are exposed by valorant-api.com, whose
    # media URLs point at Riot's public game assets.  Use fixed English
    # metadata, stable UUID filenames, and record the upstream manifest version
    # so a checked-in refresh remains auditable even after the live API moves.
    val_version_url = f"{VALORANT_API}/v1/version"
    val_version_payload = fetch_json(val_version_url).get("data")
    if not isinstance(val_version_payload, dict):
        raise RuntimeError("Valorant API returned no version metadata")
    val_manifest_id = val_version_payload.get("manifestId")
    val_version = val_version_payload.get("version")
    if not isinstance(val_manifest_id, str) or not isinstance(val_version, str):
        raise RuntimeError("Valorant API returned invalid version metadata")

    val_tiers_url = f"{VALORANT_API}/v1/competitivetiers?language=en-US"
    val_table = select_valorant_table(fetch_json(val_tiers_url))
    val_table_uuid = val_table.get("uuid", "unknown")
    by_name = {
        tier.get("tierName"): tier
        for tier in val_table["tiers"]
        if isinstance(tier, dict) and isinstance(tier.get("tierName"), str)
    }
    for tier_name, output_name in VALORANT_TIERS:
        tier_record = by_name.get(tier_name)
        if not tier_record or not isinstance(tier_record.get("largeIcon"), str):
            raise RuntimeError(f"Valorant competitive table is missing {tier_name}")
        source_url = tier_record["largeIcon"]
        assets.append(
            write_asset(
                AssetSpec(
                    asset_id=f"valorant.rank.{output_name}",
                    game="valorant",
                    kind="rank",
                    local_path=f"valorant/ranks/{output_name}.png",
                    source_url=source_url,
                    source_kind="valorant_api",
                    source_detail=f"{val_tiers_url} table={val_table_uuid} tier={tier_name}",
                    max_dimension=192,
                ),
                fetch_bytes(source_url),
            )
        )

    agents_url = f"{VALORANT_API}/v1/agents?language=en-US&isPlayableCharacter=true"
    agents = select_playable_valorant_agents(fetch_json(agents_url))
    for agent_uuid, agent in agents:
        display_name = agent["displayName"]
        source_url = agent["displayIcon"]
        assets.append(
            write_asset(
                AssetSpec(
                    asset_id=f"valorant.agent.{agent_uuid}.display_icon",
                    game="valorant",
                    kind="agent_icon",
                    local_path=f"valorant/agents/{agent_uuid}.png",
                    source_url=source_url,
                    source_kind="valorant_api",
                    source_detail=f"{agents_url} agent={display_name} uuid={agent_uuid}",
                    max_dimension=256,
                    metadata={
                        "uuid": agent_uuid,
                        "display_name": display_name,
                        "is_playable_character": True,
                    },
                ),
                fetch_bytes(source_url),
            )
        )
        portrait_spec = valorant_agent_portrait_spec(agent_uuid, agent)
        assets.append(write_asset(portrait_spec, fetch_bytes(portrait_spec.source_url)))

    maps_url = f"{VALORANT_API}/v1/maps?language=en-US"
    maps = select_valorant_maps(fetch_json(maps_url))
    for map_uuid, map_record in maps:
        display_name = map_record["displayName"]
        source_url = map_record["splash"]
        assets.append(
            write_asset(
                AssetSpec(
                    asset_id=f"valorant.map.{map_uuid}.splash",
                    game="valorant",
                    kind="map_splash",
                    local_path=f"valorant/maps/{map_uuid}.png",
                    source_url=source_url,
                    source_kind="valorant_api",
                    source_detail=f"{maps_url} map={display_name} uuid={map_uuid}",
                    max_dimension=960,
                    metadata={
                        "uuid": map_uuid,
                        "display_name": display_name,
                        "map_url": map_record.get("mapUrl"),
                        "asset_path": map_record.get("assetPath"),
                    },
                ),
                fetch_bytes(source_url),
            )
        )

    ascent_entry = next((item for item in maps if item[1]["displayName"] == "Ascent"), None)
    if ascent_entry is None:
        raise RuntimeError("Valorant API did not return the Ascent splash artwork")
    ascent_uuid, ascent = ascent_entry
    ascent_url = ascent["splash"]
    assets.append(
        write_asset(
            AssetSpec(
                asset_id="valorant.artwork.ascent",
                game="valorant",
                kind="artwork",
                local_path="artwork/valorant-ascent.png",
                source_url=ascent_url,
                source_kind="valorant_api",
                source_detail=f"{maps_url} map=Ascent uuid={ascent_uuid}",
                max_dimension=960,
            ),
            fetch_bytes(ascent_url),
        )
    )

    manifest = {
        "schema_version": 2,
        "generated_at": generated_at,
        "generator": "scripts/fetch_assets.py",
        "selection": {
            "league_of_legends_ranks": list(LOL_TIERS),
            "teamfight_tactics_ranks": list(TFT_TIERS),
            "valorant_ranks": [name for name, _ in VALORANT_TIERS],
            "valorant_agents": [agent["displayName"] for _, agent in agents],
            "valorant_agent_portraits": [agent["displayName"] for _, agent in agents],
            "valorant_maps": [map_record["displayName"] for _, map_record in maps],
            "artwork": ["Summoner's Rift", "TFT default arena", "Valorant Ascent"],
        },
        "sources": {
            "riot_developer_portal_lol": {
                "url": "https://developer.riotgames.com/docs/lol",
                "rank_bundle_url": LOL_RANK_ARCHIVE,
                "note": "Riot Games official League of Legends developer assets.",
            },
            "data_dragon": {
                "url": DD_API,
                "versions_url": versions_url,
                "patch": version,
                "note": "Riot Games Data Dragon static game assets.",
            },
            "valorant_api": {
                "url": VALORANT_API,
                "version_url": val_version_url,
                "manifest_id": val_manifest_id,
                "version": val_version,
                "competitive_tiers_url": val_tiers_url,
                "competitive_tier_table_uuid": val_table_uuid,
                "agents_url": agents_url,
                "maps_url": maps_url,
                "note": "Public media index for Riot Valorant assets; direct media URLs are retained per asset.",
            },
        },
        "assets": assets,
    }
    valorant_index = valorant_renderer_index(agents, maps)
    write_json_atomic(VALORANT_INDEX_PATH, valorant_index)
    write_json_atomic(MANIFEST_PATH, manifest)
    print(
        f"Fetched {len(assets)} assets for Data Dragon {version}; "
        f"manifest: {MANIFEST_PATH}; renderer index: {VALORANT_INDEX_PATH}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        raise SystemExit(f"error: {exc}") from None
