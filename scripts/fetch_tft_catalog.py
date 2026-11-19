"""Archive TFT sets and their localized spells for offline champion cards.

Run: uv run --with pillow python scripts/fetch_tft_catalog.py
Use --patch <version> to import a new snapshot without deleting older sets.
Raw downloads are cached under build/; only normalized data and thumbnails ship.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "src/renderer/data/tft"
ASSETS = ROOT / "src/renderer/assets/profiles/tft-library"
CACHE = ROOT / "build/profile-catalogs"
LOCALES = {"en": "en_us", "fr": "fr_fr", "ko": "ko_kr"}
# Last complete snapshots before a set/half-set disappeared from the game files.
# Latest also contains revivals; imports preserve the original snapshots below.
ARCHIVES = {"9.21": [1], "10.5": [2], "10.11": [3], "10.18": [3], "10.25": [4],
            "11.8": [4], "11.14": [5], "11.21": [5], "12.3": [6], "12.10": [6],
            "12.22": [7], "13.11": [8], "13.24": [9, 10], "14.22": [11, 12],
            "latest": [13, 14, 15, 16, 17, 18]}

METATFT_LOOKUP = "https://data.metatft.com/lookups/TFTSet18_latest_{locale}.json"


def download(patch: str, path: str, *, limit: int = 40_000_000) -> bytes:
    if not re.fullmatch(r"(?:latest|\d+\.\d+)", patch) or not re.fullmatch(r"[a-z0-9_./@ -]+", path) or ".." in path:
        raise ValueError("Invalid CommunityDragon asset path")
    target = CACHE / patch / path
    if target.exists():
        return target.read_bytes()
    with requests.Session() as session:
        session.trust_env = False
        with session.get(f"https://raw.communitydragon.org/{patch}/{path}", timeout=30, stream=True) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError("TFT asset exceeds size limit")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return bytes(data)


def source_sets(catalog: dict) -> list[dict]:
    if catalog.get("setData"):
        return catalog["setData"]
    return [dict(value, number=int(number), mutator=f"TFTSet{number}") for number, value in catalog["sets"].items()]


def unit_id(unit: dict) -> str | None:
    key = unit.get("apiName")
    if not key:
        # The first export predates apiName. Its portrait filename is the Riot ID.
        key = Path(unit.get("icon", "")).name.split(".")[0]
    return key if re.fullmatch(r"[A-Za-z0-9_]{1,128}", key or "") else None


def thumbnail(patch: str, candidates: list[str | None]) -> str | None:
    for candidate in dict.fromkeys(candidates):
        if not isinstance(candidate, str) or not candidate.lower().startswith("assets/"):
            continue
        path = "game/" + re.sub(r"\.(tex|dds)$", ".png", candidate.lower())
        try:
            raw = download(patch, path, limit=8_000_000)
            with Image.open(io.BytesIO(raw)) as image:
                image = image.convert("RGBA")
                image.thumbnail((128, 128), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, format="WEBP", quality=90, method=6)
            data = output.getvalue()
            name = hashlib.sha256(data).hexdigest()[:24] + ".webp"
            ASSETS.mkdir(parents=True, exist_ok=True)
            (ASSETS / name).write_bytes(data)
            return f"tft-library/{name}"
        except (requests.RequestException, OSError, ValueError):
            continue
    return None


def bin_hash(value: str) -> str:
    result = 2166136261
    for byte in value.lower().encode():
        result = ((result ^ byte) * 16777619) & 0xffffffff
    return "{" + format(result, "08x") + "}"


def normalize_calculation(value):
    """Older exports hash field names and omit type annotations."""
    fields = ["mSpellCalculations", "mFormulaParts", "mDataValue", "mSubpart", "mSubparts", "mRatio", "mStat",
              "mNumber", "mCoefficient", "mPart1", "mPart2", "mMultiplier", "mModifiedGameCalculation",
              "mSpellCalculationKey", "mDisplayAsPercent", "mStyleTag", "mStyleTagIfScaled"]
    hashes = {bin_hash(name): name for name in fields}
    if isinstance(value, list):
        return [normalize_calculation(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {hashes.get(k, k): normalize_calculation(v) for k, v in value.items()}
    if "__type" not in result:
        if "mFormulaParts" in result:
            result["__type"] = "GameCalculation"
        elif "mSubpart" in result and "mRatio" in result:
            result["__type"] = "SubPartScaledProportionalToStat"
        elif set(result) == {"mDataValue"}:
            result["__type"] = "NamedDataValueCalculationPart"
        elif set(result) == {"mNumber"}:
            result["__type"] = "NumberCalculationPart"
    return result


def spell_data(patch: str, unit: dict) -> tuple[dict, dict]:
    """Export calculations, never guess ModifiedFoo = Foo (often false)."""
    character = (unit.get("characterName") or unit_id(unit) or "").lower()
    paths = [f"game/characters/{character}.cdtb.bin.json", f"game/data/characters/{character}/{character}.bin.json"]
    if patch != "latest" and int(patch.split('.')[0]) < 16:
        paths.reverse()
    raw = None
    for path in paths:
        try:
            raw = json.loads(download(patch, path, limit=4_000_000))
            break
        except (requests.RequestException, ValueError):
            continue
    if raw is None:
        return {}, {}
    # Match the exported tooltip variables to a single spell. Do not merge
    # unrelated spells that happen to contain the same Damage variable.
    spells = [normalize_calculation(value["mSpell"]) for value in raw.values()
              if isinstance(value, dict) and "mSpell" in value]
    variables = {v["name"].lower() for v in unit.get("ability", {}).get("variables", [])}
    def data_values(spell):
        return spell.get("DataValues", spell.get("mDataValues", []))
    def score(spell):
        names = {v.get("name", v.get("mName", "")).lower() for v in data_values(spell)}
        return len(names & variables), bool(spell.get("mSpellCalculations")), len(names)
    spell = max(spells, key=score, default={})
    values = {v.get("name", v.get("mName")): v.get("values", v.get("mValues", [0] * 7)) for v in data_values(spell) if v.get("name", v.get("mName"))}
    return spell.get("mSpellCalculations", {}), values


@lru_cache(maxsize=3)
def translations(patch: str, locale: str) -> dict:
    try:
        raw = download(patch, f"game/{locale}/data/menu/{locale}/tft.stringtable.json")
        return json.loads(raw).get("entries", {})
    except (requests.RequestException, ValueError):
        return {}


def expand_terms(description: str | None, strings: dict) -> str:
    description = description or ""
    for _ in range(5):
        expanded = re.sub(r"\{\{([^}]+)\}\}", lambda m: strings.get(m[1].lower(), m[0]), description)
        if expanded == description:
            break
        description = expanded
    return description


def curve_star_values(points: list) -> list[float] | None:
    """Use the provider's step rows, not interpolated/invented star values."""
    if not points or any(not isinstance(p, list) or len(p) != 2 or
                         any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in p)
                         for p in points):
        return None
    points = sorted(points)
    return [0] + [next((value for level, value in reversed(points) if level <= star), points[0][1])
                  for star in range(1, 5)]


