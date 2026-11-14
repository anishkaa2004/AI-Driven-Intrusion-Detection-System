"""Create a development admin account and an enrolled demo replay device.

    python scripts/seed_demo_data.py [--email admin@aiids.local]

Generated credentials are written to backend/.demo_credentials.json with
owner-only permissions (the file is git-ignored). Development use only.
"""

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password, new_device_credential, sha256_hex  # noqa: E402
from app.core.timeutil import utcnow  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.models import Device, User  # noqa: E402
from app.services import audit  # noqa: E402

CRED_FILE = ROOT / "backend" / ".demo_credentials.json"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", default="admin@aiids.local")
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    init_db()
    creds = json.loads(CRED_FILE.read_text()) if CRED_FILE.is_file() else {}
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email))
        if user is None:
            password = secrets.token_urlsafe(12)
            role = "admin" if db.scalar(select(User.id).limit(1)) is None else "analyst"
            user = User(email=args.email, password_hash=hash_password(password), role=role)
            db.add(user)
            db.flush()
            audit.record(db, "user.seeded", target_type="user", target_id=user.id, metadata={"role": role})
            creds["user"] = {"email": args.email, "password": password, "role": role}
            print(f"Created {role} account {args.email}")
        else:
            print(f"Account {args.email} already exists; password unchanged")

        stored = creds.get("device", {}).get("device_id")
        device = db.get(Device, stored) if stored else None
        if device is None or device.status != "active":
            # No demo device yet, or it was revoked: create a fresh one.
            device = Device(owner_user_id=user.id, display_name="Demo replay device",
                            platform="replay", hostname="replay", status="active", enrolled_at=utcnow())
            db.add(device)
            db.flush()
            credential = new_device_credential(device.id)
            device.credential_hash = sha256_hex(credential)
            audit.record(db, "device.seeded", actor_user_id=user.id, target_type="device", target_id=device.id)
            creds["device"] = {"device_id": device.id, "credential": credential, "server": args.server}
            print(f"Created demo device #{device.id}")
        db.commit()

    fd = os.open(CRED_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(creds, f, indent=2)
    print(f"Credentials saved to {CRED_FILE.relative_to(ROOT)} (git-ignored). Open that file to log in.")


if __name__ == "__main__":
    main()
