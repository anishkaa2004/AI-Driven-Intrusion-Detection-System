"""Turns successive connection-table snapshots into flow-v1 records."""

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from agent.collector import ConnKey, Snapshot

STATE_MAP = {
    "ESTABLISHED": "established",
    "SYN_SENT": "attempt",
    "SYN_RECV": "attempt",
    "FIN_WAIT1": "closed", "FIN_WAIT2": "closed", "TIME_WAIT": "closed",
    "CLOSE": "closed", "CLOSE_WAIT": "closed", "LAST_ACK": "closed", "CLOSING": "closed",
}


@dataclass
class Tracked:
    first_seen: float
    last_seen: float
    states: set[str]
    last_state: str


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class FlowBuilder:
    def __init__(self, max_flow_age_s: float = 300) -> None:
        self.active: dict[ConnKey, Tracked] = {}
        self.listening: set[int] = set()
        self.max_flow_age_s = max_flow_age_s

    def update(self, snap: Snapshot, now: float | None = None) -> list[dict]:
        """Returns flow records for connections that ended (or aged out) since the last snapshot."""
        now = time.time() if now is None else now
        self.listening = snap.listening_ports
        for key, status in snap.connections.items():
            t = self.active.get(key)
            if t is None:
                self.active[key] = Tracked(now, now, {status}, status)
            else:
                t.last_seen, t.last_state = now, status
                t.states.add(status)
        finished = []
        for key in list(self.active):
            t = self.active[key]
            if key not in snap.connections:
                finished.append(self._record(key, self.active.pop(key), ended=True))
            elif now - t.first_seen >= self.max_flow_age_s:
                # Report long-lived connections periodically, then start a new interval.
                finished.append(self._record(key, t, ended=False))
                self.active[key] = Tracked(now, now, {t.last_state}, t.last_state)
        return finished

    def flush(self) -> list[dict]:
        out = [self._record(k, t, ended=False) for k, t in self.active.items()]
        self.active.clear()
        return out

    def _record(self, key: ConnKey, t: Tracked, ended: bool) -> dict:
        inbound = key.laddr[1] in self.listening
        src, dst = (key.raddr, key.laddr) if inbound else (key.laddr, key.raddr)
        state = STATE_MAP.get(t.last_state, "other")
        if ended and t.states <= {"SYN_SENT", "SYN_RECV"}:
            state = "failed"  # never progressed past the handshake
        return {
            "event_id": f"ag-{uuid.uuid4().hex}",
            "event_time": _iso(t.first_seen),
            "protocol": key.proto,
            "src_ip": src[0], "src_port": src[1],
            "dst_ip": dst[0], "dst_port": dst[1],
            "flow_duration": round(max(t.last_seen - t.first_seen, 0.0), 3),
            "conn_state": state,
            # Counters are not observable from the connection table; they are
            # omitted rather than sent as zeros.
        }
