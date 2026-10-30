"""HTTP receiver for NOOP Push."""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
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
    ERROR_REPLACEMENT_CONFLICT,
    ERROR_UNAUTHORIZED,
    ERROR_UNSUPPORTED_MEDIA_TYPE,
    ERROR_UNSUPPORTED_STREAM,
    ERROR_UNSUPPORTED_PROTOCOL,
    MAX_DECODED_PAYLOAD,
    MAX_RECORDS,
    PROTOCOL_VERSION,
    REPLACEMENT_STREAMS,
)
from .coordinator import NoopPushCoordinator

_LOGGER = logging.getLogger(__name__)


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
        self._entity_adders: dict[str, Any] = {}
        self._known_entity_keys: dict[str, set[str]] = {}

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

    def set_entity_adder(
        self, platform: str, entity_adder, known_entity_keys: set[str]
    ) -> None:
        """Register a platform callback for newly discovered devices."""
        self._entity_adders[platform] = entity_adder
        self._known_entity_keys[platform] = known_entity_keys

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
            if header["stream"] not in REPLACEMENT_STREAMS:
                return _error(422, ERROR_UNSUPPORTED_STREAM)
            return await self._replace(header, records, decoded)

        payload_hash = hashlib.sha256(decoded).hexdigest()
        storage_header = self._storage_header(header)
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
                try:
                    _append_record_keys(storage_header, records)
                except ValueError:
                    return _error(409, ERROR_DUPLICATE_KEY)
                for record in records:
                    key = _record_key(storage_header, record)
                    stored_records[key] = {
                        "sourceId": header["sourceId"],
                        "deviceId": storage_header["deviceId"],
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
                _LOGGER.debug(
                    "Accepted NOOP batch stream=%s records=%d latest_fields=%s",
                    header["stream"],
                    len(records),
                    {
                        stream: sorted(
                            {
                                field
                                for record in data["latest"].values()
                                if record["stream"] == stream
                                for field in record["payload"]
                            }
                        )
                        for stream in {
                            record["stream"] for record in data["latest"].values()
                        }
                    },
                )
                await self.store.async_save(data)
                if self.coordinator is not None:
                    self.coordinator.async_set_updated_data(data["latest"])
                    self._add_new_entities(data["latest"])
                return web.json_response(ack)
            except (OSError, TypeError, ValueError):
                return _error(500, ERROR_INTERNAL)

    async def _replace(
        self, header: dict[str, Any], records: list[dict[str, Any]], decoded: bytes
    ) -> web.Response:
        """Stage and atomically apply a complete replacement window."""
        try:
            _validate_replacement(header, records)
            storage_header = self._storage_header(header)
            async with self._lock:
                data = await self.store.async_load() or {}
                acknowledgements = data.setdefault("acknowledgements", {})
                ack_key = _scope_key(header)
                payload_hash = hashlib.sha256(decoded).hexdigest()
                prior = acknowledgements.get(ack_key)
                if prior is not None:
                    if prior["payloadHash"] == payload_hash:
                        return web.json_response(prior["ack"])
                    return _error(409, ERROR_REPLACEMENT_CONFLICT)

                staging = data.setdefault("replacement_staging", {})
                scope = _replacement_scope(storage_header)
                for key in list(staging):
                    if key.startswith(scope + "|") and key != (
                        scope + "|" + header["window"]["replacementId"]
                    ):
                        del staging[key]
                stage_key = scope + "|" + header["window"]["replacementId"]
                stage = staging.setdefault(
                    stage_key,
                    {
                        "header": header,
                        "parts": {},
                    },
                )
                if _replacement_window_identity(
                    stage["header"]["window"]
                ) != _replacement_window_identity(header["window"]):
                    return _error(409, ERROR_REPLACEMENT_CONFLICT)
                part_key = str(header["window"]["part"])
                existing_part = stage["parts"].get(part_key)
                if existing_part is not None:
                    if existing_part["payloadHash"] == payload_hash:
                        return _error(409, ERROR_REPLACEMENT_CONFLICT)
                    return _error(409, ERROR_REPLACEMENT_CONFLICT)
                stage["parts"][part_key] = {
                    "payloadHash": payload_hash,
                    "records": records,
                }
                window = header["window"]
                if len(stage["parts"]) != window["parts"] or any(
                    str(part) not in stage["parts"]
                    for part in range(1, window["parts"] + 1)
                ):
                    await self.store.async_save(data)
                    return _error(409, ERROR_REPLACEMENT_CONFLICT)

                complete_records = [
                    record
                    for part in range(1, window["parts"] + 1)
                    for record in stage["parts"][str(part)]["records"]
                ]
                record_keys = {
                    _record_key(storage_header, record) for record in complete_records
                }
                if len(record_keys) != len(complete_records):
                    return _error(409, ERROR_DUPLICATE_KEY)
                stored_records = data.setdefault("records", {})
                for key in list(stored_records):
                    stored = stored_records[key]
                    if _in_replacement_window(stored, storage_header):
                        if key not in record_keys:
                            del stored_records[key]
                for record in complete_records:
                    stored_records[_record_key(storage_header, record)] = {
                        "sourceId": storage_header["sourceId"],
                        "deviceId": storage_header["deviceId"],
                        "stream": header["stream"],
                        "primaryKey": record["key"],
                        "payload": record["data"],
                        "endCursor": None,
                        "batchId": header["batchId"],
                    }
                ack = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "batchId": header["batchId"],
                    "stream": header["stream"],
                    "deviceId": header["deviceId"],
                    "endCursor": None,
                    "acceptedRows": len(records),
                    "status": "accepted",
                }
                acknowledgements[ack_key] = {
                    "payloadHash": payload_hash,
                    "ack": ack,
                }
                del staging[stage_key]
                data["latest"] = _latest_entities(stored_records)
                await self.store.async_save(data)
                if self.coordinator is not None:
                    self.coordinator.async_set_updated_data(data["latest"])
                    self._add_new_entities(data["latest"])
                return web.json_response(ack)
        except ValueError as err:
            code = str(err)
            return _error(
                409 if code == ERROR_REPLACEMENT_CONFLICT else 400,
                code,
            )
        except (OSError, TypeError, KeyError):
            return _error(500, ERROR_INTERNAL)

    def _storage_header(self, header: dict[str, Any]) -> dict[str, Any]:
        """Group all device IDs from one NOOP installation together."""
        return {**header, "deviceId": header["sourceId"]}

    def _authorize(self, request: web.Request) -> web.Response | None:
        authorization = request.headers.get("Authorization", "")
        scheme, _, supplied = authorization.partition(" ")
        expected = self.entry.data[CONF_TOKEN]
        if scheme.lower() != "bearer" or not supplied or not secrets.compare_digest(
            supplied, expected
        ):
            return _error(401, ERROR_UNAUTHORIZED)
        return None

    def _add_new_entities(self, data: dict[str, Any]) -> None:
        """Create entities for streams discovered after platform setup."""
        from .binary_sensor import create_entities as create_binary_entities
        from .sensor import create_entities as create_sensor_entities

        creators = {
            "sensor": create_sensor_entities,
            "binary_sensor": create_binary_entities,
        }
        for platform, creator in creators.items():
            callback = self._entity_adders.get(platform)
            if callback is None:
                continue
            entities = creator(
                self.coordinator,
                data,
                self._known_entity_keys.setdefault(platform, set()),
            )
            if entities:
                callback(entities)


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
    if header["delivery"] not in {"append", "replace_window"} or header["stream"] not in enabled:
        raise ValueError(ERROR_UNSUPPORTED_STREAM)
    if not isinstance(header["recordCount"], int) or not 0 <= header["recordCount"] <= MAX_RECORDS:
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
    if header["delivery"] == "append" and (
        header["recordCount"] < 1 or any(set(record["key"]) != {"ts"} for record in records)
    ):
        raise ValueError(ERROR_MALFORMED_NDJSON)