def normalize_curve_ability(unit: dict, ability: dict | None = None) -> dict:
    """Adapt the Set 18 curve-table export to our safe text/formula renderer.

    MetaTFT's published lookup exposes the new game's structured attributes,
    while the matching CDragon character bins still contain placeholder spells.
    Keep calculation terms intact, especially mixed AD/AP and live-only stacks.
    """
    ability = ability if ability is not None else unit.get("ability", {})
    curves = {**unit.get("curveTable", {}), **unit.get("curveValues", {}),
              **ability.get("curveTable", {}), **ability.get("curveValues", {})}
    variables = {}
    for name, points in curves.items():
        values = curve_star_values(points)
        if values is not None:
            variables[f"Curve.{name}"] = values
    calculations = {name: {"__type": "GameCalculationCurveTable", **calculation}
                    for name, calculation in ability.get("attributeCalcs", {}).items()}
    # Only preserve explicit numeric values where there is no source formula.
    for name, values in ability.get("attributeValues", {}).items():
        if name not in calculations and isinstance(values, list) and values and all(
                isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) for v in values):
            variables[name] = [0, *values]

    icons = {"ap": "scaleAP", "ad": "scaleAD", "health": "scaleHealth", "armor": "scaleArmor",
             "mr": "scaleMR", "as": "scaleAS", "mana": "scaleMana", "crit": "scaleCrit",
             "critmult": "scaleCritMult", "range": "scaleRange", "damageamp": "scaleDA",
             "durability": "scaleDR", "omnivamp": "scaleSV", "manaregen": "scaleManaRegen"}

    def replace_tag(match):
        tag = match[0]
        kind = re.match(r"<\s*(\w+)", tag)[1].lower()
        attrs = {name.lower(): value for name, value in re.findall(r'([\w-]+)\s*=\s*"([^"]*)"', tag)}
        icon_names = attrs.get("icon", attrs.get("id", "")).split(",")
        rendered_icons = "".join(f"%i:{icons[key]}%" for name in icon_names
                                 if (key := name.strip().lower().removeprefix("icon.")) in icons)
        expression = ""
        if kind == "tftcurvetable" and attrs.get("row"):
            expression = "Curve." + attrs["row"]
        elif kind == "tftattribute":
            expression = attrs.get("attributeid", "")
        if expression:
            format_name = attrs.get("format", "").lower()
            suffix = ""
            if format_name in ("percent", "p"):
                expression += "*100"
                suffix = "%"
            elif format_name == "percentminusone":
                # This format is used by attack-speed curves (1.6 -> 60%).
                formatted = expression + ".PercentMinusOne"
                if expression in variables:
                    variables[formatted] = [0, *[(v - 1) * 100 for v in variables[expression][1:]]]
                elif calculations.get(expression, {}).get("resolved") is True:
                    values = calculations[expression].get("values", [])
                    if values and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values):
                        variables[formatted] = [0, *[(v - 1) * 100 for v in values]]
                expression, suffix = formatted, "%"
            return f"@{expression}@{suffix}" + (" " if rendered_icons else "") + rendered_icons
        return rendered_icons

    description = re.sub(r"<\s*(?:TFTAttribute|TFTCurveTable|img)\b[^>]*>", replace_tag,
                         ability.get("desc", ""), flags=re.IGNORECASE)
    return {"name": ability.get("name", ""), "description": description,
            "variables": variables, "calculations": calculations}


