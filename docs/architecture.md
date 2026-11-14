# Architecture

## Components

| Component | Code | Responsibility |
|---|---|---|
| Monitoring agent | `agent/agent/` | Polls the OS connection table (psutil), turns connection lifecycles into flow-v1 records, sends batches + heartbeats with a device credential. No payloads, no process names. |
| Replay tool | `scripts/replay_flows.py` | Posts synthetic scenarios or CICIDS2017 rows through the same authenticated API, tagged `source=replay`. |
| Ingestion API | `backend/app/api/telemetry.py`, `services/ingestion.py` | Authenticates device, enforces body size / batch size / rate limits, validates each event, drops duplicates by `(device_id, event_id)`, stores events, runs detection in one transaction. |
| Feature extraction | `services/features.py` | Single canonical `compute_features()` used by both training and inference (schema `flow-v1`). |
| Rule engine | `services/rule_engine.py` | R001–R005 sliding-window rules; thresholds stored in DB (`system_settings.rules`). |
| ML inference | `services/ml_inference.py` | Loads the model named in `ml/artifacts/manifest.json` only after verifying path and SHA-256; refuses incompatible feature schemas. |
| Fusion + alerts | `services/alert_service.py` | Builds ML findings, applies the fusion policy, deduplicates into open alerts. |
| WebSocket publisher | `api/ws.py`, `websocket/manager.py` | Pushes `events`, `alert`, `device` messages, only to admins and the device owner, only after commit. |
| Dashboard | `frontend/` | React pages; reconnects with backoff, resyncs after reconnect, polls when the socket is down. |

## Event path

1. Agent/replay `POST /api/v1/telemetry/batch` with `Authorization: Bearer aiids_dev_<id>_<secret>`.
2. Credential is looked up by device id and compared (constant time) with the stored SHA-256; revoked/pending devices get 401.
3. Each event is validated individually (`FlowEvent`, `extra="forbid"`, so payload fields are rejected). Future (>5 min) or too-old (>7 days) timestamps are rejected. The response lists rejected indexes and reasons → `accepted | partially_accepted | rejected`.
4. Event ids already stored for the device are counted as duplicates (retry-safe).
5. ML predicts for events that have all counters; others are stored with `ml_label = NULL` (missing counters are never imputed as zeros).
6. Rules evaluate windows that end at an event of this batch (older activity does not re-fire).
7. Findings are fused, deduplicated, committed; then messages are published.

## Detection fusion

Policy (implemented in `alert_service.fuse`, tested in `test_units.py::test_fusion_marks_corroborated_ml_findings`):

- Rule findings and ML findings are kept as **separate alerts**, so the original outputs remain auditable.
- ML findings are grouped **per predicted label per batch** (a 40-source flood is one alert; sources are listed in evidence). An ML finding needs ≥ `min_events` flows with score ≥ `min_score` (defaults 3 and 0.80).
- If a rule finding's subject IP or destination IP appears among the IPs of an ML finding's flows in the same batch, the ML alert becomes `detection_source = combined`, lists `corroborating_rules`, and its severity is raised one level (capped at **high**). The rule alert records `ml_corroboration` in its evidence.
- No combined probability is computed. The model score shown is `predict_proba` of the predicted class and is labelled *not calibrated*.

## Deduplication

`dedup_key` = `device:rule:subject` for rules (e.g. `3:R001:10.0.0.5`) and `device:ml:label` for ML.
A finding updates an existing alert with the same key if that alert is still open
(new/acknowledged/investigating) and was last seen within `AIIDS_DEDUP_WINDOW_MINUTES` (15) of the new
finding; it increments `occurrence_count`, extends `last_seen_at` and can only raise severity.

## Device health

Computed from the last authenticated batch or heartbeat — never from the dashboard's WebSocket:
`online` ≤ 60 s, `stale` ≤ 5 min, otherwise `offline` (`never_seen` before the first report).
A background task publishes transitions every 15 s.

## Security controls (blueprint §19)

| Control | Where |
|---|---|
| scrypt password hashing, constant-time compare, dummy hash for unknown users | `core/security.py`, `api/auth.py` |
| Generic login errors, per IP+email throttling (5 / 15 min) | `api/auth.py` |
| JWT access tokens (60 min) in `Authorization` header — no cookies, so no CSRF | `core/security.py`, `frontend/src/services/api.ts` |
| Device-scoped authorization on every resource; 404 for both "missing" and "not yours" | `services/devices.py`, all routers |
| WebSocket: token sent as first message (not in URL), Origin checked, per-owner fan-out, expiry enforced | `api/ws.py`, `websocket/manager.py` |
| Request body ≤ 1 MB, batch ≤ 500 events, 120 batches/min/device | `main.py`, `api/telemetry.py` |
| Enrollment codes single-use, 15 min, stored hashed; credentials shown once | `api/devices.py` |
| Audit log with secret scrubbing; never logs passwords/tokens | `services/audit.py` |
| CSV export: same scope as UI, formula-injection escaping | `api/admin.py`, `services/reporting.py` |
| Model loading: only manifest-listed file inside artifacts dir, SHA-256 verified | `services/ml_inference.py` |
| Unhandled errors return a generic 500 without stack traces | `main.py` |
| Retention job deletes raw flows/heartbeats after N days (configurable) | `main.py` |

## Deployment notes

For anything beyond localhost: set `AIIDS_ENVIRONMENT=production` and a strong `AIIDS_SECRET_KEY`,
terminate TLS in front of uvicorn (HTTPS/WSS), narrow `AIIDS_CORS_ORIGINS`, set
`AIIDS_OPEN_REGISTRATION=false`, use PostgreSQL, run a single worker (or move rate limiting to Redis),
and never expose the ingestion endpoint without device authentication (it always requires it).
