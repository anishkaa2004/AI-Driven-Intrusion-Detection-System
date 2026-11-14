from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import client_ip, get_current_user, require_writer
from app.core.ratelimit import SlidingWindowLimiter
from app.core.security import (
    new_device_credential,
    new_enrollment_code,
    normalize_enrollment_code,
    sha256_hex,
)
from app.core.timeutil import iso_z, utcnow
from app.db.session import get_db
from app.models import Device, DeviceHeartbeat, NetworkEvent, User
from app.schemas import (
    AgentRegisterRequest,
    AgentRegisterResponse,
    DeviceOut,
    DeviceUpdate,
    EnrollRequest,
    EnrollResponse,
    EventOut,
)
from app.services import audit
from app.services import devices as device_svc
from app.websocket.manager import manager

router = APIRouter(tags=["devices"])
register_limiter = SlidingWindowLimiter(20, 600)


def _get_device(db: Session, user: User, device_id: int) -> Device:
    device = db.get(Device, device_id)
    # Same 404 for "missing" and "not yours" so ids cannot be probed.
    if device is None or not device_svc.can_access_device(user, device):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return device


@router.get("/devices", response_model=list[DeviceOut])
def list_devices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    devices = db.scalars(device_svc.scope_devices(select(Device), user).order_by(Device.id)).all()
    return [device_svc.to_out(db, d) for d in devices]


