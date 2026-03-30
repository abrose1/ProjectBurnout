from fastapi import APIRouter

from app.api_schemas import FiltersApplied, QueryRequest, QueryResponse
from app.services.nl_query import run_nl_query

router = APIRouter(prefix="/api", tags=["query"])


@router.post("/query", response_model=QueryResponse)
def natural_language_query(body: QueryRequest) -> QueryResponse:
    raw = run_nl_query(body.query)
    fa = raw.get("filters_applied")
    applied = FiltersApplied.model_validate(fa) if fa else None
    return QueryResponse(
        message=raw["message"],
        filters_applied=applied,
        fallback=bool(raw.get("fallback")),
    )
