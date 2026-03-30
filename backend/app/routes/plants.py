from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, exists, func, select
from sqlalchemy.orm import Session, aliased

from app.api_schemas import (
    PlantDetailResponse,
    PlantListItem,
    PlantListResponse,
    PlantMetricRow,
    PlantProjectionBrief,
)
from app.models.database import get_db
from app.models.schemas import Plant, PlantMetric, PlantProjection
from app.plant_visibility import plant_has_923_metrics

router = APIRouter(prefix="/api/plants", tags=["plants"])

_SORT_BY = frozenset(
    {
        "stranded_gap",
        "projected_stranded_year",
        "projected_retirement_year",
        "age",
        "capacity_factor",
        "nameplate_mw",
        "cost_per_mwh",
    }
)


def _current_year() -> int:
    return datetime.now().year


def _escape_ilike_pattern(user_text: str) -> str:
    """Escape %, _, and \\ for PostgreSQL ILIKE ... ESCAPE '\\'."""
    t = user_text.strip()
    return (
        t.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _ilike_contains(column, raw: str | None) -> Any | None:
    """Return a WHERE fragment for case-insensitive substring match, or None to skip."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    pattern = f"%{_escape_ilike_pattern(s)}%"
    return column.ilike(pattern, escape="\\")


def _latest_capacity_factor_scalar():
    """Latest Form 923 capacity factor by plant (same ordering as list sort)."""
    return (
        select(PlantMetric.capacity_factor)
        .where(PlantMetric.plant_id == Plant.plant_id)
        .order_by(PlantMetric.year.desc())
        .limit(1)
        .scalar_subquery()
    )


@dataclass
class PlantFilterParams:
    """Filters for list queries. Numeric bounds exclude rows where the column IS NULL."""

    fuel_type: str = "all"
    fuel_types: list[str] | None = None
    state: str | None = None
    states: list[str] | None = None
    emm_region: str | None = None
    min_stranded_gap: int | None = None
    max_stranded_gap: int | None = None
    plant_name_contains: str | None = None
    operator_contains: str | None = None
    county_contains: str | None = None
    balancing_auth_contains: str | None = None
    status_contains: str | None = None
    commission_year_min: int | None = None
    commission_year_max: int | None = None
    planned_retirement_year_min: int | None = None
    planned_retirement_year_max: int | None = None
    projected_retirement_year_min: int | None = None
    projected_retirement_year_max: int | None = None
    projected_stranded_year_min: int | None = None
    projected_stranded_year_max: int | None = None
    nameplate_mw_min: float | None = None
    nameplate_mw_max: float | None = None
    min_capacity_factor: float | None = None
    max_capacity_factor: float | None = None
    current_cost_per_mwh_min: float | None = None
    current_cost_per_mwh_max: float | None = None
    current_revenue_per_mwh_min: float | None = None
    current_revenue_per_mwh_max: float | None = None
    current_profit_margin_min: float | None = None
    current_profit_margin_max: float | None = None


def _normalize_state_code(s: str) -> str | None:
    u = s.strip().upper()
    return u if len(u) == 2 and u.isalpha() else None


def _require_min_le_max(label: str, lo: float | int | None, hi: float | int | None) -> None:
    if lo is None or hi is None:
        return
    if lo > hi:
        raise HTTPException(
            status_code=422,
            detail=f"{label}: minimum must be less than or equal to maximum",
        )


def _merged_state_list(state: str | None, states: list[str] | None) -> list[str] | None:
    out: list[str] = []
    if states:
        for x in states:
            c = _normalize_state_code(x) if x else None
            if c and c not in out:
                out.append(c)
    if state:
        c = _normalize_state_code(state)
        if c and c not in out:
            out.append(c)
    return out if out else None


def _normalize_fuel_types(raw: list[str] | None) -> list[str] | None:
    if not raw:
        return None
    allowed = {"coal", "gas"}
    out: list[str] = []
    for x in raw:
        if x and str(x).lower() in allowed:
            v = str(x).lower()
            if v not in out:
                out.append(v)
    return out if out else None


def _apply_plant_filters(stmt: Select, p: PlantFilterParams) -> Select:
    # Fuel: multi-select wins; else single fuel_type coal/gas/all
    fts = _normalize_fuel_types(p.fuel_types)
    if fts is not None:
        stmt = stmt.where(Plant.primary_fuel.in_(fts))
    elif p.fuel_type == "coal":
        stmt = stmt.where(Plant.primary_fuel == "coal")
    elif p.fuel_type == "gas":
        stmt = stmt.where(Plant.primary_fuel == "gas")

    st_list = _merged_state_list(p.state, p.states)
    if st_list is not None:
        stmt = stmt.where(Plant.state.in_(st_list))

    if p.emm_region is not None:
        stmt = stmt.where(Plant.emm_region == p.emm_region)

    frag = _ilike_contains(Plant.plant_name, p.plant_name_contains)
    if frag is not None:
        stmt = stmt.where(frag)
    frag = _ilike_contains(Plant.operator_name, p.operator_contains)
    if frag is not None:
        stmt = stmt.where(frag)
    frag = _ilike_contains(Plant.county, p.county_contains)
    if frag is not None:
        stmt = stmt.where(frag)
    frag = _ilike_contains(Plant.balancing_auth, p.balancing_auth_contains)
    if frag is not None:
        stmt = stmt.where(frag)
    frag = _ilike_contains(Plant.status, p.status_contains)
    if frag is not None:
        stmt = stmt.where(frag)

    cy = Plant.commission_year
    if p.commission_year_min is not None:
        stmt = stmt.where(cy.is_not(None), cy >= p.commission_year_min)
    if p.commission_year_max is not None:
        stmt = stmt.where(cy.is_not(None), cy <= p.commission_year_max)

    pry = Plant.planned_retirement_year
    if p.planned_retirement_year_min is not None:
        stmt = stmt.where(pry.is_not(None), pry >= p.planned_retirement_year_min)
    if p.planned_retirement_year_max is not None:
        stmt = stmt.where(pry.is_not(None), pry <= p.planned_retirement_year_max)

    prry = Plant.projected_retirement_year
    if p.projected_retirement_year_min is not None:
        stmt = stmt.where(prry.is_not(None), prry >= p.projected_retirement_year_min)
    if p.projected_retirement_year_max is not None:
        stmt = stmt.where(prry.is_not(None), prry <= p.projected_retirement_year_max)

    psy = PlantProjection.projected_stranded_year
    if p.projected_stranded_year_min is not None:
        stmt = stmt.where(psy.is_not(None), psy >= p.projected_stranded_year_min)
    if p.projected_stranded_year_max is not None:
        stmt = stmt.where(psy.is_not(None), psy <= p.projected_stranded_year_max)

    sg = PlantProjection.stranded_gap_years
    if p.min_stranded_gap is not None:
        stmt = stmt.where(sg.is_not(None), sg >= p.min_stranded_gap)
    if p.max_stranded_gap is not None:
        stmt = stmt.where(sg.is_not(None), sg <= p.max_stranded_gap)

    nm = Plant.nameplate_mw
    if p.nameplate_mw_min is not None:
        stmt = stmt.where(nm >= p.nameplate_mw_min)
    if p.nameplate_mw_max is not None:
        stmt = stmt.where(nm <= p.nameplate_mw_max)

    cf = _latest_capacity_factor_scalar()
    if p.min_capacity_factor is not None:
        stmt = stmt.where(cf.is_not(None), cf >= p.min_capacity_factor)
    if p.max_capacity_factor is not None:
        stmt = stmt.where(cf.is_not(None), cf <= p.max_capacity_factor)

    cc = PlantProjection.current_cost_per_mwh
    if p.current_cost_per_mwh_min is not None:
        stmt = stmt.where(cc.is_not(None), cc >= p.current_cost_per_mwh_min)
    if p.current_cost_per_mwh_max is not None:
        stmt = stmt.where(cc.is_not(None), cc <= p.current_cost_per_mwh_max)

    cr = PlantProjection.current_revenue_per_mwh
    if p.current_revenue_per_mwh_min is not None:
        stmt = stmt.where(cr.is_not(None), cr >= p.current_revenue_per_mwh_min)
    if p.current_revenue_per_mwh_max is not None:
        stmt = stmt.where(cr.is_not(None), cr <= p.current_revenue_per_mwh_max)

    cpm = PlantProjection.current_profit_margin
    if p.current_profit_margin_min is not None:
        stmt = stmt.where(cpm.is_not(None), cpm >= p.current_profit_margin_min)
    if p.current_profit_margin_max is not None:
        stmt = stmt.where(cpm.is_not(None), cpm <= p.current_profit_margin_max)

    return stmt


def _plants_list_select() -> Select:
    """Base select: plant + projection + latest-year facility metric (CF, year)."""
    ly = (
        select(
            PlantMetric.plant_id.label("pid"),
            func.max(PlantMetric.year).label("max_y"),
        )
        .group_by(PlantMetric.plant_id)
        .subquery()
    )
    pm = aliased(PlantMetric)
    return (
        select(Plant, PlantProjection, pm.capacity_factor, pm.year)
        .outerjoin(PlantProjection, Plant.plant_id == PlantProjection.plant_id)
        .outerjoin(ly, ly.c.pid == Plant.plant_id)
        .outerjoin(
            pm,
            (pm.plant_id == Plant.plant_id) & (pm.year == ly.c.max_y),
        )
        .where(plant_has_923_metrics(Plant.plant_id))
    )


def _order_by(
    stmt: Select,
    *,
    sort_by: str,
    sort_order: str,
    cy: int,
) -> Select:
    descending = sort_order.lower() == "desc"

    if sort_by == "stranded_gap":
        col = PlantProjection.stranded_gap_years
    elif sort_by == "projected_stranded_year":
        col = PlantProjection.projected_stranded_year
    elif sort_by == "nameplate_mw":
        col = Plant.nameplate_mw
    elif sort_by == "cost_per_mwh":
        col = PlantProjection.current_cost_per_mwh
    elif sort_by == "projected_retirement_year":
        col = Plant.projected_retirement_year
    elif sort_by == "age":
        col = cy - Plant.commission_year
    elif sort_by == "capacity_factor":
        col = (
            select(PlantMetric.capacity_factor)
            .where(PlantMetric.plant_id == Plant.plant_id)
            .order_by(PlantMetric.year.desc())
            .limit(1)
            .scalar_subquery()
        )
    else:
        col = PlantProjection.stranded_gap_years

    # PostgreSQL: "NULLS LAST" must follow ASC/DESC (`NULLS LAST DESC` is invalid).
    if descending:
        return stmt.order_by(col.desc().nulls_last())
    return stmt.order_by(col.asc().nulls_last())


@router.get("", response_model=PlantListResponse)
def list_plants(
    db: Session = Depends(get_db),
    fuel_type: str = Query("all", pattern="^(all|coal|gas)$"),
    sort_by: str = Query("stranded_gap", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    emm_region: str | None = Query(None, description="Exact EMM region label"),
    state: str | None = Query(
        None,
        min_length=2,
        max_length=2,
        description="Single US state (2-letter). Merged with `states` if both set.",
    ),
    states: list[str] | None = Query(
        None,
        description="Repeat param: states=TX&states=OH — OR semantics (any listed state).",
    ),
    fuel_types: list[str] | None = Query(
        None,
        description="Repeat param: primary fuels coal and/or gas. When set, overrides fuel_type.",
    ),
    min_stranded_gap: int | None = Query(None, ge=0),
    max_stranded_gap: int | None = Query(None, ge=0),
    plant_name_contains: str | None = Query(None, min_length=1, max_length=512),
    operator_contains: str | None = Query(None, min_length=1, max_length=512),
    county_contains: str | None = Query(None, min_length=1, max_length=256),
    balancing_auth_contains: str | None = Query(None, min_length=1, max_length=256),
    status_contains: str | None = Query(None, min_length=1, max_length=128),
    commission_year_min: int | None = Query(None, ge=1900, le=2100),
    commission_year_max: int | None = Query(None, ge=1900, le=2100),
    planned_retirement_year_min: int | None = Query(None, ge=1900, le=2200),
    planned_retirement_year_max: int | None = Query(None, ge=1900, le=2200),
    projected_retirement_year_min: int | None = Query(None, ge=1900, le=2200),
    projected_retirement_year_max: int | None = Query(None, ge=1900, le=2200),
    projected_stranded_year_min: int | None = Query(None, ge=1900, le=2200),
    projected_stranded_year_max: int | None = Query(None, ge=1900, le=2200),
    nameplate_mw_min: float | None = Query(None, ge=0),
    nameplate_mw_max: float | None = Query(None, ge=0),
    min_capacity_factor: float | None = Query(
        None,
        ge=0,
        le=1,
        description="Latest annual capacity factor (0–1).",
    ),
    max_capacity_factor: float | None = Query(
        None,
        ge=0,
        le=1,
        description="Latest annual capacity factor (0–1).",
    ),
    current_cost_per_mwh_min: float | None = Query(None),
    current_cost_per_mwh_max: float | None = Query(None),
    current_revenue_per_mwh_min: float | None = Query(None),
    current_revenue_per_mwh_max: float | None = Query(None),
    current_profit_margin_min: float | None = Query(None),
    current_profit_margin_max: float | None = Query(None),
) -> PlantListResponse:
    if sort_by not in _SORT_BY:
        raise HTTPException(
            status_code=422,
            detail=f"sort_by must be one of: {sorted(_SORT_BY)}",
        )

    _require_min_le_max("commission_year", commission_year_min, commission_year_max)
    _require_min_le_max(
        "planned_retirement_year",
        planned_retirement_year_min,
        planned_retirement_year_max,
    )
    _require_min_le_max(
        "projected_retirement_year",
        projected_retirement_year_min,
        projected_retirement_year_max,
    )
    _require_min_le_max(
        "projected_stranded_year",
        projected_stranded_year_min,
        projected_stranded_year_max,
    )
    _require_min_le_max("stranded_gap_years", min_stranded_gap, max_stranded_gap)
    _require_min_le_max("nameplate_mw", nameplate_mw_min, nameplate_mw_max)
    _require_min_le_max("capacity_factor", min_capacity_factor, max_capacity_factor)
    _require_min_le_max(
        "current_cost_per_mwh",
        current_cost_per_mwh_min,
        current_cost_per_mwh_max,
    )
    _require_min_le_max(
        "current_revenue_per_mwh",
        current_revenue_per_mwh_min,
        current_revenue_per_mwh_max,
    )
    _require_min_le_max(
        "current_profit_margin",
        current_profit_margin_min,
        current_profit_margin_max,
    )

    cy = _current_year()
    st = state.upper() if state else None
    p = PlantFilterParams(
        fuel_type=fuel_type,
        fuel_types=fuel_types,
        state=st,
        states=states,
        emm_region=emm_region,
        min_stranded_gap=min_stranded_gap,
        max_stranded_gap=max_stranded_gap,
        plant_name_contains=plant_name_contains,
        operator_contains=operator_contains,
        county_contains=county_contains,
        balancing_auth_contains=balancing_auth_contains,
        status_contains=status_contains,
        commission_year_min=commission_year_min,
        commission_year_max=commission_year_max,
        planned_retirement_year_min=planned_retirement_year_min,
        planned_retirement_year_max=planned_retirement_year_max,
        projected_retirement_year_min=projected_retirement_year_min,
        projected_retirement_year_max=projected_retirement_year_max,
        projected_stranded_year_min=projected_stranded_year_min,
        projected_stranded_year_max=projected_stranded_year_max,
        nameplate_mw_min=nameplate_mw_min,
        nameplate_mw_max=nameplate_mw_max,
        min_capacity_factor=min_capacity_factor,
        max_capacity_factor=max_capacity_factor,
        current_cost_per_mwh_min=current_cost_per_mwh_min,
        current_cost_per_mwh_max=current_cost_per_mwh_max,
        current_revenue_per_mwh_min=current_revenue_per_mwh_min,
        current_revenue_per_mwh_max=current_revenue_per_mwh_max,
        current_profit_margin_min=current_profit_margin_min,
        current_profit_margin_max=current_profit_margin_max,
    )
    base = _plants_list_select()
    base = _apply_plant_filters(base, p)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = int(db.execute(count_stmt).scalar_one())

    stmt = _order_by(base, sort_by=sort_by, sort_order=sort_order, cy=cy)
    stmt = stmt.limit(limit).offset(offset)
    rows = db.execute(stmt).all()

    items: list[PlantListItem] = []
    for plant, proj, latest_cf, latest_y in rows:
        pbrief = None
        if proj is not None:
            pbrief = PlantProjectionBrief.model_validate(proj)
        items.append(
            PlantListItem(
                plant_id=plant.plant_id,
                plant_name=plant.plant_name,
                state=plant.state,
                county=plant.county,
                latitude=plant.latitude,
                longitude=plant.longitude,
                emm_region=plant.emm_region,
                primary_fuel=plant.primary_fuel,
                nameplate_mw=plant.nameplate_mw,
                commission_year=plant.commission_year,
                planned_retirement_year=plant.planned_retirement_year,
                projected_retirement_year=plant.projected_retirement_year,
                latest_capacity_factor=latest_cf,
                latest_metric_year=latest_y,
                projection=pbrief,
            )
        )

    return PlantListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{plant_id}", response_model=PlantDetailResponse)
def get_plant(plant_id: str, db: Session = Depends(get_db)) -> PlantDetailResponse:
    plant = db.get(Plant, plant_id)
    if plant is None:
        raise HTTPException(status_code=404, detail="Plant not found")

    if not db.scalar(select(exists().where(PlantMetric.plant_id == plant_id))):
        raise HTTPException(status_code=404, detail="Plant not found")

    mrows = (
        db.execute(
            select(PlantMetric)
            .where(PlantMetric.plant_id == plant_id)
            .order_by(PlantMetric.year.asc())
        )
        .scalars()
        .all()
    )
    metrics = [PlantMetricRow.model_validate(m) for m in mrows]

    proj = db.get(PlantProjection, plant_id)
    pbrief = PlantProjectionBrief.model_validate(proj) if proj is not None else None

    return PlantDetailResponse(
        plant_id=plant.plant_id,
        plant_name=plant.plant_name,
        state=plant.state,
        county=plant.county,
        latitude=plant.latitude,
        longitude=plant.longitude,
        emm_region=plant.emm_region,
        balancing_auth=plant.balancing_auth,
        primary_fuel=plant.primary_fuel,
        nameplate_mw=plant.nameplate_mw,
        commission_year=plant.commission_year,
        operator_name=plant.operator_name,
        status=plant.status,
        planned_retirement_year=plant.planned_retirement_year,
        projected_retirement_year=plant.projected_retirement_year,
        updated_at=plant.updated_at,
        metrics=metrics,
        projection=pbrief,
    )
