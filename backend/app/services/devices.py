"""Device health and access helpers."""

from datetime import datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutil import utcnow
from app.models import OPEN_STATUSES, Alert, Device, NetworkEvent, User
from app.schemas import DeviceOut


def device_health(device: Device, now: datetime | None = None) -> str:
    """Health is based on authenticated telemetry/heartbeats, never on UI connectivity."""
    if device.status == "revoked":
        return "revoked"
    if device.status == "pending":
        return "pending"
    if device.last_seen_at is None:
        return "never_seen"
    s = get_settings()
    age = ((now or utcnow()) - device.last_seen_at).total_seconds()
    if age <= s.online_threshold_s:
        return "online"
    if age <= s.stale_threshold_s:
        return "stale"
    return "offline"


def scope_devices(stmt: Select, user: User) -> Select:
    """Restrict a query on Device to what `user` may see."""
    if user.role == "admin":
        return stmt
    return stmt.where(Device.owner_user_id == user.id)


def visible_device_ids(db: Session, user: User) -> list[int]:
    return list(db.scalars(scope_devices(select(Device.id), user)))


def can_access_device(user: User, device: Device) -> bool:
    return user.role == "admin" or device.owner_user_id == user.id


def to_out(db: Session, device: Device, with_counts: bool = True) -> DeviceOut:
    now = utcnow()
    events_24h = open_alerts = 0
    if with_counts:
        events_24h = db.scalar(
            select(func.count(NetworkEvent.id)).where(
                NetworkEvent.device_id == device.id,
                NetworkEvent.event_time >= now - timedelta(hours=24),
            )
        ) or 0
        open_alerts = db.scalar(
            select(func.count(Alert.id)).where(
                Alert.device_id == device.id, Alert.status.in_(OPEN_STATUSES)
            )
        ) or 0
    out = DeviceOut.model_validate(
        {
            **{c: getattr(device, c) for c in DeviceOut.model_fields if hasattr(device, c)},
            "health": device_health(device, now),
            "owner_email": device.owner.email if device.owner else None,
            "events_24h": events_24h,
            "open_alerts": open_alerts,
        }
    )
    return out
