"""Constants for NOOP Push."""

from __future__ import annotations

DOMAIN = "noop_push"
NAME = "NOOP Push"
VERSION = "0.1.0"
ENDPOINT = "/api/noop/push"
PROTOCOL_VERSION = "1.0"
STORAGE_VERSION = 1
STORAGE_KEY = "noop_push"

SUPPORTED_STREAMS = ("hrSample", "battery", "dailyMetric", "sleepSession")
CONF_TOKEN = "token"
CONF_STREAMS = "streams"
CONF_DETAILED_DAILY = "detailed_daily"
CONF_RETENTION_DAYS = "retention_days"
CONF_RECEIVER_STATE_ID = "receiverStateId"
CONF_CANONICAL_DEVICE_ID = "canonical_device_id"

ERROR_UNAUTHORIZED = "unauthorized"
ERROR_UNSUPPORTED_PROTOCOL = "unsupported_protocol_version"
ERROR_UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
ERROR_INVALID_GZIP = "invalid_gzip"
ERROR_PAYLOAD_TOO_LARGE = "payload_too_large"
ERROR_MALFORMED_NDJSON = "malformed_ndjson"
ERROR_UNSUPPORTED_STREAM = "unsupported_stream"
ERROR_RECORD_COUNT_MISMATCH = "record_count_mismatch"
ERROR_DUPLICATE_KEY = "duplicate_key"
ERROR_INTERNAL = "internal_error"
ERROR_REPLACEMENT_CONFLICT = "replacement_conflict"

APPEND_STREAMS = ("hrSample", "battery")
MAX_DECODED_PAYLOAD = 4 * 1024 * 1024
MAX_RECORDS = 5000
REPLACEMENT_STREAMS = ("dailyMetric", "sleepSession")
