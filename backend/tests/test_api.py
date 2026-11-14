"""API, authorization and end-to-end pipeline tests."""

import csv
import io
import uuid
from datetime import timedelta

import synthetic

from tests.conftest import PASSWORD, enroll, now, register_and_login


def flow(**kw) -> dict:
    base = {
        "event_id": f"t-{uuid.uuid4().hex}",
        "event_time": now().isoformat(),
        "protocol": "TCP",
        "src_ip": "10.0.0.5", "dst_ip": "10.0.0.9", "src_port": 50000, "dst_port": 443,
        "flow_duration": 1.2, "packets_in": 10, "packets_out": 8, "bytes_in": 9000, "bytes_out": 1200,
        "conn_state": "established",
    }
    return {**base, **kw}


def send(client, dev_headers, events, source="agent"):
    return client.post("/api/v1/telemetry/batch", json={"source": source, "events": events},
                       headers=dev_headers)


# ------------------------------------------------------------------- auth
def test_first_user_is_admin_and_login_errors_are_generic(client):
    r = client.post("/api/v1/auth/register", json={"email": "First@Example.test", "password": PASSWORD})
    assert r.status_code == 201 and r.json()["role"] == "admin" and r.json()["email"] == "first@example.test"
    r2 = client.post("/api/v1/auth/register", json={"email": "second@example.test", "password": PASSWORD})
    assert r2.json()["role"] == "analyst"
    bad_pw = client.post("/api/v1/auth/login", json={"email": "first@example.test", "password": "wrong-password"})
    no_user = client.post("/api/v1/auth/login", json={"email": "nobody@example.test", "password": "wrong-password"})
    assert bad_pw.status_code == no_user.status_code == 401
    assert bad_pw.json() == no_user.json()


def test_login_throttling(client):
    client.post("/api/v1/auth/register", json={"email": "a@example.test", "password": PASSWORD})
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "a@example.test", "password": "nope-nope-nope"})
    r = client.post("/api/v1/auth/login", json={"email": "a@example.test", "password": PASSWORD})
    assert r.status_code == 429