@router.post("/devices/enroll", response_model=EnrollResponse, status_code=201)
def enroll_device(body: EnrollRequest, request: Request,
                  user: User = Depends(require_writer), db: Session = Depends(get_db)):
    owner_id = user.id
    if body.owner_user_id is not None and body.owner_user_id != user.id:
        if user.role != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only administrators can enroll for others")
        if db.get(User, body.owner_user_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown owner")
        owner_id = body.owner_user_id
    code = new_enrollment_code()
    expires = utcnow() + timedelta(minutes=get_settings().enrollment_code_minutes)
    device = Device(owner_user_id=owner_id, display_name=body.display_name.strip(),
                    platform=body.platform, status="pending",
                    enrollment_code_hash=sha256_hex(normalize_enrollment_code(code)),
                    enrollment_expires_at=expires)
    db.add(device)
    db.flush()
    audit.record(db, "device.enroll_started", actor_user_id=user.id, target_type="device",
                 target_id=device.id, ip=client_ip(request),
                 metadata={"display_name": device.display_name, "owner_user_id": owner_id})
    db.commit()
    return EnrollResponse(
        device_id=device.id, enrollment_code=code, expires_at=expires,
        instructions=(
            "On the device you are authorized to monitor, run: "
            f"python -m agent register --server <BACKEND_URL> --code {code}"
        ),
    )


@router.post("/devices/{device_id}/enrollment-code", response_model=EnrollResponse)
def regenerate_code(device_id: int, request: Request,
                    user: User = Depends(require_writer), db: Session = Depends(get_db)):
    device = _get_device(db, user, device_id)
    if device.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Device is already enrolled or revoked")
    code = new_enrollment_code()
    device.enrollment_code_hash = sha256_hex(normalize_enrollment_code(code))
    device.enrollment_expires_at = utcnow() + timedelta(minutes=get_settings().enrollment_code_minutes)
    audit.record(db, "device.enrollment_code_reissued", actor_user_id=user.id,
                 target_type="device", target_id=device.id, ip=client_ip(request))
    db.commit()
    return EnrollResponse(device_id=device.id, enrollment_code=code,
                          expires_at=device.enrollment_expires_at,
                          instructions=f"python -m agent register --server <BACKEND_URL> --code {code}")


@router.post("/agents/register", response_model=AgentRegisterResponse, tags=["agent"])
def agent_register(body: AgentRegisterRequest, request: Request, db: Session = Depends(get_db)):
    """Exchange a short-lived, single-use enrollment code for a device credential."""
    ip = client_ip(request) or "unknown"
    if not register_limiter.hit(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts")
    code_hash = sha256_hex(normalize_enrollment_code(body.enrollment_code))
    device = db.scalar(select(Device).where(Device.enrollment_code_hash == code_hash))
    if (device is None or device.status != "pending" or device.enrollment_expires_at is None
            or device.enrollment_expires_at < utcnow()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired enrollment code")
    credential = new_device_credential(device.id)
    device.credential_hash = sha256_hex(credential)
    device.enrollment_code_hash = None
    device.enrollment_expires_at = None
    device.status = "active"
    device.enrolled_at = utcnow()
    device.hostname = body.hostname
    device.platform = body.platform or device.platform
    device.agent_version = body.agent_version
    audit.record(db, "device.enrolled", target_type="device", target_id=device.id, ip=ip,
                 metadata={"hostname": body.hostname, "agent_version": body.agent_version})
    db.commit()
    return AgentRegisterResponse(device_id=device.id, credential=credential,
                                 display_name=device.display_name)


@router.get("/devices/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return device_svc.to_out(db, _get_device(db, user, device_id))


@router.patch("/devices/{device_id}", response_model=DeviceOut)
async def update_device(device_id: int, body: DeviceUpdate, request: Request,
                        user: User = Depends(require_writer), db: Session = Depends(get_db)):
    device = _get_device(db, user, device_id)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(device, k, v.strip() if isinstance(v, str) else v)
    audit.record(db, "device.updated", actor_user_id=user.id, target_type="device",
                 target_id=device.id, ip=client_ip(request), metadata=changes)
    db.commit()
    out = device_svc.to_out(db, device)
    await manager.publish({"type": "device", "device": out.model_dump(mode="json")}, device.owner_user_id)
    return out


@router.post("/devices/{device_id}/revoke", response_model=DeviceOut)
async def revoke_device(device_id: int, request: Request,
                        user: User = Depends(require_writer), db: Session = Depends(get_db)):
    device = _get_device(db, user, device_id)
    if device.status == "revoked":
        raise HTTPException(status.HTTP_409_CONFLICT, "Device already revoked")
    device.status = "revoked"
    device.revoked_at = utcnow()
    device.credential_hash = None
    device.enrollment_code_hash = None
    audit.record(db, "device.revoked", actor_user_id=user.id, target_type="device",
                 target_id=device.id, ip=client_ip(request))
    db.commit()
    out = device_svc.to_out(db, device)
    await manager.publish({"type": "device", "device": out.model_dump(mode="json")}, device.owner_user_id)
    return out


@router.get("/devices/{device_id}/traffic")
def device_traffic(device_id: int, minutes: int = Query(60, ge=5, le=1440),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Live-monitoring data: flow series, protocol mix, recent flows, interface counters."""
    device = _get_device(db, user, device_id)
    now = utcnow()
    start = now - timedelta(minutes=minutes)
    bucket_s = max(10, minutes * 60 // 60)
    c = NetworkEvent
    rows = db.execute(
        select(c.event_time, c.protocol, c.bytes_in, c.bytes_out)
        .where(c.device_id == device.id, c.event_time >= start)
    ).all()
    n_buckets = minutes * 60 // bucket_s + 1
    series = [{"t": iso_z(start + timedelta(seconds=i * bucket_s)), "flows": 0,
               "bytes_in": 0, "bytes_out": 0} for i in range(n_buckets)]
    protocols: Counter = Counter()
    for r in rows:
        i = min(int((r.event_time - start).total_seconds() // bucket_s), n_buckets - 1)
        series[i]["flows"] += 1
        series[i]["bytes_in"] += r.bytes_in or 0
        series[i]["bytes_out"] += r.bytes_out or 0
        protocols[r.protocol] += 1
    recent = db.scalars(select(c).where(c.device_id == device.id)
                        .order_by(c.event_time.desc(), c.id.desc()).limit(50)).all()
    hb = db.scalars(select(DeviceHeartbeat).where(
        DeviceHeartbeat.device_id == device.id, DeviceHeartbeat.received_at >= start)
        .order_by(DeviceHeartbeat.received_at)).all()
    latest = hb[-1] if hb else None
    return {
        "device": device_svc.to_out(db, device, with_counts=False).model_dump(mode="json"),
        "bucket_s": bucket_s,
        "series": series,
        "protocols": [{"protocol": k, "flows": v} for k, v in protocols.most_common()],
        "recent_flows": [EventOut.model_validate(e).model_dump(mode="json") for e in recent],
        "interface": [
            {"t": iso_z(h.received_at), "bytes_sent": h.bytes_sent, "bytes_recv": h.bytes_recv,
             "interval_s": h.interval_s} for h in hb
        ],
        "agent": None if latest is None else {
            "received_at": iso_z(latest.received_at),
            "cpu_percent": latest.agent_cpu_percent,
            "memory_mb": latest.agent_memory_mb,
            "collector_status": latest.collector_status,
            "queued_events": latest.queued_events,
        },
    }
