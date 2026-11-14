"""Typed request/response schemas."""

import ipaddress
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
)

from app.core.timeutil import iso_z, to_naive_utc

UTCDateTime = Annotated[datetime, PlainSerializer(iso_z, return_type=str | None)]

Role = Literal["admin", "analyst", "viewer"]
Severity = Literal["info", "low", "medium", "high", "critical"]
AlertStatus = Literal["new", "acknowledged", "investigating", "resolved", "false_positive"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth / users
class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=256)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        local, _, domain = v.partition("@")
        if not local or "." not in domain or " " in v:
            raise ValueError("Enter a valid email address")
        return v


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class UserOut(ORMModel):
    id: int
    email: str
    role: Role
    is_active: bool
    created_at: UTCDateTime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UserCreate(RegisterRequest):
    role: Role = "analyst"


class UserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


# --------------------------------------------------------------------- devices
class EnrollRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    platform: str | None = Field(default=None, max_length=50)
    owner_user_id: int | None = None  # admin only


class EnrollResponse(BaseModel):
    device_id: int
    enrollment_code: str
    expires_at: UTCDateTime
    instructions: str


class AgentRegisterRequest(BaseModel):
    enrollment_code: str = Field(min_length=8, max_length=32)
    hostname: str | None = Field(default=None, max_length=255)
    platform: str | None = Field(default=None, max_length=50)
    agent_version: str | None = Field(default=None, max_length=32)


class AgentRegisterResponse(BaseModel):
    device_id: int
    credential: str
    display_name: str


class DeviceOut(ORMModel):
    id: int
    owner_user_id: int
    owner_email: str | None = None
    display_name: str
    platform: str | None
    hostname: str | None
    agent_version: str | None
    status: str
    health: str  # online | stale | offline | never_seen | pending | revoked
    created_at: UTCDateTime
    enrolled_at: UTCDateTime | None
    last_seen_at: UTCDateTime | None
    revoked_at: UTCDateTime | None
    enrollment_expires_at: UTCDateTime | None
    monitoring_paused: bool
    last_collector: str | None
    last_interface: str | None
    events_24h: int = 0
    open_alerts: int = 0


class DeviceUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    monitoring_paused: bool | None = None


# ------------------------------------------------------------------- telemetry
FEATURE_SCHEMA_VERSION = "flow-v1"


class FlowEvent(BaseModel):
    """One network-flow metadata record. No payload content is accepted."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_\-:.]+$")
    event_time: datetime
    protocol: Literal["TCP", "UDP", "ICMP", "OTHER"]
    src_ip: str | None = None
    dst_ip: str | None = None
    src_port: int | None = Field(default=None, ge=0, le=65535)
    dst_port: int | None = Field(default=None, ge=0, le=65535)
    flow_duration: float | None = Field(default=None, ge=0, le=86_400)
    packets_in: int | None = Field(default=None, ge=0, le=10**9)
    packets_out: int | None = Field(default=None, ge=0, le=10**9)
    bytes_in: int | None = Field(default=None, ge=0, le=10**12)
    bytes_out: int | None = Field(default=None, ge=0, le=10**12)
    conn_state: Literal["established", "attempt", "failed", "reset", "closed", "other"] | None = None
    dns_rcode: Literal["NOERROR", "NXDOMAIN", "SERVFAIL", "REFUSED", "OTHER"] | None = None
    feature_schema_version: Literal["flow-v1"] = FEATURE_SCHEMA_VERSION

    @field_validator("protocol", mode="before")
    @classmethod
    def _proto(cls, v: Any) -> Any:
        return v.upper() if isinstance(v, str) else v

    @field_validator("src_ip", "dst_ip")
    @classmethod
    def _ip(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return str(ipaddress.ip_address(v.strip()))

    @field_validator("event_time")
    @classmethod
    def _time(cls, v: datetime) -> datetime:
        return to_naive_utc(v)


class TelemetryBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_version: str | None = Field(default=None, max_length=32)
    source: Literal["agent", "replay"] = "agent"
    collector: str | None = Field(default=None, max_length=64)
    # Events are validated one by one so a batch can be partially accepted.
    events: list[dict[str, Any]] = Field(default_factory=list)


class RejectedEvent(BaseModel):
    index: int
    event_id: str | None
    reason: str


class BatchResult(BaseModel):
    ingestion_id: str
    status: Literal["accepted", "partially_accepted", "rejected", "empty"]
    accepted: int
    duplicates: int
    rejected: list[RejectedEvent]
    alerts_created: int
    alerts_updated: int
    monitoring_paused: bool


class Heartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_version: str | None = Field(default=None, max_length=32)
    hostname: str | None = Field(default=None, max_length=255)
    platform: str | None = Field(default=None, max_length=50)
    interface: str | None = Field(default=None, max_length=64)
    collector: str | None = Field(default=None, max_length=64)
    collector_status: str | None = Field(default=None, max_length=120)
    interval_s: float | None = Field(default=None, ge=0, le=86_400)
    bytes_sent: int | None = Field(default=None, ge=0)
    bytes_recv: int | None = Field(default=None, ge=0)
    packets_sent: int | None = Field(default=None, ge=0)
    packets_recv: int | None = Field(default=None, ge=0)
    agent_cpu_percent: float | None = Field(default=None, ge=0)
    agent_memory_mb: float | None = Field(default=None, ge=0)
    queued_events: int | None = Field(default=None, ge=0)


class HeartbeatResponse(BaseModel):
    ok: bool = True
    monitoring_paused: bool
    server_time: UTCDateTime


# ---------------------------------------------------------------------- alerts
class AlertOut(ORMModel):
    id: int
    device_id: int
    device_name: str | None = None
    title: str
    category: str
    severity: Severity
    status: AlertStatus
    detection_source: str
    rule_id: str | None
    model_version: str | None
    score: float | None
    score_meaning: str | None
    occurrence_count: int
    is_demo: bool
    first_seen_at: UTCDateTime
    last_seen_at: UTCDateTime
    created_at: UTCDateTime
    updated_at: UTCDateTime


class NoteOut(ORMModel):
    id: int
    alert_id: int
    author_user_id: int
    author_email: str | None = None
    note: str
    created_at: UTCDateTime


class EventOut(ORMModel):
    id: int
    event_uid: str
    device_id: int
    source: str
    event_time: UTCDateTime
    received_at: UTCDateTime
    protocol: str
    src_ip: str | None
    dst_ip: str | None
    src_port: int | None
    dst_port: int | None
    flow_duration: float | None
    packets_in: int | None
    packets_out: int | None
    bytes_in: int | None
    bytes_out: int | None
    conn_state: str | None
    dns_rcode: str | None
    ml_label: str | None
    ml_score: float | None
    model_version: str | None


class AuditOut(ORMModel):
    id: int
    actor_user_id: int | None
    actor_email: str | None = None
    action: str
    target_type: str | None
    target_id: str | None
    ip_address: str | None
    metadata_json: dict
    created_at: UTCDateTime


class AlertDetail(AlertOut):
    evidence_json: dict
    recommendation: str | None
    notes: list[NoteOut]
    audit_trail: list[AuditOut]
    related_events: list[EventOut]


class AlertUpdate(BaseModel):
    status: AlertStatus


class NoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=5000)


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
