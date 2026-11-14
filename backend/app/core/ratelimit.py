"""Small in-process rate limiters.

These are adequate for a single-process prototype. A multi-worker deployment
would need a shared store (e.g. Redis) instead.
"""

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_s: float):
        self.max_events = max_events
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._hits[key]
        while q and now - q[0] > self.window_s:
            q.popleft()
        return q

    def is_limited(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, time.monotonic())) >= self.max_events

    def hit(self, key: str) -> bool:
        """Record a hit. Returns False when the key is over its limit."""
        with self._lock:
            now = time.monotonic()
            q = self._prune(key, now)
            if len(q) >= self.max_events:
                return False
            q.append(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()
