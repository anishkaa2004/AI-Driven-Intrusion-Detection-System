"""FastAPI dependencies for user and device authentication."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import constant_time_equals, decode_access_token, parse_device_id, sha256_hex
from app.db.session import get_db
from app.models import Device, User

bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def user_from_token(db: Session, token: str) -> User | None:
    payload = decode_access_token(token)
    if not payload:
        return None
    try:
        user = db.get(User, int(payload["sub"]))
    except (KeyError, ValueError):
        return None
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise _UNAUTHENTICATED
    user = user_from_token(db, creds.credentials)
    if user is None:
        raise _UNAUTHENTICATED
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return checker


require_admin = require_roles("admin")
require_writer = require_roles("admin", "analyst")


def get_current_device(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Device:
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked device credential")
    if creds is None:
        raise invalid
    device_id = parse_device_id(creds.credentials)
    device = db.get(Device, device_id) if device_id is not None else None
    if (
        device is None
        or device.status != "active"
        or not device.credential_hash
        or not constant_time_equals(device.credential_hash, sha256_hex(creds.credentials))
    ):
        raise invalid
    return device
