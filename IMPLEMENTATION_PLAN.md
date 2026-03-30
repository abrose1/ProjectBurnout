# Burnout — Implementation Plan

## Project Overview

**In-product name:** **Burnout** (browser tab, masthead). A web dashboard that identifies which US fossil fuel power plants are most at risk of becoming economically unviable before their projected retirement. The headline metric is the **stranded gap** — the difference between when a plant is projected to retire vs. when it's projected to become unprofitable. Users interact via a natural language query bar that filters and explores a ranked table of plants, with a map view planned for iteration 2. Built on EIA data, exposed through a standalone MCP server, deployed on Railway.

**Two deliverables:**
1. The live web application (Railway-hosted dashboard)
2. A standalone MCP server for EIA energy data (separate GitHub repo, reusable by others)

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Railway Project                                     │
│                                                      │
│  ┌──────────────┐   ┌──────────────┐  ┌──────────┐  │
│  │   Frontend    │──▶│   Backend    │──▶│ Postgres │  │
│  │  React/Vite   │   │  FastAPI     │   │          │  │
│  └──────────────┘   └──────┬───────┘  └──────────┘  │
│                            │                         │
│                     ┌──────┴───────┐                 │
│                     │  MCP Module  │                 │
│                     │ (EIA wrapper)│                 │
│                     └──────┬───────┘                 │
│                            │                         │
└────────────────────────────┼─────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │   EIA Open Data  │
                    │   API (v2)       │
                    └─────────────────┘
```

**Three Railway services:**
- **Frontend**: React (Vite), serves static build
- **Backend (web-service)**: Python FastAPI — hosts REST API, MCP endpoint, Claude API integration, projection engine
- **Postgres**: Persistent data store for cached EIA data and computed projections

The MCP module lives inside the backend service but is also packaged as a standalone repo. The backend exposes it at an MCP-compatible endpoint so external clients (Claude Desktop, other agents) can connect.

---

## Local development (first)

Develop and run the stack on your machine first; **deploy to Railway in Phase 6** when the app is stable.

**Operational details (env vars, Homebrew Postgres, secrets, run commands, data refresh, Cursor hygiene):** see **[README.md](README.md)**. This plan stays focused on architecture and product design; avoid duplicating local-setup prose here.

| Piece | Local approach |
|-------|------------------|
| Postgres | **Homebrew** on macOS — see **README.md** (`createdb`, `DATABASE_URL` with your macOS username) |
| Backend | From `backend/`: `uvicorn app.main:app --reload --port 8000`. Copy `backend/.env.example` → `backend/.env` — see **README.md** |
| Frontend | Vite dev server, `VITE_API_URL=http://localhost:8000` |

### Backend — implemented so far (dev scaffolding)

The following exists in `backend/` and matches this plan’s schema / EIA integration direction; **product REST routes** (`/api/plants`, `/api/regions`, `/api/stats`) are implemented — see `app/routes/plants.py`, `regions.py`, `stats.py`, **`app/api_schemas.py`**.

| Item | Notes |
|------|--------|
| **Postgres (local)** | **Homebrew** — **`README.md`**. Database name **`stranded_assets`**, port **`5432`**, OS username in URL. |
| **`DATABASE_URL`** | **`postgresql://...` in `.env`** → app uses **`postgresql+psycopg://...`** (psycopg v3). See **README.md** and **`backend/.env.example`**; never commit secrets. |
| **ORM + migrations** | SQLAlchemy models in `app/models/schemas.py`, session/helpers in `app/models/database.py`. **Alembic** config: `backend/alembic.ini`, migrations under `backend/alembic/versions/`. From `backend/`: `.venv/bin/alembic upgrade head` (after Postgres is up). |
| **EIA client** | `app/services/eia_client.py` — v2 HTTP client, pagination, optional **`start` / `end`** (`YYYY-MM` monthly or `YYYY` annual) on `fetch_data` / `iter_data`, `get_latest_inventory_period()`, `get_latest_facility_fuel_annual_year()`, `ping_operating_generators()` for a cheap connectivity check. |
| **Phase 1 plant refresh** | `app/services/data_refresh.py` — pulls **`electricity/operating-generator-capacity`** (coal + gas facets, status OP) for the latest inventory month, aggregates to **plant** (`stateid`–`plantid`), keeps **≥ 100 MW** nameplate, sets **`projected_retirement_year`** (planned vs commission + 45/30), upserts **`plants`**, prunes plants no longer in the snapshot, logs to **`refresh_log`**. Run: `cd backend && .venv/bin/python -m app.services.data_refresh`. |
| **Phase 1b plant metrics** | `app/services/metrics_refresh.py` — **`electricity/facility-fuel`** annual, last **10** calendar years, **`fuel2002=ALL`** plant totals; matches **`plant_id`** (`ST-plantCode`) to existing **`plants`** only; derives **capacity factor**, **heat rate** (MMBtu/MWh), **fuel_cost_per_mwh** proxy (heat rate × rough coal/gas USD per MMBtu until AEO). Batched **`plantCode`** facets per state. Run: `cd backend && .venv/bin/python -m app.services.metrics_refresh`. |
| **AEO projection inputs** | `app/services/aeo_refresh.py` — EIA **`/aeo/{release}/`** (default **`EIA_AEO_RELEASE`** / `eia_aeo_release` = **2025**), scenario **`ref2025`**. Fills **`fuel_price_projections`** (national nominal coal + gas $/MMBtu, table 3), **`regional_price_projections`** (EMM **wholesale generation** price, nominal cents/kWh → $/MWh, table 62), **`regional_renewables`** (wind + solar vs **total** electric-power capacity, tables **62** + **67**). Regional PK **`emm_region`** stores **EIA EMM region names** (e.g. `PJM / East`) — map plants in **`projection.py`**. **`_clip()`** on region labels avoids bogus trailing spaces in PKs. Throttle between regions to reduce **429** from EIA. Run: `cd backend && .venv/bin/python -m app.services.aeo_refresh`. |
| **Projection engine** | `app/services/projection.py` — unified economic model (AEO fuel + wholesale, metrics heat rate, O&M, dispatch from regional renewable share, 2 consecutive loss years → stranded year). Resolves **`plants.emm_region`** from state → EMM substring map against distinct **`regional_price_projections.emm_region`** when unset; national average wholesale + **dispatch factor 1.0** when no EMM. Upserts **`plant_projections`**. Run: `cd backend && .venv/bin/python -m app.services.projection`. |
| **REST API** | **`GET /api/plants`** — sorting + pagination + filters (fuel / multi-`fuel_types`, single or multi-`states`, `emm_region`, stranded gap min/max, text `ILIKE` fields, year and numeric bounds on plant + projection + latest CF; see **`/docs`**), **`POST /api/query`** (NL → `filters_applied` + message), **`GET /api/plants/{plant_id}`**, **`GET /api/regions`**, **`GET /api/stats`** — Pydantic models in **`app/api_schemas.py`**, routers in **`app/main.py`**. |
| **REST API — plant filter** | List, detail, stats, and regions **exclude** plants with **no** Form 923 **`plant_metrics`** rows (implementation: **`app/plant_visibility.py`**). |
| **Sanity check (after refresh)** | Spot-check **`plant_projections`** vs expectations (e.g. old coal, gaps vs retirement fields). |
| **Debug / health URLs** | `GET /api/debug/eia-ping` — EIA metadata + 2 sample rows (no DB). `GET /api/debug/db-ping` and `GET /health/db` — `SELECT 1` when `DATABASE_URL` works. Interactive API docs: `/docs`. |
| **Python env** | From `backend/`: `python3 -m venv .venv` then `pip install -r requirements.txt`. |

**Recommended data refresh order (manual):**  
1. `python -m app.services.data_refresh` — plants (inventory)  
2. `python -m app.services.metrics_refresh` — `plant_metrics` (needs existing `plants`)  
3. `python -m app.services.aeo_refresh` — AEO tables (`fuel_price_projections`, `regional_price_projections`, `regional_renewables`)  
4. `python -m app.services.projection` — `plant_projections` (+ fills `plants.emm_region` when mapped)  

`metrics_refresh` and `aeo_refresh` are independent of each other; both are required before the projection engine can use AEO prices + historical heat rate / CF.

### Full refresh pipeline (script / cron) — purpose and shape

