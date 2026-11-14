import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="aiids-test-")
os.environ["AIIDS_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["AIIDS_SECRET_KEY"] = "test-secret-key-not-for-production-use-0123456789"
os.environ["AIIDS_ENVIRONMENT"] = "test"

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml" / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from app.api import auth as auth_api  # noqa: E402
from app.api import devices as devices_api  # noqa: E402
from app.api import telemetry as telemetry_api  # noqa: E402
from app.db.session import Base, engine  # noqa: E402
from app.main import create_app  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    for limiter in (auth_api.login_failures, auth_api.register_limiter,
                    devices_api.register_limiter, telemetry_api.batch_limiter):
        limiter.clear()
    with TestClient(create_app(background_jobs=False)) as c:
        yield c


def register_and_login(client, email: str) -> dict:
    r = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def enroll(client, headers: dict, name: str = "Test laptop") -> tuple[int, dict]:
    r = client.post("/api/v1/devices/enroll", json={"display_name": name}, headers=headers)
    assert r.status_code == 201, r.text
    code = r.json()["enrollment_code"]
    r = client.post("/api/v1/agents/register",
                    json={"enrollment_code": code, "hostname": "test-host", "agent_version": "0.1.0"})
    assert r.status_code == 200, r.text
    body = r.json()
    return body["device_id"], {"Authorization": f"Bearer {body['credential']}"}


def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture()
def admin(client):
    return register_and_login(client, "admin@example.test")


@pytest.fixture()
def device(client, admin):
    return enroll(client, admin)
