"""
Form EIA-923 facility-fuel (annual): net generation and fuel use for plants already in ``plants``.

Uses ``fuel2002=ALL`` + ``primeMover=ALL`` rows (plant-level totals). Derives capacity factor,
heat rate, and a simple fuel-cost proxy (heat rate × rough dollars/MMBtu by fuel type until AEO).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.schemas import Plant, PlantMetric, utcnow
from app.services.eia_client import EIAClient

logger = logging.getLogger(__name__)

FACILITY_FUEL_ROUTE = "electricity/facility-fuel"
# Years of annual 923 data to pull (inclusive end year = latest available).
# Wider window = more history for charts/trends; larger API responses per state batch.
ANNUAL_YEARS_LOOKBACK = 10
# EIA facility-fuel: facet multiple plant codes per request (avoids scanning full states).
PLANT_CODE_BATCH = 40
UPSERT_BATCH = 500

# Rough national average delivered fuel prices ($/MMBtu) for a historical $/MWh proxy.
# Projection engine will use AEO series; these only populate plant_metrics.fuel_cost_per_mwh.
PROXY_COAL_USD_PER_MMBTU = 2.5
PROXY_GAS_USD_PER_MMBTU = 3.5


def _parse_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _split_plant_id(plant_id: str) -> tuple[str, str] | None:
    parts = plant_id.split("-", 1)
    if len(parts) != 2 or len(parts[0]) != 2:
        return None
    state, code = parts[0].strip().upper(), parts[1].strip()
    if not code:
        return None
    return state, code


def _proxy_usd_per_mmbtu(primary_fuel: str) -> float:
    p = (primary_fuel or "").lower()
    if p == "gas":
        return PROXY_GAS_USD_PER_MMBTU
    return PROXY_COAL_USD_PER_MMBTU


def _chunks(sorted_codes: list[str], size: int):
    for i in range(0, len(sorted_codes), size):
        yield sorted_codes[i : i + size]


def _group_plant_codes_by_state(plant_ids: list[str]) -> dict[str, set[str]]:
    by_state: dict[str, set[str]] = {}
    for pid in plant_ids:
        sp = _split_plant_id(pid)
        if sp is None:
            logger.warning("Skip malformed plant_id: %s", pid)
            continue
        state, code = sp
        by_state.setdefault(state, set()).add(code)
    return by_state


def _metric_row(
    *,
    plant_id: str,
    year: int,
    net_mwh: float,
    mmbtu: float,
    nameplate_mw: float,
    primary_fuel: str,
) -> dict[str, Any]:
    hours = 8760.0
    cap = nameplate_mw * hours
    cf = (net_mwh / cap) if cap > 0 else None
    hr = (mmbtu / net_mwh) if net_mwh > 0 else None
    fuel_cost = (hr * _proxy_usd_per_mmbtu(primary_fuel)) if hr is not None else None
    now = utcnow()
    return {
        "plant_id": plant_id,
        "year": year,
        "net_generation_mwh": net_mwh,
        "capacity_factor": cf,
        "fuel_consumption_mmbtu": mmbtu,
        "fuel_cost_per_mwh": fuel_cost,
        "heat_rate": hr,
        "updated_at": now,
    }


def _upsert_metrics_batch(session: Session, batch: list[dict[str, Any]]) -> None:
    if not batch:
        return
    stmt = pg_insert(PlantMetric).values(batch)
    stmt = stmt.on_conflict_do_update(
        index_elements=["plant_id", "year"],
        set_={
            "net_generation_mwh": stmt.excluded.net_generation_mwh,
            "capacity_factor": stmt.excluded.capacity_factor,
            "fuel_consumption_mmbtu": stmt.excluded.fuel_consumption_mmbtu,
            "fuel_cost_per_mwh": stmt.excluded.fuel_cost_per_mwh,
            "heat_rate": stmt.excluded.heat_rate,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    session.execute(stmt)


def refresh_plant_metrics(session: Session) -> dict[str, Any]:
    """
    Pull recent annual facility-fuel totals and upsert ``plant_metrics`` for every ``plants`` row.

    Commits on success; rolls back on error.
    """
    client = EIAClient()
    try:
        last_year = client.get_latest_facility_fuel_annual_year()
        start_year = last_year - (ANNUAL_YEARS_LOOKBACK - 1)
        start_s = str(start_year)
        end_s = str(last_year)
        logger.info("Facility-fuel annual window: %s–%s", start_s, end_s)

        plants = session.execute(select(Plant.plant_id, Plant.nameplate_mw, Plant.primary_fuel)).all()
        if not plants:
            session.commit()
            return {
                "ok": True,
                "plants_in_db": 0,
                "metrics_upserted": 0,
                "years": [start_year, last_year],
                "message": "no plants in database",
            }

        by_id = {p.plant_id: (float(p.nameplate_mw or 0.0), p.primary_fuel or "coal") for p in plants}
        by_state = _group_plant_codes_by_state(list(by_id.keys()))

        payloads: dict[tuple[str, int], dict[str, Any]] = {}
        for state, codes in sorted(by_state.items()):
            if not codes:
                continue
            for batch in _chunks(sorted(codes), PLANT_CODE_BATCH):
                for row in client.iter_data(
                    FACILITY_FUEL_ROUTE,
                    frequency="annual",
                    data_fields=["generation", "total-consumption-btu"],
                    facets={"state": [state], "fuel2002": ["ALL"], "plantCode": batch},
                    page_size=5000,
                    start=start_s,
                    end=end_s,
                ):
                    if row.get("primeMover") != "ALL":
                        continue
                    pcode = str(row.get("plantCode") or "").strip()
                    plant_id = f"{state}-{pcode}"
                    if plant_id not in by_id:
                        continue
                    period = row.get("period")
                    if not period:
                        continue
                    try:
                        y = int(str(period)[:4])
                    except ValueError:
                        continue
                    net = _parse_float(row.get("generation"))
                    mmbtu = _parse_float(row.get("total-consumption-btu"))
                    if net is None or mmbtu is None:
                        continue
                    nm, pf = by_id[plant_id]
                    key = (plant_id, y)
                    payloads[key] = _metric_row(
                        plant_id=plant_id,
                        year=y,
                        net_mwh=net,
                        mmbtu=mmbtu,
                        nameplate_mw=nm,
                        primary_fuel=pf,
                    )

        rows_out = list(payloads.values())
        for i in range(0, len(rows_out), UPSERT_BATCH):
            _upsert_metrics_batch(session, rows_out[i : i + UPSERT_BATCH])

        session.commit()
        return {
            "ok": True,
            "plants_in_db": len(by_id),
            "metrics_upserted": len(rows_out),
            "years": [start_year, last_year],
        }
    except Exception:
        logger.exception("Plant metrics refresh failed")
        session.rollback()
        raise
    finally:
        client.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    from app.models.database import get_session_factory

    sf = get_session_factory()
    with sf() as session:
        out = refresh_plant_metrics(session)
        print(out)


if __name__ == "__main__":
    main()
