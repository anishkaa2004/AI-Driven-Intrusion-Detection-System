from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import client_ip, get_current_user, require_writer
from app.core.timeutil import to_naive_utc
from app.db.session import get_db
from app.models import Alert, AuditLog, IncidentNote, NetworkEvent, User
from app.schemas import AlertDetail, AlertOut, AlertUpdate, AuditOut, EventOut, NoteCreate, NoteOut, Page
from app.services import alert_service, audit
from app.services.devices import can_access_device, visible_device_ids
from app.websocket.manager import manager

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertFilters:
    def __init__(
        self,
        status: str | None = Query(None, description="Comma-separated statuses"),
        severity: str | None = Query(None, description="Comma-separated severities"),
        category: str | None = Query(None),
        source: str | None = Query(None, description="rule, ml, anomaly, combined"),
        device_id: int | None = Query(None),
        start: datetime | None = Query(None),
        end: datetime | None = Query(None),
        include_demo: bool = Query(True),
    ):
        self.kw = dict(status=status, severity=severity, category=category, source=source,
                       device_id=device_id, start=to_naive_utc(start) if start else None,
                       end=to_naive_utc(end) if end else None, include_demo=include_demo)


def _get_alert(db: Session, user: User, alert_id: int) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None or not can_access_device(user, alert.device):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    return alert


@router.get("", response_model=Page[AlertOut])
def list_alerts(filters: AlertFilters = Depends(), page: int = Query(1, ge=1),
                page_size: int = Query(25, ge=1, le=100),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    base = alert_service.apply_filters(select(Alert), device_ids=visible_device_ids(db, user), **filters.kw)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.options(selectinload(Alert.device))
        .order_by(Alert.last_seen_at.desc(), Alert.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page[AlertOut](items=[alert_service.to_out(a) for a in rows], total=total,
                          page=page, page_size=page_size)


@router.get("/categories", response_model=list[str])
def categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(Alert.category).where(
        Alert.device_id.in_(visible_device_ids(db, user))).distinct().order_by(Alert.category)))


@router.get("/{alert_id}", response_model=AlertDetail)
def get_alert(alert_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    alert = _get_alert(db, user, alert_id)
    notes = db.scalars(select(IncidentNote).options(selectinload(IncidentNote.author))
                       .where(IncidentNote.alert_id == alert.id).order_by(IncidentNote.created_at)).all()
    trail = db.scalars(select(AuditLog).options(selectinload(AuditLog.actor)).where(
        AuditLog.target_type == "alert", AuditLog.target_id == str(alert.id))
        .order_by(AuditLog.created_at)).all()

    ev = alert.evidence_json or {}
    ids = ev.get("sample_event_ids") or []
    stmt = select(NetworkEvent).where(NetworkEvent.device_id == alert.device_id)
    margin = timedelta(seconds=5)
    window = (NetworkEvent.event_time >= alert.first_seen_at - margin) & (
        NetworkEvent.event_time <= alert.last_seen_at + margin)
    subject = ev.get("source_ip")
    if subject:
        window = window & or_(NetworkEvent.src_ip == subject, NetworkEvent.dst_ip == subject)
    related = db.scalars(stmt.where(or_(NetworkEvent.id.in_(ids), window))
                         .order_by(NetworkEvent.event_time.desc()).limit(25)).all()

    base = alert_service.to_out(alert).model_dump()
    return AlertDetail(
        **base,
        evidence_json=ev,
        recommendation=alert.recommendation,
        notes=[NoteOut.model_validate(n).model_copy(update={"author_email": n.author.email}) for n in notes],
        audit_trail=[AuditOut.model_validate(a).model_copy(
            update={"actor_email": a.actor.email if a.actor else None}) for a in trail],
        related_events=[EventOut.model_validate(e) for e in related],
    )


@router.patch("/{alert_id}", response_model=AlertOut)
async def update_alert(alert_id: int, body: AlertUpdate, request: Request,
                       user: User = Depends(require_writer), db: Session = Depends(get_db)):
    alert = _get_alert(db, user, alert_id)
    previous = alert.status
    if previous != body.status:
        alert.status = body.status
        audit.record(db, "alert.status_changed", actor_user_id=user.id, target_type="alert",
                     target_id=alert.id, ip=client_ip(request),
                     metadata={"from": previous, "to": body.status})
        db.commit()
    out = alert_service.to_out(alert)
    await manager.publish({"type": "alert", "action": "updated", "alert": out.model_dump(mode="json")},
                          alert.device.owner_user_id)
    return out


@router.post("/{alert_id}/notes", response_model=NoteOut, status_code=201)
def add_note(alert_id: int, body: NoteCreate, request: Request,
             user: User = Depends(require_writer), db: Session = Depends(get_db)):
    alert = _get_alert(db, user, alert_id)
    note = IncidentNote(alert_id=alert.id, author_user_id=user.id, note=body.note.strip())
    db.add(note)
    db.flush()
    audit.record(db, "alert.note_added", actor_user_id=user.id, target_type="alert",
                 target_id=alert.id, ip=client_ip(request), metadata={"note_id": note.id})
    db.commit()
    return NoteOut.model_validate(note).model_copy(update={"author_email": user.email})

