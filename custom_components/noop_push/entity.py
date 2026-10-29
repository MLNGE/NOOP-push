"""Base entities for NOOP Push."""

from __future__ import annotations

from homeassistant.helpers.entity import Entity


class NoopPushEntity(Entity):
    """Base class for NOOP Push entities."""

    _attr_has_entity_name = True

    def __init__(self, source_id: str, device_id: str) -> None:
        self._source_id = source_id
        self._device_id = device_id
        self._attr_device_info = {
            "identifiers": {("noop_push", f"{source_id}:{device_id}")},
            "name": f"NOOP {device_id}",
            "manufacturer": "NOOP",
            "model": "WHOOP strap",
        }
