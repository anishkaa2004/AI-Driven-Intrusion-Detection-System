# AI-IDS user guide

This guide walks through the system as a user: what each part does, what every page shows,
and how to carry out the common tasks. For installation see the [README](../README.md)
(macOS/Linux) or [WINDOWS_SETUP.md](../WINDOWS_SETUP.md).

**Contents**
1. [What AI-IDS does](#1-what-ai-ids-does)
2. [Key ideas](#2-key-ideas)
3. [Roles](#3-roles)
4. [A tour of the pages](#4-a-tour-of-the-pages)
5. [Step-by-step tasks](#5-step-by-step-tasks)
6. [What happens behind the scenes](#6-what-happens-behind-the-scenes)
7. [10-minute demo script for a presentation or viva](#7-10-minute-demo-script-for-a-presentation-or-viva)
8. [FAQ](#8-faq)

---

## 1. What AI-IDS does

AI-IDS watches **network activity metadata** from devices you are authorized to monitor and flags
patterns that *may* indicate an attack: port scans, floods, repeated failed connections, unusual DNS
activity, or traffic far above a device's normal level.

```
 Your laptop (agent) ─┐
 Other device (agent) ┼──►  Backend  ──►  Rules + ML model  ──►  Alerts  ──►  Dashboard (live)
 Demo replay tool ────┘     (checks the data)                     (stored)
```

Two detection methods work side by side:

- **Rules** — simple, transparent checks such as "one source contacted 20+ different ports in 60
  seconds". You can see exactly why a rule fired, and change its thresholds.
- **Machine-learning model** — a classifier trained on labelled traffic that recognises combinations of
  flow features (duration, packet and byte counts, rates…) typical of each attack type.

When both agree on the same activity, the alert is marked **Rule + ML**.

> AI-IDS **only alerts**. It never blocks traffic or changes your computer. An alert is a reason to
> look closer, not proof of an attack.

---

## 2. Key ideas

| Term | Meaning |
|---|---|
| **Device** | A computer you have enrolled for monitoring. |
| **Agent** | The small program running on a device that sends connection metadata to the backend. |
| **Flow** | One network conversation: protocol, source/destination address and port, duration, state, and (when available) packet and byte counts. **No content** (no web pages, messages or passwords). |
| **Heartbeat** | A health message the agent sends every 15 s (interface totals, agent CPU/memory). It is how AI-IDS knows the device is still reporting. |
| **Alert** | A finding from a rule or the model, with severity, evidence and status. |
| **Severity** | `critical`, `high`, `medium`, `low`, `info` — set by the rule or ML configuration. |
| **Detection source** | **Rule**, **ML model**, or **Rule + ML** (both agreed). |
| **Status** | Where an alert is in your investigation (below). |
| **Demo data** | Traffic sent by the replay tool, not by a real device. Always labelled with a **demo data** badge, and can be filtered out. |
| **Seen N×** | The same pattern repeated; instead of creating new alerts, the open alert is updated and its counter goes up. |

**Alert statuses**

```
 New ──► Acknowledged ──► Investigating ──► Resolved
   └────────────────────────────────────► False positive
```

- **New** — nobody has looked at it yet.
- **Acknowledged** — someone has seen it.
- **Investigating** — being actively looked into.
- **Resolved** — dealt with, or confirmed harmless with an explanation.
- **False positive** — the detection was wrong (e.g. your own network scanner). Helps you tune rules.

The first three are "open" and appear in the **Threat center**. Once an alert is resolved or marked
false positive, a new occurrence of the same pattern creates a fresh alert.

**Device health** (based on heartbeats and telemetry, not on whether your dashboard is open)

| Badge | Meaning |
|---|---|
| 🟢 **Reporting** | Heard from the device in the last 60 seconds. |
| 🟡 **Stale** | Last report 1–5 minutes ago — data may be out of date. |
| 🔴 **Not reporting** | No report for over 5 minutes — the agent stopped, crashed, or lost network. |
| ⚪ **Never seen** | Enrolled but has not sent anything yet. |
| 🔵 **Awaiting enrollment** | An enrollment code was created but not used yet. |
| **Revoked** | The device's credential has been cancelled. |

---

## 3. Roles

| Role | Can do |
|---|---|
| **Admin** | Everything: see all devices, change rule/ML/retention settings, manage users, view the full audit log. The first account created is the admin. |
| **Analyst** | Enroll and revoke their own devices, investigate and update their alerts, add notes, export. |
| **Viewer** | Read-only view of their own devices and alerts. |

Non-admins only ever see devices they own and the alerts from those devices — in the pages, the
exports and the live updates.

---

## 4. A tour of the pages

The header shows the **live connection** state: *Live updates* (green) means new data appears
instantly; *Reconnecting — polling every 30s* (amber) means the dashboard lost its live link and is
refreshing slowly until it reconnects. This is only about the dashboard; device health is shown per device.

### Dashboard

The overview for the selected period (**1h / 24h / 7d**, top right).

- **Devices reporting** — e.g. *1 / 2* with how many are stale or not reporting.
- **Flows processed** — number of flows received.
- **Alerts** and **Open alerts** — total in the period, and how many still need attention.
- **Detection engine** — *Rules + ML* when the model is loaded (with its version), *Rules only* otherwise.
- **Traffic and alerts over time** — flows (green area) and new alerts (red bars).
- **Alerts by severity / Categories / Detection source / Protocols** — breakdowns.
- **Recent alerts** — click any alert to open it.

If there are no alerts it says *No alerts observed during this period* — deliberately not "safe",
because absence of alerts is not proof of safety.

### Live monitoring

One device in detail. Choose the **device** and **time window** (15 min – 24 h) at the top right.

- **Status** — health badge and time of last report. An amber banner appears if the data is stale.
- **Collection** — **Pause collection / Resume collection** (analysts and admins). The agent stops
  collecting at its next heartbeat but keeps sending heartbeats, so you can still see it is alive.
- **Flows over time** and **Protocol distribution**.
- **Interface throughput** — bytes in/out of the whole laptop, from heartbeats (live agent only).
- **Agent health** — agent CPU and memory use, send queue, version, and collector status
  (e.g. whether it sees the full system connection table or only your own apps).
- **Recent flows** — the latest 50 flows. IP addresses are **partly hidden by default** for privacy;
  tick **Show full IP addresses** to reveal them. *Model label* shows what the ML model predicted
  and its score, or *not scored* when byte/packet counters were not collected.

### Threat center

The triage queue: open alerts (New, Acknowledged, Investigating), newest activity first.

- **Status** and **Severity** chips — click to toggle filters.
- **Device**, **category** and **source** drop-downs.
- **Include demo data** — untick to hide replayed alerts.
- **Export CSV** — downloads exactly the alerts matching the current filters.

### Incident history

The same list with **all** statuses by default plus **From / To** date filters — use it to look
back over past incidents and to export records for a report.

### Alert detail

Opened by clicking an alert.

- **Header** — severity, status, source, demo badge, title, category, device, how many times seen.
  Buttons **Mark acknowledged / investigating / resolved / false positive** change the status.
- **Why this was flagged** — the evidence: thresholds, counts, the time window, the IPs and ports
  involved, sample event ids, and for ML alerts the predicted label and scores. For Rule + ML alerts
  it lists the **corroborating rules**.
- **Feature values of the highest-scoring flow** (ML alerts) — the numbers the model saw.
- **Related flows** — the underlying flows around the alert.
- **Details** — first/last seen, rule id, model version, model score. The score is the model's
  class score and is marked **not calibrated** — 0.99 does not mean "99% chance of attack".
- **Suggested investigation** — what to check next.
- **Investigation notes** — add notes; each shows author and time.
- **Audit trail** — every status change and note on this alert.

### Devices

- **Enroll a device** — enter a name, click **Create enrollment code**. A one-time code (valid 15
  minutes, shown only once) and the exact command to run on the device appear.
- **Enrolled devices** table — status, last seen, agent version, flows in the last 24 h, open alerts.
  Click a device name to open it in Live monitoring.
- **New code** — for a device whose code expired before it was used.
- **Revoke** — immediately cancels the device's credential; its agent is rejected from then on.
- An amber banner lists devices that stopped reporting.

### ML analytics

How good the deployed model is, measured on data it never saw during training.

- An amber banner warns when the model was trained on **synthetic** data (the default bundled model).
  Those numbers prove the pipeline works, not real-world accuracy.
- **Deployed model**, **Macro F1**, **False-positive rate** (benign flows wrongly flagged), **Inference latency**.
- **Model comparison** — Logistic Regression, Decision Tree, Random Forest and the Isolation Forest
  anomaly experiment on the same test split. Click a row to see its details below.
- **Per-class metrics** and **Confusion matrix** — rows are the true class, columns the prediction;
  green diagonal = correct, red = confusions.
- **Global feature importance** — which features the model relies on overall (approximate).
- **Detection rules** — every rule's logic, required fields and **known benign causes**.

### Settings

- **Rule thresholds** — one box per rule (enabled, time window, threshold, severity). Admins edit and
  click **Save**; others can only view. Changes apply from the next batch of data and are audited.
- **ML alerting** — `min_score` (default 0.80) and `min_events` (default 3): how confident the model
  must be, and on how many flows, before it raises an alert.
- **Data retention** — how many days raw flows (default 7) and heartbeats (default 3) are kept.
  Alerts and notes are kept.
- **Users and roles** (admins) — add users, change roles, deactivate accounts. The last admin cannot be removed.

### Audit log

Who did what and when: logins (including failed ones), enrollments, revocations, alert status
changes, notes, setting changes and exports. Filter by type at the top right. Admins see everything;
others see their own actions. Passwords and credentials are never recorded.

---

## 5. Step-by-step tasks

### First login

1. Start the system (`./start.sh` on macOS, `.\start.ps1` on Windows).
2. Open http://localhost:5173 and sign in as `admin@aiids.local`, with the password from
   `backend/.demo_credentials.json`.
   *Or*, on a completely fresh install with no seed file, the login page asks you to create the
   administrator account.

### See the system working without a real attack

1. Start with `./start.sh --demo` (or `.\start.ps1 -Demo`), or run
   `python scripts/replay_flows.py --scenario all` while the system is running.
2. Watch the **Dashboard** — alerts appear without refreshing.
3. Open the **Threat center**: you will see port-scan, flood (DoS), connection-failure, brute-force
   and DNS alerts, all with **demo data** badges.

The replay sends records through the normal API; it does not send any traffic over the network.

| Scenario | Expected alerts |
|---|---|
| `normal` | none at high severity |
| `port_scan` | *Possible port scan* (high) + ML *PortScan* (Rule + ML) |
| `flood` | *High flow rate towards …* (high) + ML *DoS* from many sources |
| `conn_failures` | *Repeated connection failures* + ML *BruteForce* |
| `dns` | *High DNS query rate* and *Repeated DNS failures* |

### Monitor your own laptop

1. **Devices** → name it → **Create enrollment code**.
2. In a terminal in the `agent` folder run the `register` command shown on screen; type `y` to confirm
   you are authorized.
3. Run `python -m agent run` (or start with `--agent` / `-Agent`).
4. Within ~15 s the device shows **Reporting**. Open it in **Live monitoring**.

Everyday browsing usually produces **no alerts** — that is expected.

### Investigate an alert

1. Open it from the **Threat center**, click **Mark acknowledged**.
2. Read **Why this was flagged**: which IP, how many ports/flows/failures, against which threshold, in what window.
3. Check **Related flows** and the **known benign causes** of the rule (ML analytics → Detection rules).
   Ask: is the source one of my own tools? Was a big download or backup running?
4. Click **Mark investigating** if you need to dig further (e.g. check the device's login logs for a
   *repeated connection failures* alert).
5. Add a **note** with what you found.
6. Finish with **Mark resolved** (explained) or **Mark false positive** (detection was wrong).
   Everything is recorded in the **Audit trail**.

### Reduce false positives

If a rule keeps firing on harmless activity (e.g. your own scanner), an admin can raise its threshold
or lower its severity under **Settings → Rule thresholds**, or disable it. Re-run the scenario and
check the **Audit log** shows the change. Note what you changed and why for your report.

### Pause or stop monitoring a device

- **Pause** temporarily: Live monitoring → **Pause collection**.
- **Stop permanently**: Devices → **Revoke**. Then on the device run `python -m agent forget` to delete
  the stored credential.

### Export a report

**Incident history** → set filters/dates → **Export CSV**. The file contains only alerts you are allowed
to see, and the export is recorded in the audit log.

### Add a team member

Admin → **Settings → Users and roles** → email, initial password (10+ characters), role → **Add user**.

### Train on a real dataset

The bundled model uses synthetic data. For reportable results, download the CICIDS2017
*MachineLearningCVE* CSVs into `ml/data/CICIDS2017/`, run
`python ml/src/train.py --dataset cicids2017 --sample-per-file 100000`, and restart the backend.
The ML analytics page then shows the new model and metrics. Details in [ml/README.md](../ml/README.md).

---

## 6. What happens behind the scenes

Following one batch of flows from the agent to your screen:

1. **Agent** looks at the computer's connection table every 2 s and, when a connection ends, turns it
   into a flow record. It sends up to 200 at a time with its device credential, retrying with backoff if
   the backend is unreachable.
2. **Backend checks** the credential (revoked devices are refused), the size of the request, and each
   flow individually — malformed flows are rejected with a reason, flows already received are ignored as
   duplicates.
3. **ML model** scores flows that have packet/byte counters. Flows without them are stored unscored
   rather than guessed.
4. **Rules** look at sliding time windows of the device's recent flows.
5. **Fusion**: if a rule and the model point at the same IP, the ML alert becomes **Rule + ML** and its
   severity goes up one level (up to high).
6. **Deduplication**: if the same pattern already has an open alert from the last 15 minutes, that alert
   is updated (*seen N×*) instead of creating a new one.
7. Everything is **saved**, and only then **pushed live** to the dashboards of the device's owner and admins.

---

## 7. 10-minute demo script for a presentation or viva

| Time | Do | Say |
|---|---|---|
| 0:00 | Show the Dashboard (empty or quiet). | "AI-IDS combines transparent rules with an ML classifier. Monitoring only happens on devices I've enrolled." |
| 1:00 | **Devices**: show *This laptop* reporting, open it in **Live monitoring**. Toggle *Show full IP addresses*. | "The agent sends connection metadata only — no content. IPs are masked by default. Health comes from heartbeats." |
| 2:30 | Run `replay_flows.py --scenario normal`. | "Baseline traffic produces no high-severity alert." |
| 3:00 | Run `--scenario port_scan` with the Dashboard visible. | "Alerts arrive live over WebSockets — no refresh." |
| 4:00 | Open the port-scan alert. Walk through the evidence and *corroborating rules*. | "Every alert explains itself: threshold, window, IPs, ports. Rule and model agreed, so it's Rule + ML. The model score is not a probability." |
| 5:30 | Acknowledge → add a note → resolve. Show the **Audit trail**. | "Investigation actions are audited." |
| 6:30 | **ML analytics**: comparison table, confusion matrix, FPR. | "I report precision, recall, F1 and false-positive rate per class, not just accuracy, because the data is imbalanced." (Be upfront if the model is synthetic-trained.) |
| 8:00 | **Devices** → **Revoke** the demo device; run the replay again → it fails with 401. | "Revoked credentials are rejected immediately." |
| 9:00 | Stop the laptop agent; wait for **Stale**. | "If an agent stops, the dashboard says so rather than showing old data as current." |
| 9:30 | **Settings** and **Audit log**. | "Thresholds are configurable and every change is recorded." |

Tip: revoking the demo device stops the replay tool. To get a new one, run
`python scripts/seed_demo_data.py` again — it replaces a revoked demo device and keeps your login.

Likely viva questions and answers are in section 29 of [PROJECT_BLUEPRINT.md](../PROJECT_BLUEPRINT.md).

---

## 8. FAQ

**Why is my laptop showing no alerts?** Normal use rarely matches attack patterns. Use the replay tool
to demonstrate detections.

**Why do live flows say "not scored"?** The operating system's connection table doesn't provide
per-connection byte/packet counts, and the model needs them, so live flows are checked by the rules only.
Replayed and dataset flows include counters and are scored.

**Does the website itself monitor my computer?** No. A browser can't see your network traffic; the
separate agent does, and only after you enroll and confirm authorization.

**Can it detect every attack?** No. It only sees what the agent collects, and models trained on benchmark
data may not transfer to real networks. Treat alerts as leads to investigate.

**Why was I logged out?** Sessions last 60 minutes, and also end if the backend restarts without a fixed
`AIIDS_SECRET_KEY` in `backend/.env`.

**Where is my data stored?** In `backend/aiids.db` on your machine. Raw flows are deleted after the
retention period (Settings → Data retention).

**How do I start completely fresh?** Stop everything, delete `backend/aiids.db*` and
`backend/.demo_credentials.json`, and start again.
