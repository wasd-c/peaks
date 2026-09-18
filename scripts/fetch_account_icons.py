#!/usr/bin/env python3
"""Bundle Riot's compact champion portraits and game icons for the account picker.

Run ``python scripts/fetch_account_icons.py`` to refresh the Data Dragon roster.
Images are served from the local Vite asset graph at runtime, never a remote CDN.
The existing generated VALORANT agent catalog is reused without duplicating it.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "src" / "renderer" / "assets" / "account-icons"
DATA_DRAGON = "https://ddragon.leagueoflegends.com"
GAME_ICONS = {
    "League of Legends": (
        "league.svg",
        "https://cmsassets.rgpub.io/sanity/images/dsfx7636/news_live/"
        "d3b7bd9decb1e1672dcb80be4f8bc1aa05490dc1-110x70.svg?accountingTag=LoL",
    ),
    "VALORANT": (
        "valorant.png",
        "https://cmsassets.rgpub.io/sanity/images/dsfx7636/news/"
        "cbf4460132cdfeb2a97fad5f9dd25ba0bc058f76-128x128.png?accountingTag=VAL",
    ),
}
MAX_BYTES = 8 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Asset redirects are not accepted")


def fetch(url: str) -> bytes:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"ddragon.leagueoflegends.com", "cmsassets.rgpub.io"}
        or parsed.username
        or parsed.password
        or parsed.port
    ):
        raise ValueError("Invalid Riot asset source")
    request = Request(url, headers={"User-Agent": "Peaks account artwork bundler/1"})
    with build_opener(NoRedirect).open(request, timeout=30) as response:
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError("Asset source exceeds the size limit")
    return payload


def save_png(path: Path, payload: bytes) -> None:
    if payload[:8] != b"\x89PNG\r\n\x1a\n" or len(payload) < 24:
        raise ValueError("Riot asset is not a PNG")
    width, height = struct.unpack(">II", payload[16:24])
    if not (0 < width <= 512 and 0 < height <= 512):
        raise ValueError("Account portraits must remain compact")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main() -> None:
    versions = json.loads(fetch(f"{DATA_DRAGON}/api/versions.json"))
    version = str(versions[0])
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid Data Dragon version")
    data = {
        language: json.loads(fetch(f"{DATA_DRAGON}/cdn/{version}/data/{language}/champion.json"))[
            "data"
        ]
        for language in ("en_US", "fr_FR", "ko_KR")
    }

    def champion(row: dict[str, Any]) -> dict[str, Any]:
        identifier = str(row["id"])
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", identifier):
            raise ValueError("Invalid champion identifier")
        source = f"{DATA_DRAGON}/cdn/{version}/img/champion/{identifier}.png"
        payload = fetch(source)
        relative = f"champions/{identifier}.png"
        save_png(DESTINATION / relative, payload)
        return {
            "id": identifier,
            "key": str(row["key"]),
            "name": str(row["name"]),
            "names": {
                "en": str(row["name"]),
                "fr": str(data["fr_FR"][identifier]["name"]),
                "ko": str(data["ko_KR"][identifier]["name"]),
            },
            "path": relative,
            "source": source,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        champions = list(pool.map(champion, data["en_US"].values()))
    games = []
    for game, (filename, source) in GAME_ICONS.items():
        payload = fetch(source)
        path = DESTINATION / filename
        if path.suffix == ".png":
            save_png(path, payload)
        else:
            if b"<svg" not in payload or any(
                unsafe in payload.lower()
                for unsafe in (b"<script", b"foreignobject", b"javascript:", b"onload=")
            ):
                raise ValueError("Invalid game SVG")
            path.write_bytes(payload)
        games.append(
            {
                "game": game,
                "path": filename,
                "source": source,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "version": version,
        "source": "https://developer.riotgames.com/docs/lol#data-dragon",
        "gameIconSources": [
            "https://www.leagueoflegends.com/en-us/",
            "https://playvalorant.com/en-us/",
        ],
        "champions": sorted(champions, key=lambda item: item["name"].casefold()),
        "games": games,
    }
    (DESTINATION / "index.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Bundled {len(champions)} champion portraits from Data Dragon {version} and 2 game icons"
    )


if __name__ == "__main__":
    main()
