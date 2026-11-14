"""CSV export of alerts. Values that spreadsheets would treat as formulas are escaped."""

import csv
import io
import json
from collections.abc import Iterable

from app.core.timeutil import iso_z
from app.models import Alert

COLUMNS = [
    "id", "device_id", "device_name", "title", "category", "severity", "status",
    "detection_source", "rule_id", "model_version", "score", "score_meaning",
    "occurrence_count", "is_demo", "first_seen_at", "last_seen_at", "created_at", "evidence",
]


def _safe(value) -> str:
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def alerts_csv(alerts: Iterable[Alert]) -> Iterable[str]:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(COLUMNS)
    yield buf.getvalue()
    for a in alerts:
        buf.seek(0)
        buf.truncate()
        writer.writerow([_safe(v) for v in (
            a.id, a.device_id, a.device.display_name if a.device else "", a.title, a.category,
            a.severity, a.status, a.detection_source, a.rule_id, a.model_version, a.score,
            a.score_meaning, a.occurrence_count, a.is_demo, iso_z(a.first_seen_at),
            iso_z(a.last_seen_at), iso_z(a.created_at),
            json.dumps(a.evidence_json, separators=(",", ":"), default=str),
        )])
        yield buf.getvalue()
