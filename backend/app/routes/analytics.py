from fastapi import APIRouter, BackgroundTasks, Header
from pydantic import BaseModel, Field

from app.services.analytics_log import parse_visitor_id, persist_visit_safe

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class VisitIn(BaseModel):
    event_type: str = Field(default="app_load", max_length=32)


class VisitOut(BaseModel):
    logged: bool


@router.post("/visit", response_model=VisitOut)
def record_app_visit(
    body: VisitIn,
    background_tasks: BackgroundTasks,
    x_visitor_id: str | None = Header(default=None, alias="X-Visitor-Id"),
    user_agent: str | None = Header(default=None, alias="User-Agent"),
) -> VisitOut:
    """
    Record a client-side event (e.g. app_load). Requires a valid UUID in X-Visitor-Id.
    """
    vid = parse_visitor_id(x_visitor_id)
    if not vid:
        return VisitOut(logged=False)
    et = (body.event_type or "app_load").strip() or "app_load"
    background_tasks.add_task(persist_visit_safe, vid, et, user_agent)
    return VisitOut(logged=True)
