"""Integrity checks for checked-in artwork and its fetch boundary."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _asset_script() -> ModuleType:
    path = ROOT / "scripts" / "fetch_assets.py"
    spec = importlib.util.spec_from_file_location("peaks_asset_fetcher", path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load scripts/fetch_assets.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_asset_fetcher_rejects_non_riot_media_hosts_and_redirect_ports() -> None:
    module = _asset_script()

    module._validate_asset_url("https://media.valorant-api.com/competitivetiers/icon.png")
    with pytest.raises(RuntimeError, match="allowlist"):
        module._validate_asset_url("https://example.invalid/icon.png")
    with pytest.raises(RuntimeError, match="allowlist"):
        module._validate_asset_url("https://valorant-api.com:443/v1/maps")
    with pytest.raises(RuntimeError, match="allowlist"):
        module._validate_asset_url("http://ddragon.leagueoflegends.com/icon.png")


def test_playable_valorant_agents_are_filtered_and_sorted_by_safe_uuid() -> None:
    module = _asset_script()
    payload = {
        "data": [
            {
                "uuid": "E370FA57-4757-3604-3648-499E1F642D3F",
                "displayName": "Gekko",
                "displayIcon": "https://media.valorant-api.com/agents/gekko/displayicon.png",
                "isPlayableCharacter": True,
            },
            {
                "uuid": "00000000-0000-0000-0000-000000000001",
                "displayName": "Training Bot",
                "displayIcon": "https://media.valorant-api.com/agents/bot/displayicon.png",
                "isPlayableCharacter": False,
            },
            {
                "uuid": "117ed9e3-49f3-6512-3ccf-0cada7e3823b",
                "displayName": "Cypher",
                "displayIcon": "https://media.valorant-api.com/agents/cypher/displayicon.png",
                "isPlayableCharacter": True,
            },
        ]
    }

    agents = module.select_playable_valorant_agents(payload)

    assert [uuid for uuid, _ in agents] == [
        "117ed9e3-49f3-6512-3ccf-0cada7e3823b",
        "e370fa57-4757-3604-3648-499e1f642d3f",
    ]
    assert [record["displayName"] for _, record in agents] == ["Cypher", "Gekko"]


def test_valorant_rank_selection_includes_every_division_and_unranked() -> None:
    module = _asset_script()
    tiers = dict(module.VALORANT_TIERS)

    assert len(tiers) == 26
    assert tiers["UNRANKED"] == "unranked"
    assert tiers["ASCENDANT 1"] == "ascendant-1"
    assert tiers["ASCENDANT 3"] == "ascendant-3"
    assert tiers["RADIANT"] == "radiant"


def test_agent_portrait_source_requires_full_body_artwork() -> None:
    module = _asset_script()
    agent = {
        "displayName": "Omen",
        "fullPortraitV2": "https://media.valorant-api.com/agents/omen/fullportrait.png",
    }
    portrait = module.valorant_agent_portrait_spec("8e253930-4c05-31dd-1b6c-968525494517", agent)
    assert portrait.kind == "agent_portrait"
    assert portrait.max_dimension == 1024
    assert portrait.source_url == agent["fullPortraitV2"]
    with pytest.raises(RuntimeError, match="no full portrait"):
        module.valorant_agent_portrait_spec("8e253930-4c05-31dd-1b6c-968525494517", {"displayName": "Omen"})


def test_valorant_maps_require_splashes_and_sort_by_safe_uuid() -> None:
    module = _asset_script()
    payload = {
        "data": [
            {
                "uuid": "7eaecc1b-4337-bbf6-6ab9-04b8f06b3319",
                "displayName": "Ascent",
                "splash": "https://media.valorant-api.com/maps/ascent/splash.png",
                "mapUrl": "/Game/Maps/Ascent/Ascent",
            },
            {
                "uuid": "224b0a95-48b9-f703-1bd8-67aca101a61f",
                "displayName": "Abyss",
                "splash": "https://media.valorant-api.com/maps/abyss/splash.png",
                "mapUrl": "/Game/Maps/Infinity/Infinity",
            },
        ]
    }

    maps = module.select_valorant_maps(payload)

    assert [uuid for uuid, _ in maps] == [
        "224b0a95-48b9-f703-1bd8-67aca101a61f",
        "7eaecc1b-4337-bbf6-6ab9-04b8f06b3319",
    ]
    with pytest.raises(RuntimeError, match="no splash artwork"):
        module.select_valorant_maps(
            {
                "data": [
                    {
                        "uuid": payload["data"][0]["uuid"],
                        "displayName": "Ascent",
                        "mapUrl": "/Game/Maps/Ascent/Ascent",
                    }
                ]
            }
        )
    with pytest.raises(RuntimeError, match="invalid UUID"):
        module.select_valorant_maps(
            {
                "data": [
                    {
                        "uuid": "../../escape",
                        "displayName": "Unsafe",
                        "splash": "https://media.valorant-api.com/maps/unsafe/splash.png",
                    }
                ]
            }
        )


def test_checked_in_asset_manifest_matches_every_file() -> None:
    asset_root = ROOT / "src" / "peaks" / "ui" / "assets" / "riot"
    manifest = json.loads((asset_root / "manifest.json").read_text(encoding="utf-8"))
    assets = manifest["assets"]

    asset_paths = {asset["path"] for asset in assets}
    checked_in_paths = {
        path.relative_to(asset_root).as_posix() for path in asset_root.rglob("*.png")
    }
    assert len(assets) == len({asset["id"] for asset in assets})
    assert len(asset_paths) == len(assets)
    assert asset_paths == checked_in_paths
    assert len([asset for asset in assets if asset["kind"] == "agent_icon"]) == len(
        manifest["selection"]["valorant_agents"]
    )
    assert len([asset for asset in assets if asset["kind"] == "agent_portrait"]) == len(
        manifest["selection"]["valorant_agent_portraits"]
    )
    assert len([asset for asset in assets if asset["kind"] == "map_splash"]) == len(
        manifest["selection"]["valorant_maps"]
    )
    for asset in assets:
        path = asset_root / asset["path"]
        assert path.is_file()
        payload = path.read_bytes()
        assert len(payload) == asset["bytes"]
        assert hashlib.sha256(payload).hexdigest() == asset["sha256"]


def test_renderer_valorant_index_contains_only_complete_local_lookups() -> None:
    asset_root = ROOT / "src" / "peaks" / "ui" / "assets" / "riot"
    manifest = json.loads((asset_root / "manifest.json").read_text(encoding="utf-8"))
    index = json.loads(
        (asset_root / "valorant" / "index.json").read_text(encoding="utf-8")
    )

    assert set(index) == {"agents", "maps"}
    assert len(index["agents"]) == len(manifest["selection"]["valorant_agents"])
    assert len(index["maps"]) == len(manifest["selection"]["valorant_maps"])
    assert [entry["uuid"] for entry in index["agents"]] == sorted(
        entry["uuid"] for entry in index["agents"]
    )
    assert [entry["uuid"] for entry in index["maps"]] == sorted(
        entry["uuid"] for entry in index["maps"]
    )

    manifest_paths = {asset["path"] for asset in manifest["assets"]}
    for entry in index["agents"]:
        assert set(entry) == {"displayName", "uuid", "path", "portraitPath"}
        assert entry["path"] in manifest_paths
        assert (asset_root / entry["path"]).is_file()
        assert entry["portraitPath"] in manifest_paths
        assert (asset_root / entry["portraitPath"]).is_file()
    for entry in index["maps"]:
        assert set(entry) == {"displayName", "uuid", "path", "mapUrl"}
        assert entry["path"] in manifest_paths
        assert (asset_root / entry["path"]).is_file()
        assert entry["mapUrl"].startswith("/Game/Maps/")

    serialized = json.dumps(index)
    assert "http://" not in serialized
    assert "https://" not in serialized
    assert "source_" not in serialized
