"""Password hashing, access tokens and device credentials.

Passwords use scrypt (memory-hard KDF from the Python standard library) with a
per-password random salt. Device credentials and enrollment codes are
high-entropy random tokens, so only their SHA-256 digest is stored.
"""

import base64
import hashlib
import hmac
import secrets
import time
from datetime import timedelta

import jwt

from app.core.config import get_settings

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1
JWT_ALG = "HS256"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, expected = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(dk, _unb64(expected))
    except (ValueError, TypeError):
        return False


# A fixed hash used to keep login timing similar for unknown accounts.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


def create_access_token(user_id: int, role: str) -> tuple[str, int]:
    s = get_settings()
    now = int(time.time())
    expires = timedelta(minutes=s.access_token_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + int(expires.total_seconds()),
    }
    return jwt.encode(payload, s.secret_key, algorithm=JWT_ALG), int(expires.total_seconds())


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    return payload


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_device_credential(device_id: int) -> str:
    return f"aiids_dev_{device_id}_{secrets.token_urlsafe(32)}"


def parse_device_id(credential: str) -> int | None:
    parts = credential.split("_", 3)
    if len(parts) != 4 or parts[0] != "aiids" or parts[1] != "dev":
        return None
    try:
        return int(parts[2])
    except ValueError:
        return None


def new_enrollment_code() -> str:
    # 12 characters from an unambiguous alphabet, shown as XXXX-XXXX-XXXX.
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def normalize_enrollment_code(code: str) -> str:
    return code.strip().upper().replace(" ", "")


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
