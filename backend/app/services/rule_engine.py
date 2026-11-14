"""Transparent, configurable detection rules.

Every rule evaluates a sliding time window over a device's recent flow
records and, when it fires, records the evidence that triggered it. Rules
evaluate indicators, not proof: each one documents known benign causes.
"""

import math
from collections import Counter, defaultdict
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import iso_z
from app.models import NetworkEvent
from app.services.settings_service import RulesConfig

RULE_DOCS = [
    {
        "rule_id": "R001_port_scan",
        "name": "Excessive distinct destination ports",
        "category": "port_scan",
        "required_fields": ["event_time", "src_ip", "dst_port"],
        "logic": "One source contacts at least `distinct_ports` different destination ports within `window_s` seconds.",
        "benign_causes": ["Network inventory or vulnerability scanners you run", "Service discovery tools", "Some peer-to-peer applications"],
    },
    {
        "rule_id": "R002_high_flow_rate",
        "name": "High flow rate towards one destination",
        "category": "dos",
        "required_fields": ["event_time", "dst_ip"],
        "logic": "At least `flows` flow records target the same destination IP within `window_s` seconds.",
        "benign_causes": ["Busy legitimate servers", "Load tests", "Software updates or backups", "Chatty IoT devices"],
    },
    {
        "rule_id": "R003_connection_failures",
        "name": "Repeated connection failures to one service",
        "category": "repeated_connection_failures",
        "required_fields": ["event_time", "src_ip", "dst_ip", "dst_port", "conn_state"],
        "logic": "At least `failures` failed/reset connections from one source to the same destination service within `window_s` seconds. May indicate brute-force attempts or probing; confirming brute force requires authentication logs.",
        "benign_causes": ["A service that is down", "Misconfigured clients retrying", "Firewall rejecting legitimate traffic"],
    },
    {
        "rule_id": "R004_dns_anomaly",
        "name": "High DNS query or failure rate",
        "category": "dns_anomaly",
        "required_fields": ["event_time", "src_ip", "dst_port", "dns_rcode (for failures)"],
        "logic": "One source sends at least `queries` DNS flows, or receives at least `failures` non-NOERROR DNS responses, within `window_s` seconds.",
        "benign_causes": ["Browsers prefetching", "Misconfigured resolvers", "Mail servers performing lookups"],
    },
    {
        "rule_id": "R005_volume_deviation",
        "name": "Traffic volume deviation from device baseline",
        "category": "traffic_volume_anomaly",
        "required_fields": ["event_time", "bytes_in", "bytes_out"],
        "logic": "Bytes in the current `bucket_s` bucket exceed mean + `sigma` x std of the previous `history_buckets` buckets (requires `min_history` non-empty buckets and at least `min_bytes`).",
        "benign_causes": ["Large downloads or OS updates", "Video calls and streaming", "Cloud backup jobs"],
    },
]

RECOMMENDATIONS = {
    "port_scan": "Check whether the source is a scanner you operate. If not, identify the host owner, review which ports responded, and confirm exposed services are expected.",
    "dos": "Compare against expected service load. Check the number of distinct sources, whether the service stayed available, and upstream rate limiting.",
    "repeated_connection_failures": "Review authentication/application logs on the destination service for failed logins from this source, and confirm the service is healthy.",
    "dns_anomaly": "Review resolver logs for the queried names. Look for many random-looking subdomains or repeated NXDOMAIN responses from one host.",
    "traffic_volume_anomaly": "Identify the processes or users responsible for the traffic and confirm whether a large transfer was expected.",
    "brute_force": "Review authentication logs on the destination service and consider account lockout or MFA if attempts are confirmed.",
    "web_attack": "Review web server/application logs for the affected requests.",
    "botnet": "Inspect the host for unknown processes and compare outbound destinations against threat intelligence.",
}
GENERIC_RECOMMENDATION = "Review the evidence and surrounding activity for this device before taking action."


@dataclass
class Finding:
    rule_id: str | None
    category: str
    severity: str
    title: str
    dedup_key: str
    evidence: dict
    first_seen: datetime
    last_seen: datetime
    subject_ip: str | None = None
    related_ips: set[str] = field(default_factory=set)
    detection_source: str = "rule"
    score: float | None = None
    score_meaning: str | None = None
    model_version: str | None = None
    corroborating: list[str] = field(default_factory=list)

    @property
    def recommendation(self) -> str:
        return RECOMMENDATIONS.get(self.category, GENERIC_RECOMMENDATION)


@dataclass(frozen=True)
class Ev:
    """Lightweight view of a stored event used by rules."""

    id: int
    t: datetime
    protocol: str
    src_ip: str | None
    dst_ip: str | None
    src_port: int | None
    dst_port: int | None
    packets: int
    bytes: int
    conn_state: str | None
    dns_rcode: str | None
    is_new: bool = True  # part of the batch being evaluated


