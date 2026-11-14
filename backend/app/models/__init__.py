"""Relational schema (see docs/data-dictionary.md)."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utcnow
from app.db.session import Base

ROLES = ("admin", "analyst", "viewer")
SEVERITIES = ("info", "low", "medium", "high", "critical")
ALERT_STATUSES = ("new", "acknowledged", "investigating", "resolved", "false_positive")
OPEN_STATUSES = ("new", "acknowledged", "investigating")
DETECTION_SOURCES = ("rule", "ml", "anomaly", "combined")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="analyst")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    platform: Mapped[str | None] = mapped_column(String(50))
    hostname: Mapped[str | None] = mapped_column(String(255))
    agent_version: Mapped[str | None] = mapped_column(String(32))
    # pending -> active -> revoked
    status: Mapped[str] = mapped_column(String(16), default="pending")
    credential_hash: Mapped[str | None] = mapped_column(String(64))
    enrollment_code_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    enrollment_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    monitoring_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    last_collector: Mapped[str | None] = mapped_column(String(64))
    last_interface: Mapped[str | None] = mapped_column(String(64))

    owner: Mapped[User] = relationship()


class NetworkEvent(Base):
    __tablename__ = "network_events"
    __table_args__ = (
        UniqueConstraint("device_id", "event_uid", name="uq_event_device_uid"),
        Index("ix_events_device_time", "device_id", "event_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_uid: Mapped[str] = mapped_column(String(64))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    ingestion_id: Mapped[str] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(16), default="agent")  # agent | replay
    event_time: Mapped[datetime] = mapped_column(DateTime)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    protocol: Mapped[str] = mapped_column(String(8))
    src_ip: Mapped[str | None] = mapped_column(String(45))
    dst_ip: Mapped[str | None] = mapped_column(String(45))
    src_port: Mapped[int | None] = mapped_column(Integer)
    dst_port: Mapped[int | None] = mapped_column(Integer)
    flow_duration: Mapped[float | None] = mapped_column(Float)
    packets_in: Mapped[int | None] = mapped_column(Integer)
    packets_out: Mapped[int | None] = mapped_column(Integer)
    bytes_in: Mapped[int | None] = mapped_column(Integer)
    bytes_out: Mapped[int | None] = mapped_column(Integer)
    conn_state: Mapped[str | None] = mapped_column(String(16))
    dns_rcode: Mapped[str | None] = mapped_column(String(16))
    feature_schema_version: Mapped[str] = mapped_column(String(16))
    ml_label: Mapped[str | None] = mapped_column(String(64))
    ml_score: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String(64))


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_created", "created_at"),
        Index("ix_alerts_last_seen", "last_seen_at"),
        Index("ix_alerts_device", "device_id"),
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_dedup", "dedup_key", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("network_events.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="new")
    detection_source: Mapped[str] = mapped_column(String(16))
    rule_id: Mapped[str | None] = mapped_column(String(64))
    model_version: Mapped[str | None] = mapped_column(String(64))
    score: Mapped[float | None] = mapped_column(Float)
    score_meaning: Mapped[str | None] = mapped_column(String(120))
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendation: Mapped[str | None] = mapped_column(Text)
    dedup_key: Mapped[str] = mapped_column(String(255))
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    device: Mapped[Device] = relationship()


class IncidentNote(Base):
    __tablename__ = "incident_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    author: Mapped[User] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    actor: Mapped[User | None] = relationship()


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(64), unique=True)
    artifact_reference: Mapped[str] = mapped_column(String(255))
    artifact_sha256: Mapped[str] = mapped_column(String(64))
    feature_schema_version: Mapped[str] = mapped_column(String(16))
    dataset_reference: Mapped[str] = mapped_column(String(255))
    trained_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class DeviceHeartbeat(Base):
    __tablename__ = "device_heartbeats"
    __table_args__ = (Index("ix_heartbeats_device_time", "device_id", "received_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    interval_s: Mapped[float | None] = mapped_column(Float)
    bytes_sent: Mapped[int | None] = mapped_column(Integer)
    bytes_recv: Mapped[int | None] = mapped_column(Integer)
    packets_sent: Mapped[int | None] = mapped_column(Integer)
    packets_recv: Mapped[int | None] = mapped_column(Integer)
    agent_cpu_percent: Mapped[float | None] = mapped_column(Float)
    agent_memory_mb: Mapped[float | None] = mapped_column(Float)
    collector_status: Mapped[str | None] = mapped_column(String(120))
    queued_events: Mapped[int | None] = mapped_column(Integer)
