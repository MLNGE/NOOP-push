# NOOP Push for Home Assistant

Receive health data exported by the [NOOP app](https://github.com/ryanbr/noop)
directly in Home Assistant through a self-hosted HTTP(S) push receiver.

> **Status:** early release. The current version is recorded in the integration
> manifest. The integration is suitable for testing
> the NOOP Push protocol and receiving the supported streams. Review the
> limitations below before using it as a long-term data archive.

## Features

- Authenticated `GET` capabilities discovery.
- Authenticated gzip-compressed NDJSON `POST` ingestion.
- Persistent storage using Home Assistant's integration storage.
- Idempotent retries for previously accepted batches.
- Duplicate primary-key detection.
- Append delivery for heart-rate and battery data.
- Replacement-window delivery for daily metrics and sleep sessions.
- Automatic multi-part replacement staging.
- Empty replacement-window support.
- Home Assistant sensors and battery-charging binary sensors.
- Stable receiver state across Home Assistant restarts.

## Supported streams

The receiver currently advertises four of NOOP's twelve protocol streams:

| Stream | Delivery | Home Assistant entities |
| --- | --- | --- |
| `hrSample` | Append | Latest heart rate |
| `battery` | Append | Battery percentage and charging state |
| `dailyMetric` | Replace window | Recovery, strain, HRV, sleep, steps, calories, and related metrics |
| `sleepSession` | Replace window | Latest completed sleep duration, efficiency, HRV, heart rate, respiration, score, start, and end |

The NOOP app may therefore report that the receiver supports **4 of 12 data
types**. This is expected. Unsupported streams are not advertised and are
rejected if sent.

## Requirements

- Home Assistant with custom integrations enabled.
- The NOOP app configured for self-hosted push.
- An HTTPS URL reachable by the NOOP app.
- A shared bearer token configured in both NOOP and Home Assistant.

HTTPS is strongly recommended. Do not expose a bearer-authenticated endpoint
over public or untrusted plain HTTP.

## Installation with HACS

This repository is currently installed as a custom HACS repository:

1. Open **HACS → Integrations**.
2. Open the three-dot menu.
3. Select **Custom repositories**.
4. Add:

   ```text
   https://github.com/MLNGE/NOOP-push
   ```

5. Select **Integration** as the category.
6. Install **NOOP Push**.
7. Restart Home Assistant.

## Releases

Versions are kept synchronized in `custom_components/noop_push/manifest.json`
and `pyproject.toml`. To create a release, run the **Release** GitHub Actions
workflow manually and enter a semantic version such as `0.1.15`. The workflow
updates both version files, commits the bump to `main`, creates a matching
`v0.1.15` tag, and publishes GitHub release notes.

## Configuration

1. Open **Settings → Devices & services**.
2. Select **Add integration**.
3. Search for **NOOP Push**.
4. Enter a non-empty bearer token.
5. Select the streams to enable.
6. Choose the daily-metric preference and append retention setting. Retention
   configuration is exposed for the storage cleanup milestone and is not yet
   applied automatically.

The receiver endpoint is:

```text
/api/noop/push
```

For example:

```text
https://home.example.com/api/noop/push
```

The token is stored in the config entry and is not exposed through entity
state, attributes, diagnostics, or logbook entries.

## Security and limits

- Every request requires a bearer token.
- The decoded NDJSON payload is limited to 4 MiB.
- A batch may contain at most 5,000 records.
- Authorization headers are never logged. With debug logging enabled, incoming
  health-record keys and values are logged to diagnose imports; disable debug
  logging when troubleshooting is complete.
- Invalid credentials return `401`.
- Unsupported protocol versions return `406`.
- Unsupported media types return `415`.
- Malformed payloads return `400`.
- Duplicate primary keys return `409`.
- Unsupported streams return `422`.

Enable **Extensive data logging** from the NOOP Push integration options when
you need to inspect incoming keys and values. It is disabled by default.
Home Assistant's `custom_components.noop_push` logger must still be set to
`debug` to display debug messages.

## Entity organization

Entities are grouped automatically by NOOP source. Different device IDs
reported by the same NOOP installation are presented as one logical Home
Assistant device. The original protocol device ID remains part of the received
batch acknowledgement.

Entity names include:

- `NOOP Heart Rate`
- `NOOP Battery`
- `NOOP Battery Charging`
- `NOOP Recovery`
- `NOOP Strain`
- `NOOP Avg HRV`
- `NOOP Steps`
- `NOOP Last Sleep Duration`
- `NOOP Last Sleep Efficiency`
- `NOOP Last Sleep Start`
- `NOOP Last Sleep End`

Fields that are absent from a NOOP record remain unavailable; they are not
silently replaced with zero.

## Protocol reference

The implementation follows the NOOP Push protocol version 1.0:

<https://github.com/ryanbr/noop/blob/main/docs/PUSH_PROTOCOL.md>
