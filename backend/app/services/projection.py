"""
Stranded-year projection engine (Phase 2): AEO fuel + wholesale, metrics heat rate,
O&M, wholesale × dispatch from regional renewables, 2-year loss rule → ``plant_projections``.
Resolves ``plants.emm_region`` from state → EMM substring map when unset; national fallbacks
when no EMM match (see ``IMPLEMENTATION_PLAN.md`` Projection Model).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.schemas import (
    FuelPriceProjection,
    Plant,
    PlantMetric,
    PlantProjection,
    RegionalPriceProjection,
    RegionalRenewable,
    utcnow,
)
from app.projection_horizon import PROJECTION_END_YEAR, PROJECTION_START_YEAR

logger = logging.getLogger(__name__)

# --- Model constants (IMPLEMENTATION_PLAN.md)
DISPLACEMENT_COEFFICIENT_COAL = 0.75
DISPLACEMENT_COEFFICIENT_GAS = 0.45
BASE_OM_COAL_USD_PER_MWH = 14.0
BASE_OM_GAS_USD_PER_MWH = 6.0
BASELINE_YEAR = 2025  # AEO series start; used for "current_*" snapshot with latest heat rate
DEFAULT_HEAT_RATE_COAL = 10.2
DEFAULT_HEAT_RATE_GAS = 7.0
UPSERT_BATCH = 400

# Ordered keys: prefer exact facet names from EIA; fall back to unique substrings in ``available``.
STATE_EMM_KEYS: dict[str, tuple[str, ...]] = {
    "AL": ("SERC Reliability Corporation / Southeast", "Southeast"),
    "AK": ("Alaska",),
    "AZ": ("Western Electricity Coordinating Council / Southwest", "Southwest"),
    "AR": ("SERC Reliability Corporation / Central", "Midcontinent ISO / South"),
    "CA": ("Western Electricity Coordinating Council / California South", "California South"),
    "CO": ("Western Electricity Coordinating Council / Rockies", "Rockies"),
    "CT": ("Northeast Power Coordinating Council / New England", "New England"),
    "DE": ("PJM / East",),
    "DC": ("PJM / Dominion",),
    "FL": ("Florida",),
    "GA": ("SERC Reliability Corporation / East", "Carolinas"),
    "HI": ("Hawaii",),
    "ID": ("Western Electricity Coordinating Council / Northwest Power Pool", "Northwest"),
    "IL": ("PJM / Commonwealth Edison", "Commonwealth Edison"),
    "IN": ("Midcontinent ISO / East",),
    "IA": ("Midcontinent ISO / East",),
    "KS": ("Southwest Power Pool / Central",),
    "KY": ("SERC Reliability Corporation / Central",),
    "LA": ("SERC Reliability Corporation / Southeast",),
    "ME": ("Northeast Power Coordinating Council / New England", "New England"),
    "MD": ("PJM / Dominion",),
    "MA": ("Northeast Power Coordinating Council / New England", "New England"),
    "MI": ("Midcontinent ISO / East",),
    "MN": ("Midcontinent ISO / East",),
    "MS": ("Midcontinent ISO / South",),
    "MO": ("Midcontinent ISO / East", "Midcontinent ISO / South"),
    "MT": ("Western Electricity Coordinating Council / Northwest Power Pool", "Northwest"),
    "NE": ("Southwest Power Pool / North",),
    "NV": ("Western Electricity Coordinating Council / Great Basin", "Great Basin"),
    "NH": ("Northeast Power Coordinating Council / New England", "New England"),
    "NJ": ("PJM / East",),
    "NM": ("Western Electricity Coordinating Council / Southwest", "Southwest"),
    "NY": ("Northeast Power Coordinating Council / Upstate New York", "Upstate New York"),
    "NC": ("SERC Reliability Corporation / East", "Carolinas"),
    "ND": ("Southwest Power Pool / North",),
    "OH": ("PJM / West",),
    "OK": ("Southwest Power Pool / South",),
    "OR": ("Western Electricity Coordinating Council / Northwest Power Pool", "Northwest"),
    "PA": ("PJM / East",),
    "RI": ("Northeast Power Coordinating Council / New England", "New England"),
    "SC": ("SERC Reliability Corporation / East", "Carolinas"),
    "SD": ("Southwest Power Pool / North",),
    "TN": ("SERC Reliability Corporation / Central",),
    "TX": ("Texas", "ERCOT"),
    "UT": ("Western Electricity Coordinating Council / Rockies", "Rockies"),
    "VT": ("Northeast Power Coordinating Council / New England", "New England"),
    "VA": ("PJM / Dominion",),
    "WA": ("Western Electricity Coordinating Council / Northwest Power Pool", "Northwest"),
    "WV": ("PJM / West",),
    "WI": ("Midcontinent ISO / East",),
    "WY": ("Western Electricity Coordinating Council / Rockies", "Rockies"),
}


def _base_om(primary_fuel: str) -> float:
    return BASE_OM_GAS_USD_PER_MWH if (primary_fuel or "").lower() == "gas" else BASE_OM_COAL_USD_PER_MWH


def _default_heat_rate(primary_fuel: str) -> float:
    return DEFAULT_HEAT_RATE_GAS if (primary_fuel or "").lower() == "gas" else DEFAULT_HEAT_RATE_COAL


def _size_factor(nameplate_mw: float) -> float:
    mw = max(float(nameplate_mw or 0.0), 1.0)
    if mw >= 1000.0:
        return 1.0
    if mw <= 100.0:
        return 1.3
    return 1.3 + (mw - 100.0) * (1.0 - 1.3) / (1000.0 - 100.0)


def _age_escalation(age_years: int) -> float:
    if age_years <= 20:
        return 1.0
    return 1.0 + 0.015 * float(age_years - 20)


def _match_emm_region(available: set[str], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        if k in available:
            return k
    for k in keys:
        matches = [r for r in available if k in r]
        if not matches:
            continue
        if len(matches) == 1:
            return matches[0]
        matches.sort(key=len, reverse=True)
        return matches[0]
    return None


def resolve_emm_region(plant: Plant, available_regions: set[str]) -> str | None:
    """Pick EMM label present in ``regional_*`` tables: use ``plant.emm_region`` if set, else state map."""
    if plant.emm_region:
        er = str(plant.emm_region).strip()
        if er in available_regions:
            return er
        clipped = er[:64].rstrip()
        if clipped in available_regions:
            return clipped
    state = (plant.state or "").strip().upper()
    if len(state) == 2 and state in STATE_EMM_KEYS:
        return _match_emm_region(available_regions, STATE_EMM_KEYS[state])
    return None


def _distinct_emm_regions(session: Session) -> set[str]:
    rows = session.execute(select(RegionalPriceProjection.emm_region).distinct()).all()
    return {str(r[0]) for r in rows if r[0]}


def _national_avg_wholesale_by_year(session: Session) -> dict[int, float]:
    y = RegionalPriceProjection.year
    p = RegionalPriceProjection.wholesale_price_per_mwh
    stmt: Select[tuple[int, float]] = (
        select(y, func.avg(p)).where(p.isnot(None)).group_by(y).order_by(y)
    )
    out: dict[int, float] = {}
    for row in session.execute(stmt).all():
        out[int(row[0])] = float(row[1])
    return out


def _national_avg_renewable_pct_by_year(session: Session) -> dict[int, float]:
    y = RegionalRenewable.year
    pct = RegionalRenewable.renewable_pct
    stmt: Select[tuple[int, float]] = (
        select(y, func.avg(pct)).where(pct.isnot(None)).group_by(y).order_by(y)
    )
    out: dict[int, float] = {}
    for row in session.execute(stmt).all():
        out[int(row[0])] = float(row[1])
    return out


def _fuel_prices(session: Session) -> dict[tuple[str, int], float]:
    out: dict[tuple[str, int], float] = {}
    for row in session.execute(select(FuelPriceProjection)).scalars():
        if row.price_per_mmbtu is None:
            continue
        out[(str(row.fuel_type).lower(), int(row.year))] = float(row.price_per_mmbtu)
    return out


def _regional_wholesale(session: Session) -> dict[tuple[str, int], float]:
    out: dict[tuple[str, int], float] = {}
    for row in session.execute(select(RegionalPriceProjection)).scalars():
        if row.wholesale_price_per_mwh is None:
            continue
        key = (str(row.emm_region), int(row.year))
        out[key] = float(row.wholesale_price_per_mwh)
    return out


def _regional_renewable_pct(session: Session) -> dict[tuple[str, int], float]:
    out: dict[tuple[str, int], float] = {}
    for row in session.execute(select(RegionalRenewable)).scalars():
        if row.renewable_pct is None:
            continue
        key = (str(row.emm_region), int(row.year))
        out[key] = float(row.renewable_pct)
    return out


def _latest_metrics_by_plant(session: Session) -> dict[str, PlantMetric]:
    subq = (
        select(
            PlantMetric.plant_id,
            func.max(PlantMetric.year).label("max_y"),
        ).group_by(PlantMetric.plant_id)
    ).subquery()

    stmt = select(PlantMetric).join(
        subq,
        (PlantMetric.plant_id == subq.c.plant_id) & (PlantMetric.year == subq.c.max_y),
    )
    rows = session.execute(stmt).scalars().all()
    return {m.plant_id: m for m in rows}


def _displacement_k(fuel_type: str) -> float:
    return DISPLACEMENT_COEFFICIENT_GAS if (fuel_type or "").lower() == "gas" else DISPLACEMENT_COEFFICIENT_COAL


def _dispatch_factor(renewable_pct: float | None, has_emm: bool, fuel_type: str) -> float:
    if not has_emm or renewable_pct is None:
        return 1.0
    share = max(0.0, min(1.0, float(renewable_pct)))
    return max(0.0, 1.0 - share * _displacement_k(fuel_type))


def _profit_for_year(
    *,
    year: int,
    heat_rate: float,
    fuel_type: str,
    nameplate_mw: float,
    commission_year: int | None,
    fuel_prices: dict[tuple[str, int], float],
    wholesale: float | None,
    renewable_pct: float | None,
    has_emm: bool,
) -> float | None:
    fp = fuel_prices.get((fuel_type, year))
    if fp is None or wholesale is None:
        return None
    if commission_year is not None:
        age = max(0, year - int(commission_year))
    else:
        age = 35
    om = (
        _base_om(fuel_type)
        * _age_escalation(age)
        * _size_factor(nameplate_mw)
    )
    fuel_cost = heat_rate * fp
    total_cost = fuel_cost + om
    disp = _dispatch_factor(renewable_pct, has_emm, fuel_type)
    revenue = wholesale * disp
    return revenue - total_cost


def _upsert_projections_batch(session: Session, batch: list[dict[str, Any]]) -> None:
    if not batch:
        return
    stmt = pg_insert(PlantProjection).values(batch)
    stmt = stmt.on_conflict_do_update(
        index_elements=["plant_id"],
        set_={
            "projected_stranded_year": stmt.excluded.projected_stranded_year,
            "stranded_gap_years": stmt.excluded.stranded_gap_years,
            "current_cost_per_mwh": stmt.excluded.current_cost_per_mwh,
            "current_revenue_per_mwh": stmt.excluded.current_revenue_per_mwh,
            "current_profit_margin": stmt.excluded.current_profit_margin,
            "computed_at": stmt.excluded.computed_at,
        },
    )
    session.execute(stmt)


def refresh_plant_projections(session: Session) -> dict[str, Any]:
    """
    Recompute ``plant_projections`` for all plants; fill ``plants.emm_region`` when resolved
    from state mapping and previously null.

    Expects ``fuel_price_projections``, ``regional_price_projections``, and ``regional_renewables``
    (run ``aeo_refresh``) and ``plant_metrics`` (``metrics_refresh``) for heat rates.

    Commits on success; rolls back on error.
    """
    now = utcnow()
    try:
        available = _distinct_emm_regions(session)
        if not available:
            logger.warning("No rows in regional_price_projections — cannot run projection")
            session.commit()
            return {
                "ok": False,
                "error": "empty regional_price_projections — run aeo_refresh first",
                "plant_projections_upserted": 0,
            }

        national_w = _national_avg_wholesale_by_year(session)
        national_r = _national_avg_renewable_pct_by_year(session)
        fuel_map = _fuel_prices(session)
        reg_w = _regional_wholesale(session)
        reg_pct = _regional_renewable_pct(session)
        metrics_by_plant = _latest_metrics_by_plant(session)

        plants = session.execute(select(Plant)).scalars().all()
        projection_rows: list[dict[str, Any]] = []
        emm_updates: list[tuple[str, str]] = []

        for plant in plants:
            fuel_type = (plant.primary_fuel or "coal").lower()
            if fuel_type not in ("coal", "gas"):
                fuel_type = "coal"

            emm = resolve_emm_region(plant, available)
            has_emm = emm is not None

            if emm and not (plant.emm_region or "").strip():
                emm_updates.append((plant.plant_id, emm))

            m = metrics_by_plant.get(plant.plant_id)
            heat_rate = None
            if m and m.heat_rate is not None:
                heat_rate = float(m.heat_rate)
            if heat_rate is None or heat_rate <= 0:
                heat_rate = _default_heat_rate(fuel_type)

            def wholesale_for(y: int) -> float | None:
                if emm:
                    w = reg_w.get((emm, y))
                    if w is not None:
                        return w
                return national_w.get(y)

            def renew_for(y: int) -> float | None:
                if not has_emm:
                    return None
                p = reg_pct.get((emm, y))
                if p is not None:
                    return p
                return national_r.get(y)

            projected_stranded_year: int | None = None
            consecutive = 0
            for year in range(PROJECTION_START_YEAR, PROJECTION_END_YEAR + 1):
                profit = _profit_for_year(
                    year=year,
                    heat_rate=heat_rate,
                    fuel_type=fuel_type,
                    nameplate_mw=float(plant.nameplate_mw or 0.0),
                    commission_year=plant.commission_year,
                    fuel_prices=fuel_map,
                    wholesale=wholesale_for(year),
                    renewable_pct=renew_for(year),
                    has_emm=has_emm,
                )
                if profit is None:
                    consecutive = 0
                    continue
                if profit < 0:
                    consecutive += 1
                else:
                    consecutive = 0
                if consecutive >= 2:
                    projected_stranded_year = year - 1
                    break

            ret_y = plant.projected_retirement_year
            stranded_gap: int | None = None
            if projected_stranded_year is not None and ret_y is not None:
                stranded_gap = int(ret_y) - int(projected_stranded_year)

            fp0 = fuel_map.get((fuel_type, BASELINE_YEAR))
            bw = wholesale_for(BASELINE_YEAR)
            br = renew_for(BASELINE_YEAR)
            current_cost = current_revenue = current_margin = None
            if fp0 is not None and bw is not None:
                cy = plant.commission_year
                if cy is not None:
                    age = max(0, BASELINE_YEAR - int(cy))
                else:
                    age = 35
                om = _base_om(fuel_type) * _age_escalation(age) * _size_factor(float(plant.nameplate_mw or 0.0))
                current_cost = heat_rate * fp0 + om
                disp = _dispatch_factor(br, has_emm, fuel_type)
                current_revenue = bw * disp
                current_margin = current_revenue - current_cost

            projection_rows.append(
                {
                    "plant_id": plant.plant_id,
                    "projected_stranded_year": projected_stranded_year,
                    "stranded_gap_years": stranded_gap,
                    "current_cost_per_mwh": current_cost,
                    "current_revenue_per_mwh": current_revenue,
                    "current_profit_margin": current_margin,
                    "computed_at": now,
                }
            )

        for pid, emm in emm_updates:
            session.execute(
                update(Plant)
                .where(Plant.plant_id == pid)
                .values(emm_region=emm, updated_at=now)
            )

        for i in range(0, len(projection_rows), UPSERT_BATCH):
            _upsert_projections_batch(session, projection_rows[i : i + UPSERT_BATCH])

        session.commit()
        return {
            "ok": True,
            "plants_processed": len(plants),
            "plant_projections_upserted": len(projection_rows),
            "emm_region_updates": len(emm_updates),
        }
    except Exception:
        logger.exception("Plant projection refresh failed")
        session.rollback()
        raise


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    from app.models.database import get_session_factory

    sf = get_session_factory()
    with sf() as session:
        out = refresh_plant_projections(session)
        print(out)


if __name__ == "__main__":
    main()