**Purpose:** Run the four jobs in a fixed order so the database stays internally consistent: **inventory and retirement assumptions** (`plants`) → **historical operations for heat rate / CF** (`plant_metrics`) → **AEO macro inputs** (`fuel_price_projections`, `regional_price_projections`, `regional_renewables`) → **derived stranded economics** (`plant_projections`, and `plants.emm_region` backfill from projection). Without a pipeline, someone could run steps out of order or forget `projection` after upstream data changes, and the API or UI would show **stale or inconsistent** stranded years and gaps.

A **shell script** or **cron** entry is not required for local dev (manual commands are fine). It becomes useful for **repeatability** (same order every time), **automation** (weekly/monthly after EIA updates), and **ops** (single exit code, logging, alerts on failure). Production options sketched in the plan include **Railway cron** or an **admin-triggered HTTP refresh** (Phase 6); those wrap the same four Python modules.

**Local script:** `scripts/refresh_eia_pipeline.sh` — run from repo root: `./scripts/refresh_eia_pipeline.sh` (or `bash scripts/refresh_eia_pipeline.sh`). Override interpreter with `PY=/path/to/python ./scripts/refresh_eia_pipeline.sh` if needed. Fails fast on first error.

**Example — weekly cron** (adjust paths; run when EIA data is typically stable, e.g. Sunday 06:00 local):

```
0 6 * * 0 /path/to/StrandedAssets/scripts/refresh_eia_pipeline.sh >> /var/log/stranded-refresh.log 2>&1
```

**Operational notes:** `aeo_refresh` is heavy (many regional API calls); respect EIA rate limits and keep throttling as implemented. If any step fails, **do not** assume downstream tables are valid until the failed step is fixed and the pipeline is re-run from that step forward (or from the top for simplicity).

---

## Project Structure

```
stranded-asset-warning/          ← monorepo, one Railway project
├── docker-compose.yml             ← optional Postgres image (not the documented local path; README uses Homebrew)
├── scripts/
│   └── refresh_eia_pipeline.sh      ← full EIA refresh pipeline (see “Full refresh pipeline”)
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   ├── components/
│   │   │   ├── PlantTable.jsx         ← ranked list; server-side sort + filters + load more
│   │   │   ├── HeroStats.jsx          ← top-level summary metrics
│   │   │   ├── Layout.jsx             ← page shell + main
│   │   │   ├── Masthead.jsx           ← title, headline, lede (reorder freely)
│   │   │   ├── ErrorBanner.jsx        ← API error display
│   │   │   ├── QueryBar.jsx           ← NL search + interpretation (embedded in card)
│   │   │   ├── PlantDetailModal.jsx   ← plant detail modal (GET /api/plants/{id})
│   │   │   ├── MetricSparkline.jsx    ← capacity-factor sparkline in detail modal
│   │   │   └── MapView.jsx            ← post-sprint / Iteration 2: leaflet map
│   │   ├── hooks/
│   │   │   ├── usePlants.js           ← plant list: query params, pagination
│   │   │   ├── useRegions.js          ← region list for filters
│   │   │   ├── useStats.js            ← dashboard stats
│   │   │   ├── usePlantDetail.js      ← single-plant fetch for modal
│   │   │   └── useQuery.js            ← POST /api/query (`useNlQuery`)
│   │   ├── utils/
│   │   │   ├── api.js                 ← fetch wrapper + `VITE_API_URL` (array query params)
│   │   │   ├── plantFilters.js        ← filter state, `apiFiltersToState`, `buildPlantQueryParams`
│   │   │   └── formatError.js         ← user-facing API errors
│   │   └── styles/
│   │       └── global.css
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
│
├── backend/
│   ├── alembic/                   ← Alembic migrations
│   ├── alembic.ini
│   ├── app/
│   │   ├── main.py                    ← FastAPI app, CORS, startup
│   │   ├── api_schemas.py             ← Pydantic models for REST responses
│   │   ├── routes/
│   │   │   ├── plants.py              ← REST: list (`sort_by`, filters, pagination), detail
│   │   │   ├── regions.py
│   │   │   ├── stats.py
│   │   │   ├── health.py
│   │   │   ├── debug.py
│   │   │   ├── query.py               ← POST /api/query
│   │   │   └── admin.py               ← Phase 6: manual data refresh trigger
│   │   ├── services/
│   │   │   ├── eia_client.py          ← HTTP client for EIA API v2
│   │   │   ├── data_refresh.py        ← operating-generator inventory → `plants`
│   │   │   ├── metrics_refresh.py     ← facility-fuel → `plant_metrics`
│   │   │   ├── aeo_refresh.py         ← AEO tables (fuel, regional prices, renewables)
│   │   │   ├── projection.py          ← stranded year projection → `plant_projections`
│   │   │   └── nl_query.py            ← Claude `list_plants` tool + guardrails
│   │   ├── mcp/                       ← Phase 5: MCP tools + server (not in repo yet)
│   │   │   ├── server.py
│   │   │   ├── tools.py
│   │   │   └── __init__.py
│   │   ├── models/
│   │   │   ├── database.py            ← SQLAlchemy setup, session management
│   │   │   └── schemas.py             ← DB models: Plant, Projection, RefreshLog
│   │   └── config.py                  ← env vars: EIA_API_KEY, DATABASE_URL, ANTHROPIC_API_KEY
│   └── requirements.txt
│
├── backend/railway.toml               ← backend service: build + start (see Railway section)
├── frontend/railway.toml + Dockerfile ← frontend: DOCKERFILE builder, Node 23
└── README.md                          ← local setup: env, Postgres, run backend (not duplicated here)

# Separate repository (not part of the monorepo):
mcp-server-eia/                        ← SEPARATE GIT REPO, developed independently
├── src/
│   ├── server.py
│   ├── tools.py                       ← same tools, no DB dependency
│   └── eia_client.py                  ← same EIA client
├── README.md                          ← usage docs for others
├── requirements.txt
└── pyproject.toml
```

The standalone `mcp-server-eia/` repo is a separate GitHub repository — it is NOT a subdirectory of the monorepo. It shares the same tool logic and EIA client code but has no database dependency. During development, build the MCP tools inside `backend/app/mcp/` first, then copy the relevant code to the standalone repo in Phase 5.

---

## Design System — "Clean Energy, Not Clean Slop"

### Anti-Patterns to Avoid (AI Slop Tells)
These are the hallmarks of AI-generated UI that make audiences immediately think "ChatGPT built this." We explicitly avoid all of them:

- **NO purple/indigo gradients** — the #1 giveaway, inherited from Tailwind's bg-indigo-500 default demos
- **NO Inter, Roboto, Open Sans, or Arial** — the default AI font stack
- **NO three equal cards in a grid** — the "feature showcase" layout every AI landing page produces
- **NO glassmorphism / frosted blur effects** — the 2023 AI demo aesthetic
- **NO gradient text on headings** — especially purple-to-blue
- **NO cyan/neon accents on dark backgrounds** — the "sci-fi dashboard" look
- **NO generic blob shapes** in backgrounds
- **NO cards nested inside cards inside cards** with uniform border-radius

### What “AI Slop” Usually Is (and What It Isn’t)
Industry and design writing (2025–2026) converges on a few explanations for the generic “AI-built” look — useful so we **avoid the tells** without accidentally chasing a **dated** minimalism:

- **Distributional convergence:** Models and tools repeat the same training priors (popular component libraries, Tailwind demos, Dribbble patterns), so outputs cluster on the same gradients, fonts, and layouts.
- **Default stacks:** Purple/indigo, `Inter`, glassmorphism, and three equal feature cards are overrepresented in docs and tutorials — not because they are “wrong,” but because they are **universal defaults**.
- **Decoration over function:** Orbs, heavy scroll animations, and gradient heroes often signal “template” when they do not clarify data or tasks. The fix is **purpose-bound** chrome, not zero personality.
- **What slop often still does OK:** Legible type scale, spacing rhythm, and clear hierarchy. Stripping those in the name of “not AI” can read as **unfinished** rather than editorial.

### Corners & Radii (Anti-Slop Without Looking Stuck in 2023)
Avoiding **uniform rounded card stacks** is not the same as **banning curvature**. A credible climate product in 2026 can mix:

- **Sharp or nearly square** masthead, rules, and table shells (editorial / magazine-like, not a trading terminal).
- **Small, consistent radii** on buttons, inputs, and tags (4px-ish), with **one** radius scale — not every surface at `rounded-2xl`.
- **Asymmetry** (offset columns, full-bleed dividers, weight contrast) reads “designed”; **symmetric rounded everything** reads “template.”

