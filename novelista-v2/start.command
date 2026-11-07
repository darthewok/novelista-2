#!/bin/bash
# If macOS says "cannot be opened", run: chmod +x start.command stop.command
cd "$(dirname "$0")"

pause_exit() { echo; read -r -p "Press Enter to close..." _; exit 1; }

# 1. find Python 3.11+
PY=""
for c in python3 python3.12 python3.13 python3.11; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "[novelista] Novelista needs Python 3.11 or newer. Install it from python.org, then run this again."
  pause_exit
fi
echo "[novelista] using $($PY --version)"

# 2. venv + dependencies
VPY="backend/.venv/bin/python"
MARK="backend/.venv/.installed"
NEED=0
if [ ! -x "$VPY" ]; then
  echo "[novelista] first-time setup: creating environment..."
  "$PY" -m venv backend/.venv || { echo "[novelista] setup failed."; pause_exit; }
  NEED=1
fi
[ -f "$MARK" ] || NEED=1
[ "$MARK" -nt backend/requirements.txt ] || NEED=1
if [ "$NEED" = 1 ]; then
  echo "[novelista] first-time setup: installing components, this takes a minute..."
  "$VPY" -m pip install -q --disable-pip-version-check -r backend/requirements.txt \
    || { echo "[novelista] setup failed. Check your internet connection and run this again."; pause_exit; }
  touch "$MARK"
fi

# 3. pick a port
mkdir -p .run
PORT=""
for p in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010; do
  if ! lsof -i :"$p" -sTCP:LISTEN >/dev/null 2>&1; then PORT=$p; break; fi
done
if [ -z "$PORT" ]; then
  echo "[novelista] ports 8000-8010 are all in use. Close other programs and try again."
  pause_exit
fi
echo "[novelista] using port $PORT"

# 4. start the server
echo "$PORT" > .run/port
( cd backend && nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > ../.run/server.log 2>&1 & echo $! > ../.run/pid )
echo "[novelista] starting server..."

# 5. wait for health
READY=0
for _ in $(seq 1 30); do
  if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/health")" = 200 ]; then READY=1; break; fi
  sleep 1
done
if [ "$READY" = 1 ]; then
  echo "[novelista] ready"
else
  echo "[novelista] did not respond in 30s - check .run/server.log"
  pause_exit
fi

# 6. open the browser
echo "[novelista] opening http://127.0.0.1:$PORT"
open "http://127.0.0.1:$PORT"
