from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.database import check_db_connection, get_db
from app.models.schemas import (
    FuelPriceProjection,
    Plant,
    PlantMetric,
    PlantProjection,
    RegionalPriceProjection,
    RegionalRenewable,
)
from app.services.eia_client import EIAClient

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.get("/eia-ping")
def eia_ping() -> dict:
    """
    Calls EIA v2 metadata + a 2-row sample (operable natural gas generators).
    Confirms EIA_API_KEY and outbound HTTPS. Does not persist data.
    """
    client = EIAClient()
    try:
        return client.ping_operating_generators()
    finally:
        client.close()


@router.get("/db-ping")
def db_ping() -> dict:
    """Returns whether DATABASE_URL is set and Postgres accepts SELECT 1."""
    ok = check_db_connection()
    return {"ok": ok, "database": "connected" if ok else "unavailable"}


@router.get("/db-summary")
def db_summary(db: Session = Depends(get_db)) -> dict:
    """
    Row counts for core tables — useful to confirm pipeline completeness (e.g. Railway vs local).
    Does not include secrets. Same DB as the running API instance.
    """
    if not check_db_connection():
        return {"ok": False, "error": "database unavailable"}

    def _count(model: type) -> int:
        return int(db.scalar(select(func.count()).select_from(model)) or 0)

    pp_with_gap = int(
        db.scalar(
            select(func.count()).select_from(PlantProjection).where(
                PlantProjection.stranded_gap_years.is_not(None)
            )
        )
        or 0
    )
    pp_with_cost = int(
        db.scalar(
            select(func.count()).select_from(PlantProjection).where(
                PlantProjection.current_cost_per_mwh.is_not(None)
            )
        )
        or 0
    )

    return {
        "ok": True,
        "plants": _count(Plant),
        "plant_metrics_rows": _count(PlantMetric),
        "fuel_price_projections_rows": _count(FuelPriceProjection),
        "regional_price_projections_rows": _count(RegionalPriceProjection),
        "regional_renewables_rows": _count(RegionalRenewable),
        "plant_projections_rows": _count(PlantProjection),
        "plant_projections_with_stranded_gap": pp_with_gap,
        "plant_projections_with_current_cost": pp_with_cost,
    }
