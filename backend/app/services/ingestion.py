"""Telemetry ingestion: validate -> deduplicate -> store -> detect -> alert.

Runs synchronously inside one database transaction. Publishing to dashboards
happens only after the transaction commits (see api/telemetry.py).
"""

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutil import iso_z, utcnow
from app.models import Alert, Device, NetworkEvent
from app.schemas import BatchResult, FlowEvent, RejectedEvent, TelemetryBatch
from app.services import alert_service, rule_engine, settings_service
from app.services.ml_inference import model_service


@dataclass
class IngestOutcome:
    result: BatchResult
    alerts: list[Alert] = field(default_factory=list)
    created_ids: set[int] = field(default_factory=set)
    summary: dict | None = None


def _reason(exc: ValidationError) -> str:
    err = exc.errors()[0]
    loc = ".".join(str(p) for p in err.get("loc", ()))
    return f"{loc}: {err.get('msg', 'invalid')}"[:200]


def validate_events(raw_events: list, now) -> tuple[list[FlowEvent], list[RejectedEvent], int]:
    s = get_settings()
    future_limit = now + timedelta(minutes=5)
    past_limit = now - timedelta(days=s.max_event_age_days)
    valid: list[FlowEvent] = []
    rejected: list[RejectedEvent] = []
    seen: set[str] = set()
    in_batch_dupes = 0
    for i, raw in enumerate(raw_events):
        eid = raw.get("event_id") if isinstance(raw, dict) else None
        eid = eid if isinstance(eid, str) else None
        try:
            ev = FlowEvent.model_validate(raw)
        except ValidationError as exc:
            rejected.append(RejectedEvent(index=i, event_id=eid, reason=_reason(exc)))
            continue
        if ev.event_time > future_limit:
            rejected.append(RejectedEvent(index=i, event_id=eid, reason="event_time is in the future"))
            continue
        if ev.event_time < past_limit:
            rejected.append(RejectedEvent(index=i, event_id=eid, reason="event_time is older than allowed"))
            continue
        if ev.event_id in seen:
            in_batch_dupes += 1
            continue
        seen.add(ev.event_id)
        valid.append(ev)
    return valid, rejected, in_batch_dupes


def process_batch(db: Session, device: Device, batch: TelemetryBatch) -> IngestOutcome:
    now = utcnow()
    ingestion_id = str(uuid.uuid4())
    valid, rejected, dupes = validate_events(batch.events, now)

    existing: set[str] = set()
    uids = [e.event_id for e in valid]
    for i in range(0, len(uids), 500):
        existing |= set(db.scalars(select(NetworkEvent.event_uid).where(
            NetworkEvent.device_id == device.id, NetworkEvent.event_uid.in_(uids[i:i + 500]))))
    new = [e for e in valid if e.event_id not in existing]
    dupes += len(valid) - len(new)

    ml_cfg = settings_service.ml(db)
    records = [e.model_dump() for e in new]
    preds = model_service.predict(records) if ml_cfg.enabled else [None] * len(records)

    rows = []
    for ev, rec, pred in zip(new, records, preds):
        rows.append(NetworkEvent(
            event_uid=ev.event_id, device_id=device.id, ingestion_id=ingestion_id,
            source=batch.source, event_time=ev.event_time, received_at=now,
            protocol=ev.protocol, src_ip=ev.src_ip, dst_ip=ev.dst_ip,
            src_port=ev.src_port, dst_port=ev.dst_port, flow_duration=ev.flow_duration,
            packets_in=ev.packets_in, packets_out=ev.packets_out,
            bytes_in=ev.bytes_in, bytes_out=ev.bytes_out,
            conn_state=ev.conn_state, dns_rcode=ev.dns_rcode,
            feature_schema_version=ev.feature_schema_version,
            ml_label=pred.label if pred else None,
            ml_score=round(pred.score, 4) if pred else None,
            model_version=model_service.version if pred else None,
        ))
    db.add_all(rows)

    device.last_seen_at = now
    if batch.agent_version:
        device.agent_version = batch.agent_version
    if batch.collector:
        device.last_collector = batch.collector
    db.flush()

    outcome = IngestOutcome(result=None)  # type: ignore[arg-type]
    created = updated = 0
    if rows:
        start = min(r.event_time for r in rows)
        end = max(r.event_time for r in rows)
        rule_findings = rule_engine.evaluate(db, device.id, start, end, settings_service.rules(db),
                                              new_ids={r.id for r in rows})
        ml_findings = []
        if ml_cfg.enabled and model_service.loaded:
            ml_findings = alert_service.build_ml_findings(
                device.id, rows, benign_label=model_service.benign_label,
                min_score=ml_cfg.min_score, min_events=ml_cfg.min_events, severity=ml_cfg.severity,
            )
        new_alerts = []
        for f in alert_service.fuse(rule_findings, ml_findings):
            alert, is_new = alert_service.upsert_finding(db, device, f, is_demo=batch.source == "replay")
            outcome.alerts.append(alert)
            if is_new:
                new_alerts.append(alert)
        created, updated = len(new_alerts), len(outcome.alerts) - len(new_alerts)
        db.flush()
        outcome.created_ids = {a.id for a in new_alerts}
        outcome.summary = {
            "device_id": device.id,
            "events": len(rows),
            "bytes": sum((r.bytes_in or 0) + (r.bytes_out or 0) for r in rows),
            "protocols": dict(Counter(r.protocol for r in rows)),
            "source": batch.source,
            "received_at": iso_z(now),
        }
    db.commit()

    if not batch.events:
        status = "empty"
    elif not rejected:
        status = "accepted"
    elif rows or dupes:
        status = "partially_accepted"
    else:
        status = "rejected"
    outcome.result = BatchResult(
        ingestion_id=ingestion_id, status=status, accepted=len(rows), duplicates=dupes,
        rejected=rejected, alerts_created=created, alerts_updated=updated,
        monitoring_paused=device.monitoring_paused,
    )
    return outcome
