from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api_schemas import DataFreshness, StatsResponse
from app.models.database import get_db
from app.models.schemas import Plant, PlantProjection, RefreshLog
from app.plant_visibility import plant_has_923_metrics

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _current_year() -> int:
    return datetime.now().year


@router.get("", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)) -> StatsResponse:
    cy = _current_year()

    total_plants = int(
        db.scalar(
            select(func.count())
            .select_from(Plant)
            .where(plant_has_923_metrics(Plant.plant_id))
        )
        or 0
    )

    avg_coal = db.scalar(
        select(func.avg(PlantProjection.stranded_gap_years))
        .select_from(Plant)
        .join(PlantProjection, Plant.plant_id == PlantProjection.plant_id)
        .where(
            Plant.primary_fuel == "coal",
            PlantProjection.stranded_gap_years.is_not(None),
            plant_has_923_metrics(Plant.plant_id),
        )
    )
    avg_gas = db.scalar(
        select(func.avg(PlantProjection.stranded_gap_years))
        .select_from(Plant)
        .join(PlantProjection, Plant.plant_id == PlantProjection.plant_id)
        .where(
            Plant.primary_fuel == "gas",
            PlantProjection.stranded_gap_years.is_not(None),
            plant_has_923_metrics(Plant.plant_id),
        )
    )

    at_risk = int(
        db.scalar(
            select(func.count())
            .select_from(PlantProjection)
            .where(
                PlantProjection.projected_stranded_year.is_not(None),
                PlantProjection.projected_stranded_year <= cy,
                plant_has_923_metrics(PlantProjection.plant_id),
            )
        )
        or 0
    )

    region_row = db.execute(
        select(
            Plant.emm_region,
            func.avg(PlantProjection.stranded_gap_years).label("avg_gap"),
        )
        .join(PlantProjection, Plant.plant_id == PlantProjection.plant_id)
        .where(
            Plant.emm_region.is_not(None),
            PlantProjection.stranded_gap_years.is_not(None),
            plant_has_923_metrics(Plant.plant_id),
        )
        .group_by(Plant.emm_region)
        .order_by(func.avg(PlantProjection.stranded_gap_years).desc())
        .limit(1)
    ).first()

    highest_region = None
    highest_avg = None
    if region_row is not None:
        highest_region = region_row.emm_region
        highest_avg = float(region_row.avg_gap) if region_row.avg_gap is not None else None

    last_inv = db.scalar(
        select(func.max(RefreshLog.completed_at)).where(RefreshLog.status == "success")
    )
    last_proj = db.scalar(select(func.max(PlantProjection.computed_at)))

    return StatsResponse(
        total_plants=total_plants,
        avg_stranded_gap_coal=float(avg_coal) if avg_coal is not None else None,
        avg_stranded_gap_gas=float(avg_gas) if avg_gas is not None else None,
        plants_at_risk_count=at_risk,
        highest_risk_region=highest_region,
        highest_risk_region_avg_gap=highest_avg,
        data_freshness=DataFreshness(
            last_plant_inventory_refresh=last_inv,
            last_projection_computed=last_proj,
        ),
    )
