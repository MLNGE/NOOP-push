"""HTTP receiver for NOOP Push."""

from __future__ import annotations

import secrets
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_STREAMS,
    CONF_TOKEN,
    ENDPOINT,
    ERROR_UNAUTHORIZED,
    ERROR_UNSUPPORTED_PROTOCOL,
    PROTOCOL_VERSION,
)


class NoopPushView(HomeAssistantView):
    """Expose the NOOP Push capabilities endpoint."""

    url = ENDPOINT
    name = "api:noop_push"
    requires_auth = False

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: Store,
        receiver_state_id: str,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.store = store
        self.receiver_state_id = receiver_state_id

    async def get(self, request: web.Request) -> web.Response:
        """Return capabilities for a valid protocol request."""
        error = self._authorize(request)
        if error is not None:
            return error
        accepted = request.headers.get("NOOP-Push-Accept-Version", "")
        if PROTOCOL_VERSION not in {
            version.strip() for version in accepted.split(",") if version.strip()
        }:
            return _error(406, ERROR_UNSUPPORTED_PROTOCOL)
        return web.json_response(
            {
                "type": "capabilities",
                "protocolVersion": PROTOCOL_VERSION,
                "receiverStateId": self.receiver_state_id,
                "streams": sorted(self.entry.data[CONF_STREAMS]),
            }
        )

    async def post(self, request: web.Request) -> web.Response:
        """Reject ingestion until Milestone 2 implements it."""
        error = self._authorize(request)
        if error is not None:
            return error
        return _error(501, "not_implemented")

    def _authorize(self, request: web.Request) -> web.Response | None:
        authorization = request.headers.get("Authorization", "")
        scheme, _, supplied = authorization.partition(" ")
        expected = self.entry.data[CONF_TOKEN]
        if scheme.lower() != "bearer" or not supplied or not secrets.compare_digest(
            supplied, expected
        ):
            return _error(401, ERROR_UNAUTHORIZED)
        return None


def _error(status: int, code: str) -> web.Response:
    return web.json_response(
        {"type": "error", "protocolVersion": PROTOCOL_VERSION, "code": code},
        status=status,
    )
