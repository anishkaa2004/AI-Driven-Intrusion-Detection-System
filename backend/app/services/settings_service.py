"""Runtime-configurable detection settings stored in the database."""

import copy

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models import SystemSetting
from app.schemas import Severity


class PortScanRule(BaseModel):
    enabled: bool = True
    window_s: int = Field(60, ge=5, le=3600)
    distinct_ports: int = Field(20, ge=2, le=65_536)
    severity: Severity = "high"


class FlowRateRule(BaseModel):
    enabled: bool = True
    window_s: int = Field(10, ge=1, le=3600)
    flows: int = Field(100, ge=5, le=1_000_000)
    severity: Severity = "high"


class ConnFailureRule(BaseModel):
    enabled: bool = True
    window_s: int = Field(60, ge=5, le=3600)
    failures: int = Field(15, ge=2, le=100_000)
    severity: Severity = "medium"


class DnsRule(BaseModel):
    enabled: bool = True
    window_s: int = Field(60, ge=5, le=3600)
    queries: int = Field(120, ge=5, le=1_000_000)
    failures: int = Field(20, ge=2, le=100_000)
    severity: Severity = "medium"


class VolumeRule(BaseModel):
    enabled: bool = True
    bucket_s: int = Field(300, ge=30, le=86_400)
    history_buckets: int = Field(12, ge=3, le=288)
    min_history: int = Field(6, ge=2, le=288)
    sigma: float = Field(3.0, ge=1.0, le=20.0)
    min_bytes: int = Field(5_000_000, ge=0)
    severity: Severity = "low"


class RulesConfig(BaseModel):
    R001_port_scan: PortScanRule = PortScanRule()
    R002_high_flow_rate: FlowRateRule = FlowRateRule()
    R003_connection_failures: ConnFailureRule = ConnFailureRule()
    R004_dns_anomaly: DnsRule = DnsRule()
    R005_volume_deviation: VolumeRule = VolumeRule()


class MLConfig(BaseModel):
    enabled: bool = True
    min_score: float = Field(0.80, ge=0.5, le=1.0)
    min_events: int = Field(3, ge=1, le=10_000)
    severity: Severity = "medium"


class RetentionConfig(BaseModel):
    raw_event_days: int = Field(7, ge=1, le=365)
    heartbeat_days: int = Field(3, ge=1, le=365)


CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "rules": RulesConfig,
    "ml": MLConfig,
    "retention": RetentionConfig,
}


def get_config[T: BaseModel](db: Session, key: str, model: type[T]) -> T:
    row = db.get(SystemSetting, key)
    if row is None:
        return model()
    return model.model_validate(copy.deepcopy(row.value_json))


def set_config(db: Session, key: str, value: BaseModel, user_id: int | None) -> None:
    row = db.get(SystemSetting, key)
    data = value.model_dump()
    if row is None:
        db.add(SystemSetting(key=key, value_json=data, updated_by=user_id))
    else:
        row.value_json = data
        row.updated_by = user_id


def rules(db: Session) -> RulesConfig:
    return get_config(db, "rules", RulesConfig)


def ml(db: Session) -> MLConfig:
    return get_config(db, "ml", MLConfig)


def retention(db: Session) -> RetentionConfig:
    return get_config(db, "retention", RetentionConfig)
