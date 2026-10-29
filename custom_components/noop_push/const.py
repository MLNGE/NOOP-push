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

ERROR_UNAUTHORIZED = "unauthorized"
ERROR_UNSUPPORTED_PROTOCOL = "unsupported_protocol_version"