If the UI feels flat or timid, fix it with **structure and contrast** (typography weight, rules, optional accent colors below) — not with purple gradients or glass cards.

### Design Direction: "Climate Intelligence" (broad audience, not "old energy")
**Who it’s for:** People who care about the energy transition — advocates, journalists, policy-curious readers, and analysts — not only power users who live in terminals. The product should feel **clear and inviting**, not like a Bloomberg view, a government PDF, or a legacy fossil brand site.

**Voice:** A **modern AI × climate** company talking honestly about **coal and gas exposure** and stranded risk: confident, legible, forward-looking. Fun where it helps comprehension; never flippant about the stakes.

**What we don’t look like:**
- **Not “the old guys”** — we avoid visual language associated with traditional fossil majors (oil-barrel browns as hero identity, greasy gradients, heritage oil branding). We cover fossil fuels as **subject matter**; we don’t **dress like** the industry.
- **Not dreary “data tool”** — information can be dense when needed, but the rhythm should feel **editorial** (story → context → explore), not sterile dashboard gridding for its own sake.

**Palette note:** Greens and teal read as **climate / clarity / transition**; terracotta reads as **heat / burnout / urgency** — not petroleum earth tones chosen to echo fuel itself.

### Typography
- **Display / Numbers**: `DM Mono` or `JetBrains Mono` — gives data a distinctive, technical feel without being cold. Numbers in tables should feel precise and readable.
- **Headlines**: `Outfit` — geometric sans-serif with personality, modern but warm. NOT a safe default.
- **Body**: `Outfit` at regular weight — clean reading for UI text.
- Load from Google Fonts. Two families max to keep it fast.

### Color Palette
Canonical tokens in `frontend/src/styles/global.css` — summary:

```
Primary (green family — clarity, positive states, transition cues):
  --color-forest:         #1B4332    ← emphasis, hover on links, some headings
  --color-emerald:        #2D6A4F    ← primary buttons, pressed controls, table row hover tint
  --color-mint:           #52B788    ← positive / sparkline fill, focus rings

Brand & accents (reduces “all green” without purple/indigo slop):
  --color-terracotta:     #B85C3E    ← “Burnout” wordmark
  --color-deep-teal:      #1A535C    ← chart/sparkline stroke, modal top stripe (teal end); links use emerald
  --color-slate:          #2C4A52    ← secondary headings in chrome, filter chips, borders (with transparency)

Neutrals (green-tinted canvas — not flat white):
  --color-mist / --color-parchment     #EEF4F1  ← page background (soft green-gray mist)
  --color-surface:        #FAFCFB     ← cards, table surfaces
  --color-surface-veil:   #F3F8F5    ← table header band, chip backgrounds
  --color-sand:           #E2EBE6    ← hover chips, alt rows
  --color-charcoal:       #2D2D2D    ← primary text
  --color-stone:          #5C6670    ← secondary / muted text

Data encoding:
  --color-coal:           #D97706    ← coal fuel dot
  --color-gas:            #3B82F6    ← gas fuel dot
  --color-risk-low … critical   ← stranded gap text ramp (unchanged semantics)
```

**Usage:** Terracotta is **brand heat** (title + key rules) — burnout, not petro brown. **Emerald** is the default **link** color (inviting, climate-positive). Deep teal appears in **data viz** (e.g. sparkline) and **modal accent** stripes. Forest-tinted **borders** keep the canvas warm. Green stays for **actions** (buttons) and **risk / fuel semantics**.

### Layout Principles
- **Left-aligned content** — feels editorial and intentional, avoids the "everything centered" AI look
- **Information-rich tables** — tight enough to compare plants side by side, but paced for **scanning** (journalists, advocates, curious readers) — not a trader terminal or fake “financial terminal” cosplay
- **Asymmetric composition** — sidebar/main content splits don't have to be 50/50
- **Soft mist background** — green-gray off-white (`#EEF4F1`) keeps the page warm and readable; avoids sterile pure white without going gloomy
- **Hero metrics are fine** when they show genuinely useful summary numbers — just don't make them decorative

### Backgrounds & Texture
- Subtle noise/grain overlay on the background (CSS: very low opacity)
- Optional: faint topographic contour pattern at extreme low opacity — references geography/land use without being heavy
- Avoid **decorative** gradient blobs and meaningless color washes. **Flat editorial bands** (e.g. query strip, full-width hairlines) are fine — they structure the page; they are not the same as hero gradient slop

### Score & Risk Visualization
- **Stranded gap** uses **text color only** (muted → forest/emerald → amber → red tones aligned with the palette; UI chrome uses slate/deep-teal elsewhere) — **no** row side bars or full-row fill; other columns stay neutral
- Fuel type indicated by a small colored dot or tag (amber for coal, blue for gas) — not full row highlighting

### Mobile Approach
- Table becomes a card list (one plant per card, key metrics visible)
- QueryBar stays fixed at top
- Hero stats stack vertically
- Map (v2) becomes a tappable full-width preview

---

## Database Schema (Postgres)

**Regional keys (EMM, not NERC):** AEO wholesale and capacity series are keyed by **EIA electricity market module (EMM)** region names (e.g. `PJM / East`, `Texas`). The schema uses **`emm_region`** for that axis. NERC letter codes from Form 860 are a different taxonomy; if we ever surface them, add a separate column — do not overload `emm_region`.

### Table: `plants`
Stores plant metadata from EIA-860 generator inventory data.

| Column              | Type        | Notes                                      |
|---------------------|-------------|--------------------------------------------|
| `plant_id`          | VARCHAR PK  | EIA plant code                             |
| `plant_name`        | VARCHAR     |                                            |
| `state`             | VARCHAR(2)  |                                            |
| `county`            | VARCHAR     |                                            |
| `latitude`          | FLOAT       | For future map view                        |
| `longitude`         | FLOAT       | For future map view                        |
| `emm_region`        | VARCHAR     | EIA EMM region label for projections (e.g. `PJM / East`); populated when plant→EMM mapping exists |
| `balancing_auth`    | VARCHAR     |                                            |
| `primary_fuel`      | VARCHAR     | coal or gas                                |
| `nameplate_mw`      | FLOAT       | Total nameplate capacity                   |
| `commission_year`   | INTEGER     | Year of initial operation                  |
| `operator_name`     | VARCHAR     |                                            |
| `status`            | VARCHAR     | operating, standby, etc.                   |
| `planned_retirement_year` | INTEGER | From EIA-860 if available, NULL otherwise |
| `projected_retirement_year` | INTEGER | Computed at ingestion: `planned_retirement_year` if available, else `commission_year + expected_life`. This is the authoritative retirement year used across the app. |
| `updated_at`        | TIMESTAMP   |                                            |

**Expected life defaults** (used when `planned_retirement_year` is NULL):
- Coal: 45 years from commissioning
- Gas: 30 years from commissioning

### Table: `plant_metrics`
Stores computed operational metrics from EIA Form 923 data.

| Column                  | Type    | Notes                                     |
|-------------------------|---------|-------------------------------------------|
| `plant_id`              | VARCHAR FK |                                         |
| `year`                  | INTEGER |                                            |
| `net_generation_mwh`    | FLOAT   | Annual net generation                      |
| `capacity_factor`       | FLOAT   | Computed: generation / (capacity × 8760)   |
| `fuel_consumption_mmbtu`| FLOAT   | Annual fuel consumed                       |
| `fuel_cost_per_mwh`     | FLOAT   | Computed fuel cost proxy                   |
| `heat_rate`             | FLOAT   | Computed: fuel_consumption / net_generation (MMBtu/MWh) |
| `updated_at`            | TIMESTAMP |                                          |

### Table: `regional_renewables`
Renewable penetration by **EMM** region (AEO), used in projection model.

| Column              | Type    | Notes                                       |
|---------------------|---------|---------------------------------------------|
| `emm_region`        | VARCHAR PK | EIA EMM region name (matches AEO facets)   |
| `year`              | INTEGER PK |                                           |
| `total_capacity_mw` | FLOAT   | Total generation capacity in region          |
| `renewable_capacity_mw` | FLOAT | Wind + solar capacity                     |
| `renewable_pct`     | FLOAT   | Computed: renewable / total                  |
| `updated_at`        | TIMESTAMP |                                            |

