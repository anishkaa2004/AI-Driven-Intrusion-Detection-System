"""Connection-table collector built on psutil.

Collects only socket metadata (protocol, addresses, ports, state) from the
operating system's connection table. It never reads packet payloads, process
memory, files or browsing content, and does not send process names.

Visibility limits (documented in README): polling misses connections shorter
than the poll interval, and per-connection byte/packet counters are not
available from the OS connection table, so these flows carry no counters and
the backend applies rules but not the ML model to them.
"""

import socket
from dataclasses import dataclass

import psutil

PROTO = {socket.SOCK_STREAM: "TCP", socket.SOCK_DGRAM: "UDP"}


@dataclass(frozen=True)
class ConnKey:
    proto: str
    laddr: tuple[str, int]
    raddr: tuple[str, int]


@dataclass
class Snapshot:
    connections: dict[ConnKey, str]  # key -> psutil status
    listening_ports: set[int]
    mode: str  # "system" or "user-processes"
    error: str | None = None


def _iter_connections():
    """System-wide table if permitted, otherwise this user's processes only."""
    try:
        return psutil.net_connections(kind="inet"), "system", None
    except psutil.AccessDenied:
        conns = []
        for proc in psutil.process_iter():
            try:
                conns.extend(proc.net_connections(kind="inet"))
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
        return conns, "user-processes", "system table needs elevated privileges; showing own processes"


def snapshot(exclude: set[tuple[str, int]] | None = None) -> Snapshot:
    exclude = exclude or set()
    conns, mode, err = _iter_connections()
    table: dict[ConnKey, str] = {}
    listening: set[int] = set()
    for c in conns:
        proto = PROTO.get(c.type)
        if proto is None or not c.laddr:
            continue
        if c.status == psutil.CONN_LISTEN:
            listening.add(c.laddr.port)
            continue
        if not c.raddr:
            continue
        r = (c.raddr.ip, c.raddr.port)
        local = (c.laddr.ip, c.laddr.port)
        if r in exclude or local in exclude:
            # Don't report traffic to/from the backend itself (including the
            # server side of these sockets when the backend runs locally).
            continue
        table[ConnKey(proto, local, r)] = c.status or "NONE"
    return Snapshot(table, listening, mode, err)
