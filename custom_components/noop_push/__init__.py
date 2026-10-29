"""NOOP Push integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
from .coordinator import NoopPushCoordinator
from .http import NoopPushView

PLATFORMS: list[str] = ["sensor", "binary_sensor"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the NOOP Push integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NOOP Push from a config entry."""
    store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
    data = await store.async_load() or {}
    data.setdefault("receiverStateId", entry.data["receiverStateId"])
    data.setdefault("version", STORAGE_VERSION)
    await store.async_save(data)

    coordinator = NoopPushCoordinator(hass)
    coordinator.data = data.get("latest", {})
    view = NoopPushView(hass, entry, store, data["receiverStateId"], coordinator)
    hass.http.register_view(view)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "store": store,
        "view": view,
        "receiver_state_id": data["receiverStateId"],
        "coordinator": coordinator,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload NOOP Push from a config entry."""
    runtime = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if runtime is None:
        return True
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.http.unregister_view(runtime["view"].name)
    return unload_ok