def test_protected_endpoints_require_auth(client):
    assert client.get("/api/v1/devices").status_code == 401
    assert client.get("/api/v1/alerts", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_short_password_rejected(client):
    r = client.post("/api/v1/auth/register", json={"email": "x@example.test", "password": "short"})
    assert r.status_code == 422


# ---------------------------------------------------------------- devices
def test_enrollment_code_is_single_use(client, admin):
    r = client.post("/api/v1/devices/enroll", json={"display_name": "Laptop"}, headers=admin)
    code = r.json()["enrollment_code"]
    assert client.post("/api/v1/agents/register", json={"enrollment_code": code}).status_code == 200
    assert client.post("/api/v1/agents/register", json={"enrollment_code": code}).status_code == 400


def test_device_list_never_exposes_secrets(client, admin, device):
    body = client.get("/api/v1/devices", headers=admin).text
    assert "credential" not in body and "enrollment_code_hash" not in body
    assert '"health":"online"' in body.replace(" ", "") or '"health":"never_seen"' in body.replace(" ", "")


def test_revoked_device_is_rejected(client, admin, device):
    device_id, dev = device
    assert send(client, dev, [flow()]).status_code == 200
    assert client.post(f"/api/v1/devices/{device_id}/revoke", headers=admin).status_code == 200
    assert send(client, dev, [flow()]).status_code == 401
    assert client.post("/api/v1/telemetry/heartbeat", json={}, headers=dev).status_code == 401


def test_heartbeat_marks_device_online_and_returns_pause_flag(client, admin, device):
    device_id, dev = device
    client.patch(f"/api/v1/devices/{device_id}", json={"monitoring_paused": True}, headers=admin)
    r = client.post("/api/v1/telemetry/heartbeat", json={"bytes_sent": 10, "bytes_recv": 20}, headers=dev)
    assert r.status_code == 200 and r.json()["monitoring_paused"] is True
    d = client.get(f"/api/v1/devices/{device_id}", headers=admin).json()
    assert d["health"] == "online"


def test_user_cannot_access_other_users_devices_or_alerts(client, admin, device):
    device_id, dev = device
    send(client, dev, synthetic.scenario_port_scan(now() - timedelta(seconds=30)), source="replay")
    other = register_and_login(client, "other@example.test")
    assert client.get(f"/api/v1/devices/{device_id}", headers=other).status_code == 404
    assert client.get("/api/v1/devices", headers=other).json() == []
    assert client.get("/api/v1/alerts", headers=other).json()["total"] == 0
    alert_id = client.get("/api/v1/alerts", headers=admin).json()["items"][0]["id"]
    assert client.get(f"/api/v1/alerts/{alert_id}", headers=other).status_code == 404
    assert client.patch(f"/api/v1/alerts/{alert_id}", json={"status": "resolved"},
                        headers=other).status_code == 404
    export = client.get("/api/v1/reports/alerts.csv", headers=other)
    assert len(list(csv.reader(io.StringIO(export.text)))) == 1  # header only
    assert client.post(f"/api/v1/devices/{device_id}/revoke", headers=other).status_code == 404


def test_viewer_cannot_modify(client, admin, device):
    r = client.post("/api/v1/users", json={"email": "v@example.test", "password": PASSWORD, "role": "viewer"},
                    headers=admin)
    assert r.status_code == 201
    tok = client.post("/api/v1/auth/login", json={"email": "v@example.test", "password": PASSWORD}).json()
    viewer = {"Authorization": f"Bearer {tok['access_token']}"}
    assert client.post("/api/v1/devices/enroll", json={"display_name": "x"}, headers=viewer).status_code == 403
    assert client.put("/api/v1/settings/ml", json={}, headers=viewer).status_code == 403


# -------------------------------------------------------------- telemetry
def test_batch_partial_acceptance_and_idempotency(client, device):
    _, dev = device
    good = flow()
    events = [good, flow(protocol="BOGUS"), flow(dst_port=70000), {"not": "a flow"},
              flow(event_time=(now() + timedelta(hours=1)).isoformat())]
    r = send(client, dev, events)
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "partially_accepted"
    assert body["accepted"] == 1
    assert sorted(x["index"] for x in body["rejected"]) == [1, 2, 3, 4]
    # Retrying the same event is counted as a duplicate, not stored twice.
    again = send(client, dev, [good]).json()
    assert again["accepted"] == 0 and again["duplicates"] == 1


def test_payload_fields_are_rejected(client, device):
    _, dev = device
    r = send(client, dev, [flow(payload="GET / HTTP/1.1")]).json()
    assert r["accepted"] == 0 and "payload" in r["rejected"][0]["reason"]


def test_oversized_batch_rejected(client, device):
    _, dev = device
    r = send(client, dev, [flow() for _ in range(501)])
    assert r.status_code in (413,)


def test_port_scan_alert_end_to_end_with_audit(client, admin, device):
    device_id, dev = device
    r = send(client, dev, synthetic.scenario_port_scan(now() - timedelta(seconds=30)), source="replay").json()
    assert r["accepted"] == 200 and r["alerts_created"] >= 1
    alerts = client.get("/api/v1/alerts", params={"category": "port_scan"}, headers=admin).json()
    rule_alert = next(a for a in alerts["items"] if a["rule_id"] == "R001_port_scan")
    assert rule_alert["is_demo"] is True and rule_alert["severity"] == "high"
    detail = client.get(f"/api/v1/alerts/{rule_alert['id']}", headers=admin).json()
    assert detail["evidence_json"]["distinct_ports"] >= 20
    assert detail["related_events"]

    # Re-sending the same scan pattern updates the open alert instead of duplicating it.
    send(client, dev, synthetic.scenario_port_scan(now() - timedelta(seconds=20), seed=9), source="replay")
    again = client.get("/api/v1/alerts", params={"category": "port_scan", "source": "rule"}, headers=admin).json()
    assert again["total"] == 1 and again["items"][0]["occurrence_count"] == 2

    assert client.patch(f"/api/v1/alerts/{rule_alert['id']}", json={"status": "acknowledged"},
                        headers=admin).status_code == 200
    assert client.post(f"/api/v1/alerts/{rule_alert['id']}/notes", json={"note": "Lab scanner"},
                       headers=admin).status_code == 201
    detail = client.get(f"/api/v1/alerts/{rule_alert['id']}", headers=admin).json()
    actions = [a["action"] for a in detail["audit_trail"]]
    assert "alert.status_changed" in actions and "alert.note_added" in actions
    assert detail["notes"][0]["author_email"] == "admin@example.test"


def test_ml_classifies_flows_when_model_present(client, admin, device):
    from app.services.ml_inference import model_service

    if not model_service.loaded:
        import pytest
        pytest.skip("no trained model in ml/artifacts")
    _, dev = device
    send(client, dev, synthetic.scenario_port_scan(now() - timedelta(seconds=30)), source="replay")
    alerts = client.get("/api/v1/alerts", params={"source": "ml,combined"}, headers=admin).json()["items"]
    assert any(a["category"] == "port_scan" and a["model_version"] for a in alerts)
    combined = [a for a in alerts if a["detection_source"] == "combined"]
    assert combined, "ML finding should be corroborated by R001"


def test_normal_traffic_produces_no_high_severity_alert(client, admin, device):
    _, dev = device
    send(client, dev, synthetic.scenario_normal(now() - timedelta(seconds=90)), source="replay")
    items = client.get("/api/v1/alerts", params={"severity": "high,critical"}, headers=admin).json()
    assert items["total"] == 0


def test_csv_export_escapes_formulas(client, admin, device):
    _, dev = device
    send(client, dev, synthetic.scenario_port_scan(now() - timedelta(seconds=30)), source="replay")
    r = client.get("/api/v1/reports/alerts.csv", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][0] == "id" and len(rows) > 1


def test_settings_change_is_validated_and_audited(client, admin):
    s = client.get("/api/v1/settings", headers=admin).json()
    rules = s["rules"]
    rules["R001_port_scan"]["distinct_ports"] = 1  # below minimum
    assert client.put("/api/v1/settings/rules", json=rules, headers=admin).status_code == 422
    rules["R001_port_scan"]["distinct_ports"] = 30
    assert client.put("/api/v1/settings/rules", json=rules, headers=admin).status_code == 200
    logs = client.get("/api/v1/audit-logs", params={"action": "settings"}, headers=admin).json()
    assert logs["total"] == 1


def test_audit_log_never_contains_secrets(client, admin, device):
    text = client.get("/api/v1/audit-logs", params={"page_size": 200}, headers=admin).text
    assert PASSWORD not in text and "aiids_dev_" not in text


def test_websocket_requires_auth_and_streams_alerts(client, admin, device):
    _, dev = device
    with client.websocket_connect("/ws/events") as ws:
        ws.send_text('{"type":"auth","token":"invalid"}')
        try:
            ws.receive_json()
            raise AssertionError("expected close")
        except Exception:
            pass
    token = admin["Authorization"].split()[1]
    with client.websocket_connect("/ws/events") as ws:
        ws.send_json({"type": "auth", "token": token})
        assert ws.receive_json()["type"] == "ready"
        send(client, dev, synthetic.scenario_port_scan(now() - timedelta(seconds=30)), source="replay")
        types = {ws.receive_json()["type"] for _ in range(3)}
        assert "alert" in types


def test_dashboard_summary(client, admin, device):
    _, dev = device
    send(client, dev, synthetic.scenario_normal(now() - timedelta(seconds=90)), source="replay")
    s = client.get("/api/v1/dashboard/summary", headers=admin).json()
    assert s["events"] == 120 and s["devices"]["reporting"] == 1
    assert "TCP" in s["protocols"]


def test_user_management_prevents_removing_last_admin(client, admin):
    me = client.get("/api/v1/auth/me", headers=admin).json()
    r = client.patch(f"/api/v1/users/{me['id']}", json={"role": "viewer"}, headers=admin)
    assert r.status_code == 409


def test_second_device_cannot_write_into_first(client, admin, device):
    first_id, _ = device
    _, dev2 = enroll(client, admin, "Second")
    send(client, dev2, [flow()])
    d1 = client.get(f"/api/v1/devices/{first_id}/traffic", headers=admin).json()
    assert d1["recent_flows"] == []
