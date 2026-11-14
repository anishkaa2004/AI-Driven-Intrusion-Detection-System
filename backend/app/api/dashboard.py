from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user
from app.core.timeutil import iso_z, utcnow
from app.db.session import get_db
from app.models import OPEN_STATUSES, SEVERITIES, Alert, Device, NetworkEvent, User
from app.services import alert_service
from app.services import devices as device_svc
from app.services.ml_inference import model_service
from app.websocket.manager import manager

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary")
def summary(hours: int = Query(24, ge=1, le=24 * 30),
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = utcnow()
    start = now - timedelta(hours=hours)
    devices = db.scalars(device_svc.scope_devices(select(Device), user)).all()
    ids = [d.id for d in devices]
    health = Counter(device_svc.device_health(d, now) for d in devices)

    # Traffic series: 48 buckets across the window.
    bucket_s = max(60, hours * 3600 // 48)
    n = hours * 3600 // bucket_s + 1
    series = [{"t": iso_z(start + timedelta(seconds=i * bucket_s)), "flows": 0, "bytes": 0, "alerts": 0}
              for i in range(n)]
    c = NetworkEvent
    protocols: Counter = Counter()
    events = 0
    for r in db.execute(select(c.event_time, c.protocol, c.bytes_in, c.bytes_out)
                        .where(c.device_id.in_(ids), c.event_time >= start)):
        i = min(int((r.event_time - start).total_seconds() // bucket_s), n - 1)
        series[i]["flows"] += 1
        series[i]["bytes"] += (r.bytes_in or 0) + (r.bytes_out or 0)
        protocols[r.protocol] += 1
        events += 1

    window_alerts = db.scalars(select(Alert).where(Alert.device_id.in_(ids), Alert.last_seen_at >= start)).all()
    for a in window_alerts:
        i = min(max(int((a.first_seen_at - start).total_seconds() // bucket_s), 0), n - 1)
        series[i]["alerts"] += 1
    by_sev = Counter(a.severity for a in window_alerts)
    open_alerts = db.scalar(select(func.count(Alert.id)).where(
        Alert.device_id.in_(ids), Alert.status.in_(OPEN_STATUSES))) or 0
    recent = db.scalars(select(Alert).options(selectinload(Alert.device))
                        .where(Alert.device_id.in_(ids))
                        .order_by(Alert.last_seen_at.desc(), Alert.id.desc()).limit(8)).all()
    return {
        "window_hours": hours,
        "generated_at": iso_z(now),
        "devices": {
            "total": len([d for d in devices if d.status != "revoked"]),
            "reporting": health.get("online", 0),
            "stale": health.get("stale", 0),
            "offline": health.get("offline", 0) + health.get("never_seen", 0),
            "pending": health.get("pending", 0),
            "revoked": health.get("revoked", 0),
        },
        "events": events,
        "open_alerts": open_alerts,
        "alerts_by_severity": {s: by_sev.get(s, 0) for s in SEVERITIES},
        "alerts_by_category": dict(Counter(a.category for a in window_alerts).most_common()),
        "alerts_by_source": dict(Counter(a.detection_source for a in window_alerts)),
        "protocols": dict(protocols.most_common()),
        "series": series,
        "bucket_s": bucket_s,
        "recent_alerts": [alert_service.to_out(a).model_dump(mode="json") for a in recent],
        "health": {
            "backend": "ok",
            "model_loaded": model_service.loaded,
            "model_version": model_service.version,
            "model_error": model_service.load_error,
            "dashboard_clients": manager.count,
        },
    }


@router.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)):
    db_ok = True
    try:
        db.execute(select(1))
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": "ok" if db_ok else "error",
            "model_loaded": model_service.loaded, "model_version": model_service.version}
