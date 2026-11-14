# AI-IDS — Intelligent Network Intrusion Detection and Real-Time Threat Monitoring

A hybrid rule-based + machine-learning intrusion detection prototype for a user's own laptop
and other explicitly authorized devices. Built from [PROJECT_BLUEPRINT.md](PROJECT_BLUEPRINT.md).

> **Educational, defensive prototype.** Alerts are evidence-backed indicators that need human
> investigation, not proof that an attack occurred. Monitor only devices you own or are
> explicitly authorized to monitor. Nothing here blocks traffic.

```
 authorized agent ─┐                      ┌─ rule engine (R001–R005) ─┐
 replay tool ──────┼─► FastAPI ingestion ─┤                            ├─► fusion ─► alerts DB ─► WebSocket ─► React dashboard
                   │   (auth, validation, └─ ML inference (versioned) ─┘                    │
                   │    idempotency)                                                         └─► REST API / CSV export
```

**Guides:** [Developer manual (Word, Windows + VS Code)](docs/AI-IDS_Developer_Manual.docx) · [User guide — tour of the system](docs/USER_GUIDE.md) ·
[Windows setup](WINDOWS_SETUP.md) · [Architecture](docs/architecture.md) · [API](docs/api-specification.md)

## What is implemented

| Area | Status |
|---|---|
| User auth (scrypt hashes, short-lived JWT, login throttling), roles admin/analyst/viewer | ✅ |
| Device enrollment with single-use 15-min codes, per-device hashed credentials, revocation | ✅ |
| Telemetry ingestion: typed schema, partial acceptance, idempotent event ids, size/rate limits | ✅ |
| Rule engine: port scan, flow rate, connection failures, DNS anomalies, volume vs baseline | ✅ configurable |
| ML: LR / Decision Tree / Random Forest + Isolation Forest experiment, versioned + checksummed | ✅ |
| Detection fusion (documented), dedup of repeated alerts | ✅ |
| WebSocket live updates with auth, per-user scoping, reconnect + resync + polling fallback | ✅ |
| Dashboard, live monitoring, threat center, alert evidence, notes, statuses, history, CSV export | ✅ |
| Device health from heartbeats (online / stale / offline), pause collection from dashboard | ✅ |
| ML analytics page (per-class metrics, confusion matrix, FPR, latency, feature importance) | ✅ |
| Settings (thresholds, ML, retention), user management, audit log | ✅ |
| Lightweight Python agent (psutil connection table, heartbeats, retry/backoff) | ✅ |
| Safe replay of synthetic scenarios or CICIDS2017 rows | ✅ |
| Tests: 34 backend (unit + API + integration), 4 agent | ✅ |
| PDF reports, multi-tenancy, Alembic migrations, Docker images | ❌ not built (see Future work) |

## Repository layout

```
ai-ids/
├── backend/        FastAPI app (app/api, app/services, app/models, ...) + tests/
├── frontend/       React + TypeScript + Tailwind + Recharts dashboard
├── agent/          Monitoring agent (python -m agent ...) + tests/
├── ml/             src/ (prepare_data, train, evaluate, synthetic), artifacts/, reports/
├── scripts/        seed_demo_data.py, replay_flows.py
└── docs/           architecture, API, data dictionary, test plan, report outline
```

## One-command start

On Windows use `.\start.ps1` (`-Demo`, `-Agent`) — see [WINDOWS_SETUP.md](WINDOWS_SETUP.md).

```bash
./start.sh            # backend + dashboard, opens http://localhost:5173
./start.sh --demo     # also replays demo attack traffic every 30 s
./start.sh --agent    # also runs the monitoring agent (enroll it first)
```

On first run it creates the virtualenv, installs packages, writes `backend/.env`, trains the model
and seeds an admin account (password in `backend/.demo_credentials.json`). Ctrl+C stops everything;
logs go to `logs/`.

## Quick start, step by step (macOS / Linux)

Requirements: Python 3.12+ (developed on 3.14), Node.js 20+.

```bash
python3 -m venv .venv
```
```bash
.venv/bin/pip install -r backend/requirements.txt -r agent/requirements.txt
```
```bash
cp .env.example backend/.env   # then set AIIDS_SECRET_KEY (command is in the file)
```

**1. Train a model** (≈20 s; uses synthetic data unless you download CICIDS2017 — see [ml/README.md](ml/README.md)):

```bash
.venv/bin/python ml/src/train.py
```

**2. Start the backend** (API docs at http://127.0.0.1:8000/api/docs):

```bash
cd backend && ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**3. Start the dashboard** in another terminal, then open http://localhost:5173:

```bash
cd frontend && npm install && npm run dev
```

The first account you register becomes the administrator.

**4. Demo data without touching the network** — creates an admin + demo device (credentials are
written to the git-ignored `backend/.demo_credentials.json`) and replays labelled scenarios:

```bash
.venv/bin/python scripts/seed_demo_data.py
```
```bash
.venv/bin/python scripts/replay_flows.py --scenario all
```

Use `--loop 30` to keep sending every 30 s during a presentation. Replayed alerts are tagged
**demo data** everywhere in the UI and exports.

**5. Monitor this laptop** — on the *Devices* page create an enrollment code, then:

```bash
cd agent && ../.venv/bin/python -m agent register --server http://127.0.0.1:8000 --code XXXX-XXXX-XXXX
```
```bash
cd agent && ../.venv/bin/python -m agent run
```

The agent prints exactly what it collects and asks you to confirm authorization. Without
`sudo` on macOS it can only see your own user's processes' connections (it tells you so in the
dashboard); with elevated privileges it reads the full connection table.

## Tests

```bash
cd backend && ../.venv/bin/python -m pytest -q
```
```bash
cd agent && ../.venv/bin/python -m pytest -q
```
```bash
cd frontend && npm run build
```

## Demonstration scenarios (blueprint §20.6)

| # | Scenario | How | Expected |
|---|---|---|---|
| 1 | Normal baseline | `replay_flows.py --scenario normal` | no high-severity alert |
| 2 | Port scan | `--scenario port_scan` | R001 (high) + ML PortScan marked *Rule + ML* |
| 3 | Flood | `--scenario flood` | R002 (high) + ML DoS from many sources |
| 4 | Repeated failures | `--scenario conn_failures` | R003 + ML BruteForce |
| 5 | DNS anomaly | `--scenario dns` | R004 query-rate and failure-rate alerts |
| 6 | Revoked agent | revoke on Devices page, agent stops with *credential rejected* | 401 |
| 7 | Offline agent | stop the agent | status → *Stale* after 60 s, *Not reporting* after 5 min |
| 8 | Analyst workflow | acknowledge / add note / resolve | visible in alert audit trail and Audit log |

## Honest limitations

- The bundled model is trained on **synthetic** data; its metrics only prove the pipeline works.
  Train on CICIDS2017 for reportable numbers, and still treat them as benchmark results that may
  not transfer to real traffic.
- The live agent sees connection metadata only (no byte/packet counters per connection), so ML
  scoring applies to replayed/dataset flows; live flows go through the rules. Very short
  connections between polls are missed. A pcap/flow-exporter collector would remove both limits.
- Brute-force detection from flows is only a suspicion; confirming it needs authentication logs.
- Rate limiters are in-process (single worker). Tables are created with `create_all`; add Alembic
  before evolving the schema in a shared deployment.

See [docs/architecture.md](docs/architecture.md) for design details and the fusion policy.