def fetch_window(db: Session, device_id: int, start: datetime, end: datetime,
                 new_ids: set[int] | None = None) -> list[Ev]:
    c = NetworkEvent
    rows = db.execute(
        select(
            c.id, c.event_time, c.protocol, c.src_ip, c.dst_ip, c.src_port, c.dst_port,
            c.packets_in, c.packets_out, c.bytes_in, c.bytes_out, c.conn_state, c.dns_rcode,
        )
        .where(c.device_id == device_id, c.event_time >= start, c.event_time <= end)
        .order_by(c.event_time, c.id)
    ).all()
    return [
        Ev(
            r.id, r.event_time, r.protocol, r.src_ip, r.dst_ip, r.src_port, r.dst_port,
            (r.packets_in or 0) + (r.packets_out or 0), (r.bytes_in or 0) + (r.bytes_out or 0),
            r.conn_state, r.dns_rcode, new_ids is None or r.id in new_ids,
        )
        for r in rows
    ]


@dataclass
class WindowResult:
    value: int
    events: list[Ev]


def sliding_max(
    events: Sequence[Ev], window_s: float, distinct: Callable[[Ev], Hashable] | None = None
) -> WindowResult:
    """Maximum event count (or distinct-key count) in any window of `window_s`.

    Only windows ending at an event from the current batch are considered, so
    activity that was already evaluated in earlier batches does not re-fire.
    """
    window = timedelta(seconds=window_s)
    counts: Counter = Counter()
    left = 0
    best = WindowResult(0, [])
    for right, e in enumerate(events):
        if distinct:
            counts[distinct(e)] += 1
        while e.t - events[left].t > window:
            if distinct:
                k = distinct(events[left])
                counts[k] -= 1
                if counts[k] == 0:
                    del counts[k]
            left += 1
        value = len(counts) if distinct else right - left + 1
        if e.is_new and value > best.value:
            best = WindowResult(value, list(events[left : right + 1]))
    return best


def _group(events: list[Ev], key: Callable[[Ev], Hashable | None]) -> dict:
    groups: dict = defaultdict(list)
    for e in events:
        k = key(e)
        if k is not None:
            groups[k].append(e)
    return groups


def _window_evidence(w: WindowResult) -> dict:
    return {
        "window_start": iso_z(w.events[0].t),
        "window_end": iso_z(w.events[-1].t),
        "matched_event_count": len(w.events),
        "sample_event_ids": [e.id for e in w.events[:10]],
    }


def rule_port_scan(device_id: int, events: list[Ev], cfg) -> list[Finding]:
    out = []
    for src, evs in _group(events, lambda e: e.src_ip if e.dst_port is not None else None).items():
        w = sliding_max(evs, cfg.window_s, distinct=lambda e: e.dst_port)
        if w.value >= cfg.distinct_ports:
            ports = sorted({e.dst_port for e in w.events})
            hosts = sorted({e.dst_ip for e in w.events if e.dst_ip})
            out.append(Finding(
                rule_id="R001_port_scan", category="port_scan", severity=cfg.severity,
                title=f"Possible port scan from {src} ({w.value} ports in {cfg.window_s}s)",
                dedup_key=f"{device_id}:R001:{src}", subject_ip=src,
                first_seen=w.events[0].t, last_seen=w.events[-1].t,
                evidence={
                    "source_ip": src, "distinct_ports": w.value, "threshold": cfg.distinct_ports,
                    "window_s": cfg.window_s, "target_hosts": hosts[:10], "target_host_count": len(hosts),
                    "sample_ports": ports[:25], **_window_evidence(w),
                },
            ))
    return out


def rule_flow_rate(device_id: int, events: list[Ev], cfg) -> list[Finding]:
    out = []
    for dst, evs in _group(events, lambda e: e.dst_ip).items():
        w = sliding_max(evs, cfg.window_s)
        if w.value >= cfg.flows:
            sources = Counter(e.src_ip for e in w.events if e.src_ip)
            span = max((w.events[-1].t - w.events[0].t).total_seconds(), 1e-3)
            out.append(Finding(
                rule_id="R002_high_flow_rate", category="dos", severity=cfg.severity,
                title=f"High flow rate towards {dst} ({w.value} flows in {cfg.window_s}s)",
                dedup_key=f"{device_id}:R002:{dst}",
                subject_ip=sources.most_common(1)[0][0] if sources else None,
                first_seen=w.events[0].t, last_seen=w.events[-1].t,
                evidence={
                    "destination_ip": dst, "flows": w.value, "threshold": cfg.flows,
                    "window_s": cfg.window_s, "flows_per_second": round(w.value / span, 2),
                    "distinct_sources": len(sources), "top_sources": sources.most_common(5),
                    "total_packets": sum(e.packets for e in w.events),
                    "total_bytes": sum(e.bytes for e in w.events), **_window_evidence(w),
                },
            ))
    return out


