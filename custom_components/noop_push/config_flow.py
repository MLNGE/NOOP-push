"""Config flow for NOOP Push."""

from __future__ import annotations

from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN
from homeassistant.core import callback

from .const import (
    CONF_DETAILED_DAILY,
    CONF_RECEIVER_STATE_ID,
    CONF_RETENTION_DAYS,
    CONF_STREAMS,
    DOMAIN,
    SUPPORTED_STREAMS,
)


class NoopPushConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a NOOP Push config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            if not token:
                errors[CONF_TOKEN] = "required"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                data = dict(user_input)
                data[CONF_TOKEN] = token
                data[CONF_RECEIVER_STATE_ID] = str(uuid4())
                return self.async_create_entry(
                    title="NOOP Push",
                    data=data,
                    description_placeholders={"endpoint": "/api/noop/push"},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN): str,
                vol.Required(CONF_STREAMS, default=list(SUPPORTED_STREAMS)): vol.All(
                    cv_streams,
                ),
                vol.Required(CONF_DETAILED_DAILY, default=False): bool,
                vol.Optional(CONF_RETENTION_DAYS, default=30): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=0),
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NoopPushOptionsFlow(config_entry)


def cv_streams(value):
    """Validate the selected stream names."""
    streams = list(value)
    if not streams or any(stream not in SUPPORTED_STREAMS for stream in streams):
        raise vol.Invalid("unsupported stream")
    return streams


class NoopPushOptionsFlow(config_entries.OptionsFlow):
    """Handle NOOP Push options."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DETAILED_DAILY,
                        default=self.config_entry.data.get(CONF_DETAILED_DAILY, False),
                    ): bool,
                    vol.Optional(
                        CONF_RETENTION_DAYS,
                        default=self.config_entry.data.get(CONF_RETENTION_DAYS, 30),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                }
            ),
        )