def curve_units_by_asset(catalog: dict) -> dict:
    result = {}
    for unit in catalog.get("units", []):
        assets = unit.get("assetNames", [])
        if assets:
            result[assets[0]] = (unit, unit.get("ability", {}))
        for index, extra in enumerate(unit.get("extraAbilities", {}).values(), 1):
            key = extra.get("apiName", "")
            asset = key if key.startswith("DA_") else assets[index] if index < len(assets) else None
            if asset:
                result[asset] = (unit, extra)
    return result


def enrich_set18_tooltips() -> None:
    """Refresh only Set 18 tooltips; retain provider/PBE provenance per ability.

    Run --set18-tooltips. Cached inputs can be removed separately to request a
    newer snapshot. No account data is used and other archived sets are untouched.
    """
    localized, sources = {}, {}
    for language, locale in LOCALES.items():
        cache = CACHE / f"metatft-set18-{locale}.json"
        url = METATFT_LOOKUP.format(locale=locale)
        if cache.exists():
            data = cache.read_bytes()
        else:
            with requests.Session() as session:
                session.trust_env = False
                response = session.get(url, timeout=30)
                response.raise_for_status()
                data = response.content
            if len(data) > 8_000_000:
                raise ValueError("Set 18 lookup exceeds size limit")
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(data)
        parsed = json.loads(data)
        metadata = parsed.get("_metadata", {})
        if metadata.get("set") != "TFTSet18" or metadata.get("tooltips") != "curvetable":
            raise ValueError("Unexpected Set 18 tooltip format")
        localized[language] = curve_units_by_asset(parsed)
        sources[language] = {"provider": "MetaTFT", "url": url, "sha256": hashlib.sha256(data).hexdigest(),
                             "patch": metadata.get("patch", "unknown"), "generated": metadata.get("generated", ""),
                             "coreHash": metadata.get("coreHash", "")}
    if len({(s["patch"], s["coreHash"]) for s in sources.values()}) != 1:
        raise ValueError("Set 18 tooltip locales refer to different snapshots")
    path = DEST / "sets" / "18.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for variant in catalog["variants"].values():
        for key, unit in variant.get("units", {}).items():
            if key not in localized["en"]:
                continue
            source_unit, source_ability = localized["en"][key]
            normalized = normalize_curve_ability(source_unit, source_ability)
            ability = unit["ability"]
            ability["variables"], ability["calculations"] = normalized["variables"], normalized["calculations"]
            for language, lookup in localized.items():
                local_unit, local_ability = lookup.get(key, localized["en"][key])
                translated = normalize_curve_ability(local_unit, local_ability)
                ability["names"][language] = translated["name"]
                ability["descriptions"][language] = translated["description"]
                ability["variables"].update(translated["variables"])
            ability["source"] = {field: sources["en"][field] for field in ("provider", "patch", "generated", "url")}
            changed += 1
    catalog.setdefault("sources", {})["metatft-set18-tooltips"] = sources
    path.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Enriched {changed} Set 18 abilities ({sources['en']['patch']} snapshot)", flush=True)


