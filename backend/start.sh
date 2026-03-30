#!/usr/bin/env sh
set -e
cd "$(dirname "$0")" || exit 1
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
