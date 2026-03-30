from fastapi import APIRouter

from app.models.database import check_db_connection
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
