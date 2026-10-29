"""Tests for the NOOP Push config flow."""

from unittest.mock import patch

from custom_components.noop_push.const import CONF_RECEIVER_STATE_ID, DOMAIN


async def test_user_flow_creates_stable_receiver_state_id(hass):
    """A valid setup creates one config entry with a receiver state ID."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"

    with patch("custom_components.noop_push.config_flow.uuid4", return_value="state-id"):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "token": "secret",
                "streams": ["hrSample"],
                "detailed_daily": False,
                "retention_days": 30,
            },
        )

    assert result["type"] == "create_entry"
    assert result["result"].data[CONF_RECEIVER_STATE_ID] == "state-id"
