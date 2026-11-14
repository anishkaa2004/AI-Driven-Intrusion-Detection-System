"""AI-IDS monitoring agent CLI.

    python -m agent register --server http://127.0.0.1:8000 --code ABCD-EFGH-JKLM
    python -m agent run
    python -m agent status
    python -m agent forget

Run this only on a device you own or are explicitly authorized to monitor.
"""

import argparse
import logging
import platform
import signal
import socket
import sys
import time
from urllib.parse import urlparse

import httpx

from agent import config
from agent.collector import snapshot
from agent.flow_builder import FlowBuilder
from agent.health import HealthReporter
from agent.sender import CredentialRevoked, Sender

log = logging.getLogger("aiids.agent")

NOTICE = """\
AI-IDS agent - what is collected
  * Connection metadata from this computer's connection table: protocol,
    local/remote IP address and port, connection state, start time, duration.
  * Interface totals (bytes/packets sent and received) and the agent's own
    CPU/memory usage, sent as heartbeats.
NOT collected: packet payloads, browsing content, passwords, messages,
files, or process names. Data is sent only to the server you enrolled with.
Stop at any time with Ctrl+C; revoke the device from the dashboard to
invalidate its credential.
"""


def cmd_register(args) -> int:
    print(NOTICE)
    if not args.yes:
        answer = input("I own this device or am explicitly authorized to monitor it [y/N]: ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return 1
    server = args.server.rstrip("/")
    parsed = urlparse(server)
    if parsed.scheme not in ("http", "https"):
        print("Server must be an http(s) URL")
        return 1
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        print("WARNING: using plain HTTP to a non-local server; credentials are sent unencrypted.")
    try:
        r = httpx.post(f"{server}/api/v1/agents/register", timeout=10, verify=not args.insecure, json={
            "enrollment_code": args.code,
            "hostname": socket.gethostname()[:255],
            "platform": f"{platform.system()} {platform.release()}"[:50],
            "agent_version": config.AGENT_VERSION,
        })
    except httpx.HTTPError as exc:
        print(f"Could not reach server: {exc}")
        return 1
    if r.status_code != 200:
        print(f"Registration failed ({r.status_code}): {r.json().get('detail', r.text)}")
        return 1
    body = r.json()
    path = config.save(config.AgentConfig(server=server, device_id=body["device_id"],
                                          credential=body["credential"], display_name=body["display_name"],
                                          verify_tls=not args.insecure))
    print(f"Enrolled as device #{body['device_id']} ({body['display_name']}). Credential stored in {path}")
    return 0


def cmd_status(_args) -> int:
    cfg = config.load()
    if not cfg:
        print("Not enrolled. Run `python -m agent register ...` first.")
        return 1
    print(f"Server:  {cfg.server}\nDevice:  #{cfg.device_id} {cfg.display_name}\nConfig:  {config.CONFIG_FILE}")
    try:
        r = httpx.get(f"{cfg.server}/api/v1/health", timeout=5, verify=cfg.verify_tls)
        print(f"Backend: {r.json().get('status')}")
    except httpx.HTTPError as exc:
        print(f"Backend: unreachable ({exc.__class__.__name__})")
    return 0


def cmd_forget(_args) -> int:
    print("Local credential removed." if config.forget() else "No local credential found.")
    print("Also revoke the device in the dashboard so the credential cannot be reused.")
    return 0


def cmd_run(args) -> int:
    cfg = config.load()
    if not cfg:
        print("Not enrolled. Run `python -m agent register ...` first.")
        return 1
    print(NOTICE)
    srv = urlparse(cfg.server)
    exclude = set()
    try:
        port = srv.port or (443 if srv.scheme == "https" else 80)
        for info in socket.getaddrinfo(srv.hostname, port):
            exclude.add((info[4][0], port))
    except OSError:
        pass

    sender = Sender(cfg.server, cfg.credential, verify_tls=cfg.verify_tls)
    builder = FlowBuilder(max_flow_age_s=args.max_flow_age)
    health = HealthReporter()
    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    last_hb = 0.0
    collector_status = "starting"
    log.info("Agent running: device #%s -> %s (poll %ss)", cfg.device_id, cfg.server, args.interval)
    try:
        while not stop:
            now = time.time()
            if not sender.monitoring_paused:
                snap = snapshot(exclude)
                collector_status = f"{snap.mode}: {len(snap.connections)} connections"
                if snap.error:
                    collector_status = f"{snap.mode} ({snap.error})"[:120]
                flows = builder.update(snap, now)
                if flows:
                    sender.enqueue(flows)
            else:
                collector_status = "paused from dashboard"
                builder.flush()  # discard in-progress flows while paused
            if now - last_hb >= args.heartbeat:
                metrics = health.sample()
                metrics["collector_status"] = collector_status[:120]
                if sender.heartbeat(metrics):
                    last_hb = now
            accepted = sender.flush()
            if accepted:
                log.info("sent %d flows (queue %d)", accepted, len(sender.queue))
            time.sleep(args.interval)
        sender.enqueue(builder.flush())
        sender.flush(force=True)
    except CredentialRevoked as exc:
        log.error("%s. Stopping. Re-enroll if this device should be monitored.", exc)
        return 2
    finally:
        sender.close()
    log.info("Agent stopped")
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="python -m agent", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register", help="enroll this device using a dashboard enrollment code")
    r.add_argument("--server", required=True)
    r.add_argument("--code", required=True)
    r.add_argument("--yes", action="store_true", help="confirm authorization non-interactively")
    r.add_argument("--insecure", action="store_true", help="skip TLS verification (lab only)")
    run = sub.add_parser("run", help="start collecting and sending telemetry")
    run.add_argument("--interval", type=float, default=2.0, help="connection-table poll interval (s)")
    run.add_argument("--heartbeat", type=float, default=15.0, help="heartbeat interval (s)")
    run.add_argument("--max-flow-age", type=float, default=300.0,
                     help="report long-lived connections every N seconds")
    sub.add_parser("status", help="show enrollment and backend reachability")
    sub.add_parser("forget", help="delete the locally stored credential")
    args = ap.parse_args(argv)
    return {"register": cmd_register, "run": cmd_run, "status": cmd_status, "forget": cmd_forget}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
