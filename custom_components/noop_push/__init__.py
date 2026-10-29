"""NOOP Push integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
from .coordinator import NoopPushCoordinator
from .http import NoopPushView, _latest_entities

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
    if data.get("records"):
        data["latest"] = _latest_entities(data["records"])
    await store.async_save(data)

    coordinator = NoopPushCoordinator(hass)
    coordinator.async_set_updated_data(data.get("latest", {}))
    view = hass.data[DOMAIN].get("http_view")
    if view is None:
        view = NoopPushView(hass, entry, store, data["receiverStateId"], coordinator)
        hass.http.register_view(view)
        hass.data[DOMAIN]["http_view"] = view
    else:
        view.configure(entry, store, data["receiverStateId"], coordinator)
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
    runtime["view"].deactivate()
    return unload_ok
