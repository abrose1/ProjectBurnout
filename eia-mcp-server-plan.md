# Standalone EIA MCP Server — Technical Plan

## What This Is

A standalone MCP server that gives any AI agent (Claude Desktop, Cursor, Claude Code, etc.) structured access to the U.S. Energy Information Administration's open data API. It wraps EIA's notoriously painful API — cryptic facet codes, inconsistent pagination, multiple overlapping route families — into clean, human-readable tools that an LLM can call naturally.

**This is a separate GitHub repo from the Burnout dashboard.** No database dependency, no Postgres, no connection to the stranded asset projection model. Pure API passthrough with smart abstractions.

**v1 build (historical): ~4–6 hours with Cursor** once patterns from Burnout’s backend were available. Most of the hard EIA API work (pagination, generator-to-plant aggregation, AEO table routing) was already solved there and was extracted into the standalone repo.

### Implementation status — v1 + expansion wave 1 + `get_fuel_prices` shipped

| | |
|--|--|
| **Repository** | **[github.com/abrose1/mcp-server-eia](https://github.com/abrose1/mcp-server-eia)** (public). Tagged releases (**`v0.3.0`**, **`v0.2.0`**, **`v0.1.0`**), **CHANGELOG**, **MIT** license. |
| **Runtime** | Python **`mcp`** SDK (**FastMCP**), **`httpx`**; **stdio** MCP. **`EIA_API_KEY`** supplied by the MCP host (**`env`** in Cursor / Claude config) or shell. |
| **Shipped** | **Nine** tools (v1 six + **`get_generation_mix`**, **`get_capacity_by_fuel`**, **`get_fuel_prices`**), standard **`{ data, meta }`** envelope, **`scripts/smoke_eia.py`** (live API check), **`pytest`**, GitHub Actions (unit tests only). Tag **`v0.3.0`**. |
| **Spec location** | This file (`eia-mcp-server-plan.md`) stays in the **StrandedAssets** monorepo as the technical spec; **source code does not live here** — edit **[mcp-server-eia](https://github.com/abrose1/mcp-server-eia)** only. |

## Supplying `EIA_API_KEY` (for live EIA calls)

When a tool makes live requests, `mcp-server-eia` reads `EIA_API_KEY` from the environment. There are two common ways to provide it:

1. **MCP host (Cursor / Claude Desktop):** set the MCP server `env` value so the process gets the key.
   - Example (matches how Cursor/MCP typically passes env vars): `env: { "EIA_API_KEY": "your-key-here" }`
2. **Local shell / smoke tests:** export the variable before running the server or `scripts/smoke_eia.py`.
   - Example: `export EIA_API_KEY=your-key-here`

### Next steps — further expansion

**Shipped in `mcp-server-eia` `v0.2.0`:** **`get_generation_mix`** (`electricity/electric-power-operational-data`, Electric Power sector 98, headline fuel buckets + `other`) and **`get_capacity_by_fuel`** (`electricity/operating-generator-capacity` summed by `energy_source_code` with plant counts).

**Shipped in `mcp-server-eia` `v0.3.0`:** **`get_fuel_prices`** — historical spot/market fuel prices (not AEO): Henry Hub (`natural-gas/pri/fut`), U.S. citygate and wellhead (`natural-gas/pri/sum`), coal open-market price by basin (`coal/market-sales-price`; API v2 route — not the deprecated `coal/market` name), WTI/Brent spot (`petroleum/pri/spt`).

**Next:** continue with **Optional Expansion Phase** (STEO, RTO, composites, etc.) in any order. **Distribution** stretch goals (PyPI, MCP directories, hosted SSE) are separate — see **Stretch Goals (Post-v1)** below.

### Burnout & this monorepo (history — read this first)

**Burnout** is the **in-product name** of the climate dashboard: a web app that ranks US fossil plants by **stranded-asset risk** (gap between projected unprofitability and retirement), built on EIA data and a custom **projection** model in Postgres. The codebase is often referred to by the repo/folder name **StrandedAssets** — a **monorepo**, not the standalone MCP repo.

| Piece | Role |
|-------|------|
| **`frontend/`** | React (Vite) UI: table, stats, NL query bar, plant detail — talks to the backend over **`VITE_API_URL`**. |
| **`backend/`** | FastAPI: **`/api/plants`**, **`/api/query`** (Claude → structured filters), refresh scripts, **`projection.py`**. |
| **`backend/app/services/eia_client.py`** | Shared EIA HTTP client (pagination, retries) — primary extraction source for **`mcp-server-eia`**. |
| **`backend/app/services/data_refresh.py`**, **`metrics_refresh.py`**, **`aeo_refresh.py`** | Batch jobs that fill Postgres; logic for aggregation and AEO mappings is reused in the MCP, **without** DB writes. |
| **`backend/app/services/projection.py`** | **Burnout-only** economics → stranded years; **not** used by the standalone EIA MCP. |
| **`scripts/`** | e.g. **`refresh_eia_pipeline.sh`** — full DB refresh order for the dashboard. |
| **`IMPLEMENTATION_PLAN.md`** | Umbrella doc: product design, phases, REST + NL MCP tool shapes (**Postgres-backed**, optional). |
| **`README.md`** | Local setup: Postgres, env, how to run — **not** the MCP spec. |
| **`docs/EIA_DATA_PIPELINE.md`** | How EIA ingestion maps to tables and the API; onboarding for “where does this route go?” |

**This file (`eia-mcp-server-plan.md`)** lives in the **monorepo** as the **technical spec** for **`mcp-server-eia`**, which is built and versioned **elsewhere** (separate Git remote). Agents may see both “stranded gap” REST docs and this plan — **they are different products**: the dashboard serves **materialized** projections from the DB; the standalone MCP **calls EIA live** with broader plant-search scope and no stranded metrics unless you add a separate integration.

> **Leave Burnout alone (unless the task is Burnout).** The Burnout app is **done, deployed, and working** (production on Railway; v1 feature-complete). This MCP is **greenfield** in a separate repo — do not risk regressions in the monorepo while building it. Work for the MCP belongs in the **`mcp-server-eia`** checkout: **copy** or adapt logic from `eia_client.py` / refresh modules there — do **not** refactor, rename, or “clean up” **`frontend/`**, **`backend/`**, API routes, Alembic, or pipeline scripts in the StrandedAssets monorepo as a side effect of MCP work. That code path is **live** (local + Railway) and easy to break. If something truly must change in the monorepo (e.g. a bugfix in **`eia_client.py`** shared by both products), treat it as a **separate, explicit** change with tests / smoke checks on refresh + API — never as an accidental edit while building the standalone server.

### Related documentation (this monorepo)

- **[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)** — Burnout product, REST API, NL query, optional **Postgres-backed** MCP tool shapes (`list_plants`, etc.). Not the same as this standalone EIA MCP.
- **[`docs/EIA_DATA_PIPELINE.md`](docs/EIA_DATA_PIPELINE.md)** — How the **Burnout backend** uses the EIA API today: **`eia_client.py`** patterns, the three refresh pipelines (inventory → metrics → AEO), what lands in which tables, refresh order, and how **`projection.py`** sits downstream. **Read this before extracting** code into `mcp-server-eia`: it maps **routes ↔ modules ↔ stored data** and explains why the dashboard is **materialized Postgres** while this MCP is **live EIA** per tool call.

### Pre-build decisions (agreed)

| Topic | Decision |
|-------|----------|
| **Scope vs Burnout** | This MCP is **broader** than the dashboard dataset: more fuels and routes where useful (e.g. `search_power_plants`), not limited to Burnout’s coal/gas + ≥100 MW inventory. |
| **`plant_id` format** | **Canonical:** `{STATE}-{plantid}` — **2-letter US state** + **hyphen** + EIA **`plantid`** (same as Burnout’s `data_refresh` key, e.g. `OH-3470`). **Always include state** so IDs are unique and match EIA-860/923 joins. Document this in every tool that takes `plant_id`; reject or normalize ambiguous bare numeric IDs with a clear error. |
| **AEO / `get_aeo_projections`** | **Learn** from **`aeo_refresh.py`** (table paths, scenario codes, EMM handling) but **do not** treat it as a hard spec — simplify or extend categories if it improves the MCP tool UX. |
| **Python MCP library** | Use the **official [`mcp`](https://pypi.org/project/mcp/)** Python SDK (stdio server) for spec alignment and maintenance; avoid an extra wrapper unless we hit a concrete gap. |
| **Repo workflow** | **Develop in a local directory** that will become the **separate Git** `mcp-server-eia` remote (no nesting inside the Burnout monorepo); push to GitHub when ready. |

---

## Why This Is Differentiated

There are a couple of existing EIA MCP servers (zen-tradings/eia-mcp, ebarros23/mcp-energy). They're thin wrappers that expose raw EIA routes as tools — you still need to know facet codes, field names, and API structure to use them. They're "APIs relabeled as MCP."

This server is different because:

1. **Domain-aware tools, not route mirrors.** Instead of `query_eia_route(path="electricity/facility-fuel", facets={...})`, you get `get_plant_operations(plant_id="OH-3470", years=[2022, 2023])`. The tool handles generator-vs-plant aggregation, facet encoding, pagination, and returns clean data.

2. **Cross-route joins the API can't do.** EIA splits plant metadata (860), operations (923), prices, and capacity across different routes. A tool like `get_plant_profile` pulls from multiple routes in one call and returns a coherent picture — something that takes 3-4 separate API calls to assemble manually.

3. **AEO projections made usable.** The AEO API is the single most confusing part of the EIA system — table IDs, scenario codes, release paths, EMM region facets. This MCP server translates `get_aeo_projections(category="fuel_prices", fuel_type="gas")` into the right table/scenario/release combination.

---

## EIA API Landscape — Reference

The EIA API v2 has 14 top-level route families. The core v1 tools use routes from `electricity`, `aeo`, and `seds`. The optional expansion phase adds routes from `natural-gas`, `steo`, and `electricity/rto`.

| Route | Name | v1 Tools | Expansion |
|-------|------|----------|-----------|
| `electricity` | Electricity | `operating-generator-capacity`, `facility-fuel`, `retail-sales`, **`electric-power-operational-data`** (generation mix) | `rto/*`, `state-electricity-profiles` |
| `aeo` | Annual Energy Outlook | Fuel prices, wholesale prices, capacity by region | — |
| `seds` | State Energy Data System | CO2 emissions by state/sector/fuel | — |
| `natural-gas` | Natural Gas | — | Prices, consumption, storage |
| `steo` | Short-Term Energy Outlook | — | 18-month price/demand forecasts |
| `coal` | Coal | — | Shipments, production |
| `petroleum` | Petroleum | — | Future |
| `total-energy` | Total Energy | — | Future |
| `co2-emissions` | State CO2 (deprecated) | — | Redirects to SEDS |
| `nuclear-outages`, `crude-oil-imports`, `international`, `ieo`, `densified-biomass` | Various | — | Future / unlikely |

---

## Tool Design Principles

- **One tool = one question a human would ask.** Not one tool per API route.
- **Tools handle the pain.** Generator-to-plant aggregation, facet code translation (e.g., "coal" → BIT/SUB/LIG/RC), pagination across large result sets.
- **Sensible defaults.** Most recent year if no year specified. All fuel types if no filter. Top 25 results if no limit.
- **Rich tool descriptions.** MCP tool descriptions are what the LLM reads to decide which tool to use — invest in these.

### Standard Response Envelope

Every tool returns the same top-level shape. EIA routes vary wildly in field names, date formats (`"2023"` vs `"2023-06"` vs `"2023-06-15T14"`), and units — the envelope normalizes this so the LLM always gets a predictable structure.

```json
{
  "data": [ ... ],
  "meta": {
    "source": "electricity/facility-fuel",
    "frequency": "annual",
    "period_format": "YYYY",
    "units": { "net_generation": "MWh", "fuel_consumption": "MMBtu" },
    "record_count": 3,
    "notes": [
      "Results combine EIA codes BIT, SUB, LIG, RC under 'coal'",
      "Capacity factor computed from nameplate via EIA-860"
    ]
  }
}
```

Rules:
- `data` is always an array (even for single-record tools like `get_plant_profile` — wrap in `[{...}]`).
- `meta.units` documents every numeric field's unit so the LLM doesn't have to guess.
- `meta.notes` is an array of strings for transparency: fuel code consolidation, computed vs raw fields, data vintage, etc. Empty array if nothing to flag.
- `meta.source` identifies the EIA route(s) used — useful for debugging and credibility.

### Default Sort Order

Every tool that hits a paginated EIA route must specify a sort order in the API call to ensure stable, predictable results across pages. Default: `period` descending (most recent first) unless the tool has a more natural order (e.g., `search_power_plants` sorts by `nameplate_capacity` descending).

### Error Handling

EIA returns 429s frequently, especially during AEO-heavy runs. The `eia_client.py` retry logic (already built in Burnout) handles this. Tools should surface human-readable messages when retries are exhausted:
- Rate limit: `"EIA API rate limit reached. Try again in a moment."`
- Timeout / 5xx: `"EIA API is temporarily unavailable."`
- Empty results (invalid facet combo): `"No data found for this combination. Check that the state/fuel/frequency values are valid."`

Never expose raw HTTP status codes or stack traces through MCP tool responses.

---

## Core Tools (v1 — ship these)

These 6 tools use EIA routes already wrangled in Burnout, plus 2 straightforward new routes.

### 1. `search_power_plants`

Search the EIA generator inventory (EIA-860) for power plants matching criteria.

```
Parameters:
  fuel_type: string (coal, gas, oil, nuclear, solar, wind, hydro, all)
             → translates to EIA energy_source_code facets internally
  state: string (2-letter code, optional)
  min_capacity_mw: number (default 0)
  max_capacity_mw: number (optional)
  status: string (operating, standby, retired, planned; default: operating)
  limit: integer (default 25, max 100)

Returns: Array of plants with:
  plant_id, name, state, county, latitude, longitude,
  primary_fuel, nameplate_mw, commission_year, operator,
  planned_retirement_year, balancing_authority
```

**Handles:** Generator-to-plant aggregation (sums capacity across generators at same plant, picks primary fuel by largest MW share), fuel code translation ("coal" → BIT/SUB/LIG/RC), pagination.

**Reuses from Burnout:** `data_refresh.py` aggregation logic — extract the generator→plant rollup, drop DB upserts.

**EIA route:** `electricity/operating-generator-capacity`

---

### 2. `get_plant_operations`

Get operational data (generation, fuel consumption, efficiency) for a specific plant over time. Wraps EIA Form 923 facility-fuel data.

```
Parameters:
  plant_id: string (required)
  years: array of integers (optional; default: most recent 3 years available)
  frequency: string (annual or monthly; default: annual)

Returns: Array by year/month with:
  net_generation_mwh, fuel_consumption_mmbtu,
  capacity_factor, heat_rate
```

**Handles:** Pagination, `fuel2002=ALL` / `primeMover=ALL` for plant-level totals, capacity factor computation (requires nameplate from 860 — makes an internal call to get it).

**Reuses from Burnout:** `metrics_refresh.py` — the CF/heat-rate computation logic is identical. Extract it, drop DB writes.

**EIA route:** `electricity/facility-fuel`

---

### 3. `get_plant_profile`

Comprehensive profile combining inventory + operations for one plant. The "tell me everything about this plant" tool — makes multiple EIA API calls internally.

```
Parameters:
  plant_id: string (required)

Returns: {
  metadata: {
    name, state, county, primary_fuel, nameplate_mw,
    commission_year, age_years, operator,
    planned_retirement_year, latitude, longitude,
    balancing_authority
  },
  recent_operations: [
    { year, net_generation_mwh, capacity_factor, heat_rate, fuel_consumption_mmbtu }
    // last 3 years
  ]
}
```

**Handles:** Cross-route joining (860 inventory + 923 operations in one tool call). This is the tool that most clearly demonstrates why MCP wrapping adds value over raw API access.

**Reuses from Burnout:** Composes the logic from tools 1 and 2 above. No new EIA route knowledge needed.

**EIA routes:** `electricity/operating-generator-capacity` + `electricity/facility-fuel`

---

### 4. `get_electricity_prices`

Retail electricity prices by state and sector.

```
Parameters:
  state: string (2-letter code, optional; omit for national)
  sector: string (residential, commercial, industrial, all; default: all)
             → translates to EIA sectorid facet (RES, COM, IND, ALL)
  start_year: integer (optional)
  end_year: integer (optional; default: most recent available)

Returns: Array of {
  state, sector, year, price_cents_per_kwh,
  revenue_million_dollars, sales_million_kwh
}
```

**Handles:** Sector code translation ("residential" → "RES"), state facet encoding, sensible defaults.

**New route** (not used in Burnout): `electricity/retail-sales` — one of the simplest EIA routes (2 facets: state + sector, 3 data fields).

---

### 5. `get_aeo_projections`

Annual Energy Outlook long-term projections (out to ~2050). This is where the MCP abstraction adds the most value — AEO's API structure (table IDs, scenario codes, release paths, EMM region facets) is genuinely confusing.

```
Parameters:
  category: string (fuel_prices, electricity_prices, capacity, emissions)
             → maps internally to AEO table IDs
  fuel_type: string (optional; coal, gas, oil — for fuel-specific tables)
  region: string (optional; EMM region name like "PJM / East", or omit for national)
  scenario: string (reference, high_oil, low_oil, high_renewables; default: reference)
             → maps to AEO scenario facet code (e.g. "ref2025")
  start_year: integer (optional; default: current year)
  end_year: integer (optional; default: 2050)

Returns: Array of {
  year, value, unit, series_name, scenario, region
}
```

**Handles:** Category → table ID mapping, scenario code translation, EMM region facet encoding, release path construction (`/aeo/{release}/`). The mapping layer is the core value — users don't need to know that "fuel_prices for gas" means table 13 in release 2025 with scenario ref2025.

**Reuses from Burnout:** `aeo_refresh.py` — the table ID mappings, scenario codes, and EMM region handling are already implemented. Extract the mapping logic, drop DB persistence.

**EIA route:** `aeo/{release}`

---

### 6. `get_state_co2_emissions`

CO2 emissions from energy consumption by state, sector, and fuel source.

```
Parameters:
  state: string (required; 2-letter code)
  sector: string (electric_power, residential, commercial, industrial,
          transportation, total; default: total)
  fuel: string (coal, natural_gas, petroleum, total; default: total)
  start_year: integer (optional; default: 10 years ago)
  end_year: integer (optional; default: most recent)

Returns: Array of {
  year, emissions_million_metric_tons, state, sector, fuel
}
```

**Handles:** SEDS series ID construction (CO2 series follow a naming pattern), sector/fuel code mapping.

**New route** (not used in Burnout): `seds` — CO2 emissions data moved here from the deprecated `co2-emissions` route. Straightforward once the SEDS series ID naming convention is understood.

---

## Architecture

```
mcp-server-eia/
├── src/
│   └── mcp_server_eia/
│       ├── __init__.py
│       ├── server.py          ← MCP server entry point (FastMCP or mcp SDK)
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── plants.py      ← search_power_plants, get_plant_operations, get_plant_profile
│       │   ├── prices.py      ← get_electricity_prices
│       │   ├── projections.py ← get_aeo_projections
│       │   └── emissions.py   ← get_state_co2_emissions
│       ├── eia_client.py      ← HTTP client (pagination, retries, rate limiting)
│       ├── mappings.py        ← Fuel codes, AEO table IDs, sector codes, state codes
│       └── config.py          ← EIA_API_KEY from env
├── tests/
│   ├── test_plants.py
│   ├── test_mappings.py
│   └── ...
├── README.md
├── pyproject.toml             ← deps + metadata (PyPI publishing is a stretch goal)
├── LICENSE                    ← MIT
└── .github/
    └── workflows/
        └── test.yml           ← CI (optional for v1)
```

### Key Implementation Details

**EIA Client (`eia_client.py`):**
Copy from Burnout backend. Already handles:
- Paginated `fetch_data` / `iter_data` with `offset` + `length`
- Route metadata discovery (`get_route_metadata`) for finding latest available periods
- Retry on 429/502/503/504 with bounded backoff
- `httpx`-based GET with `EIA_API_KEY` auth

Generalize: strip any Burnout-specific imports (SQLAlchemy, DB sessions). The client should be a pure HTTP wrapper with no framework dependencies.

**Mappings (`mappings.py`):**
This is where a big chunk of the value lives. The EIA API uses cryptic codes that users shouldn't have to know:

```python
FUEL_CODE_MAP = {
    "coal": ["BIT", "SUB", "LIG", "RC", "WC", "SC"],
    "gas": ["NG"],
    "oil": ["DFO", "RFO", "JF", "KER", "PC", "WO"],
    "nuclear": ["NUC"],
    "solar": ["SUN"],
    "wind": ["WND"],
    "hydro": ["WAT"],
}

SECTOR_CODE_MAP = {
    "residential": "RES",
    "commercial": "COM",
    "industrial": "IND",
    "all": "ALL",
}

AEO_TABLE_MAP = {
    # category → table ID (or fuel-keyed dict)
    "fuel_prices": {"coal": 15, "gas": 13, "oil": 12},
    "electricity_prices": 8,
    "capacity": 9,
    "emissions": 18,
}

AEO_SCENARIO_MAP = {
    "reference": "ref2025",
    "high_oil": "highmacro",
    "low_oil": "lowmacro",
    # etc. — pulled from Burnout's aeo_refresh.py
}

# EMM region labels, state abbreviations, BA code → human name, etc.
```

**MCP Framework:**
- Use `fastmcp` (simpler API) or official `mcp` Python SDK
- **stdio transport only** for v1 — this is what Claude Desktop, Cursor, and Claude Code expect. No SSE / HTTP hosting needed.
- Entry point: `python -m mcp_server_eia.server`
- Users clone the repo, install deps, and point their MCP client config at the entry point

---

## What Transfers From Burnout

Pipeline context (EIA routes, table names, refresh order): **[`docs/EIA_DATA_PIPELINE.md`](docs/EIA_DATA_PIPELINE.md)**.

| Burnout Module | Reuse in MCP | What to Extract |
|---------------|-------------|-----------------|
| `eia_client.py` | **Yes — core** | Copy whole file, strip SQLAlchemy imports. This is the foundation. |
| `data_refresh.py` | **Aggregation logic** | Generator → plant rollup (sum MW, pick primary fuel, compute commission year). Drop DB upserts. |
| `metrics_refresh.py` | **CF / heat-rate math** | Capacity factor and heat rate computation from 923 data. Drop DB writes. |
| `aeo_refresh.py` | **Table/scenario/region mappings** | AEO table IDs, scenario codes, EMM region facet values, release path construction. Drop DB persistence. |
| `projection.py` | **No** | Stranded asset model is Burnout-specific. |
| DB models / schemas | **No** | MCP server is stateless. |

---

## Build Order

**Status:** Phases 1–4 are **complete** in **[mcp-server-eia](https://github.com/abrose1/mcp-server-eia)** (`v0.1.0+`). The following steps remain as a **historical checklist** for anyone re-reading the plan.

### Phase 1: Foundation + First Tool (~1.5 hr)

1. Create repo, `pyproject.toml` with `fastmcp` (or `mcp`) + `httpx` dependencies
2. Copy `eia_client.py` from Burnout backend — strip DB imports, verify it works standalone
3. Build `mappings.py` — fuel code map, state codes (pull from Burnout where applicable)
4. Set up `server.py` with MCP framework, register first tool
5. Implement `search_power_plants`:
   - Extract generator→plant aggregation from `data_refresh.py`
   - Wire up fuel code translation from `mappings.py`
   - Return clean JSON (no DB, no ORM objects)
6. Test with MCP inspector or Claude Desktop: "Show me coal plants in Ohio over 500 MW"

### Phase 2: Plant Operations + Profile (~1 hr)

7. Implement `get_plant_operations`:
   - Extract 923 computation logic from `metrics_refresh.py`
   - Internal call to 860 for nameplate (needed for CF calculation)
   - Return year-by-year operations data
8. Implement `get_plant_profile`:
   - Compose tools 1 + 2 internally
   - Single call returns metadata + operations
9. Test: "Tell me everything about plant OH-3470" / "What's plant GA-6166's heat rate trend?"

### Phase 3: Prices, Projections, Emissions (~2 hr)

10. Implement `get_electricity_prices`:
    - New route (`electricity/retail-sales`), simple facets
    - Sector code translation from `mappings.py`
11. Implement `get_aeo_projections`:
    - Extract table ID / scenario / region mappings from `aeo_refresh.py`
    - Build the category → table ID translation layer
    - This is the most complex tool — budget extra time
12. Implement `get_state_co2_emissions`:
    - New route (`seds`), learn SEDS series ID patterns
    - Straightforward once the ID convention is understood
13. Test: "AEO gas price projections through 2050" / "Texas CO2 trends" / "California electricity prices"

### Phase 4: README + Ship to GitHub (~1 hr)

14. Write README:
    - "Why not just use the EIA API?" section (the pitch)
    - Installation: clone repo, `pip install -r requirements.txt`, set `EIA_API_KEY`
    - Claude Desktop / Cursor config JSON snippet (stdio, pointing at local clone)
    - Tool reference: each tool with parameters and example queries
    - 2-3 example conversation screenshots from Claude Desktop
15. Push to GitHub as public repo — **done** (`abrose1/mcp-server-eia`)
16. Cross-reference in Burnout dashboard README — **done** (see StrandedAssets **`README.md`** — documentation map)

---

## Optional Expansion Phase (~3–4 additional hours cumulative)

These tools add breadth beyond v1. **Start with** **`get_generation_mix`** and **`get_capacity_by_fuel`** (same `electricity` family as v1; fastest wins). After that, each remaining tool is largely independent — new route families (`natural-gas`, `steo`, `rto`, etc.) take more discovery time.

### `get_fuel_prices` — **shipped** (`mcp-server-eia` **`v0.3.0`**)
Historical spot/market fuel prices — natural gas (Henry Hub, U.S. citygate, U.S. wellhead), coal (open-market price by basin), crude benchmarks (WTI, Brent). Distinct from **`get_aeo_projections(category="fuel_prices")`** (AEO projections).
```
Parameters:
  fuel: string (natural_gas, coal, crude_oil)
  price_type: string (henry_hub, citygate, wellhead, appalachian, powder_river, wti, brent, …)
  frequency: string (daily, weekly, monthly, annual) — constrained by EIA route (e.g. coal market sales: annual only; sum-route gas: monthly/annual)
  start_year / end_year: integer (optional)
Returns: Array of { period, price, unit }
```
Routes: `natural-gas/pri/fut`, `natural-gas/pri/sum`, `coal/market-sales-price`, `petroleum/pri/spt`

Example natural-language prompts:

- "Henry Hub natural gas spot prices for 2024 by month"
- "Citygate natural gas prices (U.S.) for 2022 monthly"
- "Coal open-market price in the Powder River Basin, annual from 2020 through 2023"
- "WTI spot crude oil price monthly for 2023"
- "Brent crude spot price daily in January 2024"

### `get_generation_mix` (~30 min)
Electricity generation breakdown by fuel type for a state or nationally.
```
Parameters:
  state: string (optional), year: integer (optional), frequency: string
Returns: Array of { fuel_type, generation_mwh, share_pct }
```
Route: `electricity/electric-power-operational-data`

### `get_capacity_by_fuel` (~30 min)
Installed generating capacity by fuel type — useful for tracking renewable buildout vs fossil.
```
Parameters:
  state: string (optional), fuel_type: string (optional), year: integer (optional)
Returns: Array of { fuel_type, capacity_mw, plant_count }
```
Route: `electricity/operating-generator-capacity` (aggregated differently than `search_power_plants`)

### `get_natural_gas_summary` (~45 min)
Supply/demand picture — production, consumption by sector, underground storage, imports/exports.
```
Parameters:
  state: string (optional), frequency: string, start_year: integer
Returns: { production, consumption_by_sector, storage, imports, exports }
```
Routes: `natural-gas/sum`, `natural-gas/cons`, `natural-gas/stor`

### `get_steo_forecast` (~30 min)
Short-Term Energy Outlook — 18-month forecasts for prices, production, demand.
```
Parameters:
  series: string (crude_oil_price, natural_gas_price, electricity_demand, etc.)
  frequency: string (monthly or quarterly)
Returns: Array of { period, value, unit } — historical actuals + forecast
```
Route: `steo` (maps human-readable names to STEO series IDs)

### `get_state_energy_profile` (~45 min)
Comprehensive state profile — generation mix, consumption by sector, prices, CO2, top plants.
```
Parameters:
  state: string (required)
Returns: { generation_mix, consumption_by_sector, electricity_prices, co2_trend, top_plants }
```
Routes: Composite — `electricity/state-electricity-profiles` + `seds` + `retail-sales` + `operating-generator-capacity`

### `get_grid_demand` (~30 min)
Real-time / recent hourly-daily electricity demand by balancing authority.
```
Parameters:
  region: string (CISO, PJM, MISO, ERCO, etc.), frequency: string (hourly, daily),
  start_date / end_date: string (ISO date)
Returns: Array of { period, demand_mwh, region }
```
Route: `electricity/rto/daily-region-data` or `electricity/rto/region-data`

### `get_grid_generation_by_fuel` (~30 min)
What's actually running right now — generation by fuel type for a balancing authority.
```
Parameters:
  region: string (BA code), frequency: string, start_date / end_date
Returns: Array of { period, fuel_type, generation_mwh }
```
Route: `electricity/rto/fuel-type-data`

---

## Scope Summary

| Scope | Tools | New EIA Routes | Estimate |
|-------|-------|----------------|----------|
| **v1** | 6 tools | 2 new (`retail-sales`, `seds`) | **Shipped** — see repo |
| **Expansion (next)** | **Shipped** — **`get_generation_mix`**, **`get_capacity_by_fuel`** | `electric-power-operational-data`; 860 agg by fuel | Done in **`v0.2.0`** |
| **Expansion (rest)** | +5 tools (after `get_fuel_prices`) | `steo`, `rto/*`, composites, etc. | +3–4 hours |
| **Future** | Petroleum (beyond spot), international, nuclear | Many | TBD |

v1, the first **`electricity`**-family expansion tools (**`v0.2.0`**), and **`get_fuel_prices`** (**`v0.3.0`**) are **released** on GitHub. **Next priority** is the remaining **Optional Expansion Phase** tools in this doc.

---

## Stretch Goals (Post-v1)

These are separate from the expansion tools — they're about distribution and hosting, not new functionality.

- **PyPI packaging:** Make it `pip install mcp-server-eia` with a proper `mcp-server-eia` CLI entry point. Requires setting up `pyproject.toml` entry points, building the package, and publishing.
- **MCP directory submission:** Submit to mcp.so and/or Smithery. Requires the PyPI package (or at minimum a clean install path) plus directory-specific metadata.
- **Remote hosting (SSE):** Host as a Railway service alongside Burnout with an SSE endpoint, so people can connect without cloning. Adds auth questions (your EIA key vs. BYOK) and infra cost. Nice for demos but not needed for the LinkedIn story.

---

## README Structure

```markdown
# mcp-server-eia

Give any AI agent structured access to U.S. energy data from the
Energy Information Administration.

## Why not just use the EIA API directly?

Because the EIA API is powerful but painful:
- Fuel types are coded as BIT, SUB, LIG, RC, NG, DFO…
  not "coal" and "gas"
- Plant data lives at the generator level — a single plant
  can have 12 generators across 3 fuel types that need aggregating
- AEO projections hide behind cryptic table IDs, scenario codes,
  and release paths
- Getting a complete picture of one power plant requires
  joining 3+ separate API routes
- Pagination behavior varies across route families

This MCP server handles all of that.

## Example Queries (via Claude Desktop / Cursor)

> "What coal plants over 500 MW are still operating in Ohio?"
> "Give me a full profile of plant GA-6166"
> "What does the AEO reference case project for gas prices through 2050?"
> "Show me CO2 emission trends in Texas over the last decade"
> "What are residential electricity prices in California?"

## Quick Start

### Install
git clone https://github.com/YOUR_USERNAME/mcp-server-eia.git
cd mcp-server-eia
pip install -r requirements.txt

### Set your EIA API key
export EIA_API_KEY=your-key-here
# Get one free: https://www.eia.gov/opendata/register.php

### Claude Desktop
Add to ~/Library/Application Support/Claude/claude_desktop_config.json:
{
  "mcpServers": {
    "eia": {
      "command": "python",
      "args": ["-m", "mcp_server_eia.server"],
      "cwd": "/path/to/mcp-server-eia",
      "env": { "EIA_API_KEY": "your-key-here" }
    }
  }
}

### Cursor
Add the same config in Cursor's MCP settings.

## Available Tools
[tool reference with parameters and example queries for each]

## Built With
- Python, FastMCP / mcp SDK
- EIA Open Data API v2
- httpx

## Related
- [Burnout](link) — Stranded asset early warning dashboard
  built on the same EIA data

## License
MIT
```

---

## LinkedIn Angle

With this as a separate deliverable, the post story becomes:

*"I built two things for the climate-tech AI ecosystem:*

*1. **Burnout** — a stranded asset early warning dashboard that identifies which US fossil fuel plants are most at risk of becoming economically unviable before retirement. [live link]*

*2. **mcp-server-eia** — a standalone MCP server that gives any AI agent structured access to EIA energy data. Power plant inventory, operational metrics, AEO projections, state emissions — all through natural language. Connect it to Claude Desktop and ask 'What coal plants in the Southeast have the worst heat rates?' [repo link]*

*The MCP server started as a component of the dashboard, but I realized it had independent value — anyone working on energy/climate AI projects can use it."*
