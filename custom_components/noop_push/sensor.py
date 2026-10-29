"""Sensor platform for NOOP Push."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .entity import NoopPushEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOOP Push sensors known at startup."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    runtime = hass.data[DOMAIN][entry.entry_id]
    runtime["known_entity_keys"] = set()
    runtime["view"].set_entity_adder(
        async_add_entities, runtime["known_entity_keys"]
    )
    async_add_entities(
        create_entities(coordinator, coordinator.data, runtime["known_entity_keys"])
    )


def create_entities(coordinator, data: dict, known: set[str]) -> list:
    """Create entities for newly observed device streams."""
    entities = []
    for key in data:
        device_id, stream = key.split(":", 1)
        if stream == "hrSample":
            field, suffix, device_class = "bpm", "heart_rate", SensorDeviceClass.HEART_RATE
        elif stream == "battery":
            field, suffix, device_class = "soc", "battery", SensorDeviceClass.BATTERY
        elif stream == "dailyMetric":
            field, suffix, device_class = "recovery", "recovery", None
        elif stream == "sleepSession":
            field, suffix, device_class = "endTs", "last_sleep_end", None
        else:
            continue
        unique_id = f"noop_push_{device_id}_{suffix}"
        if unique_id in known:
            continue
        known.add(unique_id)
        entities.append(
            NoopPushMetricSensor(
                coordinator, device_id, stream, field, suffix, device_class
            )
        )
    return entities


class NoopPushMetricSensor(CoordinatorEntity, NoopPushEntity):
    """Expose the latest append metric."""

    def __init__(
        self, coordinator, device_id: str, stream: str, field: str, suffix: str,
        device_class: SensorDeviceClass,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._stream = stream
        self._field = field
        self._attr_unique_id = f"noop_push_{device_id}_{suffix}"
        self._attr_name = f"NOOP {suffix.replace('_', ' ').title()}"
        if device_class is not None:
            self._attr_device_class = device_class
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if stream == "battery":
            self._attr_native_unit_of_measurement = PERCENTAGE
        elif stream == "sleepSession":
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS

    @property
    def native_value(self):
        record = self.coordinator.data.get(f"{self._device_id}:{self._stream}")
        return record["payload"].get(self._field) if record else None
