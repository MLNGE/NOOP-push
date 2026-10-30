"""Sensor platform for NOOP Push."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfTime,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .entity import NoopPushEntity

DAILY_FIELDS = {
    "recovery": ("recovery", None, SensorStateClass.MEASUREMENT, None),
    "strain": ("strain", None, SensorStateClass.MEASUREMENT, None),
    "avgHr": ("avg_heart_rate", None, SensorStateClass.MEASUREMENT, "bpm"),
    "restingHr": ("resting_heart_rate", None, SensorStateClass.MEASUREMENT, "bpm"),
    "avgHrv": ("avg_hrv", None, SensorStateClass.MEASUREMENT, "ms"),
    "respRateBpm": ("respiratory_rate", None, SensorStateClass.MEASUREMENT, "breaths/min"),
    "skinTempDevC": ("skin_temperature", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT, UnitOfTemperature.CELSIUS),
    "totalSleepMin": ("sleep_minutes", SensorDeviceClass.DURATION, SensorStateClass.MEASUREMENT, UnitOfTime.MINUTES),
    "steps": ("steps", None, SensorStateClass.TOTAL_INCREASING, None),
    "distanceM": ("distance_meters", None, SensorStateClass.TOTAL_INCREASING, UnitOfLength.METERS),
    "activeKcalEst": ("active_calories", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_CALORIE),
    "totalKcal": ("total_calories", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING, UnitOfEnergy.KILO_CALORIE),
}

SLEEP_FIELDS = {
    "duration": ("last_sleep_duration", SensorDeviceClass.DURATION, UnitOfTime.SECONDS),
    "efficiency": ("last_sleep_efficiency", None, PERCENTAGE),
    "restingHr": ("last_sleep_resting_heart_rate", None, "bpm"),
    "avgHrv": ("last_sleep_hrv", None, "ms"),
    "respRateBpm": ("last_sleep_respiratory_rate", None, "breaths/min"),
    "score": ("last_sleep_score", None, None),
    "startTs": ("last_sleep_start", SensorDeviceClass.TIMESTAMP, None),
    "endTs": ("last_sleep_end", SensorDeviceClass.TIMESTAMP, None),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOOP Push sensors."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    runtime["known_entity_keys"] = set()
    runtime["view"].set_entity_adder("sensor", async_add_entities, runtime["known_entity_keys"])
    async_add_entities(create_entities(runtime["coordinator"], runtime["coordinator"].data, runtime["known_entity_keys"]))


def create_entities(coordinator, data: dict, known: set[str]) -> list:
    """Create all sensors represented by configured streams."""
    entities = []
    for key, record in data.items():
        source_id, device_id, stream = key.split("|", 2)
        definitions = {}
        if stream == "hrSample":
            definitions = {"bpm": ("heart_rate", None, "bpm")}
        elif stream == "battery":
            definitions = {"soc": ("battery", SensorDeviceClass.BATTERY, PERCENTAGE)}
        elif stream == "dailyMetric":
            definitions = DAILY_FIELDS
        elif stream == "sleepSession":
            definitions = dict(SLEEP_FIELDS)
            payload = record.get("payload", {})
            if "endTs" in payload and "startTs" in payload:
                payload = dict(payload)
                payload["duration"] = payload["endTs"] - payload["startTs"]
                record["payload"] = payload
        for field, definition in definitions.items():
            suffix = definition[0]
            unique_id = f"noop_push_{source_id}_{device_id}_{suffix}"
            if unique_id in known:
                continue
            known.add(unique_id)
            entities.append(
                NoopPushSensor(coordinator, source_id, device_id, stream, field, suffix, definition)
            )
    return entities


class NoopPushSensor(CoordinatorEntity, NoopPushEntity):
    """Expose one NOOP field as a Home Assistant sensor."""

    def __init__(self, coordinator, source_id, device_id, stream, field, suffix, definition):
        CoordinatorEntity.__init__(self, coordinator)
        NoopPushEntity.__init__(self, source_id, device_id)
        self._stream = stream
        self._field = field
        self._key = f"{source_id}|{device_id}|{stream}"
        self._attr_unique_id = f"noop_push_{source_id}_{device_id}_{suffix}"
        self._attr_name = f"NOOP {suffix.replace('_', ' ').title()}"
        device_class, state_class, unit = (
            (definition[1], definition[2], definition[3])
            if stream == "dailyMetric"
            else (definition[1], None, definition[2])
            if stream == "sleepSession"
            else (definition[1], SensorStateClass.MEASUREMENT, definition[2])
        )
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        record = _find_record(self.coordinator.data, self._key)
        value = _field_value(record, self._field) if record else None
        if self._attr_device_class == SensorDeviceClass.TIMESTAMP and value is not None:
            from datetime import UTC, datetime

            return datetime.fromtimestamp(value, UTC)
        return value


FIELD_ALIASES = {
    "avgHr": ("avgHr", "averageHr"),
    "restingHr": ("restingHr", "avgRhr"),
    "avgHrv": ("avgHrv", "averageHrv"),
    "respRateBpm": ("respRateBpm", "respRate"),
    "skinTempDevC": ("skinTempDevC", "skinTemp"),
    "totalSleepMin": ("totalSleepMin", "sleepMin"),
    "distanceM": ("distanceM", "distance"),
    "activeKcalEst": ("activeKcalEst", "activeCal"),
    "totalKcal": ("totalKcal", "totalCal"),
}


def _field_value(record: dict, field: str):
    """Return a protocol field, accepting names used by older senders."""
    payload = record.get("payload", {})
    if not isinstance(payload, dict):
        return None
    for candidate in FIELD_ALIASES.get(field, (field,)):
        if candidate in payload:
            return payload[candidate]
    return None


def _find_record(data: dict, key: str) -> dict | None:
    """Find a latest record across current and legacy coordinator keys."""
    record = data.get(key)
    if record is not None:
        return record
    _, device_id, stream = key.split("|", 2)
    record = data.get(f"{device_id}:{stream}")
    if record is not None:
        return record
    for candidate in data.values():
        if (
            isinstance(candidate, dict)
            and candidate.get("deviceId") == device_id
            and candidate.get("stream") == stream
        ):
            return candidate
    return None
