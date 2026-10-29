"""Persistence helpers for NOOP Push."""

from __future__ import annotations

from homeassistant.helpers.storage import Store


async def async_load_receiver_state(store: Store, receiver_state_id: str) -> str:
    """Load a stable receiver state ID, initializing it when necessary."""
    data = await store.async_load() or {}
    state_id = data.get("receiverStateId", receiver_state_id)
    if data.get("receiverStateId") != state_id:
        await store.async_save({"version": 1, "receiverStateId": state_id})
    return state_id