def enrich_catalogs() -> None:
    """Refresh derived spell metadata without downloading/encoding art again."""
    for path in sorted((DEST / "sets").glob("*.json"), key=lambda p: int(p.stem)):
        catalog = json.loads(path.read_text(encoding="utf-8"))
        for variant in catalog["variants"].values():
            if "units" not in variant:
                continue
            patch = variant["patch"]
            strings = {lang: translations(patch, locale) for lang, locale in LOCALES.items()}
            def enrich(item):
                key, unit = item
                ability = unit["ability"]
                if ability.get("source", {}).get("provider") == "MetaTFT":
                    # These newer curve tables must not be replaced by stale
                    # CDragon template spells during a legacy archive refresh.
                    return
                raw = {"apiName": key, "ability": {"variables": [{"name": k} for k in ability["variables"]]}}
                calculations, values = spell_data(patch, raw)
                ability["calculations"] = calculations
                ability["variables"] = {**values, **ability["variables"]}
                ability["descriptions"] = {lang: expand_terms(desc, strings.get(lang, {})) for lang, desc in ability["descriptions"].items()}
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(enrich, variant["units"].items()))
        path.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"Enriched set {catalog['number']}", flush=True)


def import_patch(patch: str, allowed: list[int] | None) -> None:
    catalogs, sources = {}, {}
    for language, locale in LOCALES.items():
        data = download(patch, f"cdragon/tft/{locale}.json")
        catalogs[language] = source_sets(json.loads(data))
        sources[language] = {"url": f"https://raw.communitydragon.org/{patch}/cdragon/tft/{locale}.json",
                             "sha256": hashlib.sha256(data).hexdigest()}
    numbers = sorted({s["number"] for s in catalogs["en"] if allowed is None or s["number"] in allowed})
    for number in numbers:
        filename = DEST / "sets" / f"{number}.json"
        previous = json.loads(filename.read_text(encoding="utf-8")) if filename.exists() else {}
        variants = previous.get("variants", {})
        current_sets = [s for s in catalogs["en"] if s["number"] == number and len(s["champions"]) > 10]
        # Keep genuinely different rosters (including half-sets), but don't copy
        # an identical roster for every queue. The mutator remains addressable.
        for current in current_sets:
            mutator = current.get("mutator", f"TFTSet{number}")
            old_variant = variants.get(mutator, {})
            if old_variant.get("units") and old_variant.get("patch") != patch:
                # Some half-sets reuse the same mutator. Retain removed units too.
                previous_key = f"{mutator}_{old_variant['patch'].replace('.', '_')}"
                variants.setdefault(previous_key, old_variant)
            localized = {lang: next((s for s in rows if s["number"] == number and s.get("mutator", f"TFTSet{number}") == mutator), current)
                         for lang, rows in catalogs.items()}
            maps = {lang: {unit_id(u): u for u in data["champions"]} for lang, data in localized.items()}
            def build_unit(unit):
                key = unit_id(unit)
                if not key:
                    return None
                translations = {lang: rows.get(key, unit) for lang, rows in maps.items()}
                ability = unit.get("ability") or {}
                calculations, extra_values = spell_data(patch, unit)
                variables = {v["name"]: v["value"] for v in ability.get("variables", []) if isinstance(v.get("value"), list)}
                variables = {**extra_values, **variables}
                portrait = thumbnail(patch, [unit.get("squareIcon"), unit.get("tileIcon"), unit.get("icon")])
                icon = thumbnail(patch, [ability.get("icon")])
                return key, {"names": {lang: u.get("name") for lang, u in translations.items()}, "cost": unit.get("cost"),
                             "role": unit.get("role"), "stats": unit.get("stats", {}), "portrait": portrait,
                             "traits": {lang: u.get("traits", []) for lang, u in translations.items()},
                             "ability": {"names": {lang: (u.get("ability") or {}).get("name", "") for lang, u in translations.items()},
                                         "descriptions": {lang: (u.get("ability") or {}).get("desc", "") for lang, u in translations.items()},
                                         "icon": icon, "variables": variables, "calculations": calculations}}
            # Reuse an identical roster inside this patch without refetching art.
            signature = hashlib.sha256(json.dumps(current["champions"], sort_keys=True).encode()).hexdigest()
            if variants.get(mutator, {}).get("signature") == signature and variants[mutator].get("patch") == patch:
                continue
            duplicate = next((v for v in variants.values() if v.get("signature") == signature and v.get("patch") == patch), None)
            if duplicate:
                variants[mutator] = {"alias": next(k for k, v in variants.items() if v is duplicate)}
                continue
            with ThreadPoolExecutor(max_workers=8) as pool:
                units = dict(row for row in pool.map(build_unit, current["champions"]) if row)
            variants[mutator] = {"patch": patch, "signature": signature, "units": units}
        if not variants:
            continue
        standard = next((k for k in variants if re.fullmatch(r"TFT_?Set" + str(number), k)), next(iter(variants)))
        result = {"number": number, "defaultVariant": standard, "sources": {**previous.get("sources", {}), patch: sources}, "variants": variants}
        filename.parent.mkdir(parents=True, exist_ok=True)
        filename.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"Set {number}: {len(variants)} variants ({patch})", flush=True)


