"""Reports, model metrics, settings, users and audit logs."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.alerts import AlertFilters
from app.core.deps import client_ip, get_current_user, require_admin
from app.core.security import hash_password
from app.core.timeutil import utcnow
from app.db.session import get_db
from app.models import Alert, AuditLog, ModelRegistry, User
from app.schemas import AuditOut, Page, UserCreate, UserOut, UserUpdate
from app.services import alert_service, audit, reporting, settings_service
from app.services.devices import visible_device_ids
from app.services.ml_inference import model_service
from app.services.rule_engine import RULE_DOCS

router = APIRouter()

MAX_EXPORT_ROWS = 50_000


# --------------------------------------------------------------------- reports
@router.get("/reports/alerts.csv", tags=["reports"])
def export_alerts(request: Request, filters: AlertFilters = Depends(),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Exports apply exactly the same authorization scope as the dashboard."""
    stmt = alert_service.apply_filters(select(Alert), device_ids=visible_device_ids(db, user), **filters.kw)
    alerts = db.scalars(stmt.options(selectinload(Alert.device))
                        .order_by(Alert.last_seen_at.desc()).limit(MAX_EXPORT_ROWS)).all()
    audit.record(db, "report.alerts_exported", actor_user_id=user.id, target_type="report",
                 ip=client_ip(request), metadata={"rows": len(alerts),
                                                  "filters": {k: str(v) for k, v in filters.kw.items() if v is not None}})
    db.commit()
    name = f"aiids-alerts-{utcnow():%Y%m%d-%H%M%S}.csv"
    return StreamingResponse(reporting.alerts_csv(alerts), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------------- models
@router.get("/models/metrics", tags=["models"])
def model_metrics(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ModelRegistry).order_by(ModelRegistry.created_at.desc())).all()
    return {
        "active": {
            "loaded": model_service.loaded,
            "model_version": model_service.version,
            "load_error": model_service.load_error,
            "last_inference_latency_ms": model_service.last_latency_ms,
            "manifest": {k: v for k, v in (model_service.manifest or {}).items() if k != "sha256"},
        },
        "registry": [
            {"id": r.id, "model_name": r.model_name, "model_version": r.model_version,
             "feature_schema_version": r.feature_schema_version,
             "dataset_reference": r.dataset_reference, "is_active": r.is_active,
             "trained_at": r.trained_at.isoformat() + "Z" if r.trained_at else None,
             "metrics": r.metrics_json} for r in rows
        ],
        "rules": RULE_DOCS,
    }


# -------------------------------------------------------------------- settings
@router.get("/settings", tags=["settings"])
def get_settings_view(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "rules": settings_service.rules(db).model_dump(),
        "ml": settings_service.ml(db).model_dump(),
        "retention": settings_service.retention(db).model_dump(),
        "rule_docs": RULE_DOCS,
        "editable": user.role == "admin",
    }


@router.put("/settings/{key}", tags=["settings"])
def update_setting(key: str, body: dict, request: Request,
                   user: User = Depends(require_admin), db: Session = Depends(get_db)):
    model = settings_service.CONFIG_MODELS.get(key)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown setting")
    try:
        value = model.model_validate(body)
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)[:500]) from None
    before = settings_service.get_config(db, key, model).model_dump()
    settings_service.set_config(db, key, value, user.id)
    audit.record(db, "settings.updated", actor_user_id=user.id, target_type="setting", target_id=key,
                 ip=client_ip(request), metadata={"before": before, "after": value.model_dump()})
    db.commit()
    return value.model_dump()


# ----------------------------------------------------------------------- users
@router.get("/users", response_model=list[UserOut], tags=["users"])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("/users", response_model=UserOut, status_code=201, tags=["users"])
def create_user(body: UserCreate, request: Request,
                admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    user = User(email=body.email, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.flush()
    audit.record(db, "user.created", actor_user_id=admin.id, target_type="user", target_id=user.id,
                 ip=client_ip(request), metadata={"role": body.role})
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut, tags=["users"])
def update_user(user_id: int, body: UserUpdate, request: Request,
                admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    changes = body.model_dump(exclude_none=True)
    demoting_self = user.id == admin.id and (changes.get("role", "admin") != "admin"
                                             or changes.get("is_active") is False)
    if demoting_self:
        active_admins = db.scalar(select(func.count(User.id)).where(
            User.role == "admin", User.is_active.is_(True))) or 0
        if active_admins <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Cannot remove the last active administrator")
    for k, v in changes.items():
        setattr(user, k, v)
    audit.record(db, "user.updated", actor_user_id=admin.id, target_type="user", target_id=user.id,
                 ip=client_ip(request), metadata=changes)
    db.commit()
    return user


# ------------------------------------------------------------------ audit logs
@router.get("/audit-logs", response_model=Page[AuditOut], tags=["audit"])
def audit_logs(action: str | None = None, page: int = Query(1, ge=1),
               page_size: int = Query(50, ge=1, le=200),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Admins see all entries; other users see only their own actions."""
    stmt = select(AuditLog)
    if user.role != "admin":
        stmt = stmt.where(AuditLog.actor_user_id == user.id)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.options(selectinload(AuditLog.actor))
                      .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    items = [AuditOut.model_validate(r).model_copy(update={"actor_email": r.actor.email if r.actor else None})
             for r in rows]
    return Page[AuditOut](items=items, total=total, page=page, page_size=page_size)
