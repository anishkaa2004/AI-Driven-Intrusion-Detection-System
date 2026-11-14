"""Authenticated ingestion endpoints used by agents and the replay tool."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.deps import get_current_device
from app.core.ratelimit import SlidingWindowLimiter
from app.core.timeutil import utcnow
from app.db.session import SessionLocal, get_db
from app.models import Device, DeviceHeartbeat
from app.schemas import BatchResult, Heartbeat, HeartbeatResponse, TelemetryBatch
from app.services import alert_service, ingestion
from app.services import devices as device_svc
from app.websocket.manager import manager

router = APIRouter(prefix="/telemetry", tags=["agent"])
batch_limiter = SlidingWindowLimiter(get_settings().agent_batches_per_minute, 60)


def _ingest(device_id: int, batch: TelemetryBatch):
    for attempt in range(2):
        db = SessionLocal()
        try:
            device = db.get(Device, device_id)
            outcome = ingestion.process_batch(db, device, batch)
            alerts = [
                (alert_service.to_out(a).model_dump(mode="json"), a.id in outcome.created_ids)
                for a in outcome.alerts
            ]
            return outcome, alerts, device.owner_user_id, device_svc.to_out(db, device, with_counts=False)
        except IntegrityError:
            # A concurrent retry inserted the same event ids; re-run to count them as duplicates.
            db.rollback()
            if attempt:
                raise
        finally:
            db.close()


@router.post("/batch", response_model=BatchResult)
async def submit_batch(batch: TelemetryBatch, device: Device = Depends(get_current_device)):
    s = get_settings()
    if len(batch.events) > s.max_batch_events:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"Batch exceeds {s.max_batch_events} events")
    if not batch_limiter.hit(f"device:{device.id}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Device rate limit exceeded")

    outcome, alerts, owner_id, device_out = await run_in_threadpool(_ingest, device.id, batch)

    # Publish only after the transaction has committed.
    if outcome.summary:
        await manager.publish({"type": "events", **outcome.summary}, owner_id)
    for alert, created in alerts:
        await manager.publish({"type": "alert", "action": "created" if created else "updated",
                               "alert": alert}, owner_id)
    await manager.publish({"type": "device", "device": device_out.model_dump(mode="json")}, owner_id)
    return outcome.result


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(body: Heartbeat, device: Device = Depends(get_current_device),
                    db: Session = Depends(get_db)):
    if not batch_limiter.hit(f"hb:{device.id}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Device rate limit exceeded")
    now = utcnow()
    device.last_seen_at = now
    for attr in ("agent_version", "hostname", "platform"):
        if (v := getattr(body, attr)) is not None:
            setattr(device, attr, v)
    if body.collector:
        device.last_collector = body.collector
    if body.interface:
        device.last_interface = body.interface
    db.add(DeviceHeartbeat(
        device_id=device.id, received_at=now, interval_s=body.interval_s,
        bytes_sent=body.bytes_sent, bytes_recv=body.bytes_recv,
        packets_sent=body.packets_sent, packets_recv=body.packets_recv,
        agent_cpu_percent=body.agent_cpu_percent, agent_memory_mb=body.agent_memory_mb,
        collector_status=body.collector_status, queued_events=body.queued_events,
    ))
    db.commit()
    out = device_svc.to_out(db, device, with_counts=False)
    await manager.publish({"type": "device", "device": out.model_dump(mode="json")}, device.owner_user_id)
    return HeartbeatResponse(monitoring_paused=device.monitoring_paused, server_time=now)
