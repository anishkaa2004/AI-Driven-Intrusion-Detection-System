"""Audit logging. Secrets are stripped from metadata before storage."""

from sqlalchemy.orm import Session

from app.models import AuditLog

_SENSITIVE = ("password", "token", "credential", "secret", "code", "authorization")


def _scrub(value):
    if isinstance(value, dict):
        return {
            k: ("[redacted]" if any(s in k.lower() for s in _SENSITIVE) else _scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def record(
    db: Session,
    action: str,
    *,
    actor_user_id: int | None = None,
    target_type: str | None = None,
    target_id: object | None = None,
    ip: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=None if target_id is None else str(target_id),
        ip_address=ip,
        metadata_json=_scrub(metadata or {}),
    )
    db.add(entry)
    return entry
