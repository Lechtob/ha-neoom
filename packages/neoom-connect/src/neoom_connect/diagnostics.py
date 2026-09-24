"""Allowlisted diagnostics without tokens, names, locations or original IDs."""

import math
from typing import Any

from .models import EnergyFlow, SiteConfiguration, State


def numeric_value(value: Any) -> int | float | None:
    """Do not turn booleans, malformed strings or NaN into measurements."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value if math.isfinite(value) else None


def diagnostic_report(
    configuration: SiteConfiguration | None,
    flow: EnergyFlow,
    things: dict[str, dict[str, State]],
) -> dict[str, Any]:
    """Rebuild a report from safe fields instead of redacting an arbitrary payload."""

    def readings(states):
        return {
            key: {
                "value": state.value
                if isinstance(state.value, bool)
                else numeric_value(state.value),
                "timestamp": state.timestamp.isoformat() if state.timestamp else None,
            }
            for key, state in states.items()
            if key not in {"SERIAL_NUMBER", "LAST_RFID_CARD", "CHARGING_PROCESS_ID"}
        }

    def points(data_points):
        return [
            {
                "key": point.key,
                "type": point.data_type,
                "unit": point.unit,
                "controllable": point.controllable,
            }
            for point in data_points.values()
        ]

    return {
        "energy_flow": readings(flow.states),
        "energy_flow_metadata": points(configuration.energy_flow_data_points)
        if configuration
        else [],
        "devices": [
            {
                "device": index,
                "type": thing.type,
                "data_points": points(thing.data_points),
                "states": readings(things.get(thing.id, {})),
            }
            for index, thing in enumerate(configuration.things.values(), 1)
        ]
        if configuration
        else [],
    }
