from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import client_ip, get_current_user
from app.core.ratelimit import SlidingWindowLimiter
from app.core.security import DUMMY_PASSWORD_HASH, create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])

_s = get_settings()
login_failures = SlidingWindowLimiter(_s.login_max_failures, _s.login_lockout_minutes * 60)
register_limiter = SlidingWindowLimiter(10, 3600)

INVALID_LOGIN = "Invalid email or password"


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request) or "unknown"
    user_count = db.scalar(select(func.count(User.id))) or 0
    if user_count > 0 and not get_settings().open_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is disabled; ask an administrator")
    if not register_limiter.hit(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many registration attempts")
    if db.scalar(select(User).where(User.email == body.email)):
        # Same generic response shape as success is not possible here without
        # email verification; keep the message neutral.
        raise HTTPException(status.HTTP_409_CONFLICT, "Unable to create account with these details")
    # The first account becomes the administrator.
    user = User(email=body.email, password_hash=hash_password(body.password),
                role="admin" if user_count == 0 else "analyst")
    db.add(user)
    db.flush()
    audit.record(db, "user.register", actor_user_id=user.id, target_type="user",
                 target_id=user.id, ip=ip, metadata={"role": user.role})
    db.commit()
    return user


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request) or "unknown"
    email = body.email.strip().lower()
    key = f"{ip}|{email}"
    if login_failures.is_limited(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many failed attempts. Try again later.")
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(body.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if not user or not ok or not user.is_active:
        login_failures.hit(key)
        audit.record(db, "auth.login_failed", target_type="user",
                     target_id=user.id if user else None, ip=ip)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_LOGIN)
    login_failures.reset(key)
    token, expires_in = create_access_token(user.id, user.role)
    audit.record(db, "auth.login", actor_user_id=user.id, target_type="user", target_id=user.id, ip=ip)
    db.commit()
    return TokenResponse(access_token=token, expires_in=expires_in, user=UserOut.model_validate(user))


@router.post("/logout", status_code=204)
def logout(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Tokens are short-lived and held in client memory; the client discards it.
    audit.record(db, "auth.logout", actor_user_id=user.id, target_type="user",
                 target_id=user.id, ip=client_ip(request))
    db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/config")
def auth_config(db: Session = Depends(get_db)):
    has_users = (db.scalar(select(func.count(User.id))) or 0) > 0
    return {"registration_open": get_settings().open_registration or not has_users,
            "has_users": has_users}
