"""Heartbeat metrics: interface totals and the agent's own resource usage."""

import os
import platform
import socket
import time

import psutil


class HealthReporter:
    def __init__(self) -> None:
        self._proc = psutil.Process(os.getpid())
        self._proc.cpu_percent(None)
        self._last = psutil.net_io_counters()
        self._last_t = time.time()

    def sample(self) -> dict:
        now = time.time()
        cur = psutil.net_io_counters()
        interval = max(now - self._last_t, 1e-3)
        delta = {
            "bytes_sent": max(cur.bytes_sent - self._last.bytes_sent, 0),
            "bytes_recv": max(cur.bytes_recv - self._last.bytes_recv, 0),
            "packets_sent": max(cur.packets_sent - self._last.packets_sent, 0),
            "packets_recv": max(cur.packets_recv - self._last.packets_recv, 0),
        }
        self._last, self._last_t = cur, now
        return {
            "hostname": socket.gethostname()[:255],
            "platform": f"{platform.system()} {platform.release()}"[:50],
            "interface": "all",
            "interval_s": round(interval, 2),
            "agent_cpu_percent": round(self._proc.cpu_percent(None), 2),
            "agent_memory_mb": round(self._proc.memory_info().rss / 1e6, 1),
            **delta,
        }