### Table: `fuel_price_projections`
EIA Annual Energy Outlook projected fuel prices, used for stranded year projection.

| Column              | Type    | Notes                                       |
|---------------------|---------|---------------------------------------------|
| `fuel_type`         | VARCHAR PK | coal or gas                              |
| `year`              | INTEGER PK | projection year (2025–2060; 2051+ forward-filled from 2050 AEO) |
| `price_per_mmbtu`   | FLOAT   | Projected delivered fuel price               |
| `source`            | VARCHAR | e.g., "AEO2025 Reference Case"               |
| `updated_at`        | TIMESTAMP |                                            |

### Table: `regional_price_projections`
EIA AEO projected wholesale electricity prices by **EMM** region, used as the revenue assumption.

| Column              | Type    | Notes                                       |
|---------------------|---------|---------------------------------------------|
| `emm_region`        | VARCHAR PK | EIA EMM region name (matches AEO facets)   |
| `year`              | INTEGER PK | projection year (2025–2060; 2051+ forward-filled from 2050 AEO) |
| `wholesale_price_per_mwh` | FLOAT | Projected average wholesale price        |
| `source`            | VARCHAR | e.g., "AEO2025 Reference Case"               |
| `updated_at`        | TIMESTAMP |                                            |

### Table: `plant_projections`
Precomputed stranded asset projections — one row per plant.

| Column                    | Type    | Notes                                     |
|---------------------------|---------|-------------------------------------------|
| `plant_id`                | VARCHAR FK |                                        |
| `projected_stranded_year` | INTEGER | Year plant is projected to become unprofitable (NULL if viable through projection horizon, **2060**) |
| `stranded_gap_years`      | INTEGER | retirement - stranded. Positive = years of stranded risk |
| `current_cost_per_mwh`    | FLOAT   | Most recent year's total cost/MWh        |
| `current_revenue_per_mwh` | FLOAT   | Most recent year's projected revenue/MWh |
| `current_profit_margin`   | FLOAT   | Revenue - cost (negative = already losing money) |
| `computed_at`             | TIMESTAMP |                                         |

**Note:** `projected_retirement_year` lives only in the `plants` table. To compute `stranded_gap_years` during the projection step, join on `plants.projected_retirement_year`. API responses that include both stranded gap and retirement year should join these two tables — do NOT duplicate the retirement year column here.

### Table: `refresh_log`
Tracks data refresh history.

| Column       | Type      | Notes                        |
|--------------|-----------|------------------------------|
| `id`         | SERIAL PK |                              |
| `started_at` | TIMESTAMP |                              |
| `completed_at`| TIMESTAMP|                              |
| `status`     | VARCHAR   | success, failed, in_progress |
| `plant_count`| INTEGER   | Plants processed             |
| `notes`      | TEXT      | Error messages if any        |

---

## Projection Model

The projection is the single analytical engine. It answers: "When does this plant stop being profitable?" and compares that to "When is it projected to retire?" The difference — the **stranded gap** — is the headline metric.

All factors that affect a plant's viability (age, efficiency, fuel costs, regional competition from renewables, plant size) are integrated into one economic model rather than split across disconnected scoring systems.

### Core Equation (Per Plant, Per Future Year)

```
profit_per_mwh(year) = revenue_per_mwh(year) - total_cost_per_mwh(year)

When profit_per_mwh < 0 for 2+ consecutive years → stranded
```

### Cost Side

```
total_cost_per_mwh(year) = fuel_cost_per_mwh(year) + om_cost_per_mwh(year)
```

**Fuel cost:**
```
fuel_cost_per_mwh(year) = plant_heat_rate × projected_fuel_price(year, fuel_type)
```
- `plant_heat_rate`: from EIA Form 923 historical data (MMBtu per MWh), averaged over recent years. This is the plant's efficiency — how much fuel it burns per unit of electricity. Older, less efficient plants have higher heat rates and therefore higher fuel costs.
- `projected_fuel_price(year, fuel_type)`: from EIA AEO reference case. Coal and gas have different price trajectories.

**Operating & maintenance cost:**
```
om_cost_per_mwh(year) = base_om_per_mwh(fuel_type) × age_escalation(plant_age_in_year) × size_factor(nameplate_mw)
```
- `base_om_per_mwh`: non-fuel operating + maintenance per MWh by fuel type (before age and size multipliers). Coal is higher than gas. **Hardcoded defaults** are aligned in magnitude with **EIA-reported** fleet-average non-fuel O&M (e.g. Form 861 / operating-expense tables — order-of-magnitude check), not live API pulls:
  - Coal (fossil steam): **$14/MWh**
  - Gas: **$6/MWh** (CC-heavy fleet; gas subcategories vary in reported data)
  - If better plant-specific or updated values become available from EIA data, replace these defaults.
- `age_escalation`: multiplier that increases O&M costs as plants age. Older plants require more maintenance. Model as: 1.0 up to 20 years, then +1.5% per year beyond that. A 40-year-old plant has ~1.3x base O&M.
- `size_factor`: smaller plants have higher per-MWh fixed cost overhead due to worse economies of scale. Model as: 1.0 at 1000+ MW, scaling up to ~1.3x at 100 MW.

### Revenue Side

```
revenue_per_mwh(year) = projected_wholesale_price(year, region) × dispatch_factor(year)
```
- `projected_wholesale_price(year, region)`: from EIA AEO reference case, average wholesale electricity price by region per year.
- `dispatch_factor`: reflects the plant's ability to actually sell into the market as renewables grow. Derived from projected regional renewable share:
  ```
  dispatch_factor(year) = 1.0 - (renewable_share(year, region) × displacement_coefficient(fuel_type))
  ```
  As renewables capture more of the generation mix, fossil plants dispatch less frequently and at worse prices. **`displacement_coefficient` is fuel-specific (stylized):** coal **0.75**, gas **0.45**. Example at 50% renewable share: coal dispatch factor **0.625**, gas **0.775**; at 30%: coal **0.775**, gas **0.865**. Tunable in `projection.py`.

**Capacity factor decay:**
The projection also models declining generation over time. Start from the plant's current capacity factor (3-year average from Form 923), and apply a gradual decay as the plant dispatches less:
```
projected_cf(year) = current_cf × dispatch_factor(year)
```
This doesn't directly affect the per-MWh profit calculation, but it's useful context for the detail view — showing how a plant's utilization is expected to decline.

### Stranded Year Determination

```python
for year in range(2025, 2061):  # PROJECTION_END_YEAR = 2060 in projection_horizon.py
    cost = fuel_cost(year) + om_cost(year)
    revenue = wholesale_price(year) * dispatch_factor(year)
    profit = revenue - cost
    
    if profit < 0:
        consecutive_loss_years += 1
    else:
        consecutive_loss_years = 0
    
    if consecutive_loss_years >= 2:
        projected_stranded_year = year - 1  # first year of the losing streak
        break
```

If a plant never hits 2 consecutive loss years by the horizon end year (**2060**): `projected_stranded_year = NULL` (viable through projection horizon). Years **2051–2060** reuse **2050** AEO fuel, wholesale, and renewable-share inputs (forward-fill) — EIA does not publish AEO annual series past 2050.

### Stranded Gap

```
stranded_gap = projected_retirement_year - projected_stranded_year
```
- **Positive gap** (e.g., +14 years): Plant becomes unviable 14 years before retirement. This is the danger zone — years of unrecoverable investment.
- **Zero or negative gap**: Plant retires before or around when it becomes unviable. Lower concern.
- **NULL stranded year**: Plant projected to remain viable. Shown as viable through the horizon end (**2060**) in copy.
- **Already stranded**: If `projected_stranded_year <= current_year`, plant is modeled as already unprofitable. Shown as "Already at risk" in the UI.

### Projected Retirement Year
- If EIA-860 has a `planned_retirement_year` for the plant → use that.
- If not → estimate: `commission_year + expected_life` (45 years for coal, 30 years for gas).
- Label in the UI as "Projected Retirement" with a tooltip: "Based on reported retirement plans where available, otherwise estimated from plant type and typical lifecycle."

### Where Each Factor Lives