def build_index() -> None:
    units = {}
    for path in sorted((DEST / "sets").glob("*.json"), key=lambda p: int(p.stem)):
        catalog = json.loads(path.read_text(encoding="utf-8"))
        variants = catalog["variants"]
        # Default roster wins where a champion also occurs in a special mode.
        default = catalog["defaultVariant"]
        preferred = variants[default].get("alias", default)
        order = sorted(variants, key=lambda key: key == preferred)
        for variant in order:
            for key, unit in variants[variant].get("units", {}).items():
                entry = {"set": catalog["number"], "variant": variant, "names": unit["names"], "cost": unit["cost"], "portrait": unit["portrait"]}
                versions = units.setdefault(key, {})
                versions[str(catalog["number"])] = entry
    (DEST / "index.json").write_text(json.dumps({"units": units}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch", help="CommunityDragon patch (e.g. 16.19 or latest); preserves all other sets")
    parser.add_argument("--enrich-only", action="store_true", help="Refresh formulas and localized terms in the existing archive")
    parser.add_argument("--set18-tooltips", action="store_true", help="Refresh only Set 18 curve-table tooltips from the published MetaTFT lookup")
    args = parser.parse_args()
    if args.set18_tooltips:
        enrich_set18_tooltips()
        raise SystemExit(0)
    if not args.enrich_only:
        for patch, allowed in ({args.patch: None} if args.patch else ARCHIVES).items():
            import_patch(patch, allowed)
    enrich_catalogs()
    build_index()
