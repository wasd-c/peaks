"""Bundle official Riot profile artwork and localized TFT composition metadata.

Run with ``uv run --with pillow python scripts/fetch_profile_assets.py``.
Only public Data Dragon files are requested; runtime profiles stay offline.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError

from fetch_account_icons import DATA_DRAGON, ROOT, fetch
from PIL import Image

DESTINATION = ROOT / "src" / "renderer" / "assets" / "profiles"


def main() -> None:
    version = json.loads(fetch(f"{DATA_DRAGON}/api/versions.json"))[0]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid Data Dragon version")
    champions = json.loads((ROOT / "src/renderer/assets/account-icons/index.json").read_text(encoding="utf-8"))["champions"]
    destination = DESTINATION / "champions"
    destination.mkdir(parents=True, exist_ok=True)

    def splash(champion: dict) -> dict:
        identifier = champion["id"]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", identifier):
            raise ValueError("Invalid champion identifier")
        source = f"{DATA_DRAGON}/cdn/img/champion/splash/{identifier}_0.jpg"
        path = destination / f"{identifier}.webp"
        if not path.exists():
            with Image.open(io.BytesIO(fetch(source))) as image:
                image.thumbnail((1100, 700))
                image.convert("RGB").save(path, "WEBP", quality=82)
        return {"id": identifier, "path": f"champions/{identifier}.webp", "source": source, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    with ThreadPoolExecutor(max_workers=6) as pool:
        splashes = list(pool.map(splash, champions))
    print(f"Bundled {len(splashes)} champion splashes", flush=True)

    catalog: dict = {}
    sprites: set[str] = set()
    sprite_members: dict[str, list[dict]] = {}
    for kind in ("champion", "item", "trait", "augments"):
        locales = {
            language: json.loads(fetch(f"{DATA_DRAGON}/cdn/{version}/data/{language}/tft-{kind}.json"))["data"]
            for language in ("en_US", "fr_FR", "ko_KR")
        }
        rows = {}
        for key, row in locales["en_US"].items():
            icon = row.get("image", {})
            sprite = icon.get("sprite", "")
            if not re.fullmatch(r"tft-[a-z-]+\d+\.png", sprite):
                continue
            sprites.add(sprite)
            sprite_members.setdefault(sprite, []).append(icon)
            rows[row["id"]] = {
                "names": {lang: locales[locale].get(key, row)["name"] for lang, locale in (("en", "en_US"), ("fr", "fr_FR"), ("ko", "ko_KR"))},
                "sprite": sprite, "x": icon["x"], "y": icon["y"],
            }
        catalog[kind] = rows

    sprite_dir = DESTINATION / "tft"
    sprite_dir.mkdir(parents=True, exist_ok=True)

    def sprite(name: str) -> dict:
        source = f"{DATA_DRAGON}/cdn/{version}/img/sprite/{name}"
        try:
            payload = fetch(source)
        except HTTPError as error:
            if error.code not in {403, 404}:
                raise
            # Riot sometimes publishes individual icons before their sheet.
            # Rebuild that same atlas from the official images and coordinates.
            members = sprite_members[name]
            sheet = Image.new("RGBA", (480, max(icon["y"] for icon in members) + 48))
            sources = []
            for icon in members:
                filename, group = icon["full"], icon["group"]
                if not re.fullmatch(r"[A-Za-z0-9_.-]+\.png", filename) or not re.fullmatch(r"tft-[a-z-]+", group):
                    raise ValueError("Invalid TFT icon path") from None
                icon_source = f"{DATA_DRAGON}/cdn/{version}/img/{group}/{filename}"
                with Image.open(io.BytesIO(fetch(icon_source))) as image:
                    sheet.paste(image.convert("RGBA").resize((48, 48)), (icon["x"], icon["y"]))
                sources.append(icon_source)
            output = io.BytesIO()
            sheet.save(output, "PNG", optimize=True)
            payload = output.getvalue()
            (sprite_dir / name).write_bytes(payload)
            print(f"Rebuilt official sprite: {name}", flush=True)
            return {"path": f"tft/{name}", "sources": sources, "sha256": hashlib.sha256(payload).hexdigest()}
        if payload[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("Invalid sprite image")
        (sprite_dir / name).write_bytes(payload)
        return {"path": f"tft/{name}", "source": source, "sha256": hashlib.sha256(payload).hexdigest()}

    with ThreadPoolExecutor(max_workers=6) as pool:
        files = list(pool.map(sprite, sorted(sprites)))
    for rows in catalog.values():
        for row in rows.values():
            path = sprite_dir / row["sprite"]
            if path.exists():
                with Image.open(path) as image:
                    row["columns"] = image.width / 48
    tft_icon_source = "https://cmsassets.rgpub.io/sanity/images/dsfx7636/content_organization_live/99f44365b1293979d094be183adfc57ee1d8f529-24x24.svg?accountingTag=TFT"
    icon = fetch(tft_icon_source)
    if b"<svg" not in icon or any(unsafe in icon.lower() for unsafe in (b"<script", b"foreignobject", b"javascript:", b"onload=")):
        raise ValueError("Invalid TFT icon")
    (DESTINATION / "tft.svg").write_bytes(icon)
    files.append({"path": "tft.svg", "source": tft_icon_source, "sha256": hashlib.sha256(icon).hexdigest()})
    # The official League mark includes wide layout padding; tighten its SVG
    # viewport so the icon has the same optical size as the other games.
    league = (ROOT / "src/renderer/assets/account-icons/league.svg").read_text(encoding="utf-8")
    league = league.replace('viewBox="0 0 110 70"', 'viewBox="29 7 52 56"').replace('height="70" width="110"', 'height="24" width="24"')
    (DESTINATION / "league.svg").write_text(league, encoding="utf-8")
    files.append({"path": "league.svg", "source": "../account-icons/league.svg", "sha256": hashlib.sha256((DESTINATION / "league.svg").read_bytes()).hexdigest()})
    (DESTINATION / "tft.json").write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (DESTINATION / "manifest.json").write_text(json.dumps({"version": version, "sources": ["https://developer.riotgames.com/docs/lol#data-dragon", "https://developer.riotgames.com/docs/tft#data-dragon"], "files": splashes + files}, indent=2) + "\n", encoding="utf-8")
    print(f"Bundled {len(sprites)} TFT sprite sheets and 2 game icons from Data Dragon {version}")


if __name__ == "__main__":
    main()