| Factor | Role in Projection |
|--------|-------------------|
| Plant age | Drives O&M cost escalation (older = more expensive to maintain) |
| Plant efficiency (heat rate) | Drives fuel cost per MWh (less efficient = more expensive) |
| Fuel type | Different fuel price curves, different base O&M, different default lifespans |
| Regional renewable growth | Drives revenue depression via dispatch factor |
| Plant size | Drives per-MWh fixed cost overhead via size factor |
| Capacity factor | Starting baseline for projected generation trajectory |
| Carbon pricing (v2) | Would add a cost adder per MWh — clear extension point |

### Projection Caveats (document in README / product copy — no page footer)
- Projections use EIA Annual Energy Outlook reference case assumptions
- Does not account for policy changes, carbon pricing, specific utility decisions, or market shocks
- Revenue is **energy-only** (wholesale × dispatch); **capacity, ancillary, and PPA revenues are not modeled** — thermal plants in capacity markets often earn material non-energy revenue, so stranded timing can look earlier than full economics would suggest
- O&M cost escalation uses industry averages, not plant-specific maintenance data
- "Projected Stranded Year" is an indicative estimate, not a financial forecast

---

## EIA API Integration

### API Base
```
https://api.eia.gov/v2/
```

All requests require `api_key` query parameter. Register at https://www.eia.gov/opendata/register.php and store the key in `EIA_API_KEY` in your `.env` file.

### Key Routes

**1. Plant/Generator Inventory (EIA-860)**
```
GET /electricity/operating-generator-capacity
```
Parameters: **`frequency=monthly`** (latest inventory month via **`start`/`end`** `YYYY-MM`), facets **`energy_source_code`** (coal: BIT, SUB, LIG, RC; gas: NG), **`status=OP`**. Aggregates to **plant** as `stateid`–`plantid` (same as Form 923 `plantCode` + `state`).

Use to: build the `plants` table. Filter for nameplate ≥ 100 MW (aggregate generators at the same plant). See `app/services/data_refresh.py`.

**2. Plant-Level Operations (EIA Form 923)**
```
GET /electricity/facility-fuel
```
Parameters: `frequency=annual`, facets `state`, `plantCode` (batched), `fuel2002=ALL` for plant-level totals; data fields **`generation`** (net MWh) and **`total-consumption-btu`** (MMBtu). *(EIA v2 field id is `generation`, not `net-generation`.)*

Use to: compute capacity factor, heat rate, and fuel cost proxy for `plant_metrics` — see `app/services/metrics_refresh.py`.

**3. Regional renewables (implemented path: AEO, not generator inventory)**

`regional_renewables` (wind + solar vs total capacity, renewable share) is loaded from **AEO** tables **62** and **67** by EMM region in **`app/services/aeo_refresh.py`**. An alternative sketched in early drafts was aggregating **`electricity/operating-generator-capacity`** by NERC; that is **not** what the current pipeline uses.

**4. Annual Energy Outlook Projections**
```
GET /aeo/
```
- Fuel price projections by fuel type and year (reference case)
- Renewable capacity projections by region and year
- Wholesale electricity price projections by region and year
- These are published annually and cover projections out to ~2050

Use to: build `fuel_price_projections`, `regional_price_projections`, and (with table 67) renewable capacity inputs; **`aeo_refresh.py`** implements this for `ref2025` + default release **`/aeo/2025/`**.

### Data Refresh Flow

```
[Manual trigger or future cron]
        │
        ▼
  1. Pull generator inventory → upsert plants table
     (also compute projected_retirement_year: use planned_retirement_year if available,
      else commission_year + expected_life — 45yr coal, 30yr gas)
     → app.services.data_refresh; refresh_log
        │
        ▼
  2. Pull recent annual facility-fuel data → compute metrics (CF, heat rate, fuel $ proxy) → upsert plant_metrics
     → app.services.metrics_refresh
        │
        ▼
  3. Pull AEO reference case → upsert fuel_price_projections, regional_price_projections,
     and regional_renewables (EMM wind+solar vs total capacity)
     → app.services.aeo_refresh
        │
        ▼
  4. Run projection engine across all plants → compute stranded year + gap
     → projection.py
        │
        ▼
  5. Upsert plant_projections table
        │
        ▼
  6. (Optional) refresh_log or admin notes for projection runs — TBD when wired
```

### EIA API Notes
- Rate limit: ~1000 requests/hour (unconfirmed, build with conservative delays). **HTTP 429** can occur on heavy AEO runs; use **retry with backoff** (see `eia_client.py`); **`aeo_refresh.py`** adds a short delay between regions.
- Paginated: use `offset` and `length` params, default page size is 5000
- Data is typically 2-3 months behind (e.g., in March 2026 the latest monthly data may be Dec 2025)
- Some routes return generator-level data that must be aggregated to plant-level
- AEO projections update annually (usually early in the year)

---

## Backend API Routes

### Plant Data (REST)

```
GET  /api/plants
     ?fuel_type=coal|gas|all
     &sort_by=stranded_gap|projected_stranded_year|projected_retirement_year|age|capacity_factor|nameplate_mw|cost_per_mwh
     &sort_order=desc|asc
     &limit=50
     &offset=0
     &emm_region=PJM%20%2F%20East (optional filter; URL-encoded EMM label)
     &min_stranded_gap=0 (optional filter)
     → Returns: list of plants with metadata + projection data

GET  /api/plants/{plant_id}
     → Returns: full plant detail with metrics history and projection breakdown

GET  /api/regions
     → Returns: list of EMM regions with renewable penetration stats and avg stranded gap

GET  /api/stats
     → Returns: dashboard summary stats for HeroStats component:
       - total plants tracked
       - avg stranded gap (coal vs gas)
       - # plants already at risk (stranded year ≤ current year)
       - highest risk region
       - data freshness date
```

### Natural Language Query

```
POST /api/query
     Body: { "query": "Which coal plants in Texas have the biggest stranded gap?" }
     → Returns: {
         "message": "Here are coal plants in Texas sorted by stranded gap — the years between projected unprofitability and retirement...",
         "plants": [ ...filtered/sorted plant list... ],
         "filters_applied": { "fuel_type": "coal", "state": "TX", "sort": "stranded_gap" }
       }
```

### Admin

```
POST  /api/admin/refresh
     Header: X-Admin-Key (simple shared secret for now)
     → Triggers full data refresh pipeline
     → Returns: { "status": "started", "refresh_id": 123 }

GET  /api/admin/refresh/{refresh_id}
     → Returns: refresh status and progress
```

---

## Natural Language Query — Claude Integration

### Flow
```
User types query in QueryBar
        │
        ▼
Frontend POST /api/query with raw text
        │
        ▼
Backend sends to Claude API:
  - System prompt with strict guardrails
  - User's query
  - Tool definitions that map to DB queries
        │
        ▼
Claude returns structured tool calls + summary message
        │
        ▼
Backend executes DB queries based on tool calls
        │
        ▼
Backend returns filtered/sorted plants + Claude's summary message
        │
        ▼
Frontend renders results in PlantTable
```

### System Prompt (for Claude API call)

```
You are a query assistant for the Burnout dashboard (stranded asset risk for US power plants). Your ONLY
job is to translate natural language questions into structured filters and sorts
for a database of US coal and gas power plants analyzed for stranded asset risk.

The database contains plants with these key fields:
- fuel_type (coal or gas), state, emm_region, nameplate_mw, commission_year
- projected_stranded_year (year the plant is projected to become unprofitable)
- projected_retirement_year (when the plant is expected to retire)
- stranded_gap_years (retirement year minus stranded year — positive = years of stranded risk)
- capacity_factor (3-year average utilization)
- heat_rate (plant efficiency — higher = less efficient)
- current_cost_per_mwh (current total operating cost)
- current_profit_margin (revenue minus cost — negative = already losing money)

You have access to these tools (same as the MCP tools — see MCP Server section for full schemas):
- list_plants(fuel_type, state, emm_region, min_capacity_mw, limit,
              sort_by, sort_order)  — filter and sort the plant table
- rank_plants_by_stranded_risk(fuel_type, emm_region, top_n)  — shortcut for
  "show me the most at-risk plants"
- get_plant_details(plant_id)  — full detail on one plant
- get_regional_summary(emm_region)  — summary stats for a region

STRICT RULES:
1. You may ONLY discuss US power plants, energy, stranded assets, and related
   energy/climate topics. Nothing else.
2. If a query is CLEARLY off-topic and seems like someone testing you, respond
   with a brief, cheeky deflection that redirects to energy topics. Examples:
   - "Nice try, but I only have eyes for power plants. Ask me which coal plants
     in the Southeast are running on borrowed time!"
   - "I'm flattered, but I'm a one-trick pony — stranded assets only. Want to
     know which gas plants might not make it to 2035?"
3. If a query is UNCLEAR or too broad, ask for specifics and explain what details
   would help. Example: "I can help with that — are you looking at coal, gas, or
   both? And any particular region or state? The more specific you are, the better
   I can filter the results."
4. Always return a structured tool call. Even for vague queries, make a
   reasonable default (e.g., top 50 by stranded gap).
5. Include a short plain-English "message" explaining what you're showing and why.
6. Never fabricate plant data. Only use the tools provided.
```