def _validate_replacement(
    header: dict[str, Any], records: list[dict[str, Any]]
) -> None:
    if header["stream"] not in REPLACEMENT_STREAMS:
        raise ValueError(ERROR_UNSUPPORTED_STREAM)
    window = header.get("window")
    if not isinstance(window, dict) or not {
        "replacementId", "selector", "startInclusive", "endExclusive",
        "part", "parts",
    }.issubset(window):
        raise ValueError(ERROR_MALFORMED_NDJSON)
    if window["selector"] not in {"day", "startTs"}:
        raise ValueError(ERROR_MALFORMED_NDJSON)
    if (
        not isinstance(window["part"], int)
        or not isinstance(window["parts"], int)
        or window["parts"] < 1
        or not 1 <= window["part"] <= window["parts"]
    ):
        raise ValueError(ERROR_MALFORMED_NDJSON)
    if header["startCursor"] is not None or header["endCursor"] is not None:
        raise ValueError(ERROR_MALFORMED_NDJSON)
    key_name = "day" if header["stream"] == "dailyMetric" else "startTs"
    if any(set(record["key"]) != {key_name} for record in records):
        raise ValueError(ERROR_MALFORMED_NDJSON)
    if window["selector"] != ("day" if key_name == "day" else "startTs"):
        raise ValueError(ERROR_MALFORMED_NDJSON)
    if any(
        not _key_in_window(record["key"][key_name], window)
        for record in records
    ):
        raise ValueError(ERROR_MALFORMED_NDJSON)


