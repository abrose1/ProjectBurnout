#!/usr/bin/env bash
# Run full EIA → Postgres refresh: plants → metrics → AEO inputs → plant_projections.
# Requires backend/.venv and DATABASE_URL. From repo root: ./scripts/refresh_eia_pipeline.sh
set -euo pipefail
cd "$(dirname "$0")/../backend"
PY="${PY:-.venv/bin/python}"
$PY -m app.services.data_refresh
$PY -m app.services.metrics_refresh
$PY -m app.services.aeo_refresh
$PY -m app.services.projection
