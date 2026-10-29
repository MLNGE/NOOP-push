"""Coordinator for NOOP Push data."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator


class NoopPushCoordinator(DataUpdateCoordinator[dict]):
    """Coordinate updates from the persistent NOOP Push store."""

    def __init__(self, hass):
        super().__init__(hass, logger=None, name="NOOP Push")

    async def _async_update_data(self) -> dict:
        return {}
