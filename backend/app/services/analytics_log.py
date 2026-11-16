"""Anonymous product analytics: visitor id validation and DB writes (best-effort).

Query rows store **plain text** (user input + NL interpretation + JSON filters). This is not
encryption — restrict DB access and document retention if required for privacy policy.
"""

from __future__ import annotations

import json
import logging
import re

from sqlalchemy.orm import Session

from app.models.schemas import AnalyticsQuery, AnalyticsVisit, utcnow

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def parse_visitor_id(raw: str | None) -> str | None:
    """Return normalized UUID string or None if missing/invalid."""
    if not raw:
        return None
    s = str(raw).strip()
    if len(s) != 36 or not _UUID_RE.match(s):
        return None
    return s.lower()


def _truncate_ua(ua: str | None, max_len: int = 255) -> str | None:
    if not ua:
        return None
    u = str(ua).strip()
    if len(u) <= max_len:
        return u
    return u[:max_len]


def record_visit(
    session: Session,
    *,
    visitor_id: str,
    event_type: str,
    user_agent_snippet: str | None,
) -> None:
    row = AnalyticsVisit(
        visitor_id=visitor_id,
        occurred_at=utcnow(),
        event_type=event_type[:32],
        user_agent_snippet=_truncate_ua(user_agent_snippet),
    )
    session.add(row)
    session.commit()


def record_query_attempt(
    session: Session,
    *,
    visitor_id: str,
    query_text: str,
    nl_message: str,
    filters_applied: dict | None,
    ok: bool,
    status_code: int,
    fallback: bool | None = None,
) -> None:
    filters_json: str | None = None
    if filters_applied is not None:
        filters_json = json.dumps(filters_applied, default=str, sort_keys=True)
    row = AnalyticsQuery(
        visitor_id=visitor_id,
        occurred_at=utcnow(),
        query_text=query_text,
        nl_message=nl_message,
        filters_applied_json=filters_json,
        ok=ok,
        status_code=status_code,
        fallback=fallback,
    )
    session.add(row)
    session.commit()


def persist_visit_safe(visitor_id: str, event_type: str, user_agent: str | None) -> None:
    from app.models.database import get_session_factory

    try:
        with get_session_factory()() as session:
            record_visit(
                session,
                visitor_id=visitor_id,
                event_type=event_type,
                user_agent_snippet=user_agent,
            )
    except Exception:
        logger.exception("analytics visit log failed")


def persist_query_safe(
    visitor_id: str,
    query_text: str,
    nl_message: str,
    filters_applied: dict | None,
    ok: bool,
    status_code: int,
    fallback: bool | None = None,
) -> None:
    from app.models.database import get_session_factory

    try:
        with get_session_factory()() as session:
            record_query_attempt(
                session,
                visitor_id=visitor_id,
                query_text=query_text,
                nl_message=nl_message,
                filters_applied=filters_applied,
                ok=ok,
                status_code=status_code,
                fallback=fallback,
            )
    except Exception:
        logger.exception("analytics query log failed")
