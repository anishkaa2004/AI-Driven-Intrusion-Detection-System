"""Safe demonstration replay: sends synthetic or labelled dataset flows to the backend.

No network traffic is generated against any host; records are posted as
telemetry over the authenticated API and are flagged as demo data.

    python scripts/replay_flows.py --scenario all
    python scripts/replay_flows.py --scenario port_scan --scenario normal
    python scripts/replay_flows.py --loop 20             # keep the dashboard busy
    python scripts/replay_flows.py --csv ml/data/CICIDS2017/Wednesday.csv --limit 2000

Uses the demo device credential written by seed_demo_data.py, or pass
--credential and --server explicitly.
"""

import argparse
import json
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml" / "src"))
sys.path.insert(0, str(ROOT / "backend"))

import synthetic  # noqa: E402

CRED_FILE = ROOT / "backend" / ".demo_credentials.json"


def csv_events(path: Path, limit: int, seed: int) -> list[dict]:
    """Map CICIDS2017 rows to flow-v1 events with documentation-range IPs."""
    import pandas as pd
    import prepare_data

    raw = pd.read_csv(path, encoding="latin-1", low_memory=False, nrows=limit * 5)
    raw.columns = [c.strip() for c in raw.columns]
    df = raw[list(prepare_data.CICIDS_COLUMNS)].rename(columns=prepare_data.CICIDS_COLUMNS)
    df["flow_duration"] = pd.to_numeric(df["flow_duration"], errors="coerce") / 1e6
    df["label"] = df["label"].map(prepare_data.map_cicids_label)
    df, _ = prepare_data.clean(df, min_class_rows=1)
    df = df.sample(min(limit, len(df)), random_state=seed)
    rng = random.Random(seed)
    start = datetime.now(timezone.utc) - timedelta(seconds=len(df) * 0.05)
    out = []
    for i, row in enumerate(df.itertuples()):
        out.append({
            "event_id": f"csv-{uuid.uuid4().hex}",
            "event_time": (start + timedelta(seconds=i * 0.05)).isoformat().replace("+00:00", "Z"),
            "protocol": "TCP",
            "src_ip": f"198.51.100.{rng.randint(1, 254)}", "dst_ip": "192.0.2.10",
            "src_port": rng.randint(1024, 65535), "dst_port": int(row.dst_port),
            "flow_duration": float(row.flow_duration),
            "packets_in": int(row.packets_in), "packets_out": int(row.packets_out),
            "bytes_in": int(row.bytes_in), "bytes_out": int(row.bytes_out),
        })
    return out


def post(client: httpx.Client, events: list[dict], batch: int) -> dict:
    totals = {"accepted": 0, "duplicates": 0, "rejected": 0, "alerts_created": 0, "alerts_updated": 0}
    for i in range(0, len(events), batch):
        r = client.post("/api/v1/telemetry/batch", json={
            "source": "replay", "collector": "replay", "agent_version": "replay-0.1",
            "events": events[i:i + batch]})
        if r.status_code != 200:
            sys.exit(f"Server returned {r.status_code}: {r.text[:300]}")
        b = r.json()
        for k in totals:
            totals[k] += len(b[k]) if k == "rejected" else b[k]
    return totals


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", action="append", choices=[*synthetic.SCENARIOS, "all"])
    ap.add_argument("--csv", type=Path, help="CICIDS2017 CSV file to replay")
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--server")
    ap.add_argument("--credential", help="device credential (default: from seed file)")
    ap.add_argument("--batch", type=int, default=200)
    ap.add_argument("--loop", type=float, default=0, help="repeat every N seconds")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    creds = json.loads(CRED_FILE.read_text()).get("device", {}) if CRED_FILE.is_file() else {}
    credential = args.credential or creds.get("credential")
    server = args.server or creds.get("server", "http://127.0.0.1:8000")
    if not credential:
        sys.exit("No device credential. Run scripts/seed_demo_data.py or pass --credential.")
    client = httpx.Client(base_url=server, timeout=30, headers={"Authorization": f"Bearer {credential}"})

    names = args.scenario or ["all"]
    if "all" in names:
        names = list(synthetic.SCENARIOS)
    rnd = 0
    while True:
        rnd += 1
        if args.csv:
            events = csv_events(args.csv, args.limit, args.seed + rnd)
            print(f"[{rnd}] csv {args.csv.name}: {post(client, events, args.batch)}")
        else:
            for name in names:
                start = datetime.now(timezone.utc) - timedelta(seconds=60)
                kwargs = {"seed": args.seed + rnd * 31 + sum(map(ord, name))}
                events = synthetic.SCENARIOS[name](start, **kwargs)
                print(f"[{rnd}] {name:14s} {len(events):4d} flows -> {post(client, events, args.batch)}")
        if not args.loop:
            break
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