def rule_conn_failures(device_id: int, events: list[Ev], cfg) -> list[Finding]:
    out = []
    failed = [e for e in events if e.conn_state in ("failed", "reset")]
    for (src, dst, port), evs in _group(
        failed, lambda e: (e.src_ip, e.dst_ip, e.dst_port) if e.src_ip and e.dst_ip else None
    ).items():
        w = sliding_max(evs, cfg.window_s)
        if w.value >= cfg.failures:
            out.append(Finding(
                rule_id="R003_connection_failures", category="repeated_connection_failures",
                severity=cfg.severity,
                title=f"Repeated connection failures {src} -> {dst}:{port} ({w.value} in {cfg.window_s}s)",
                dedup_key=f"{device_id}:R003:{src}:{dst}:{port}", subject_ip=src,
                first_seen=w.events[0].t, last_seen=w.events[-1].t,
                evidence={
                    "source_ip": src, "destination_ip": dst, "destination_port": port,
                    "failures": w.value, "threshold": cfg.failures, "window_s": cfg.window_s,
                    "states": dict(Counter(e.conn_state for e in w.events)), **_window_evidence(w),
                    "note": "Flow metadata cannot confirm login failures; check authentication logs.",
                },
            ))
    return out


def rule_dns(device_id: int, events: list[Ev], cfg) -> list[Finding]:
    out = []
    dns = [e for e in events if e.dst_port == 53]
    for src, evs in _group(dns, lambda e: e.src_ip).items():
        w = sliding_max(evs, cfg.window_s)
        if w.value >= cfg.queries:
            out.append(Finding(
                rule_id="R004_dns_anomaly", category="dns_anomaly", severity=cfg.severity,
                title=f"High DNS query rate from {src} ({w.value} in {cfg.window_s}s)",
                dedup_key=f"{device_id}:R004:rate:{src}", subject_ip=src,
                first_seen=w.events[0].t, last_seen=w.events[-1].t,
                evidence={"source_ip": src, "indicator": "query_rate", "queries": w.value,
                          "threshold": cfg.queries, "window_s": cfg.window_s, **_window_evidence(w)},
            ))
        fails = [e for e in evs if e.dns_rcode and e.dns_rcode != "NOERROR"]
        if fails:
            wf = sliding_max(fails, cfg.window_s)
            if wf.value >= cfg.failures:
                out.append(Finding(
                    rule_id="R004_dns_anomaly", category="dns_anomaly", severity=cfg.severity,
                    title=f"Repeated DNS failures for {src} ({wf.value} in {cfg.window_s}s)",
                    dedup_key=f"{device_id}:R004:fail:{src}", subject_ip=src,
                    first_seen=wf.events[0].t, last_seen=wf.events[-1].t,
                    evidence={"source_ip": src, "indicator": "failure_rate", "failures": wf.value,
                              "threshold": cfg.failures, "window_s": cfg.window_s,
                              "rcodes": dict(Counter(e.dns_rcode for e in wf.events)),
                              **_window_evidence(wf)},
                ))
    return out


def rule_volume(device_id: int, events: list[Ev], cfg, end: datetime) -> list[Finding]:
    buckets = [0] * (cfg.history_buckets + 1)  # index 0 = current bucket
    for e in events:
        idx = int((end - e.t).total_seconds() // cfg.bucket_s)
        if 0 <= idx <= cfg.history_buckets:
            buckets[idx] += e.bytes
    current, history = buckets[0], buckets[1:]
    nonempty = [b for b in history if b > 0]
    if len(nonempty) < cfg.min_history:
        return []
    mean = sum(history) / len(history)
    std = math.sqrt(sum((b - mean) ** 2 for b in history) / len(history))
    threshold = mean + cfg.sigma * max(std, 1.0)
    if current <= threshold or current < cfg.min_bytes:
        return []
    return [Finding(
        rule_id="R005_volume_deviation", category="traffic_volume_anomaly", severity=cfg.severity,
        title=f"Traffic volume {current / 1e6:.1f} MB above device baseline",
        dedup_key=f"{device_id}:R005", first_seen=end - timedelta(seconds=cfg.bucket_s), last_seen=end,
        evidence={
            "current_bucket_bytes": current, "baseline_mean_bytes": round(mean),
            "baseline_std_bytes": round(std), "threshold_bytes": round(threshold),
            "sigma": cfg.sigma, "bucket_s": cfg.bucket_s, "history_buckets_used": len(history),
            "nonempty_history_buckets": len(nonempty),
        },
    )]


def evaluate(db: Session, device_id: int, batch_start: datetime, batch_end: datetime,
             cfg: RulesConfig, new_ids: set[int] | None = None) -> list[Finding]:
    windowed = [
        (cfg.R001_port_scan, rule_port_scan),
        (cfg.R002_high_flow_rate, rule_flow_rate),
        (cfg.R003_connection_failures, rule_conn_failures),
        (cfg.R004_dns_anomaly, rule_dns),
    ]
    enabled = [(c, fn) for c, fn in windowed if c.enabled]
    findings: list[Finding] = []
    if enabled:
        lookback = max(c.window_s for c, _ in enabled)
        events = fetch_window(db, device_id, batch_start - timedelta(seconds=lookback), batch_end, new_ids)
        for c, fn in enabled:
            findings.extend(fn(device_id, events, c))
    vc = cfg.R005_volume_deviation
    if vc.enabled:
        start = batch_end - timedelta(seconds=vc.bucket_s * (vc.history_buckets + 1))
        findings.extend(rule_volume(device_id, fetch_window(db, device_id, start, batch_end), vc, batch_end))
    return findings
