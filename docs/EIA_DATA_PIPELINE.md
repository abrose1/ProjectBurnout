# EIA data pipeline (Burnout backend)

This document describes how the **Stranded Assets / Burnout** backend pulls from the U.S. Energy Information Administration (EIA) Open Data API, what is stored, and how it feeds projections and the API. Use it when planning **MCP tools**, onboarding, or explaining the system to others.

**Related:** [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) (full architecture), [eia-mcp-server-plan.md](../eia-mcp-server-plan.md) (standalone EIA-only MCP — no database). **Implemented repo:** [github.com/abrose1/mcp-server-eia](https://github.com/abrose1/mcp-server-eia) (v1 shipped; **next tools** in that spec: **`get_generation_mix`**, **`get_capacity_by_fuel`**).

---

## External source and client

- **API:** [EIA Open Data API v2](https://api.eia.gov/v2/) — base URL `https://api.eia.gov/v2`.
- **Auth:** `EIA_API_KEY` (see `backend/.env`).
- **Client:** `backend/app/services/eia_client.py` — **httpx** GETs with retries on transient HTTP errors (429, 502, 503, 504), bounded exponential backoff.
- **Patterns:**
  - **`/data/`** — paginated pulls via `fetch_data` / `iter_data` with `frequency`, facets, optional `start` / `end`, and selected `data[]` fields.
  - **Route metadata** — `get_route_metadata` to discover **latest** periods (e.g. newest `YYYY-MM` for monthly routes, newest calendar year for annual routes).

There is **no** separate scraper or custom model hitting government sites; ingestion is **batch EIA HTTP** into Postgres, then the app serves **materialized** data.

---

## Three refresh pipelines

| Pipeline | EIA route(s) | Module | What it pulls | Stored as |
|----------|----------------|--------|----------------|-----------|
| **Plant inventory** | `electricity/operating-generator-capacity` (monthly) | `app/services/data_refresh.py` | Operable **coal + gas** generators (`energy_source_code` coal codes + `NG`, `status=OP`), **single latest inventory month** (from metadata). Fields include nameplate MW, lat/lon, operating / planned-retirement month, county, plant identifiers. | **`plants`** (+ **`refresh_log`**) |
| **Plant metrics** | `electricity/facility-fuel` (annual) | `app/services/metrics_refresh.py` | Form **923–style** facility fuel: **generation** and **total fuel consumption** for plants already in `plants`, ~**10-year** lookback, batched by state + `plantCode`, `fuel2002=ALL`, `primeMover=ALL` plant totals. | **`plant_metrics`** |
| **AEO projection inputs** | `aeo/{release}` (annual) + facet metadata | `app/services/aeo_refresh.py` | **Annual Energy Outlook** reference case: national **gas/coal** fuel prices ($/MMBtu); per-**EMM region** wholesale price, capacity, **wind/solar** (and derived renewable share). EMM region names come from EIA facet metadata. | **`fuel_price_projections`**, **`regional_price_projections`**, **`regional_renewables`** |

**Refresh order (for a full rebuild):** inventory → metrics → AEO → projection. See `scripts/refresh_eia_pipeline.sh` and the implementation plan.

---

## Inventory: what we aggregate and keep

- Source rows are **generator-level**; the code aggregates by **`stateid`–`plantid`** into a single plant key.
- **Fossil filter:** coal codes (BIT, SUB, LIG, RC) + natural gas (`NG`) — see `COAL_ENERGY_CODES` / `GAS_ENERGY_CODES` in `eia_client.py`.
- **Size filter:** plants with total nameplate **&lt; 100 MW** are dropped.
- **Derived fields:** primary fuel (coal vs gas by MW), commission year, planned retirement vs **projected** retirement (planned date if present, else commission + assumed life: coal 45 yr, gas 30 yr).
- **`emm_region`** on `plants` may start unset; the projection pass can fill it from a **state → EMM name** map when matching AEO regional tables.

---

## Metrics: what we compute

From annual facility-fuel data, per plant and year:

- **Capacity factor** (from net generation vs nameplate × hours).
- **Heat rate** (MMBtu/MWh).
- **Fuel cost proxy ($/MWh)** — heat rate × rough national **$/MMBtu** by fuel type until AEO-driven economics in the projection layer.

---

## AEO: what we use in the model

- **National** nominal gas and coal prices by year.
- **Per EMM region:** wholesale generation price ($/MWh), total capacity, wind + solar MW (for displacement-style logic in the projection engine).
- Series IDs and table IDs are **EIA-specific**; see `aeo_refresh.py` and the implementation plan’s projection section.

---

## Downstream: projections and API

- **`app/services/projection.py`** combines:
  - plant facts (`plants`),
  - latest operational metrics (`plant_metrics`),
  - forward **fuel** and **regional** series from AEO tables,
  - fixed **economic/engineering rules** (O&M, displacement coefficients, size/age factors, stranded-year logic per the implementation plan),
  and writes **`plant_projections`** (including timing vs retirement for stranded-asset views).

- **REST API and UI** read from Postgres (not live EIA on every request). **Natural-language query** uses the same conceptual schema (plants, regions, stranded gap) backed by the database.

---

## MCP vs this pipeline

- **Burnout backend MCP (if added):** would expose **read/query** (and optionally **trigger refresh**) against this **same** Postgres-backed pipeline — aligned with `nl_query.py` tool shapes in the implementation plan.
- **Standalone EIA MCP** (see `eia-mcp-server-plan.md`; code: **[mcp-server-eia](https://github.com/abrose1/mcp-server-eia)**): **stateless** EIA API passthrough; **no** Postgres, **no** `projection.py` / stranded-gap metrics unless you deliberately call a hosted Burnout API.
