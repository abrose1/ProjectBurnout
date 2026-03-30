#!/usr/bin/env bash
# Backend (FastAPI) + frontend (Vite). From repo root: ./scripts/dev.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
(
  cd "$ROOT/backend" && .venv/bin/uvicorn app.main:app --reload --port 8000
) &
PID_API=$!
(
  cd "$ROOT/frontend" && npm run dev
) &
PID_WEB=$!
trap 'kill "$PID_API" "$PID_WEB" 2>/dev/null; wait "$PID_API" "$PID_WEB" 2>/dev/null' EXIT INT TERM
wait "$PID_API" "$PID_WEB"
