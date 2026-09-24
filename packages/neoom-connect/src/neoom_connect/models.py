"""Domain models shared by cloud and local clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .exceptions import InvalidResponseError

JsonObject = dict[str, Any]


def timestamp_ms_to_datetime(value: int | float | None) -> datetime | None:
    """Convert neoom millisecond timestamps to UTC datetimes."""
    if value is None or value < 0:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


@dataclass(frozen=True, slots=True)
class Site:
    id: str
    name: str | None = None
    raw: JsonObject = field(default_factory=dict)

    @classmethod
    def from_cloud(cls, data: JsonObject) -> Site:
        if not isinstance(data, dict) or not isinstance(data.get("id"), str) or not data["id"]:
            raise InvalidResponseError("Missing site ID")
        return cls(id=str(data["id"]), name=data.get("name"), raw=data)


@dataclass(frozen=True, slots=True)
class DataPoint:
    id: str
    key: str
    data_type: str | None = None
    unit: str | None = None
    controllable: bool = False
    raw: JsonObject = field(default_factory=dict)

    @classmethod
    def from_api(cls, data_point_id: str, data: JsonObject) -> DataPoint:
        if not isinstance(data, dict) or not isinstance(data.get("key"), str):
            raise InvalidResponseError("Invalid data point metadata")
        return cls(
            id=data_point_id,
            key=str(data["key"]),
            data_type=data.get("dataType"),
            unit=data.get("unitOfMeasure"),
            controllable=bool(data.get("controllable", False)),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class Thing:
    id: str
    type: str
    data_points: dict[str, DataPoint]
    name: str | None = None
    raw: JsonObject = field(default_factory=dict)

    @classmethod
    def from_api(cls, thing_id: str, data: JsonObject) -> Thing:
        if not isinstance(data, dict) or not isinstance(data.get("dataPoints", {}), dict):
            raise InvalidResponseError("Invalid device metadata")
        data_points = {
            data_point_id: DataPoint.from_api(data_point_id, data_point)
            for data_point_id, data_point in data.get("dataPoints", {}).items()
        }
        return cls(
            id=thing_id,
            type=str(data.get("type", "UNKNOWN")),
            name=data.get("name"),
            data_points=data_points,
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class State:
    key: str
    value: Any
    data_point_id: str | None = None
    timestamp: datetime | None = None
    timestamp_ms: int | float | None = None
    raw: JsonObject = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: JsonObject) -> State:
        timestamp = data.get("ts")
        return cls(
            key=str(data["key"]),
            value=data.get("value"),
            data_point_id=data.get("dataPointId"),
            timestamp=timestamp_ms_to_datetime(timestamp),
            timestamp_ms=timestamp,
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class EnergyFlow:
    states: dict[str, State]
    raw: JsonObject = field(default_factory=dict)

    @classmethod
    def from_local_state(cls, data: JsonObject) -> EnergyFlow:
        if not isinstance(data, dict) or not isinstance(data.get("energyFlow"), dict):
            raise InvalidResponseError("Missing energyFlow object")
        return cls(states=parse_states(data["energyFlow"]), raw=data)

    @classmethod
    def from_cloud(cls, data: JsonObject) -> EnergyFlow:
        if not isinstance(data, dict):
            raise InvalidResponseError("Expected a cloud energy-flow object")
        states: dict[str, State] = {}
        for key, item in data.items():
            if key not in CLOUD_MEASUREMENTS:
                continue
            timestamp = None
            if isinstance(item, dict) and "value" in item:
                value = item["value"]
                try:
                    if item.get("time") is not None:
                        timestamp = datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
                        if timestamp.tzinfo is None:
                            raise ValueError("Missing timezone")
                        timestamp = timestamp.astimezone(UTC)
                except (ValueError, TypeError, AttributeError) as err:
                    raise InvalidResponseError("Invalid cloud timestamp") from err
            elif item is None:
                value = None
            else:
                raise InvalidResponseError("Expected a cloud time-series value")
            states[key.upper()] = State(key=key.upper(), value=value, timestamp=timestamp)
        return cls(states=states, raw=data)


@dataclass(frozen=True, slots=True)
class SiteConfiguration:
    site_id: str
    things: dict[str, Thing]
    energy_flow_data_points: dict[str, DataPoint]
    raw: JsonObject = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: JsonObject) -> SiteConfiguration:
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("siteId"), str)
            or not data["siteId"]
            or not isinstance(data.get("things"), dict)
            or not isinstance(data.get("energyFlow"), dict)
        ):
            raise InvalidResponseError("Invalid site configuration")
        things = {
            thing_id: Thing.from_api(thing_id, thing)
            for thing_id, thing in data.get("things", {}).items()
        }
        energy_flow_meta = data.get("energyFlow", {}).get("dataPoints", {})
        if not isinstance(energy_flow_meta, dict):
            raise InvalidResponseError("Invalid energy-flow metadata")
        energy_flow_data_points = {
            data_point_id: DataPoint.from_api(data_point_id, data_point)
            for data_point_id, data_point in energy_flow_meta.items()
        }
        return cls(
            site_id=str(data.get("siteId", "")),
            things=things,
            energy_flow_data_points=energy_flow_data_points,
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class Command:
    key: str
    value: Any

    def to_api(self) -> JsonObject:
        return {"key": self.key, "value": self.value}


@dataclass(frozen=True, slots=True)
class CommandResult:
    key: str
    status: str
    message: str | None = None
    raw: JsonObject = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: JsonObject) -> CommandResult:
        return cls(
            key=str(data["key"]),
            status=str(data["status"]),
            message=data.get("message"),
            raw=data,
        )


CLOUD_MEASUREMENTS = {
    "power_production",
    "power_consumption",
    "power_consumption_calc",
    "power_grid",
    "power_storage",
    "power_charging_stations",
    "power_appliances",
    "power_heating",
    "state_of_charge",
    "self_sufficiency",
}


def parse_states(data: JsonObject) -> dict[str, State]:
    """Reject invalid envelopes rather than silently reporting an empty site."""
    if not isinstance(data, dict) or not isinstance(data.get("states"), list):
        raise InvalidResponseError("Missing states list")
    try:
        states = [State.from_api(item) for item in data["states"]]
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError, OSError) as err:
        raise InvalidResponseError("Invalid data point state") from err
    return {state.key: state for state in states}
