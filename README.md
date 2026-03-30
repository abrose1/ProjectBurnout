# Stranded Assets

Early-warning tooling for US coal and gas power plants at risk of stranding before retirement. Product direction, schema, and build order live in **[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)**. This README is **how to run the repo locally** (Postgres, env, secrets).

**Disclaimer:** Data comes from the US Energy Information Administration. Projections in the app are **illustrative**, not investment advice or a financial forecast. See **Projection Caveats** in the implementation plan for modeling limits.

## Prerequisites

- Python 3.11+ (project uses a `backend/.venv`)
- **Postgres 16 via Homebrew** on macOS (see below)
- [EIA Open Data API key](https://www.eia.gov/opendata/) for data refresh scripts

## Environment variables

1. Copy **`backend/.env.example`** → **`backend/.env`**.
2. Set secrets only in **`backend/.env`**. **Do not commit `.env`** or paste API keys into issues, PRs, or the implementation plan.
3. If a key was ever committed, rotate it in the provider’s portal (EIA, Anthropic, etc.).

| Variable | Purpose |
|----------|---------|
| **`DATABASE_URL`** | Required. Use your **macOS login name** as the Postgres user (see [Postgres (Homebrew)](#postgres-homebrew)). |
| **`EIA_API_KEY`** | Required for EIA refresh modules and `GET /api/debug/eia-ping`. |
| **`EIA_AEO_RELEASE`** | Optional; default `2025` — must match an EIA AEO API path you use. |
| **`ANTHROPIC_API_KEY`** | Required for **`POST /api/query`** (Claude NL → structured list filters). |
| **`CORS_ORIGINS`** | Comma-separated origins for the API (e.g. `http://localhost:5173`). |

## Postgres (Homebrew)

Local development assumes **Homebrew** Postgres on **`localhost:5432`**.

1. Install and start the service, e.g. `brew install postgresql@16`, `brew services start postgresql@16` (exact formula may vary).
2. Create the database once: `createdb stranded_assets`
3. Set **`DATABASE_URL`** in **`backend/.env`** to:

   `postgresql://YOUR_MACOS_USERNAME@localhost:5432/stranded_assets`

   Replace **`YOUR_MACOS_USERNAME`** with the output of `whoami` (often no password for local TCP). **Do not** use `postgres` / `postgres` as the user — that is a different setup and usually fails on Homebrew with **`FATAL: role "postgres" does not exist`**.

**`backend/.env.example`** shows the same shape; adjust the username if yours differs.

## Backend setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- DB health: `GET /health/db` (requires a working `DATABASE_URL`)

## Frontend (Vite)

From `frontend/`: copy **`.env.example`** → **`.env`**, set **`VITE_API_URL=http://localhost:8000`**, then `npm install` and `npm run dev` (default port **5173**). Backend **`CORS_ORIGINS`** should include `http://localhost:5173` (see **`backend/.env.example`**).

## Data refresh (EIA → database)

Order matters: **inventory → metrics → AEO → projection**. From repo root (with `backend/.venv` and `DATABASE_URL` set):

```bash
./scripts/refresh_eia_pipeline.sh
```

Or run the Python modules in order from `backend/` (see **IMPLEMENTATION_PLAN.md**). `aeo_refresh` is heavy; EIA may return **429** if you hammer it.

## Cursor / agents

- **`.cursor/rules/avoid-terminal-logs.mdc`** — avoid reading Cursor `terminals/*.txt` unless debugging or the user asks; traces often include huge HTTP URLs and accidental secrets.

## Documentation map

| Doc | Contents |
|-----|----------|
| **This README** | Local setup, env, Postgres, run commands |
| **[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)** | Architecture, schema, API design, UI, build order, deployment |
