"""
Phase 1: pull EIA operating-generator-capacity (coal + gas), aggregate to plant level,
keep plants with total nameplate ≥ 100 MW, upsert ``plants`` + ``refresh_log``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, not_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.schemas import Plant, RefreshLog, utcnow
from app.services.eia_client import COAL_ENERGY_CODES, GAS_ENERGY_CODES, EIAClient

logger = logging.getLogger(__name__)

OPERATING_GENERATOR_ROUTE = "electricity/operating-generator-capacity"
MIN_NAMEPLATE_MW = 100.0
COAL_LIFE_YEARS = 45
GAS_LIFE_YEARS = 30
UPSERT_BATCH = 250


def _year_from_iso_ym(s: str | None) -> int | None:
    if not s or not isinstance(s, str):
        return None
    parts = s.strip().split("-")
    if not parts:
        return None
    try:
        return int(parts[0])
    except ValueError:
        return None


def _clip(s: str | None, max_len: int) -> str:
    if s is None:
        return ""
    t = str(s).strip()
    return t[:max_len] if len(t) > max_len else t


def _parse_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@dataclass
class _Agg:
    plant_name: str = ""
    state: str = ""
    county: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    operator_name: str | None = None
    balancing_auth: str | None = None
    nameplate_mw: float = 0.0
    coal_mw: float = 0.0
    gas_mw: float = 0.0
    op_years: list[int] = field(default_factory=list)
    planned_retirement_years: list[int] = field(default_factory=list)


def _primary_fuel_from_mw(coal_mw: float, gas_mw: float) -> str:
    if coal_mw <= 0 and gas_mw <= 0:
        return "coal"
    return "coal" if coal_mw >= gas_mw else "gas"


def _fossil_energy_codes() -> list[str]:
    return list(dict.fromkeys([*COAL_ENERGY_CODES, *GAS_ENERGY_CODES]))


def _aggregate_generators(rows: list[dict[str, Any]]) -> dict[str, _Agg]:
    by_plant: dict[str, _Agg] = {}
    for row in rows:
        state = row.get("stateid") or ""
        pid = row.get("plantid") or ""
        plant_key = f"{state}-{pid}"
        esc = row.get("energy_source_code") or ""
        mw = _parse_float(row.get("nameplate-capacity-mw")) or 0.0
        if mw <= 0:
            continue

        if plant_key not in by_plant:
            by_plant[plant_key] = _Agg()
        a = by_plant[plant_key]

        if not a.plant_name and row.get("plantName"):
            a.plant_name = _clip(row.get("plantName"), 512)
        if not a.state and state:
            a.state = _clip(state, 2)
        if row.get("county"):
            a.county = _clip(row.get("county"), 128)
        lat = _parse_float(row.get("latitude"))
        lon = _parse_float(row.get("longitude"))
        if lat is not None:
            a.latitude = lat
        if lon is not None:
            a.longitude = lon
        if row.get("entityName"):
            a.operator_name = _clip(row.get("entityName"), 512)
        if row.get("balancing_authority_code"):
            a.balancing_auth = _clip(row.get("balancing_authority_code"), 128)

        a.nameplate_mw += mw
        if esc in COAL_ENERGY_CODES:
            a.coal_mw += mw
        elif esc in GAS_ENERGY_CODES:
            a.gas_mw += mw

        oy = _year_from_iso_ym(row.get("operating-year-month"))
        if oy is not None:
            a.op_years.append(oy)

        pr = _year_from_iso_ym(row.get("planned-retirement-year-month"))
        if pr is not None:
            a.planned_retirement_years.append(pr)

    return by_plant


def _build_plant_row(
    plant_id: str,
    a: _Agg,
) -> dict[str, Any]:
    primary = _primary_fuel_from_mw(a.coal_mw, a.gas_mw)
    life = COAL_LIFE_YEARS if primary == "coal" else GAS_LIFE_YEARS
    commission_year = min(a.op_years) if a.op_years else None

    planned_retirement_year: int | None = None
    if a.planned_retirement_years:
        planned_retirement_year = max(a.planned_retirement_years)

    projected_retirement_year: int | None
    if planned_retirement_year is not None:
        projected_retirement_year = planned_retirement_year
    elif commission_year is not None:
        projected_retirement_year = commission_year + life
    else:
        projected_retirement_year = None

    now = utcnow()
    return {
        "plant_id": _clip(plant_id, 32),
        "plant_name": a.plant_name or plant_id,
        "state": a.state or "",
        "county": a.county,
        "latitude": a.latitude,
        "longitude": a.longitude,
        "emm_region": None,
        "balancing_auth": a.balancing_auth,
        "primary_fuel": primary,
        "nameplate_mw": a.nameplate_mw,
        "commission_year": commission_year,
        "operator_name": a.operator_name,
        "status": "OP",
        "planned_retirement_year": planned_retirement_year,
        "projected_retirement_year": projected_retirement_year,
        "updated_at": now,
    }


def _upsert_plant_batch(session: Session, batch: list[dict[str, Any]]) -> None:
    if not batch:
        return
    stmt = pg_insert(Plant).values(batch)
    stmt = stmt.on_conflict_do_update(
        index_elements=["plant_id"],
        set_={
            "plant_name": stmt.excluded.plant_name,
            "state": stmt.excluded.state,
            "county": stmt.excluded.county,
            "latitude": stmt.excluded.latitude,
            "longitude": stmt.excluded.longitude,
            "emm_region": stmt.excluded.emm_region,
            "balancing_auth": stmt.excluded.balancing_auth,
            "primary_fuel": stmt.excluded.primary_fuel,
            "nameplate_mw": stmt.excluded.nameplate_mw,
            "commission_year": stmt.excluded.commission_year,
            "operator_name": stmt.excluded.operator_name,
            "status": stmt.excluded.status,
            "planned_retirement_year": stmt.excluded.planned_retirement_year,
            "projected_retirement_year": stmt.excluded.projected_retirement_year,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    session.execute(stmt)


def fetch_operating_generator_rows(
    client: EIAClient,
    *,
    period: str,
) -> list[dict[str, Any]]:
    """All operable coal + gas generator rows for one monthly inventory snapshot."""
    fields = [
        "nameplate-capacity-mw",
        "latitude",
        "longitude",
        "operating-year-month",
        "planned-retirement-year-month",
        "county",
    ]
    facets = {
        "energy_source_code": _fossil_energy_codes(),
        "status": ["OP"],
    }
    out: list[dict[str, Any]] = []
    for row in client.iter_data(
        OPERATING_GENERATOR_ROUTE,
        frequency="monthly",
        data_fields=fields,
        facets=facets,
        page_size=5000,
        start=period,
        end=period,
    ):
        out.append(row)
    return out


def refresh_plant_inventory(session: Session) -> dict[str, Any]:
    """
    Full Phase-1 plant refresh: EIA snapshot → aggregate → upsert plants (≥100 MW).

    Creates a ``RefreshLog`` row and commits on success (rolls back on error).
    """
    client = EIAClient()
    log = RefreshLog(started_at=utcnow(), status="in_progress")
    session.add(log)
    session.flush()

    try:
        period = client.get_latest_inventory_period()
        logger.info("EIA inventory period: %s", period)
        rows = fetch_operating_generator_rows(client, period=period)
        by_plant = _aggregate_generators(rows)

        payloads: list[dict[str, Any]] = []
        for plant_id, agg in by_plant.items():
            if agg.nameplate_mw < MIN_NAMEPLATE_MW:
                continue
            payloads.append(_build_plant_row(plant_id, agg))

        keep_ids = [p["plant_id"] for p in payloads]
        for i in range(0, len(payloads), UPSERT_BATCH):
            _upsert_plant_batch(session, payloads[i : i + UPSERT_BATCH])

        if keep_ids:
            session.execute(delete(Plant).where(not_(Plant.plant_id.in_(keep_ids))))
        else:
            session.execute(delete(Plant))

        log.completed_at = utcnow()
        log.status = "success"
        log.plant_count = len(payloads)
        log.notes = f"period={period}; rows={len(rows)}; plants_>=_{MIN_NAMEPLATE_MW}MW={len(payloads)}"

        session.commit()
        return {
            "ok": True,
            "period": period,
            "generator_rows": len(rows),
            "plants_upserted": len(payloads),
            "refresh_log_id": log.id,
        }
    except Exception:
        logger.exception("Plant inventory refresh failed")
        session.rollback()
        raise
    finally:
        client.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    from app.models.database import get_session_factory

    sf = get_session_factory()
    with sf() as session:
        out = refresh_plant_inventory(session)
        print(out)


if __name__ == "__main__":
    main()
