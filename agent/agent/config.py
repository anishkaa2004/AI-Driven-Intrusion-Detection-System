"""Agent configuration and credential storage (owner-only file permissions)."""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

AGENT_VERSION = "0.1.0"
CONFIG_DIR = Path(os.environ.get("AIIDS_AGENT_HOME", Path.home() / ".aiids-agent"))
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class AgentConfig:
    server: str
    device_id: int
    credential: str
    display_name: str = ""
    verify_tls: bool = True


def save(cfg: AgentConfig) -> Path:
    CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(asdict(cfg), f, indent=2)
    tmp.replace(CONFIG_FILE)
    return CONFIG_FILE


def load() -> AgentConfig | None:
    if not CONFIG_FILE.is_file():
        return None
    return AgentConfig(**json.loads(CONFIG_FILE.read_text()))


def forget() -> bool:
    if CONFIG_FILE.is_file():
        CONFIG_FILE.unlink()
        return True
    return False
