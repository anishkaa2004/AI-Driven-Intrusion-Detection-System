"""Batching sender with bounded queue, retries and exponential backoff."""

import logging
import time
from collections import deque

import httpx

from agent.config import AGENT_VERSION

log = logging.getLogger("aiids.agent.sender")


class CredentialRevoked(Exception):
    pass


class Sender:
    def __init__(self, server: str, credential: str, *, verify_tls: bool = True,
                 batch_size: int = 200, max_queue: int = 20_000, collector: str = "psutil-conn",
                 source: str = "agent", timeout: float = 10.0) -> None:
        self.client = httpx.Client(
            base_url=server.rstrip("/"), timeout=timeout, verify=verify_tls,
            headers={"Authorization": f"Bearer {credential}", "User-Agent": f"aiids-agent/{AGENT_VERSION}"},
        )
        self.queue: deque[dict] = deque(maxlen=max_queue)
        self.batch_size = batch_size
        self.collector = collector
        self.source = source
        self.dropped = 0
        self.backoff = 0.0
        self.next_attempt = 0.0
        self.last_success: float | None = None
        self.monitoring_paused = False

    def enqueue(self, events: list[dict]) -> None:
        overflow = max(len(self.queue) + len(events) - (self.queue.maxlen or 0), 0)
        self.dropped += overflow  # oldest events are discarded when the queue is full
        self.queue.extend(events)

    def _post(self, path: str, body: dict) -> httpx.Response | None:
        try:
            r = self.client.post(path, json=body)
        except httpx.HTTPError as exc:
            log.warning("send failed: %s", exc.__class__.__name__)
            self._fail()
            return None
        if r.status_code == 401:
            raise CredentialRevoked("Device credential rejected (revoked or invalid)")
        if r.status_code == 429 or r.status_code >= 500:
            log.warning("server returned %s; backing off", r.status_code)
            self._fail()
            return None
        self.backoff, self.next_attempt = 0.0, 0.0
        self.last_success = time.time()
        return r

    def _fail(self) -> None:
        self.backoff = min(max(self.backoff * 2, 1.0), 60.0)
        self.next_attempt = time.time() + self.backoff

    def flush(self, force: bool = False) -> int:
        """Send queued events. Returns number accepted by the server."""
        accepted = 0
        while self.queue and (force or time.time() >= self.next_attempt):
            n = min(self.batch_size, len(self.queue))
            batch = [self.queue[i] for i in range(n)]
            r = self._post("/api/v1/telemetry/batch", {
                "agent_version": AGENT_VERSION, "source": self.source,
                "collector": self.collector, "events": batch,
            })
            if r is None:
                if force:
                    break
                return accepted
            for _ in range(n):
                self.queue.popleft()  # same event ids are safe to resend (idempotent)
            if r.status_code == 200:
                body = r.json()
                accepted += body["accepted"]
                self.monitoring_paused = body.get("monitoring_paused", False)
                if body["rejected"]:
                    log.warning("%d events rejected, first: %s", len(body["rejected"]), body["rejected"][0])
            else:
                log.error("batch refused (%s): %s", r.status_code, r.text[:200])
        return accepted

    def heartbeat(self, metrics: dict) -> bool:
        r = self._post("/api/v1/telemetry/heartbeat", {
            "agent_version": AGENT_VERSION, "collector": self.collector,
            "queued_events": len(self.queue), **metrics,
        })
        if r is not None and r.status_code == 200:
            self.monitoring_paused = r.json().get("monitoring_paused", False)
            return True
        return False

    def close(self) -> None:
        self.client.close()
