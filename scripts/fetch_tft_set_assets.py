"""Bundle set-specific Riot TFT portraits, names, costs and UI border colors.

CommunityDragon distributes the original game assets and their exact API IDs.
Run: uv run --with pillow python scripts/fetch_tft_set_assets.py
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "src/renderer/assets/profiles"
BASE = "https://raw.communitydragon.org/latest/"
LOCALES = {"en": "en_us", "fr": "fr_fr", "ko": "ko_kr"}


def rarity_palette():
    """Sample actual 1-5 cost unit frames from Riot's team-planner atlas."""
    source = "game/assets/ux/tft/teamplanner/tft_teamplanner_atlas_pc.png"
    data = fetch(source, limit=1_000_000)
    palette, files = {}, []
    with Image.open(io.BytesIO(data)).convert("RGBA") as image:
        if image.size != (512, 1024):
            raise ValueError("TFT unit-frame atlas changed; review frame coordinates")
        for cost, left in enumerate((110, 189, 270, 351, 432), 1):
            pixels = [image.getpixel((x, y)) for x in range(left, left + 66) for y in range(667, 733)
                      if x < left + 2 or x >= left + 64 or y < 669 or y >= 731]
            colors = Counter((r, g, b) for r, g, b, a in pixels if a > 200 and max(r, g, b) > 30)
            color, _ = colors.most_common(1)[0]
            palette[str(cost)] = "#" + "".join(f"{channel:02x}" for channel in color)
            files.append({"source": BASE + source, "sha256": hashlib.sha256(data).hexdigest(), "cost": cost,
                          "frame": [left, 667, 66, 66], "color": palette[str(cost)]})
    return palette, files


def fetch(path: str, *, limit: int = 40_000_000) -> bytes:
    if not re.fullmatch(r"[a-z0-9_./-]+", path) or ".." in path:
        raise ValueError("Invalid catalog asset path")
    with requests.Session() as session:
        session.trust_env = False
        with session.get(BASE + path, timeout=30, stream=True) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError("Catalog asset exceeds the size limit")
            return bytes(data)


def build_set_catalog() -> None:
    cache = ROOT / "build/profile-catalogs"
    cache.mkdir(parents=True, exist_ok=True)
    catalogs = {}
    for language, locale in LOCALES.items():
        path = cache / f"tft-{locale}.json"
        if not path.exists():
            path.write_bytes(fetch(f"cdragon/tft/{locale}.json"))
        catalogs[language] = json.loads(path.read_text(encoding="utf-8"))
    newest = max(item["number"] for item in catalogs["en"]["setData"])
    units: dict[str, dict] = {}
    traits: dict[str, dict] = {}
    for language, catalog in catalogs.items():
        # Highest set wins for shared NPCs. Character API IDs stay exact.
        for current in sorted(catalog["setData"], key=lambda item: item["number"]):
            if current["number"] < newest - 1:
                continue
            for unit in current["champions"]:
                key = unit.get("apiName", "")
                if not re.fullmatch(r"[A-Za-z0-9_]{1,128}", key):
                    continue
                row = units.setdefault(key, {"names": {}})
                row["names"][language] = unit["name"]
                row.update(cost=unit.get("cost"), set=current["number"])
                if language == "en":
                    row["sourcePath"] = unit.get("squareIcon") or unit.get("tileIcon")
                    row["fallbackPath"] = unit.get("tileIcon")
            for trait in current.get("traits", []):
                key = trait.get("apiName", "")
                if re.fullmatch(r"[A-Za-z0-9_]{1,128}", key):
                    traits.setdefault(key, {"names": {}})["names"][language] = trait["name"]
    destination = DEST / "tft-units"
    destination.mkdir(parents=True, exist_ok=True)

    def portrait(item: tuple[str, dict]) -> dict:
        key, row = item
        target = destination / f"{key}.png"
        candidates = [row.pop("sourcePath", None), row.pop("fallbackPath", None)]
        for candidate in dict.fromkeys(candidates):
            if not isinstance(candidate, str) or not candidate.lower().startswith("assets/"):
                continue
            path = "game/" + re.sub(r"\.(tex|dds)$", ".png", candidate.lower())
            try:
                data = target.read_bytes() if target.exists() else fetch(path, limit=8_000_000)
                with Image.open(io.BytesIO(data)) as image:
                    image.verify()
                target.write_bytes(data)
                row["image"] = f"tft-units/{key}.png"
                return {"path": row["image"], "source": BASE + path, "sha256": hashlib.sha256(data).hexdigest()}
            except (requests.RequestException, OSError, ValueError):
                continue
        return {"id": key, "missing": True}

    with ThreadPoolExecutor(max_workers=6) as pool:
        files = list(pool.map(portrait, sorted(units.items())))
    palette, frames = rarity_palette()
    files.extend(frames)
    (DEST / "tft-sets.json").write_text(json.dumps({"set": newest, "units": units, "traits": traits, "rarityColors": palette}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (DEST / "tft-set-manifest.json").write_text(json.dumps({"source": BASE + "cdragon/tft/en_us.json", "catalogSha256": hashlib.sha256((cache / 'tft-en_us.json').read_bytes()).hexdigest(), "files": files}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"set": newest, "units": len(units), "portraits": sum('path' in item for item in files), "missing": [item['id'] for item in files if item.get('missing')], "rarityColors": palette}))


if __name__ == "__main__":
    build_set_catalog()
