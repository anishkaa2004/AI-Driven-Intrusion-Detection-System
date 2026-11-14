"""All timestamps are stored as naive UTC and serialized with a trailing 'Z'."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def iso_z(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=None).isoformat(timespec="milliseconds") + "Z"