def _replacement_scope(header: dict[str, Any]) -> str:
    return json.dumps(
        [header["sourceId"], header["deviceId"], header["stream"]],
        separators=(",", ":"),
    )


def _replacement_window_identity(window: dict[str, Any]) -> dict[str, Any]:
    """Return replacement bounds and identity without the current part number."""
    return {
        key: window[key]
        for key in (
            "replacementId",
            "selector",
            "startInclusive",
            "endExclusive",
            "parts",
        )
    }


def _key_in_window(value: Any, window: dict[str, Any]) -> bool:
    return window["startInclusive"] <= value < window["endExclusive"]


def _in_replacement_window(
    stored: dict[str, Any], header: dict[str, Any]
) -> bool:
    if (
        stored["sourceId"] != header["sourceId"]
        or stored["deviceId"] != header["deviceId"]
        or stored["stream"] != header["stream"]
    ):
        return False
    key_name = "day" if header["stream"] == "dailyMetric" else "startTs"
    return _key_in_window(stored["primaryKey"].get(key_name), header["window"])


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


def _append_record_keys(
    header: dict[str, Any], records: list[dict[str, Any]]
) -> list[str]:
    """Return append keys, rejecting duplicate primary keys in one batch."""
    keys = [_record_key(header, record) for record in records]
    if len(set(keys)) != len(keys):
        raise ValueError(ERROR_DUPLICATE_KEY)
    return keys


def _latest_entities(records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for record in records.values():
        scope = (record["sourceId"], record["deviceId"], record["stream"])
        current = latest.get(scope)
        if current is None or _latest_key(record) > _latest_key(current):
            latest[scope] = record
    return {
        f"{source}|{device}|{stream}": record
        for (source, device, stream), record in latest.items()
    }


def _latest_key(record: dict[str, Any]) -> Any:
    """Return the natural-key value used to select the latest record."""
    primary_key = record["primaryKey"]
    if "endTs" in record["payload"] and record["payload"].get("endTs") is not None:
        return record["payload"]["endTs"]
    return primary_key.get("ts", primary_key.get("day", primary_key.get("startTs")))
