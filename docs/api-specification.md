# API specification

Interactive OpenAPI docs: **http://127.0.0.1:8000/api/docs** (generated from the code, always current).
All paths below are under `/api/v1` unless noted. User endpoints need `Authorization: Bearer <access token>`;
agent endpoints need `Authorization: Bearer <device credential>`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/register` | — | Create account (first becomes admin; disabled if `OPEN_REGISTRATION=false`) |
| POST | `/auth/login` | — | Returns `access_token`, `expires_in`, `user` |
| POST | `/auth/logout` | user | Audited; client discards token |
| GET | `/auth/me` | user | Current user |
| GET | `/auth/config` | — | Whether registration is open / any users exist |
| GET | `/dashboard/summary?hours=24` | user | Counters, series, breakdowns, recent alerts, health |
| GET | `/health` | — | DB + model status |
| GET | `/devices` | user | Devices in scope with health, 24h flow count, open alerts |
| POST | `/devices/enroll` | admin/analyst | Create pending device + single-use enrollment code |
| POST | `/devices/{id}/enrollment-code` | admin/analyst | Re-issue code for a pending device |
| GET | `/devices/{id}` | user | Device detail |
| PATCH | `/devices/{id}` | admin/analyst | `display_name`, `monitoring_paused` |
| POST | `/devices/{id}/revoke` | admin/analyst | Invalidate credential |
| GET | `/devices/{id}/traffic?minutes=60` | user | Live-monitoring series, protocols, recent flows, heartbeats |
| POST | `/agents/register` | enrollment code | Exchange code for device credential (shown once) |
| POST | `/telemetry/batch` | device | Ingest ≤ 500 flow events |
| POST | `/telemetry/heartbeat` | device | Health metrics; response carries `monitoring_paused` |
| GET | `/alerts` | user | Filters: `status, severity, category, source` (comma lists), `device_id, start, end, include_demo, page, page_size` |
| GET | `/alerts/categories` | user | Distinct categories in scope |
| GET | `/alerts/{id}` | user | Evidence, recommendation, notes, audit trail, related flows |
| PATCH | `/alerts/{id}` | admin/analyst | `{"status": "acknowledged"}` etc. |
| POST | `/alerts/{id}/notes` | admin/analyst | Add investigation note |
| GET | `/reports/alerts.csv` | user | Same filters as `/alerts`; same scope |
| GET | `/models/metrics` | user | Active model manifest, experiments, registry, rule docs |
| GET | `/settings` | user | Rules / ML / retention config (editable flag) |
| PUT | `/settings/{rules\|ml\|retention}` | admin | Validated replacement |
| GET/POST | `/users` | admin | List / create users |
| PATCH | `/users/{id}` | admin | Role / active (cannot remove last admin) |
| GET | `/audit-logs?action=alert` | user | Admin: all; others: own actions |
| WS | `/ws/events` (no prefix) | first message `{"type":"auth","token":...}` | `ready`, `events`, `alert`, `device`, `pong` |

## Telemetry batch

```json
POST /api/v1/telemetry/batch
{
  "agent_version": "0.1.0",
  "source": "agent",
  "collector": "psutil-conn",
  "events": [{
    "event_id": "ag-6f1c...",              // unique per device; retries are idempotent
    "event_time": "2026-10-13T10:00:00Z",
    "protocol": "TCP",                     // TCP | UDP | ICMP | OTHER
    "src_ip": "192.168.1.20", "src_port": 51544,
    "dst_ip": "93.184.216.34", "dst_port": 443,
    "flow_duration": 1.25,                 // seconds
    "packets_in": 12, "packets_out": 9,    // optional; ML runs only when all counters are present
    "bytes_in": 9800, "bytes_out": 1400,
    "conn_state": "established",           // established | attempt | failed | reset | closed | other
    "dns_rcode": null,                     // NOERROR | NXDOMAIN | SERVFAIL | REFUSED | OTHER
    "feature_schema_version": "flow-v1"
  }]
}
```

Response:

```json
{"ingestion_id": "…", "status": "partially_accepted", "accepted": 1, "duplicates": 0,
 "rejected": [{"index": 1, "event_id": "x", "reason": "protocol: Input should be 'TCP', 'UDP', 'ICMP' or 'OTHER'"}],
 "alerts_created": 0, "alerts_updated": 0, "monitoring_paused": false}
```

Errors: `401` invalid/revoked credential · `413` body > 1 MB or > 500 events · `422` malformed envelope ·
`429` rate limit. Error bodies are `{"detail": "..."}` without stack traces.
