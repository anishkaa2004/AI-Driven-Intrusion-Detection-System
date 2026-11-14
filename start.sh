#!/usr/bin/env bash
# Start AI-IDS (backend + dashboard) with one command.
#
#   ./start.sh            start backend and dashboard
#   ./start.sh --demo     also replay demo attack traffic every 30 s
#   ./start.sh --agent    also run the monitoring agent (device must be enrolled first)
#
# Press Ctrl+C to stop everything. Logs are written to ./logs/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
LOGS="$ROOT/logs"
BACKEND_PORT=8000
FRONTEND_PORT=5173

DEMO=0
AGENT=0
for arg in "$@"; do
  case "$arg" in
    --demo) DEMO=1 ;;
    --agent) AGENT=1 ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)"; exit 1 ;;
  esac
done

step() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mxx\033[0m %s\n' "$*"; exit 1; }

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

# ---------------------------------------------------------------- checks
command -v python3 >/dev/null || fail "python3 not found. Install Python 3.12+."
command -v npm >/dev/null || fail "npm not found. Install Node.js 20+."
for p in $BACKEND_PORT $FRONTEND_PORT; do
  if port_busy "$p"; then
    fail "Port $p is already in use. Stop whatever is using it (lsof -i :$p) and try again."
  fi
done

# ------------------------------------------------------- first-time setup
if [[ ! -x "$PY" ]]; then
  step "Creating Python virtual environment"
  python3 -m venv .venv
fi
if ! "$PY" -c "import fastapi, sklearn, psutil" 2>/dev/null; then
  step "Installing Python packages"
  "$PY" -m pip install -q -r backend/requirements.txt -r agent/requirements.txt
fi
if [[ ! -d frontend/node_modules ]]; then
  step "Installing dashboard packages (npm install)"
  (cd frontend && npm install --silent)
fi
if [[ ! -f backend/.env ]]; then
  step "Creating backend/.env with a new secret key"
  KEY="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(48))')"
  sed "s|^AIIDS_SECRET_KEY=.*|AIIDS_SECRET_KEY=$KEY|; s|^AIIDS_DATABASE_URL=.*|# AIIDS_DATABASE_URL defaults to backend/aiids.db|" \
    .env.example > backend/.env
  chmod 600 backend/.env
fi
if [[ ! -f ml/artifacts/manifest.json ]]; then
  step "Training the ML model (first run only, ~20 s)"
  "$PY" ml/src/train.py >/dev/null
fi
if [[ ! -f backend/.demo_credentials.json ]]; then
  step "Creating admin account and demo device"
  "$PY" scripts/seed_demo_data.py 2>&1 | grep -v SECRET_KEY || true
fi

# ------------------------------------------------------------- start
mkdir -p "$LOGS"
PIDS=()
# Kill a process and all of its descendants (npm -> sh -> vite, etc.).
kill_tree() {
  local child
  for child in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$child"; done
  kill -TERM "$1" 2>/dev/null || true
}
cleanup() {
  trap - INT TERM EXIT
  echo
  step "Stopping AI-IDS"
  for pid in "${PIDS[@]}"; do kill_tree "$pid"; done
  wait 2>/dev/null || true
  echo "Stopped."
}
trap cleanup INT TERM EXIT

step "Starting backend on http://127.0.0.1:$BACKEND_PORT  (log: logs/backend.log)"
(cd backend && exec "$ROOT/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port $BACKEND_PORT) \
  >"$LOGS/backend.log" 2>&1 &
PIDS+=($!)

for _ in $(seq 1 60); do
  curl -fs "http://127.0.0.1:$BACKEND_PORT/api/v1/health" >/dev/null 2>&1 && break
  kill -0 "${PIDS[0]}" 2>/dev/null || { tail -20 "$LOGS/backend.log"; fail "Backend failed to start"; }
  sleep 0.5
done
curl -fs "http://127.0.0.1:$BACKEND_PORT/api/v1/health" >/dev/null || fail "Backend did not become healthy (see logs/backend.log)"

step "Starting dashboard on http://localhost:$FRONTEND_PORT  (log: logs/frontend.log)"
(cd frontend && exec npm run dev -- --host 127.0.0.1 --port $FRONTEND_PORT --strictPort) \
  >"$LOGS/frontend.log" 2>&1 &
PIDS+=($!)

for _ in $(seq 1 60); do
  curl -fs "http://127.0.0.1:$FRONTEND_PORT" >/dev/null 2>&1 && break
  sleep 0.5
done

if [[ $DEMO == 1 ]]; then
  step "Replaying demo traffic every 30 s  (log: logs/replay.log)"
  "$PY" -u scripts/replay_flows.py --scenario all --loop 30 >"$LOGS/replay.log" 2>&1 &
  PIDS+=($!)
fi

if [[ $AGENT == 1 ]]; then
  if (cd agent && "$PY" -m agent status >/dev/null 2>&1); then
    step "Starting monitoring agent  (log: logs/agent.log)"
    (cd agent && exec "$PY" -u -m agent run) >"$LOGS/agent.log" 2>&1 &
    PIDS+=($!)
  else
    warn "Agent not enrolled yet: create a code on the Devices page, then run"
    warn "  cd agent && ../.venv/bin/python -m agent register --server http://127.0.0.1:$BACKEND_PORT --code XXXX-XXXX-XXXX"
  fi
fi

EMAIL="$("$PY" -c "import json; print(json.load(open('backend/.demo_credentials.json')).get('user', {}).get('email', 'your account'))" 2>/dev/null || echo "your account")"
cat <<EOF

  AI-IDS is running
  ─────────────────────────────────────────────
  Dashboard:  http://localhost:$FRONTEND_PORT
  API docs:   http://127.0.0.1:$BACKEND_PORT/api/docs
  Login:      $EMAIL
              password is in backend/.demo_credentials.json
  ─────────────────────────────────────────────
  Press Ctrl+C to stop.

EOF

command -v open >/dev/null && open "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1 || true

# Exit (and clean up) if any service dies.
while true; do
  for pid in "${PIDS[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      warn "A service stopped unexpectedly. Last log lines:"
      tail -n 15 "$LOGS"/*.log
      exit 1
    fi
  done
  sleep 2
done