### Guardrail Implementation
- Claude API call uses `claude-haiku-4-5-20251001` for cost (Haiku 4.5; structured translation, not open-ended reasoning)
- Max tokens: 1024 (tool call + interpretation `message`; cap matches `nl_query.py`)
- Temperature: 0 (deterministic structured output)
- If Claude API fails, fall back to showing all plants sorted by stranded gap with a message: "Showing all plants by stranded gap. Try a specific query like 'coal plants in Ohio with the biggest risk.'"

---

## MCP Server — Tool Definitions

These tools are exposed via the MCP protocol. They're used both internally by the backend and externally by any MCP client.

### Tool: `list_plants`

```json
{
  "name": "list_plants",
  "description": "List US fossil fuel power plants with metadata and stranded asset projections. Filter by fuel type, region, capacity, and stranded gap.",
  "parameters": {
    "fuel_type": { "type": "string", "enum": ["coal", "gas", "all"], "default": "all" },
    "emm_region": { "type": "string", "optional": true },
    "min_capacity_mw": { "type": "number", "default": 100 },
    "state": { "type": "string", "optional": true },
    "limit": { "type": "integer", "default": 50 },
    "sort_by": { "type": "string", "enum": ["stranded_gap", "projected_stranded_year", "projected_retirement_year", "capacity_factor", "nameplate_mw", "cost_per_mwh"], "default": "stranded_gap" },
    "sort_order": { "type": "string", "enum": ["asc", "desc"], "default": "desc" }
  }
}
```

### Tool: `get_plant_details`

```json
{
  "name": "get_plant_details",
  "description": "Get detailed information about a specific power plant including operational metrics history and stranded asset projection details.",
  "parameters": {
    "plant_id": { "type": "string", "required": true }
  }
}
```

### Tool: `rank_plants_by_stranded_risk`

```json
{
  "name": "rank_plants_by_stranded_risk",
  "description": "Return the top N plants with the largest stranded gap (years between projected unprofitability and retirement). These are the plants most at risk of becoming stranded assets.",
  "parameters": {
    "fuel_type": { "type": "string", "enum": ["coal", "gas", "all"], "default": "all" },
    "emm_region": { "type": "string", "optional": true },
    "top_n": { "type": "integer", "default": 25 }
  }
}
```

### Tool: `get_regional_summary`

```json
{
  "name": "get_regional_summary",
  "description": "Get summary statistics for an EIA EMM region: number of plants, average stranded gap, renewable penetration, and breakdown by fuel type.",
  "parameters": {
    "emm_region": { "type": "string", "required": true }
  }
}
```

### Standalone MCP Repo Differences
The standalone `mcp-server-eia/` version calls EIA APIs directly (no database). It's stateless — every tool call hits the EIA API. This makes it simple to run but slower. The backend-integrated version reads from Postgres for speed.

---

## Frontend Components

### Layout (top to bottom)

```
┌───────────────────────────────────────────────────────┐
│  Masthead: "Burnout" + headline question + lede        │
├───────────────────────────────────────────────────────┤
│                                                        │
│  HeroStats (3-4 key metrics)                           │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐  │
│  │  342         │ │  14.2 yrs   │ │  PJM / East     │  │
│  │  Plants      │ │  Avg Coal   │ │  Highest Risk   │  │
│  │  Tracked     │ │  Stranded   │ │  Region         │  │
│  │              │ │  Gap        │ │                  │  │
│  └─────────────┘ └─────────────┘ └─────────────────┘  │
│                                                        │
├───────────────────────────────────────────────────────┤
│                                                        │
│  [MAP VIEW - ITERATION 2]                              │
│  Space reserved, skip for v1                           │
│                                                        │
├───────────────────────────────────────────────────────┤
│                                                        │
│  ┌─ QueryBar ──────────────────────────────────────┐  │
│  │  🔍 "Which coal plants in the Southeast have    │  │
│  │     the biggest stranded gap?"        [Search]   │  │
│  └──────────────────────────────────────────────────┘  │
│  AI response: "Showing 23 coal plants in PJM / East   │
│  sorted by stranded gap — years between projected      │
│  unprofitability and retirement..."                  │
│                                                        │
├───────────────────────────────────────────────────────┤
│                                                        │
│  Plant Table (full width)                              │
│  ┌────┬──────────┬─────┬────┬───────┬───────┬────────┐ │
│  │Rank│Name      │State│Type│Strand.│Gap    │Cost    │ │
│  │    │          │     │    │Year   │(yrs)  │$/MWh   │ │
│  ├────┼──────────┼─────┼────┼───────┼───────┼────────┤ │
│  │ 1  │Hunter    │UT   │Coal│ 2028  │ +17   │ $38.20 │ │
│  │ 2  │Scherer   │GA   │Coal│ 2029  │ +16   │ $41.50 │ │
│  │ 3  │Gibson    │IN   │Coal│ 2030  │ +12   │ $35.80 │ │
│  │ ...│          │     │    │       │       │        │ │
│  └────┴──────────┴─────┴────┴───────┴───────┴────────┘ │
│                                                        │
│  Showing 50 of 342 plants  [Load more]                 │
└───────────────────────────────────────────────────────┘
```

### Table Columns

| Column              | Sortable | Notes                                      |
|---------------------|----------|---------------------------------------------|
| Rank                | No       | **UI-only:** row index in the **current** filtered + sorted result set for the loaded page (`offset` + position). Not a field from the API. |
| Plant Name          | Yes      |                                             |
| State               | Yes      |                                             |
| Fuel Type           | Yes      | Color-coded dot: amber (coal) / blue (gas)   |
| Stranded Gap        | Yes      | Years; palette-based text color by magnitude (default sort) |
| Projected Stranded  | Yes      | Year, e.g., "2028" or "Already at risk"      |
| Projected Retirement| Yes      | Year, e.g., "2045"                           |
| Cost $/MWh          | Yes      | Current total operating cost per MWh         |
| Capacity Factor     | Yes      | 3-year avg, shown as %                       |
| Nameplate (MW)      | Yes      |                                             |
| Age (years)         | Yes      |                                             |
| Market region (EMM) | Yes      | EIA EMM label, e.g. `PJM / East`            |

Default sort: stranded gap descending (biggest gaps first = most at risk).

### Iteration 2: Map View
- Library: React-Leaflet (free, OpenStreetMap tiles, no API key needed)
- Plants as dots; **color** can encode fuel, region, or another dimension — avoid a default “traffic light” stranded-gap ramp unless we deliberately bring it back for maps only
- Coal and gas plants distinguished by shape (circle vs diamond) or border style
- Click dot → popup with plant name, stranded gap, fuel type, capacity, projected stranded year
- Map syncs with table: query filters apply to both views

---

## Build Order

This is the recommended sequence. Each phase should be testable independently.

### Phase 1: Data Foundation (Day 1 morning)
1. Register for EIA API key; add `EIA_API_KEY` to `.env` (not committed)
2. Run **Postgres locally** via **Homebrew** (see **README.md**). Set `DATABASE_URL` in `.env`
3. Set up Python backend with FastAPI skeleton (monorepo `backend/`)
4. Create database models and run migrations
5. Build `eia_client.py` — test raw API calls to EIA v2, confirm data shape for:
   - Generator inventory (EIA-860)
   - Plant operations (Form 923)
   - Regional capacity
   - AEO fuel price projections
6. Build `data_refresh.py` — pull plant inventory + metrics, write to DB
7. Run first full data refresh, verify data in Postgres

**Status in repo:** Steps 1–4 and 5–7 are done as separate modules: `eia_client.py`, `data_refresh.py`, `metrics_refresh.py`, `aeo_refresh.py`, **`projection.py`** (see **Backend — implemented so far**). Run order: data_refresh → metrics_refresh → aeo_refresh → **projection**. REST **`/api/plants`**, **`/api/regions`**, **`/api/stats`** are implemented (see **Backend — implemented so far**).

