# Data dictionary

Defined in `backend/app/models/__init__.py`. All timestamps are naive UTC in the database and
serialized with a trailing `Z`.

## users
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| email | str unique | lower-cased |
| password_hash | str | `scrypt$N$r$p$salt$hash` |
| role | str | admin / analyst / viewer |
| is_active | bool | inactive users cannot log in |
| created_at | datetime | |

## devices
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| owner_user_id | FK users | scope for non-admins |
| display_name, platform, hostname, agent_version | str | hostname/platform reported by agent |
| status | str | pending → active → revoked |
| credential_hash | sha256 hex | of the full credential; NULL after revocation |
| enrollment_code_hash, enrollment_expires_at | | single-use, cleared on use |
| created_at, enrolled_at, last_seen_at, revoked_at | datetime | health derives from last_seen_at |
| monitoring_paused | bool | relayed to agent in responses |
| last_collector, last_interface | str | |

## network_events (raw flows; deleted by retention)
| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| event_uid | str | agent-provided id; unique with device_id (idempotency) |
| device_id | FK devices | index with event_time |
| ingestion_id | uuid | groups a batch |
| source | str | agent / replay |
| event_time, received_at | datetime | |
| protocol | str | TCP/UDP/ICMP/OTHER |
| src_ip, dst_ip, src_port, dst_port | | sensitive metadata; access-controlled |
| flow_duration | float s | |
| packets_in/out, bytes_in/out | int, nullable | NULL = not collected |
| conn_state, dns_rcode | str nullable | |
| feature_schema_version | str | `flow-v1` |
| ml_label, ml_score, model_version | | NULL when not scored |

## alerts
| Column | Notes |
|---|---|
| device_id, event_id | event_id = representative flow |
| title, category, severity, status | status: new/acknowledged/investigating/resolved/false_positive |
| detection_source | rule / ml / combined |
| rule_id, model_version, score, score_meaning | score only for ML, labelled uncalibrated |
| evidence_json | thresholds, counts, sample event ids, feature values |
| recommendation | suggested investigation |
| dedup_key, occurrence_count | see architecture.md |
| is_demo | true when produced by replay data |
| first_seen_at, last_seen_at, created_at, updated_at | indexed: created_at, last_seen_at, device_id, severity, status |

## incident_notes
`id, alert_id → alerts, author_user_id → users, note, created_at`

## audit_logs
`id, actor_user_id (NULL for agent/system), action, target_type, target_id, ip_address, metadata_json (secrets scrubbed), created_at`

Actions: `auth.login`, `auth.login_failed`, `auth.logout`, `user.register`, `user.created`, `user.updated`,
`device.enroll_started`, `device.enrollment_code_reissued`, `device.enrolled`, `device.updated`, `device.revoked`,
`alert.status_changed`, `alert.note_added`, `settings.updated`, `report.alerts_exported`.

## model_registry
`model_name, model_version (unique), artifact_reference, artifact_sha256, feature_schema_version, dataset_reference, trained_at, is_active, metrics_json`

## system_settings
Key/value JSON: `rules`, `ml`, `retention` (schemas in `services/settings_service.py`).

## device_heartbeats (deleted by retention)
`device_id, received_at, interval_s, bytes/packets sent/recv (interface deltas), agent_cpu_percent, agent_memory_mb, collector_status, queued_events`

## ML feature schema flow-v1
`flow_duration, packets_in, packets_out, bytes_in, bytes_out, dst_port, dst_port_well_known,
bytes_per_packet_in, bytes_per_packet_out, packets_per_second, bytes_per_second, out_in_packet_ratio`.
IP addresses, ids and timestamps are excluded to avoid learning dataset artifacts.
