# NOOP Push for Home Assistant

Receive health data exported by the [NOOP app](https://github.com/ryanbr/noop)
directly in Home Assistant through a self-hosted HTTP(S) push receiver.

> **Status:** early release (`0.1.4`). The integration is suitable for testing
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

## Test capabilities discovery

The endpoint requires both bearer authentication and the protocol-version
header:

```powershell
$headers = @{
    Authorization = "Bearer YOUR_TOKEN"
    "NOOP-Push-Accept-Version" = "1.0"
}

Invoke-RestMethod `
    -Method Get `
    -Uri "https://home.example.com/api/noop/push" `
    -Headers $headers
```

Expected response:

```json
{
  "type": "capabilities",
  "protocolVersion": "1.0",
  "receiverStateId": "stable-uuid",
  "streams": [
    "battery",
    "dailyMetric",
    "hrSample",
    "sleepSession"
  ]
}
```

The `receiverStateId` should remain unchanged after a Home Assistant restart.

## Test a batch manually

The receiver accepts `application/x-ndjson`. NOOP normally sends gzip-compressed
payloads, but an uncompressed request is useful for troubleshooting:

```powershell
curl.exe `
  -X POST `
  -H "Authorization: Bearer YOUR_TOKEN" `
  -H "Content-Type: application/x-ndjson" `
  --data-binary "@C:\path\to\batch.ndjson" `
  "https://home.example.com/api/noop/push"
```

For a gzip request, add:

```text
Content-Encoding: gzip
```

and upload the `.gz` file with `--data-binary`.

A successful request returns an acknowledgement containing the original batch
identity:

```json
{
  "protocolVersion": "1.0",
  "batchId": "batch-uuid",
  "stream": "hrSample",
  "deviceId": "device-id",
  "endCursor": null,
  "acceptedRows": 1,
  "status": "accepted"
}
```

## Security and limits

- Every request requires a bearer token.
- The decoded NDJSON payload is limited to 4 MiB.
- A batch may contain at most 5,000 records.
- Authorization headers and health-record payloads must not be logged.
- Invalid credentials return `401`.
- Unsupported protocol versions return `406`.
- Unsupported media types return `415`.
- Malformed payloads return `400`.
- Duplicate primary keys return `409`.
- Unsupported streams return `422`.

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

## Troubleshooting

### The config flow returns HTTP 500

Update the integration through HACS and restart Home Assistant. Check
**Settings → System → Logs** for a `noop_push` traceback.

### The app reports `4 of 12 data types`

This is expected. The current release advertises only:

```text
hrSample, battery, dailyMetric, sleepSession
```

### The receiver returns `invalid_gzip`

Confirm that the uploaded file is actually gzip-compressed. If testing an
uncompressed NDJSON file, remove the `Content-Encoding: gzip` header.

### Entities show `unknown`

First confirm that the sync returned a successful acknowledgement. Then check
the exact entity ID in **Developer tools → States** and inspect
**Settings → System → Logs** immediately after a sync. Old entities from
previous releases may remain in Home Assistant's entity registry; remove stale
entries after confirming the current integration version is installed.

### The same batch is retried

Retries with the same decoded NDJSON payload are intentionally idempotent.
The receiver stores a SHA-256 hash of the decoded payload and returns the
previous acknowledgement.

## Data storage

The integration uses Home Assistant's storage helper rather than writing to the
recorder database. Stored data includes records, acknowledgements, replacement
staging, and receiver state.

The receiver state ID is persisted so a Home Assistant restart does not create
a new destination identity.

## Development

Run the syntax and focused checks locally:

```powershell
python -m compileall -q custom_components tests
python -m pytest -q
```

The Home Assistant pytest plugin currently requires a Unix-compatible
environment because it imports `fcntl`; Linux-based CI is recommended for the
full Home Assistant test suite.

## Protocol reference

The implementation follows the NOOP Push protocol version 1.0:

<https://github.com/ryanbr/noop/blob/main/docs/PUSH_PROTOCOL.md>
