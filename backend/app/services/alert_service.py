"""Alert creation, deduplication, detection fusion and filtering."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import OPEN_STATUSES, SEVERITIES, Alert, Device, NetworkEvent
from app.schemas import AlertOut
from app.services.features import compute_features
from app.services.ml_inference import SCORE_MEANING
from app.services.rule_engine import Finding

SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}

# Maps model labels to the same categories used by rules, so dashboards group
# them together. Unknown labels keep their own category.
LABEL_CATEGORY = {
    "PortScan": "port_scan",
    "DoS": "dos",
    "DDoS": "dos",
    "BruteForce": "brute_force",
    "WebAttack": "web_attack",
    "Bot": "botnet",
}


def bump(severity: str) -> str:
    return SEVERITIES[min(SEV_RANK[severity] + 1, SEV_RANK["high"])] if SEV_RANK[severity] < SEV_RANK["high"] else severity


def build_ml_findings(
    device_id: int,
    events: list[NetworkEvent],
    *,
    benign_label: str,
    min_score: float,
    min_events: int,
    severity: str,
) -> list[Finding]:
    """Group confident non-benign predictions by label (one finding per label per batch).

    Grouping by label rather than by source keeps a distributed pattern (e.g.
    a flood from many sources) as one alert; the sources are listed in the
    evidence instead.
    """
    groups: dict[str, list[NetworkEvent]] = defaultdict(list)
    for e in events:
        if e.ml_label and e.ml_label != benign_label and (e.ml_score or 0) >= min_score:
            groups[e.ml_label].append(e)
    findings = []
    for label, evs in groups.items():
        if len(evs) < min_events:
            continue
        top = max(evs, key=lambda e: e.ml_score or 0)
        feats = compute_features(pd.DataFrame([{
            "flow_duration": top.flow_duration, "packets_in": top.packets_in,
            "packets_out": top.packets_out, "bytes_in": top.bytes_in,
            "bytes_out": top.bytes_out, "dst_port": top.dst_port,
        }])).iloc[0].round(3).to_dict()
        scores = [e.ml_score or 0 for e in evs]
        sources = Counter(e.src_ip for e in evs if e.src_ip)
        dests = Counter(e.dst_ip for e in evs if e.dst_ip)
        main_src = sources.most_common(1)[0][0] if sources else None
        who = main_src if len(sources) == 1 else f"{len(sources)} sources"
        findings.append(Finding(
            rule_id=None,
            category=LABEL_CATEGORY.get(label, f"ml_{label.lower()}"),
            severity=severity,
            title=f"Model classified {len(evs)} flows from {who or 'unknown'} as {label}",
            dedup_key=f"{device_id}:ml:{label}",
            subject_ip=main_src,
            related_ips=set(sources) | set(dests),
            first_seen=min(e.event_time for e in evs),
            last_seen=max(e.event_time for e in evs),
            detection_source="ml",
            score=round(sum(scores) / len(scores), 4),
            score_meaning=SCORE_MEANING,
            model_version=top.model_version,
            evidence={
                "predicted_label": label,
                "matched_events": len(evs),
                "mean_score": round(sum(scores) / len(scores), 4),
                "max_score": round(max(scores), 4),
                "score_threshold": min_score,
                "source_ip": main_src if len(sources) == 1 else None,
                "distinct_sources": len(sources),
                "top_sources": sources.most_common(5),
                "top_destinations": dests.most_common(5),
                "destination_ports": sorted({e.dst_port for e in evs if e.dst_port is not None})[:20],
                "top_event_id": top.id,
                "top_event_features": feats,
                "model_version": top.model_version,
                "sample_event_ids": [e.id for e in evs[:10]],
                "caveat": "Model trained on benchmark/synthetic data; performance may not transfer to this network.",
            },
        ))
    return findings


def fuse(rule_findings: list[Finding], ml_findings: list[Finding]) -> list[Finding]:
    """Documented fusion policy (see docs/architecture.md#detection-fusion).

    Rule and ML findings stay separate alerts so the original outputs remain
    auditable. When a rule finding's subject IP (or destination) appears among
    the IPs of an ML finding's flows in the same batch, the ML alert is marked `combined`, lists the
    corroborating rule ids, and its severity is raised one level (max high).
    The rule alert gets a note of the ML corroboration in its evidence.
    """
    for m in ml_findings:
        matches = [r for r in rule_findings
                   if (r.subject_ip and r.subject_ip in m.related_ips)
                   or r.evidence.get("destination_ip") in m.related_ips]
        if not matches:
            continue
        m.detection_source = "combined"
        m.corroborating = sorted({r.rule_id for r in matches if r.rule_id})
        m.evidence["corroborating_rules"] = m.corroborating
        m.severity = bump(max((m.severity, *[r.severity for r in matches]), key=SEV_RANK.get))
        for r in matches:
            r.evidence.setdefault("ml_corroboration", []).append(
                {"label": m.evidence["predicted_label"], "matched_events": m.evidence["matched_events"],
                 "model_version": m.model_version}
            )
    return rule_findings + ml_findings


def upsert_finding(db: Session, device: Device, f: Finding, is_demo: bool) -> tuple[Alert, bool]:
    window = timedelta(minutes=get_settings().dedup_window_minutes)
    existing = db.scalar(
        select(Alert)
        .where(
            Alert.dedup_key == f.dedup_key,
            Alert.status.in_(OPEN_STATUSES),
            Alert.last_seen_at >= f.first_seen - window,
        )
        .order_by(Alert.id.desc())
        .limit(1)
    )
    if existing:
        existing.occurrence_count += 1
        existing.last_seen_at = max(existing.last_seen_at, f.last_seen)
        existing.first_seen_at = min(existing.first_seen_at, f.first_seen)
        if SEV_RANK[f.severity] > SEV_RANK[existing.severity]:
            existing.severity = f.severity
        if f.detection_source == "combined":
            existing.detection_source = "combined"
        existing.title = f.title
        existing.evidence_json = {**f.evidence, "occurrences": existing.occurrence_count}
        if f.score is not None:
            existing.score = f.score
        return existing, False
    alert = Alert(
        device_id=device.id,
        event_id=f.evidence.get("top_event_id") or (f.evidence.get("sample_event_ids") or [None])[0],
        title=f.title,
        category=f.category,
        severity=f.severity,
        status="new",
        detection_source=f.detection_source,
        rule_id=f.rule_id,
        model_version=f.model_version,
        score=f.score,
        score_meaning=f.score_meaning,
        evidence_json=f.evidence,
        recommendation=f.recommendation,
        dedup_key=f.dedup_key,
        is_demo=is_demo,
        first_seen_at=f.first_seen,
        last_seen_at=f.last_seen,
    )
    db.add(alert)
    return alert, True


def to_out(alert: Alert) -> AlertOut:
    out = AlertOut.model_validate(alert)
    out.device_name = alert.device.display_name if alert.device else None
    return out


def _split(v: str | None) -> list[str]:
    return [x for x in (v or "").split(",") if x]


def apply_filters(
    stmt: Select,
    *,
    device_ids: list[int],
    status: str | None = None,
    severity: str | None = None,
    category: str | None = None,
    source: str | None = None,
    device_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    include_demo: bool = True,
) -> Select:
    stmt = stmt.where(Alert.device_id.in_(device_ids))
    if s := _split(status):
        stmt = stmt.where(Alert.status.in_(s))
    if s := _split(severity):
        stmt = stmt.where(Alert.severity.in_(s))
    if s := _split(category):
        stmt = stmt.where(Alert.category.in_(s))
    if s := _split(source):
        stmt = stmt.where(Alert.detection_source.in_(s))
    if device_id is not None:
        stmt = stmt.where(Alert.device_id == device_id)
    if start is not None:
        stmt = stmt.where(Alert.last_seen_at >= start)
    if end is not None:
        stmt = stmt.where(Alert.last_seen_at <= end)
    if not include_demo:
        stmt = stmt.where(Alert.is_demo.is_(False))
    return stmt
