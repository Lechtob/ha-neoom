"""Helpers for mapping neoom units to Home Assistant friendly units."""

from __future__ import annotations

UNIT_MAP = {
    "None": None,
    "Wh": "Wh",
    "W": "W",
    "V": "V",
    "A": "A",
    "Hz": "Hz",
    "%": "%",
    "°C": "°C",
    "s": "s",
    "h": "h",
}


def normalize_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    return UNIT_MAP.get(unit, unit)
