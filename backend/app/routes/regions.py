from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.api_schemas import RegionItem, RegionsResponse
from app.models.database import get_db
from app.models.schemas import Plant, PlantProjection, RegionalRenewable
from app.plant_visibility import plant_has_923_metrics

router = APIRouter(prefix="/api/regions", tags=["regions"])


@router.get("", response_model=RegionsResponse)
def list_regions(db: Session = Depends(get_db)) -> RegionsResponse:
    gap_stmt = (
        select(
            Plant.emm_region,
            func.count(Plant.plant_id).label("plant_count"),
            func.avg(PlantProjection.stranded_gap_years).label("avg_gap"),
        )
        .join(PlantProjection, Plant.plant_id == PlantProjection.plant_id)
        .where(Plant.emm_region.is_not(None), plant_has_923_metrics(Plant.plant_id))
        .group_by(Plant.emm_region)
    )
    gap_rows = {r.emm_region: (r.plant_count, r.avg_gap) for r in db.execute(gap_stmt)}

    ly = (
        select(
            RegionalRenewable.emm_region.label("reg"),
            func.max(RegionalRenewable.year).label("max_y"),
        )
        .group_by(RegionalRenewable.emm_region)
        .subquery()
    )
    rr = aliased(RegionalRenewable)
    ren_stmt = select(rr.emm_region, rr.renewable_pct, rr.year).join(
        ly,
        (rr.emm_region == ly.c.reg) & (rr.year == ly.c.max_y),
    )
    ren_by_region: dict[str, tuple[float | None, int | None]] = {}
    for row in db.execute(ren_stmt):
        ren_by_region[row.emm_region] = (row.renewable_pct, row.year)

    items: list[RegionItem] = []
    for emm_region in sorted(gap_rows.keys()):
        pc, avg_gap = gap_rows[emm_region]
        ren_pct, ren_y = ren_by_region.get(emm_region, (None, None))
        items.append(
            RegionItem(
                emm_region=emm_region,
                plant_count=int(pc),
                avg_stranded_gap_years=float(avg_gap) if avg_gap is not None else None,
                renewable_pct_latest=ren_pct,
                renewable_data_year=ren_y,
            )
        )

    return RegionsResponse(items=items)
