"""HTTP receiver for NOOP Push."""

from __future__ import annotations

import gzip
import hashlib
import json
import secrets
from asyncio import Lock
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    APPEND_STREAMS,
    CONF_STREAMS,
    CONF_TOKEN,
    ENDPOINT,
    ERROR_DUPLICATE_KEY,
    ERROR_INTERNAL,
    ERROR_INVALID_GZIP,
    ERROR_MALFORMED_NDJSON,
    ERROR_PAYLOAD_TOO_LARGE,
    ERROR_RECORD_COUNT_MISMATCH,
    ERROR_UNAUTHORIZED,
    ERROR_UNSUPPORTED_MEDIA_TYPE,
    ERROR_UNSUPPORTED_STREAM,
    ERROR_UNSUPPORTED_PROTOCOL,
    MAX_DECODED_PAYLOAD,
    MAX_RECORDS,
    PROTOCOL_VERSION,
)
from .coordinator import NoopPushCoordinator


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
        coordinator: NoopPushCoordinator | None = None,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.store = store
        self.receiver_state_id = receiver_state_id
        self.coordinator = coordinator
        self._lock = Lock()
        self._active = True
        self._entity_adder = None
        self._known_entity_keys: set[str] = set()

    def configure(
        self,
        entry: ConfigEntry,
        store: Store,
        receiver_state_id: str,
        coordinator: NoopPushCoordinator,
    ) -> None:
        """Attach the view to an active config entry."""
        self.entry = entry
        self.store = store
        self.receiver_state_id = receiver_state_id
        self.coordinator = coordinator
        self._active = True

    def deactivate(self) -> None:
        """Disable requests after the config entry unloads."""
        self._active = False

    def set_entity_adder(self, entity_adder, known_entity_keys: set[str]) -> None:
        """Register the platform callback used for newly discovered devices."""
        self._entity_adder = entity_adder
        self._known_entity_keys = known_entity_keys

    async def get(self, request: web.Request) -> web.Response:
        """Return capabilities for a valid protocol request."""
        if not self._active:
            return _error(404, "not_found")
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
        """Ingest an append batch."""
        if not self._active:
            return _error(404, "not_found")
        error = self._authorize(request)
        if error is not None:
            return error
        if request.content_type != "application/x-ndjson":
            return _error(415, ERROR_UNSUPPORTED_MEDIA_TYPE)
        try:
            encoded = await request.read()
            decoded = _decode_payload(encoded, request.headers.get("Content-Encoding", ""))
        except (OSError, EOFError, ValueError):
            return _error(400, ERROR_INVALID_GZIP)
        if len(decoded) > MAX_DECODED_PAYLOAD:
            return _error(413, ERROR_PAYLOAD_TOO_LARGE)
        try:
            header, records = _parse_ndjson(decoded)
            _validate_batch(header, records, self.entry.data[CONF_STREAMS])
        except ValueError as err:
            code = str(err)
            return _error(422 if code == ERROR_UNSUPPORTED_STREAM else 400, code)
        if header["stream"] not in APPEND_STREAMS:
            return _error(422, ERROR_UNSUPPORTED_STREAM)

        payload_hash = hashlib.sha256(decoded).hexdigest()
        async with self._lock:
            try:
                data = await self.store.async_load() or {}
                acknowledgements = data.setdefault("acknowledgements", {})
                ack_key = _scope_key(header)
                prior = acknowledgements.get(ack_key)
                if prior is not None:
                    if prior["payloadHash"] == payload_hash:
                        return web.json_response(prior["ack"])
                    return _error(409, ERROR_DUPLICATE_KEY)
                stored_records = data.setdefault("records", {})
                batch_keys = set()
                for record in records:
                    key = _record_key(header, record)
                    if key in batch_keys or key in stored_records:
                        return _error(409, ERROR_DUPLICATE_KEY)
                    batch_keys.add(key)
                for record in records:
                    key = _record_key(header, record)
                    stored_records[key] = {
                        "sourceId": header["sourceId"],
                        "deviceId": header["deviceId"],
                        "stream": header["stream"],
                        "primaryKey": record["key"],
                        "payload": record["data"],
                        "endCursor": header["endCursor"],
                        "batchId": header["batchId"],
                    }
                ack = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "batchId": header["batchId"],
                    "stream": header["stream"],
                    "deviceId": header["deviceId"],
                    "endCursor": header["endCursor"],
                    "acceptedRows": len(records),
                    "status": "accepted",
                }
                acknowledgements[ack_key] = {"payloadHash": payload_hash, "ack": ack}
                data["latest"] = _latest_entities(stored_records)
                await self.store.async_save(data)
                if self.coordinator is not None:
                    self.coordinator.async_set_updated_data(data["latest"])
                    if self._entity_adder is not None:
                        from .sensor import create_entities

                        new_entities = create_entities(
                            self.coordinator, data["latest"], self._known_entity_keys
                        )
                        if new_entities:
                            self._entity_adder(new_entities)
                return web.json_response(ack)
            except (OSError, TypeError, ValueError):
                return _error(500, ERROR_INTERNAL)

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


