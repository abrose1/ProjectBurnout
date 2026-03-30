from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
def health_db() -> dict[str, str | bool]:
    from app.models.database import check_db_connection

    ok = check_db_connection()
    return {"status": "ok" if ok else "unavailable", "database": ok}
