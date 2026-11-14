"""Unit tests: rules, features, security helpers, fusion and CSV escaping."""

from datetime import datetime, timedelta

import pandas as pd

from app.core.security import hash_password, parse_device_id, verify_password
from app.services import alert_service, reporting
from app.services.audit import _scrub
from app.services.features import FEATURE_COLUMNS, compute_features, has_required_counters
from app.services.rule_engine import Ev, Finding, rule_conn_failures, rule_port_scan, rule_volume, sliding_max
from app.services.settings_service import ConnFailureRule, PortScanRule, VolumeRule

T0 = datetime(2026, 1, 1, 12, 0, 0)


def ev(i, t, src="10.0.0.1", dst="10.0.0.2", dport=80, state="established", nbytes=100):
    return Ev(i, t, "TCP", src, dst, 40000, dport, 2, nbytes, state, None)


def test_password_hash_roundtrip():
    h = hash_password("a-long-password")
    assert h.startswith("scrypt$") and verify_password("a-long-password", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", "garbage")


def test_parse_device_id():
    assert parse_device_id("aiids_dev_12_abc_def") == 12
    assert parse_device_id("aiids_dev_x_abc") is None
    assert parse_device_id("bearer") is None


def test_sliding_max_respects_window():
    events = [ev(i, T0 + timedelta(seconds=i * 10)) for i in range(10)]
    assert sliding_max(events, 25).value == 3  # 0,10,20s
    assert sliding_max(events, 1000).value == 10


def test_port_scan_threshold_and_window():
    cfg = PortScanRule(distinct_ports=20, window_s=60)
    fast = [ev(i, T0 + timedelta(seconds=i), dport=1000 + i) for i in range(25)]
    assert len(rule_port_scan(1, fast, cfg)) == 1
    slow = [ev(i, T0 + timedelta(seconds=i * 10), dport=1000 + i) for i in range(25)]
    assert rule_port_scan(1, slow, cfg) == []  # never 20 ports in 60 s
    same_port = [ev(i, T0 + timedelta(seconds=i), dst=f"10.0.1.{i}", dport=443) for i in range(50)]
    assert rule_port_scan(1, same_port, cfg) == []  # browsing many hosts on 443 is not a port scan


def test_already_evaluated_events_do_not_refire():
    cfg = PortScanRule(distinct_ports=20, window_s=60)
    old = [Ev(i, T0 + timedelta(seconds=i), "TCP", "10.0.0.1", "10.0.0.2", 1, 1000 + i, 2, 100, None, None,
              is_new=False) for i in range(25)]
    new = [ev(100, T0 + timedelta(seconds=30), dport=443)]
    # The window ending at the new event still contains 21 distinct ports -> fires.
    assert len(rule_port_scan(1, old + new, cfg)) == 1
    later = [ev(101, T0 + timedelta(seconds=200), dport=443)]
    assert rule_port_scan(1, old + later, cfg) == []


def test_conn_failures_only_count_failed_states():
    cfg = ConnFailureRule(failures=5, window_s=60)
    ok = [ev(i, T0 + timedelta(seconds=i), dport=22) for i in range(10)]
    assert rule_conn_failures(1, ok, cfg) == []
    failed = [ev(i, T0 + timedelta(seconds=i), dport=22, state="failed") for i in range(6)]
    [f] = rule_conn_failures(1, failed, cfg)
    assert f.evidence["failures"] == 6 and f.evidence["destination_port"] == 22


def test_volume_deviation_needs_baseline():
    cfg = VolumeRule(bucket_s=60, history_buckets=6, min_history=4, sigma=3, min_bytes=1000)
    end = T0 + timedelta(minutes=10)
    history = [ev(i, end - timedelta(seconds=60 * k + 30), nbytes=500) for i, k in enumerate(range(1, 7))]
    spike = [ev(100, end - timedelta(seconds=5), nbytes=50_000)]
    assert len(rule_volume(1, history + spike, cfg, end)) == 1
    assert rule_volume(1, spike, cfg, end) == []  # no baseline -> no alert


def test_features_schema_and_missing_counters():
    df = pd.DataFrame([{"flow_duration": 0.0, "packets_in": 0, "packets_out": 1,
                        "bytes_in": 0, "bytes_out": 60, "dst_port": 22}])
    X = compute_features(df)
    assert list(X.columns) == FEATURE_COLUMNS and X.notna().all().all()
    assert not has_required_counters({"flow_duration": 1, "packets_in": None, "packets_out": 1,
                                      "bytes_in": 1, "bytes_out": 1, "dst_port": 1})


def _finding(src, source="rule", sev="medium", rule="R001_port_scan"):
    return Finding(rule_id=rule if source == "rule" else None, category="port_scan", severity=sev,
                   title="t", dedup_key=f"k:{source}:{src}", evidence={"predicted_label": "PortScan",
                                                                        "matched_events": 3},
                   first_seen=T0, last_seen=T0, subject_ip=src, detection_source=source,
                   related_ips={src} if source == "ml" else set())


def test_fusion_marks_corroborated_ml_findings():
    rule = _finding("1.1.1.1", sev="high")
    ml_match = _finding("1.1.1.1", source="ml")
    ml_alone = _finding("2.2.2.2", source="ml")
    out = alert_service.fuse([rule], [ml_match, ml_alone])
    assert len(out) == 3  # originals are kept
    assert ml_match.detection_source == "combined" and ml_match.corroborating == ["R001_port_scan"]
    assert ml_match.severity == "high"  # capped at high
    assert ml_alone.detection_source == "ml" and ml_alone.severity == "medium"
    assert rule.evidence["ml_corroboration"]


def test_csv_formula_escaping():
    assert reporting._safe("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert reporting._safe("normal") == "normal"


def test_audit_scrub():
    assert _scrub({"password": "x", "nested": {"api_token": "y", "ok": 1}}) == {
        "password": "[redacted]", "nested": {"api_token": "[redacted]", "ok": 1}}
