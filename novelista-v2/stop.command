#!/bin/bash
# If macOS says "cannot be opened", run: chmod +x start.command stop.command
cd "$(dirname "$0")"

PORT=8000
[ -f .run/port ] && PORT=$(cat .run/port)

echo "[novelista] stopping server..."
if [ -f .run/pid ]; then
  PID=$(cat .run/pid)
  kill "$PID" 2>/dev/null
  sleep 2
  kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
fi

# fallback: anything still listening on the port
for p in $(lsof -ti :"$PORT" -sTCP:LISTEN 2>/dev/null); do kill -9 "$p" 2>/dev/null; done

if [ "$1" = "--full" ]; then
  echo "[novelista] stopping Ollama..."
  pkill ollama 2>/dev/null
  echo "[novelista] If you use LM Studio, close it from its own window."
fi

rm -f .run/pid .run/port
echo "[novelista] stopped"
