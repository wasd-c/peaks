"""Bounded, identity-free composition data from completed TFT matches."""

import re
from collections.abc import Mapping
from typing import Any


def _identifier(value: object) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100_000:
        return str(value)
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_]{1,128}", value):
        return value
    return None


def _integer(value: object, minimum: int, maximum: int) -> int | None:
    return value if type(value) is int and minimum <= value <= maximum else None


def composition_view(value: object) -> dict[str, Any]:
    """Accept Riot's match DTO or our saved DTO, never arbitrary provider fields."""
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    raw_units = value.get("units")
    if isinstance(raw_units, list) and len(raw_units) <= 32:
        units = []
        for row in raw_units:
            if not isinstance(row, Mapping):
                continue
            identifier = _identifier(row.get("character_id", row.get("characterId", row.get("id"))))
            stars = _integer(row.get("tier", row.get("stars")), 1, 4)
            if not identifier or stars is None:
                continue
            unit: dict[str, Any] = {"id": identifier, "stars": stars}
            raw_items = row.get("itemNames", row.get("item_names", row.get("items")))
            if isinstance(raw_items, list) and len(raw_items) <= 6:
                unit["items"] = [item for raw in raw_items if (item := _identifier(raw))]
            units.append(unit)
        if len(units) == len(raw_units):
            result["units"] = units
    raw_traits = value.get("traits")
    if isinstance(raw_traits, list) and len(raw_traits) <= 32:
        traits = []
        for row in raw_traits:
            if not isinstance(row, Mapping):
                continue
            identifier = _identifier(row.get("name", row.get("id")))
            count = _integer(row.get("num_units", row.get("numUnits", row.get("count"))), 0, 32)
            tier = _integer(row.get("tier_current", row.get("tierCurrent", row.get("tier"))), 0, 10)
            if identifier and count is not None and tier is not None:
                traits.append({"id": identifier, "count": count, "tier": tier})
        result["traits"] = traits
    raw_augments = value.get("augments")
    if isinstance(raw_augments, list) and len(raw_augments) <= 8:
        result["augments"] = [item for raw in raw_augments if (item := _identifier(raw))]
    return result