**Railway (later):** In Phase 6, provision Railway Postgres and point `DATABASE_URL` / `CORS_ORIGINS` / `VITE_API_URL` at deployed URLs — same env vars as local, different values.

### Phase 2: Projection Engine (Day 1 afternoon)
8. Implement `projection.py` with the unified economic model (cost side + revenue side) — **done**
9. Add projection computation to the refresh pipeline — **manual order documented** above (optional shell script / cron); dedicated wrapper module or Railway job can follow at deploy time
10. Verify outputs look reasonable (spot-check known plants — do old, inefficient coal plants get early stranded years? Do stranded gaps seem plausible?)
11. Build REST endpoints: `/api/plants`, `/api/plants/{id}`, `/api/regions`, `/api/stats` — **done**
12. Test endpoints — use interactive **`/docs`** (OpenAPI), curl, or Postman as needed during development

### Phase 3: Frontend — Table View (Day 1 evening)

**Implemented in repo:** Vite + React; Layout; HeroStats (`/api/stats`); PlantTable (`/api/plants`) with **server-side** sorting and filtering (`sort_by`, `sort_order`, `fuel_type`, `emm_region`, `min_stranded_gap`), **Load more** pagination (`limit` / `offset`), loading / empty / error states, **Projected Retirement** column, and **rank** as display-only position in the current list (no backend `rank`). **Stranded gap** column uses palette-aligned **text color** only; fuel dots; no row edge bars.

13. Scaffold React app with Vite — **done**
14. Set up design system: CSS variables, fonts (Outfit + DM Mono from Google Fonts), color palette — **done**
15. Build Layout + Masthead, soft mist (`#EEF4F1`) background — **done** (no site footer; caveats in README)
16. Build HeroStats component — fetch from `/api/stats` — **done**
17. Build PlantTable component — fetch from `/api/plants`, ranked list with stranded gap + projection fields — **done**
18. Column sorting — **server-side** via API `sort_by` / `sort_order` (not client-side re-sort of the full dataset)
19. Pagination — Load More — **done**
20. Basic responsive layout — **iterate** as needed (mobile card view optional; plan remains the target)
21. Plant detail modal — row/card opens modal; `usePlantDetail` + `PlantDetailModal` + `MetricSparkline`; retirement copy (EIA planned vs model); metrics sparkline + expandable year table — **done**

**Phase 3 closed.** Further UI polish is always optional.

### Phase 4: Natural Language Query — **implemented** (core + expanded list filters)

**Done:** Anthropic key in config; **`nl_query.py`** (`list_plants` tool, `_coerce_tool_input`, guardrails); **`POST /api/query`**; **`QueryBar`** + **`useNlQuery`**; filter-driven table via shared state + **`GET /api/plants`**. **Expanded REST + `FiltersApplied` + NL tool:** text `ILIKE`, numeric min/max, multi **`states`** / **`fuel_types`**, latest CF bounds, projection financial fields — see **`app/routes/plants.py`** and **`/docs`**. **UI:** interpretation sentence is **inside** the search card (sand-tinted band), not duplicate filter chips.

**Optional / follow-up:** Deeper guardrail test matrix; optional DB indexes for large lists; manual toolbar for rarely used filters if product requires.

22. Set up Anthropic API key in backend config — **done**
23. Build `nl_query.py` — system prompt, tool definitions, guardrails — **done**
24. Build `/api/query` endpoint — **done**
25. Build QueryBar frontend component — **done**
26. Wire up: query → Claude → tool calls → structured filters → table update — **done**
27. Test guardrails — **iterate** as needed

### Phase 5: MCP Server (Day 2 afternoon)
28. Implement MCP tools in `backend/app/mcp/tools.py`
29. Set up MCP server endpoint in FastAPI
30. Test with MCP inspector or Claude Desktop
31. Copy MCP logic to standalone `mcp-server-eia/` repo
32. Write README with setup instructions for standalone usage

### Phase 6: Polish & Deploy (Day 2 evening)
33. Visual polish: table density, typography, loading animations; tune stranded-gap text contrast if needed
34. Error states: deepen beyond Phase 3 baseline (API failures, empty results, loading states are already present for the main table/stats)
35. Mobile testing and fixes
36. Projection caveats and data attribution (README / in-app copy as needed — not a global footer)
37. **Railway:** **Done (baseline):** project **ProjectBurnout**, services **Postgres**, **backend**, **frontend**; `DATABASE_URL` on backend references Postgres; `CORS_ORIGINS`, `VITE_API_URL`, `EIA_API_KEY` set — see **Railway (production deploy)** below.
38. **Deploy:** **Done:** frontend uses **`frontend/Dockerfile`** (Node 23) + `frontend/railway.toml` (`builder = DOCKERFILE`); backend deploys from `backend/` with `start.sh` (Alembic + uvicorn). Each service uses **Root directory** `frontend` or `backend` when connected to GitHub.
39. **Test on deployed URL:** **Partially done** — app loads; **production DB may be empty or out of sync** until EIA pipeline is run successfully against the **same** database the API uses (see handoff / open issues below).
40. Add admin refresh endpoint with simple auth — **not done** (still manual / SSH / cron).

### Future Iterations (post-sprint)
- Map view with React-Leaflet
- Cron job for automatic data refresh (Railway cron or external)
- Rich plant detail (e.g. projection chart) if not fully covered in Phase 3
- Carbon pricing cost adder (v2 — adds a $/MWh cost term to the projection model)
- Publish standalone MCP to mcp.so / Smithery

---

## Environment Variables

### Backend
```
# Local (Homebrew Postgres — use your macOS username; see README):
DATABASE_URL=postgresql://YOUR_MACOS_USERNAME@localhost:5432/stranded_assets
# Production (Railway Postgres plugin injects DATABASE_URL)

EIA_API_KEY=...                      # From EIA registration — use .env only
# EIA_AEO_RELEASE=2025               # Optional; AEO API path segment (default 2025)
ANTHROPIC_API_KEY=...                # For Claude API (NL query)
ADMIN_KEY=...                        # Simple secret for admin endpoints

# Local: Vite default origin. Production: your Railway frontend URL
CORS_ORIGINS=http://localhost:5173
```

### Frontend
```
# Local:
VITE_API_URL=http://localhost:8000
# Production (Railway):
# VITE_API_URL=https://your-backend.up.railway.app
```

---

## Railway (production deploy)