def _parse_ndjson(payload: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not payload or not payload.endswith(b"\n") or payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError(ERROR_MALFORMED_NDJSON)
    lines = payload[:-1].split(b"\n")
    try:
        objects = [json.loads(line) for line in lines]
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError(ERROR_MALFORMED_NDJSON) from None
    if not objects or any(not isinstance(item, dict) for item in objects):
        raise ValueError(ERROR_MALFORMED_NDJSON)
    return objects[0], objects[1:]


def _decode_payload(payload: bytes, content_encoding: str) -> bytes:
    """Decode gzip while tolerating aiohttp/proxy pre-decompression."""
    if content_encoding.lower() != "gzip":
        return payload
    if payload[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(payload)
        except (OSError, EOFError):
            raise ValueError(ERROR_INVALID_GZIP) from None
    if payload.lstrip().startswith(b"{"):
        return payload
    raise ValueError(ERROR_INVALID_GZIP)


def _validate_batch(
    header: dict[str, Any], records: list[dict[str, Any]], enabled: list[str]
) -> None:
    required = {
        "type", "protocolVersion", "batchId", "sourceId", "deviceId",
        "stream", "delivery", "recordCount", "startCursor", "endCursor",
    }
    if set(header) < required or header["type"] != "batch":
        raise ValueError(ERROR_MALFORMED_NDJSON)
    if header["protocolVersion"] != PROTOCOL_VERSION:
        raise ValueError(ERROR_MALFORMED_NDJSON)
    if header["delivery"] != "append" or header["stream"] not in enabled:
        raise ValueError(ERROR_UNSUPPORTED_STREAM)
    if not isinstance(header["recordCount"], int) or not 1 <= header["recordCount"] <= MAX_RECORDS:
        raise ValueError(ERROR_RECORD_COUNT_MISMATCH)
    if header["recordCount"] != len(records):
        raise ValueError(ERROR_RECORD_COUNT_MISMATCH)
    if not all(
        isinstance(item, dict)
        and item.get("type") == "record"
        and isinstance(item.get("key"), dict)
        and isinstance(item.get("data"), dict)
        for item in records
    ):
        raise ValueError(ERROR_MALFORMED_NDJSON)
    if any(set(record["key"]) != {"ts"} for record in records):
        raise ValueError(ERROR_MALFORMED_NDJSON)


def _scope_key(header: dict[str, Any]) -> str:
    return json.dumps(
        [header["sourceId"], header["deviceId"], header["stream"], header["batchId"]],
        separators=(",", ":"),
    )


def _record_key(header: dict[str, Any], record: dict[str, Any]) -> str:
    return json.dumps(
        [header["sourceId"], header["deviceId"], header["stream"], record["key"]],
        sort_keys=True,
        separators=(",", ":"),
    )


def _latest_entities(records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for record in records.values():
        scope = (record["deviceId"], record["stream"])
        current = latest.get(scope)
        if current is None or record["primaryKey"]["ts"] > current["primaryKey"]["ts"]:
            latest[scope] = record
    return {f"{device}:{stream}": record for (device, stream), record in latest.items()}
