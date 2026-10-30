"""Tests for the NOOP Push capabilities endpoint."""

from aiohttp.test_utils import make_mocked_request
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.storage import Store

from custom_components.noop_push.http import NoopPushView
from custom_components.noop_push import _logical_record_key


def test_logical_record_key_is_hashable():
    """Persisted records can be rebuilt during integration startup."""
    record = {
        "sourceId": "source",
        "deviceId": "device",
        "stream": "hrSample",
        "primaryKey": {"ts": 123},
        "payload": {"bpm": 60},
    }

    key = _logical_record_key(record)

    assert isinstance(key, str)
    assert {key: record}[key] == record


def _view(hass):
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="noop_push",
        title="NOOP Push",
        data={"token": "secret", "streams": ["hrSample"]},
        source="user",
        entry_id="entry",
        options={},
    )
    return NoopPushView(hass, entry, Store(hass, 1, "test"), "state-id")


async def test_get_capabilities(hass):
    """GET returns the configured capabilities."""
    request = make_mocked_request(
        "GET",
        "/api/noop/push",
        headers={
            "Authorization": "Bearer secret",
            "NOOP-Push-Accept-Version": "1.0",
        },
    )
    response = await _view(hass).get(request)
    assert response.status == 200
    assert response.body is not None
    assert b'"receiverStateId": "state-id"' in response.body


async def test_get_rejects_bad_token(hass):
    """GET rejects invalid credentials."""
    request = make_mocked_request(
        "GET",
        "/api/noop/push",
        headers={"Authorization": "Bearer wrong", "NOOP-Push-Accept-Version": "1.0"},
    )
    response = await _view(hass).get(request)
    assert response.status == 401
