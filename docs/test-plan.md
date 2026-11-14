# Test plan

Run: `cd backend && ../.venv/bin/python -m pytest -q` (34 tests) and `cd agent && ../.venv/bin/python -m pytest -q` (4 tests).

| Blueprint item | Test |
|---|---|
| Rule threshold & window logic | `test_units.py::test_port_scan_threshold_and_window`, `test_sliding_max_respects_window`, `test_conn_failures_only_count_failed_states`, `test_volume_deviation_needs_baseline`, `test_already_evaluated_events_do_not_refire` |
| Feature extraction / missing values | `test_features_schema_and_missing_counters` |
| Fusion and severity mapping | `test_fusion_marks_corroborated_ml_findings` |
| Password hashing, credential parsing, audit scrubbing, CSV escaping | `test_password_hash_roundtrip`, `test_parse_device_id`, `test_audit_scrub`, `test_csv_formula_escaping` |
| Successful / failed login, generic errors | `test_first_user_is_admin_and_login_errors_are_generic` |
| Login throttling | `test_login_throttling` |
| Unauthenticated access | `test_protected_endpoints_require_auth` |
| Enrollment single use | `test_enrollment_code_is_single_use` |
| Revoked device rejected | `test_revoked_device_is_rejected` |
| Invalid schema, partial acceptance, idempotency | `test_batch_partial_acceptance_and_idempotency`, `test_payload_fields_are_rejected` |
| Oversized batch | `test_oversized_batch_rejected` |
| User A cannot read/update/export/revoke User B's data | `test_user_cannot_access_other_users_devices_or_alerts`, `test_second_device_cannot_write_into_first` |
| Viewer read-only | `test_viewer_cannot_modify` |
| Test event → rule → DB → alert, dedup, status + note audited | `test_port_scan_alert_end_to_end_with_audit` |
| ML inference with registered schema; combined alert | `test_ml_classifies_flows_when_model_present` |
| Normal baseline → no high alert | `test_normal_traffic_produces_no_high_severity_alert` |
| WebSocket auth and streaming | `test_websocket_requires_auth_and_streams_alerts` |
| Settings validation + audit | `test_settings_change_is_validated_and_audited` |
| Logs don't leak secrets | `test_audit_log_never_contains_secrets` |
| Last admin protection | `test_user_management_prevents_removing_last_admin` |
| Agent flow building, direction, failed handshakes, bounded queue | `agent/tests/test_agent.py` |

## Manual / system checks (record results in the report)

- [ ] Dashboard on laptop and phone width (sidebar collapses under 768 px).
- [ ] Stop the agent → device turns *Stale* (60 s) then *Not reporting* (5 min); banner shown.
- [ ] Stop the backend while dashboard open → header shows *Reconnecting — polling every 30s*; restart → resync.
- [ ] Revoke device while agent runs → agent exits with "credential rejected".
- [ ] Pause collection from Live monitoring → agent reports "paused from dashboard".
- [ ] Load test: `replay_flows.py --scenario flood --loop 1` for 5 min; record accepted events/s and API latency.
- [ ] Database restart: stop backend, restart, verify history intact.
- [ ] Export CSV as analyst and admin; confirm row counts match the filtered table.

## ML checks

`ml/src/train.py` uses fixed seeds, fits preprocessing inside each pipeline on the training split only,
selects on validation, evaluates once on the held-out test split, reports per-class metrics,
confusion matrix, binary FPR/detection rate, PR-AUC and latency, and compares against a
logistic-regression baseline. Review `ml/reports/<version>.json` for false-positive examples by class.
