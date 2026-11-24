"""Bundle Riot's TFT stat glyphs from CommunityDragon's game exports.

The source CSS maps spell tokens such as %i:scaleAP% to Riot texture paths.
The exporter packs those paths into an atlas. Keep the source metadata in build/
so extraction can be reviewed and regenerated without runtime HTTP requests.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "build/profile-catalogs/latest"
BASE = "https://raw.communitydragon.org/latest/"
DEST = ROOT / "src/renderer/assets/profiles/tft-stats"
FONT_PATH = "game/ux/fonts.cdtb.bin.json"
ATLAS_MAP_PATH = "game/ux/fonts/css/stylesheet.cdtb.json"
TOKENS = {
    "ap": "scaleAP", "ad": "scaleAD", "armor": "scaleArmor", "mr": "scaleMR",
    "health": "scaleHealth", "mana": "scaleMana", "attack-speed": "scaleAS",
    "range": "scaleRange", "crit": "scaleCrit", "crit-multiplier": "scaleCritMult",
    "gold": "goldCoins",
}


def fetch(path: str) -> bytes:
    if not re.fullmatch(r"[a-z0-9_./-]+", path) or ".." in path:
        raise ValueError("Invalid CommunityDragon asset path")
    destination = CACHE / (path + "index.html" if path.endswith("/") else path)
    if destination.exists():
        return destination.read_bytes()
    with build_opener(ProxyHandler({})).open(BASE + path, timeout=30) as response:
        data = response.read(8_000_001)
        if len(data) > 8_000_000:
            raise ValueError("Stat asset exceeds size limit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return bytes(data)


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href", "") or ""
            if re.fullmatch(r"[a-z0-9_-]+(?:[./][a-z0-9_-]+)*(?:/)?", href):
                self.links.append(href)


def discover(directory: str, depth: int = 0) -> list[str]:
    listing = Links()
    listing.feed(fetch(directory).decode("utf-8"))
    files: list[str] = []
    for name in listing.links:
        if name.endswith("/") and depth < 3:
            files.extend(discover(directory + name, depth + 1))
        elif name.endswith((".json", ".png", ".atlas")):
            path = directory + name
            fetch(path)
            files.append(path)
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--check", action="store_true", help="Verify bundled assets against cached Riot data")
    args = parser.parse_args()
    font_bytes = fetch(FONT_PATH)
    fonts = json.loads(font_bytes)
    icons = fonts["UX/Fonts/CSS/StyleSheet"]["icons"]
    if args.discover:
        for directory in ("game/ux/fonts/", "game/uiautoatlas/ux/fonts/css/"):
            for path in discover(directory):
                raw = fetch(path)
                print(json.dumps({"path": path, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}))
        return

    atlas_map_bytes = fetch(ATLAS_MAP_PATH)
    atlas_map = json.loads(atlas_map_bytes)
    manifest = {
        "source": "Riot Games spell-text glyphs, extracted by CommunityDragon",
        "documentation": "https://communitydragon.org/documentation/assets",
        "fontDefinitions": {"url": BASE + FONT_PATH, "sha256": hashlib.sha256(font_bytes).hexdigest()},
        "atlasMapping": {"url": BASE + ATLAS_MAP_PATH, "sha256": hashlib.sha256(atlas_map_bytes).hexdigest()},
        "transformation": "Exact atlas crop; original RGBA pixels, no redraw, tint or resampling",
        "icons": {},
    }
    generated: dict[str, bytes] = {}
    for key, token in TOKENS.items():
        texture = icons[token]["texture"].lower()
        mapping = atlas_map[texture]
        atlas_path = "game/" + mapping["atlasPath"].lower()
        raw = fetch(atlas_path)
        with Image.open(io.BytesIO(raw)) as atlas:
            atlas = atlas.convert("RGBA")
            left, top, right, bottom = (
                round(mapping["startX"] * atlas.width), round(mapping["startY"] * atlas.height),
                round(mapping["endX"] * atlas.width), round(mapping["endY"] * atlas.height),
            )
            if not (0 <= left < right <= atlas.width and 0 <= top < bottom <= atlas.height):
                raise ValueError(f"Invalid Riot atlas rectangle for {token}")
            crop = atlas.crop((left, top, right, bottom))
            if crop.getchannel("A").getbbox() is None:
                raise ValueError(f"Riot glyph is empty: {token}")
            output = io.BytesIO()
            crop.save(output, format="PNG", optimize=True)
            png = output.getvalue()
            generated[f"{key}.png"] = png
            manifest["icons"][key] = {
                "path": f"tft-stats/{key}.png", "token": token, "texture": texture,
                "source": BASE + atlas_path, "sourceSha256": hashlib.sha256(raw).hexdigest(),
                "atlasSize": list(atlas.size), "crop": [left, top, right - left, bottom - top],
                "width": crop.width, "height": crop.height, "sha256": hashlib.sha256(png).hexdigest(),
            }
    generated["index.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if args.check:
        changed = [name for name, content in generated.items() if not (DEST / name).exists() or (DEST / name).read_bytes() != content]
        if changed:
            raise SystemExit("Stat assets differ: " + ", ".join(changed))
        print(f"Verified {len(TOKENS)} Riot stat glyphs against source metadata and pixels")
    else:
        DEST.mkdir(parents=True, exist_ok=True)
        for name, content in generated.items():
            (DEST / name).write_bytes(content)
        print(f"Bundled {len(TOKENS)} Riot stat glyphs with source URLs, hashes and exact crop coordinates")


if __name__ == "__main__":
    main()
