"""AI-IDS backend entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select

from app.api import admin, alerts, auth, dashboard, devices, telemetry, ws
from app.core.config import get_settings
from app.core.timeutil import utcnow
from app.db.session import SessionLocal, init_db
from app.models import Device, DeviceHeartbeat, NetworkEvent
from app.services import devices as device_svc
from app.services import settings_service
from app.services.ml_inference import model_service
from app.websocket.manager import manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("aiids")


async def watch_device_health(interval_s: float = 15) -> None:
    """Publish health transitions (e.g. online -> stale) that happen without new telemetry."""
    last: dict[int, str] = {}
    while True:
        try:
            with SessionLocal() as db:
                for d in db.scalars(select(Device)).all():
                    h = device_svc.device_health(d)
                    if last.get(d.id) not in (None, h):
                        out = device_svc.to_out(db, d, with_counts=False)
                        await manager.publish({"type": "device", "device": out.model_dump(mode="json")},
                                              d.owner_user_id)
                    last[d.id] = h
        except Exception:
            log.exception("device health watcher failed")
        await asyncio.sleep(interval_s)


async def enforce_retention(interval_s: float = 3600) -> None:
    while True:
        try:
            with SessionLocal() as db:
                cfg = settings_service.retention(db)
                now = utcnow()
                ev = db.execute(delete(NetworkEvent).where(
                    NetworkEvent.received_at < now - timedelta(days=cfg.raw_event_days)))
                hb = db.execute(delete(DeviceHeartbeat).where(
                    DeviceHeartbeat.received_at < now - timedelta(days=cfg.heartbeat_days)))
                db.commit()
                if ev.rowcount or hb.rowcount:
                    log.info("Retention removed %s events, %s heartbeats", ev.rowcount, hb.rowcount)
        except Exception:
            log.exception("retention job failed")
        await asyncio.sleep(interval_s)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if model_service.load():
        with SessionLocal() as db:
            model_service.sync_registry(db)
    tasks = []
    if app.state.background_jobs:
        tasks = [asyncio.create_task(watch_device_health()), asyncio.create_task(enforce_retention())]
    yield
    for t in tasks:
        t.cancel()


def create_app(background_jobs: bool = True) -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="AI-IDS API",
        version="0.1.0",
        description="Hybrid rule-based and ML network intrusion detection (educational prototype).",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.background_jobs = background_jobs
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition"],
    )

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        length = request.headers.get("content-length")
        if length is not None:
            try:
                too_big = int(length) > s.max_request_bytes
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
            if too_big:
                return JSONResponse({"detail": "Request body too large"}, status_code=413)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    prefix = "/api/v1"
    for r in (auth.router, devices.router, telemetry.router, alerts.router,
              dashboard.router, admin.router):
        app.include_router(r, prefix=prefix)
    app.include_router(ws.router)
    return app


app = create_app()
