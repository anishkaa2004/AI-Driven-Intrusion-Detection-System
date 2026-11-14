"""Application configuration loaded from environment variables (prefix AIIDS_)."""

import logging
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

log = logging.getLogger("aiids.config")

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"), env_prefix="AIIDS_", extra="ignore"
    )

    environment: str = "development"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'aiids.db'}"
    secret_key: str = ""
    access_token_minutes: int = 60
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    open_registration: bool = True

    # Only artifacts inside this directory are ever loaded.
    model_artifacts_dir: str = str(REPO_DIR / "ml" / "artifacts")

    max_batch_events: int = 500
    max_request_bytes: int = 1_000_000
    agent_batches_per_minute: int = 120

    online_threshold_s: int = 60
    stale_threshold_s: int = 300
    enrollment_code_minutes: int = 15
    dedup_window_minutes: int = 15
    max_event_age_days: int = 7

    login_max_failures: int = 5
    login_lockout_minutes: int = 15

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str) and not v.strip().startswith("["):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.secret_key:
        if s.environment != "development":
            raise RuntimeError("AIIDS_SECRET_KEY must be set outside development")
        s.secret_key = secrets.token_urlsafe(48)
        log.warning(
            "AIIDS_SECRET_KEY not set; using an ephemeral key. "
            "User sessions will be invalidated when the server restarts."
        )
    return s
