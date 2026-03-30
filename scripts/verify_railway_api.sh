#!/usr/bin/env bash
# Curl production (or any) API to confirm DB-backed routes return data after refresh.
# Usage: API_BASE_URL=https://your-backend.up.railway.app ./scripts/verify_railway_api.sh
set -euo pipefail
BASE="${API_BASE_URL:?Set API_BASE_URL to the backend origin, e.g. https://backend-….up.railway.app}"
BASE="${BASE%/}"

echo "== $BASE/health/db"
curl -sS "$BASE/health/db" | python3 -m json.tool

echo "== $BASE/api/debug/db-summary"
curl -sS "$BASE/api/debug/db-summary" | python3 -m json.tool

echo "== $BASE/api/stats (excerpt)"
curl -sS "$BASE/api/stats" | python3 -m json.tool

echo "== $BASE/api/plants?limit=1 (projection fields)"
curl -sS "$BASE/api/plants?limit=1&sort_by=stranded_gap" | python3 -m json.tool

echo "== $BASE/api/regions?limit=3"
curl -sS "$BASE/api/regions" | python3 -c "import json,sys; d=json.load(sys.stdin); print('regions', len(d.get('items',[])))"

echo "Done."
