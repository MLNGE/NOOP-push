"""Binary sensor platform for NOOP Push."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
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
    """Set up NOOP Push binary sensors."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    runtime["known_binary_entity_keys"] = set()
    runtime["view"].set_entity_adder(
        "binary_sensor", async_add_entities, runtime["known_binary_entity_keys"]
    )
    async_add_entities(
        create_entities(
            runtime["coordinator"],
            runtime["coordinator"].data,
            runtime["known_binary_entity_keys"],
        )
    )


def create_entities(coordinator, data: dict, known: set[str]) -> list:
    """Create battery charging entities for observed battery streams."""
    entities = []
    for key in data:
        source_id, device_id, stream = key.split("|", 2)
        if stream != "battery":
            continue
        unique_id = f"noop_push_{source_id}_{device_id}_battery_charging"
        if unique_id in known:
            continue
        known.add(unique_id)
        entities.append(
            NoopPushChargingSensor(coordinator, source_id, device_id, stream)
        )
    return entities


class NoopPushChargingSensor(CoordinatorEntity, NoopPushEntity):
    """Expose battery charging state."""

    def __init__(self, coordinator, source_id, device_id, stream):
        CoordinatorEntity.__init__(self, coordinator)
        NoopPushEntity.__init__(self, source_id, device_id)
        self._key = f"{source_id}|{device_id}|{stream}"
        self._attr_unique_id = f"noop_push_{source_id}_{device_id}_battery_charging"
        self._attr_name = "NOOP Battery Charging"
        self._attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    @property
    def is_on(self):
        record = self.coordinator.data.get(self._key)
        return record.get("payload", {}).get("charging") if record else None