**Repo:** [ProjectBurnout](https://github.com/abrose1/ProjectBurnout) (public). **In-product name:** Burnout. **Railway project:** ProjectBurnout.

### Services (typical layout)

| Service | Role | Root directory (monorepo) |
|---------|------|---------------------------|
| **Postgres** | Managed PostgreSQL | — |
| **backend** | FastAPI API | `backend` |
| **frontend** | Static Vite app (Docker + `serve`) | `frontend` |

### Public URLs

- Railway assigns `*.up.railway.app` hostnames per service (custom subdomain editable in the service’s **Settings → Networking / Domains**).
- **Frontend** is the browser URL users open (e.g. a custom name like `project-burnout.up.railway.app`).
- **Backend** has its own hostname (e.g. `backend-production-….up.railway.app`); **`VITE_API_URL`** on the frontend service must be the **HTTPS** backend base URL (no trailing slash), set for **build time** so the Vite bundle calls the correct API.

### Config as code (in repo)

- `backend/railway.toml` — Nixpacks/Railpack build; `start.sh` runs `alembic upgrade head` then uvicorn.
- `frontend/railway.toml` — **`builder = DOCKERFILE`** so the image uses **`frontend/Dockerfile`** (official `node:23-bookworm-slim`; Railway’s default **Railpack** was resolving to **Node 18**, which breaks Vite 8).
- `frontend/Dockerfile` — multi-stage: `npm ci` → `npm run build` → `serve` on `$PORT`.

### Required Railway variables (summary)

- **Postgres:** plugin provides `DATABASE_URL` / `DATABASE_PUBLIC_URL` (internal vs TCP proxy).
- **backend:** `DATABASE_URL` should **reference** the Postgres service (e.g. `${{Postgres.DATABASE_URL}}`). **`EIA_API_KEY`** must be set for EIA refresh scripts and debug routes. **`CORS_ORIGINS`** must include the exact frontend origin (e.g. `https://<your-frontend-host>.up.railway.app`). Use a variable reference like `${{frontend.RAILWAY_PUBLIC_DOMAIN}}` with `https://` prefix if supported, or set explicitly. **After changing the frontend public domain, redeploy the backend** so CORS picks up the new origin.
- **frontend:** **`VITE_API_URL`** = backend public API base URL (often `${{backend.RAILWAY_PUBLIC_DOMAIN}}` with `https://` — confirm pattern in Railway variable UI). Mark as available at **build** time if the UI offers it.

### CLI (from repo root, with [Railway CLI](https://docs.railway.com/guides/cli) installed)

```bash
railway login
cd /path/to/StrandedAssets    # monorepo root
railway link                  # if not already linked to ProjectBurnout

# Deploy manually (uploads current directory; use path-as-root for monorepo)
railway service backend
railway up --path-as-root backend

railway service frontend
railway up --path-as-root frontend
```

- **`railway service <name>`** selects which service subsequent commands target.
- **`railway up --path-as-root backend`** (or `frontend`) mirrors setting **Root Directory** in the UI for that service.
- If the repo is connected to GitHub with auto-deploy, **`git push`** may deploy without `railway up`; avoid doing both for every change or you may double-deploy.

Useful: `railway variables -s backend`, `railway domain`, `railway open` (opens dashboard; may require interactive session).

### Production data load (EIA → Postgres)

Order is the same as local: **inventory → metrics → AEO → projection** (`scripts/refresh_eia_pipeline.sh` runs the four Python modules from `backend/`).

**Gotcha:** `railway run ./scripts/refresh_eia_pipeline.sh` injects the backend service env, but **`DATABASE_URL` uses `postgres.railway.internal`**, which **does not resolve on your laptop**. So a naive `railway run` from your machine fails DB connect unless you override `DATABASE_URL` with **`DATABASE_PUBLIC_URL`** from the Postgres service (TCP proxy). Conversely, writing only via `DATABASE_PUBLIC_URL` from outside **must** target the **same** logical database the backend uses, or the API will still show empty lists.

**Preferred direction for production refresh:** run the pipeline **inside** the running backend container so it uses the same `DATABASE_URL` as uvicorn, e.g. `railway ssh` then from `/app`:

`/opt/venv/bin/python -m app.services.data_refresh` → `metrics_refresh` → `aeo_refresh` → `projection` (long-running; **aeo_refresh** can hit EIA **429** — retries exist; may need spacing or re-run).

**Open issue:** Confirm row counts via internal DB (`railway ssh` + SQL or small Python one-liner) match what `/api/plants` returns; if the UI shows “No plant data” but local loads seemed to succeed, suspect **wrong DB**, **incomplete pipeline**, or **list API filters** (plants without `plant_metrics` are excluded per `plant_visibility`).

---

## Key Technical Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Backend language | Python (FastAPI) | Better for data wrangling, pandas available |
| Database | Postgres (local first, Railway in prod) | Persistent storage, familiar, good for structured queries |
| Frontend | React (Vite) | Fast build, good ecosystem |
| Map library | React-Leaflet (iteration 2) | Free, no API key, good enough for dots on a map |
| Headline metric | Stranded gap (years) | Most compelling number — "14 years of unrecoverable investment" |
| Analytical model | Unified projection (cost vs revenue per year) | All factors (age, efficiency, fuel, renewables, size) integrated into one economic model |
| Risk score | Removed | Replaced by projection model — factors are now inputs to economic projection, not a separate composite score |
| Revenue assumption | EIA AEO regional wholesale price projections | Same source as fuel prices, avoids real-time LMP complexity |
| Retirement estimate | EIA planned if available, else age-based default (45yr coal, 30yr gas) | Labeled "Projected Retirement" to avoid overpromising |
| AI integration | NL query bar via Claude API | Not a chat — single input translates to structured DB queries |
| Claude model for NL | claude-haiku-4-5-20251001 | Lower cost than Sonnet; sufficient for structured query translation |
| Regional mapping | **`emm_region`** is the AEO/EMM axis (`plants` + regional tables) | Wholesale + renewables are EMM-keyed; **`projection.py`** assigns plant → EMM (or fallback) |
| Carbon pricing | Named as v2 extension point in projection model | Would be a cost adder per MWh — clear where it goes |
| Coal vs gas frontend | Same table, same projection model | Fuel type drives different price curves and base O&M, no separate logic |
| MCP packaging | Module in backend + standalone repo | Fast in production, reusable for community |
| Data refresh | Manual first, cron later | Keeps sprint scope manageable |
| Railway frontend image | `frontend/Dockerfile` (`node:23-bookworm-slim`) + `railway.toml` `DOCKERFILE` | Default Railpack/Nixpacks picked Node 18; Vite 8 needs newer Node; Dockerfile pins runtime |
| Design approach | Explicit anti-AI-slop design system | See Design System section — distinctive typography, warm palette, no purple |
| Plant detail view | **Done** (modal) | `PlantDetailModal` + `GET /api/plants/{id}` + metrics history / sparkline |

---

## Risk & Gotchas

1. **EIA API pagination**: Some queries return thousands of rows. Always paginate with `offset` + `length`. Build this into `eia_client.py` from the start.
2. **Generator vs plant aggregation**: EIA data is at the generator level. A single plant can have multiple generators with different fuels. You'll need to aggregate: sum capacities, pick primary fuel by largest capacity share, average capacity factors.
3. **EIA data freshness**: Data lags 2-3 months. Don't promise "real-time" anywhere in the UI. Surface "Data through [month/year]" in stats or docs as appropriate.
4. **Claude API latency**: NL query will take 1-3 seconds. Show a loading state. Never block the default table view — show ranked plants immediately on page load, NL query refines them.
5. **Railway cold starts**: Free/hobby tier may have cold starts. Backend should be fast to boot. Keep startup lightweight — don't refresh data on boot.
6. **EIA API key rate limits**: Unknown exact limits. Build in retry logic with exponential backoff. Cache aggressively in Postgres.
7. **EMM region mapping**: **`projection.py`** assigns **`plants.emm_region`** where it can match plants to **EIA EMM labels** used in **`regional_*`** (e.g. `PJM / East`); some plants may still lack a match. Handle nulls gracefully in API and UI — projection falls back to national average wholesale and neutralizes renewable displacement when appropriate. (Optional later: a separate NERC column from 860 if we want both taxonomies.)
8. **AEO projection availability**: **`aeo_refresh.py`** loads AEO via `/v2/aeo/{release}/` (default release from `EIA_AEO_RELEASE`, scenario `ref2025`). If the API is unavailable, fall back to hardcoded projection curves from the most recent AEO PDF tables. **Emergency fallback anchor points (approximate AEO2024 reference case — use ONLY if the API is unavailable, replace with real data as soon as possible):**
   - Coal delivered price: ~$2.10/MMBtu in 2025, rising to ~$2.40/MMBtu by 2050
   - Gas delivered price: ~$3.50/MMBtu in 2025, rising to ~$4.50/MMBtu by 2050
   - National avg wholesale electricity: ~$45/MWh in 2025, rising to ~$55/MWh by 2050
   - These are rough national averages for bootstrapping only. Regional variation is significant. Once real AEO data is loaded, these should never be referenced.
9. **AEO regional price granularity**: Wholesale prices are **per EMM region** in the API. Bridge **plants → EMM** (or to a national default) in **`projection.py`**.
10. **Stranded year edge cases**: Some plants may already be past their projected stranded year (they're currently unviable but still operating). Handle this in the UI — show "Already at risk" instead of a past year.
11. **Projection model credibility**: The model is simple by design. State caveats clearly (README, modal, or future stats strip) — this is an indicative tool, not a financial forecast. Honest framing improves credibility.
12. **O&M cost data**: EIA publishes average O&M costs by plant type, but these are industry averages, not plant-specific. Acceptable for the prototype — note this in the caveats.
13. **Railway production DB vs API:** Loading data from a dev machine using **`DATABASE_PUBLIC_URL`** can succeed while the deployed API still shows **no plants** if the backend’s **`DATABASE_URL`** does not point at that same database, or if the refresh did not complete (metrics/AEO/projection). **`railway run`** against the repo from localhost does not resolve **`postgres.railway.internal`** — use SSH on the backend service or a confirmed public URL to the **same** DB the service uses. After changing **frontend domain**, **redeploy backend** so **CORS** updates.
