from fastapi import APIRouter, BackgroundTasks, Header

from app.api_schemas import FiltersApplied, QueryRequest, QueryResponse
from app.services.analytics_log import parse_visitor_id, persist_query_safe
from app.services.nl_query import run_nl_query

router = APIRouter(prefix="/api", tags=["query"])


@router.post("/query", response_model=QueryResponse)
def natural_language_query(
    body: QueryRequest,
    background_tasks: BackgroundTasks,
    x_visitor_id: str | None = Header(default=None, alias="X-Visitor-Id"),
) -> QueryResponse:
    raw = run_nl_query(body.query)
    fa = raw.get("filters_applied")
    applied = FiltersApplied.model_validate(fa) if fa else None
    msg = str(raw.get("message") or "")
    fb = bool(raw.get("fallback"))
    vid = parse_visitor_id(x_visitor_id)
    if vid:
        filters_dict = applied.model_dump() if applied is not None else None
        background_tasks.add_task(
            persist_query_safe,
            vid,
            body.query,
            msg,
            filters_dict,
            True,
            200,
            fb,
        )
    return QueryResponse(
        message=msg,
        filters_applied=applied,
        fallback=fb,
    )
