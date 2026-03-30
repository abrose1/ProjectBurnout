"""Natural-language query → structured plant list filters via Claude tool use."""

from __future__ import annotations

import json
import re
from typing import Any

from anthropic import Anthropic

from app.config import settings

# Keep in sync with GET /api/plants and frontend SORTS.
_SORT_BY = (
    "stranded_gap",
    "projected_stranded_year",
    "projected_retirement_year",
    "age",
    "capacity_factor",
    "nameplate_mw",
    "cost_per_mwh",
)

_NUM_PROP = {
    "type": "number",
    "description": "Numeric bound; omit if unused.",
}

LIST_PLANTS_TOOL: dict[str, Any] = {
    "name": "list_plants",
    "description": (
        "Apply filters and sorting to the stranded-asset plant table. "
        "Use this tool for every on-topic request that should change which plants are shown. "
        "Use 2-letter US state codes. For multiple states or fuels, use states / fuel_types arrays."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "fuel_type": {
                "type": "string",
                "enum": ["all", "coal", "gas"],
                "description": "Primary fuel filter when fuel_types is omitted.",
            },
            "fuel_types": {
                "type": "array",
                "items": {"type": "string", "enum": ["coal", "gas"]},
                "description": "Any of these fuels (OR). When set, overrides fuel_type.",
            },
            "state": {
                "type": "string",
                "description": "Single US state 2-letter code. Merged with states if both provided.",
            },
            "states": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple states (OR), e.g. Texas and Oklahoma → TX, OK.",
            },
            "emm_region": {
                "type": "string",
                "description": "Exact EIA EMM region label (e.g. 'PJM / East').",
            },
            "min_stranded_gap": {
                "type": "number",
                "description": "Stranded gap years ≥ this value.",
            },
            "max_stranded_gap": {
                "type": "number",
                "description": "Stranded gap years ≤ this value.",
            },
            "plant_name_contains": {
                "type": "string",
                "description": "Case-insensitive substring match on plant name.",
            },
            "operator_contains": {
                "type": "string",
                "description": "Case-insensitive substring match on operator name.",
            },
            "county_contains": {
                "type": "string",
                "description": "Case-insensitive substring match on county.",
            },
            "balancing_auth_contains": {
                "type": "string",
                "description": "Case-insensitive substring match on balancing authority name.",
            },
            "status_contains": {
                "type": "string",
                "description": "Case-insensitive substring match on plant status.",
            },
            "commission_year_min": _NUM_PROP.copy(),
            "commission_year_max": _NUM_PROP.copy(),
            "planned_retirement_year_min": _NUM_PROP.copy(),
            "planned_retirement_year_max": _NUM_PROP.copy(),
            "projected_retirement_year_min": _NUM_PROP.copy(),
            "projected_retirement_year_max": _NUM_PROP.copy(),
            "projected_stranded_year_min": _NUM_PROP.copy(),
            "projected_stranded_year_max": _NUM_PROP.copy(),
            "nameplate_mw_min": _NUM_PROP.copy(),
            "nameplate_mw_max": _NUM_PROP.copy(),
            "min_capacity_factor": {
                "type": "number",
                "description": "Latest annual capacity factor lower bound (0–1).",
            },
            "max_capacity_factor": {
                "type": "number",
                "description": "Latest annual capacity factor upper bound (0–1).",
            },
            "current_cost_per_mwh_min": _NUM_PROP.copy(),
            "current_cost_per_mwh_max": _NUM_PROP.copy(),
            "current_revenue_per_mwh_min": _NUM_PROP.copy(),
            "current_revenue_per_mwh_max": _NUM_PROP.copy(),
            "current_profit_margin_min": _NUM_PROP.copy(),
            "current_profit_margin_max": _NUM_PROP.copy(),
            "sort_by": {
                "type": "string",
                "enum": list(_SORT_BY),
                "description": "Column to sort by; default stranded_gap for risk ranking.",
            },
            "sort_order": {
                "type": "string",
                "enum": ["asc", "desc"],
                "description": "Sort direction; desc is typical for largest gaps first.",
            },
            "message": {
                "type": "string",
                "description": (
                    "Short plain-English summary (one or two sentences) of what you are showing and why."
                ),
            },
        },
        "required": ["message"],
    },
}

SYSTEM_PROMPT = """You are the query interpreter for a Stranded Asset Early Warning dashboard. Your ONLY job is to \
translate natural language into structured filters for a database of US coal and gas power plants analyzed for \
stranded asset risk.

The database has plants with: fuel type (coal/gas), US state, EIA EMM market region, nameplate MW, stranded gap \
years (years between projected unprofitability and retirement), projected stranded year, capacity factor, cost per MWh.

STRICT RULES:
1. You may ONLY discuss US power plants, energy markets, stranded assets, and closely related energy/climate topics.
2. If a query is CLEARLY off-topic or testing you, respond with a brief, friendly deflection that redirects to \
power-plant topics. Do NOT call list_plants for off-topic queries — respond with normal assistant text only.
3. If a query is UNCLEAR or too broad, briefly ask what fuel or region they care about, and still call list_plants \
with reasonable defaults (e.g. fuel_type all, sort_by stranded_gap, sort_order desc) so the UI shows something useful.
4. For every on-topic request that should show data, you MUST call the list_plants tool with a helpful message field.
5. Never invent plant names or numbers; filters only.
6. Prefer sort_by stranded_gap and sort_order desc when the user asks for riskiest, biggest gap, or most exposed plants.
7. Map US state names to 2-letter codes; use the states array for multiple states ("coal in Texas or Oklahoma").
8. Use operator_contains, plant_name_contains, MW/nameplate bounds, capacity_factor bounds, and year ranges when the user asks for them.

Model: use list_plants; the message field is shown to the user as the interpretation line."""


def _parse_opt_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(round(float(val)))
    except (TypeError, ValueError):
        return None


def _parse_opt_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _fix_int_pair(
    lo: int | None,
    hi: int | None,
) -> tuple[int | None, int | None]:
    if lo is not None and hi is not None and lo > hi:
        return hi, lo
    return lo, hi


def _fix_float_pair(
    lo: float | None,
    hi: float | None,
) -> tuple[float | None, float | None]:
    if lo is not None and hi is not None and lo > hi:
        return hi, lo
    return lo, hi


def _normalize_states_from_tool(raw: Any) -> list[str] | None:
    out: list[str] = []
    if isinstance(raw, list):
        for x in raw:
            if x is None:
                continue
            c = _normalize_state(str(x))
            if c and c not in out:
                out.append(c)
    return out if out else None


def _normalize_fuel_types_from_tool(raw: Any) -> list[str] | None:
    if not isinstance(raw, list):
        return None
    allowed = frozenset({"coal", "gas"})
    out: list[str] = []
    for x in raw:
        if x is None:
            continue
        v = str(x).lower().strip()
        if v in allowed and v not in out:
            out.append(v)
    return out if out else None


def _text_opt(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    return s if s else None


def _normalize_state(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip().upper()
    if len(s) == 2 and s.isalpha():
        return s
    # Minimal full-name → code (Claude should return 2-letter; this is fallback)
    names = {
        "ALABAMA": "AL",
        "ALASKA": "AK",
        "ARIZONA": "AZ",
        "ARKANSAS": "AR",
        "CALIFORNIA": "CA",
        "COLORADO": "CO",
        "CONNECTICUT": "CT",
        "DELAWARE": "DE",
        "FLORIDA": "FL",
        "GEORGIA": "GA",
        "HAWAII": "HI",
        "IDAHO": "ID",
        "ILLINOIS": "IL",
        "INDIANA": "IN",
        "IOWA": "IA",
        "KANSAS": "KS",
        "KENTUCKY": "KY",
        "LOUISIANA": "LA",
        "MAINE": "ME",
        "MARYLAND": "MD",
        "MASSACHUSETTS": "MA",
        "MICHIGAN": "MI",
        "MINNESOTA": "MN",
        "MISSISSIPPI": "MS",
        "MISSOURI": "MO",
        "MONTANA": "MT",
        "NEBRASKA": "NE",
        "NEVADA": "NV",
        "NEW HAMPSHIRE": "NH",
        "NEW JERSEY": "NJ",
        "NEW MEXICO": "NM",
        "NEW YORK": "NY",
        "NORTH CAROLINA": "NC",
        "NORTH DAKOTA": "ND",
        "OHIO": "OH",
        "OKLAHOMA": "OK",
        "OREGON": "OR",
        "PENNSYLVANIA": "PA",
        "RHODE ISLAND": "RI",
        "SOUTH CAROLINA": "SC",
        "SOUTH DAKOTA": "SD",
        "TENNESSEE": "TN",
        "TEXAS": "TX",
        "UTAH": "UT",
        "VERMONT": "VT",
        "VIRGINIA": "VA",
        "WASHINGTON": "WA",
        "WEST VIRGINIA": "WV",
        "WISCONSIN": "WI",
        "WYOMING": "WY",
        "DISTRICT OF COLUMBIA": "DC",
    }
    key = re.sub(r"[^a-zA-Z ]", "", raw).strip().upper()
    return names.get(key)


def _coerce_tool_input(raw: dict[str, Any]) -> dict[str, Any]:
    fuel = raw.get("fuel_type") or "all"
    if fuel not in ("all", "coal", "gas"):
        fuel = "all"
    sort_by = raw.get("sort_by") or "stranded_gap"
    if sort_by not in _SORT_BY:
        sort_by = "stranded_gap"
    order = (raw.get("sort_order") or "desc").lower()
    if order not in ("asc", "desc"):
        order = "desc"
    state = _normalize_state(raw.get("state"))
    states = _normalize_states_from_tool(raw.get("states"))
    fuel_types = _normalize_fuel_types_from_tool(raw.get("fuel_types"))
    emm = raw.get("emm_region")
    if isinstance(emm, str):
        emm = emm.strip() or None
    else:
        emm = None

    min_gap = _parse_opt_int(raw.get("min_stranded_gap"))
    if min_gap is not None and min_gap < 0:
        min_gap = None
    max_gap = _parse_opt_int(raw.get("max_stranded_gap"))
    if max_gap is not None and max_gap < 0:
        max_gap = None
    min_gap, max_gap = _fix_int_pair(min_gap, max_gap)

    cy_lo = _parse_opt_int(raw.get("commission_year_min"))
    cy_hi = _parse_opt_int(raw.get("commission_year_max"))
    cy_lo, cy_hi = _fix_int_pair(cy_lo, cy_hi)

    pr_lo = _parse_opt_int(raw.get("planned_retirement_year_min"))
    pr_hi = _parse_opt_int(raw.get("planned_retirement_year_max"))
    pr_lo, pr_hi = _fix_int_pair(pr_lo, pr_hi)

    pry_lo = _parse_opt_int(raw.get("projected_retirement_year_min"))
    pry_hi = _parse_opt_int(raw.get("projected_retirement_year_max"))
    pry_lo, pry_hi = _fix_int_pair(pry_lo, pry_hi)

    psy_lo = _parse_opt_int(raw.get("projected_stranded_year_min"))
    psy_hi = _parse_opt_int(raw.get("projected_stranded_year_max"))
    psy_lo, psy_hi = _fix_int_pair(psy_lo, psy_hi)

    nm_lo = _parse_opt_float(raw.get("nameplate_mw_min"))
    nm_hi = _parse_opt_float(raw.get("nameplate_mw_max"))
    nm_lo, nm_hi = _fix_float_pair(nm_lo, nm_hi)

    cf_lo = _parse_opt_float(raw.get("min_capacity_factor"))
    cf_hi = _parse_opt_float(raw.get("max_capacity_factor"))
    if cf_lo is not None:
        cf_lo = max(0.0, min(1.0, cf_lo))
    if cf_hi is not None:
        cf_hi = max(0.0, min(1.0, cf_hi))
    cf_lo, cf_hi = _fix_float_pair(cf_lo, cf_hi)

    cost_lo = _parse_opt_float(raw.get("current_cost_per_mwh_min"))
    cost_hi = _parse_opt_float(raw.get("current_cost_per_mwh_max"))
    cost_lo, cost_hi = _fix_float_pair(cost_lo, cost_hi)

    rev_lo = _parse_opt_float(raw.get("current_revenue_per_mwh_min"))
    rev_hi = _parse_opt_float(raw.get("current_revenue_per_mwh_max"))
    rev_lo, rev_hi = _fix_float_pair(rev_lo, rev_hi)

    margin_lo = _parse_opt_float(raw.get("current_profit_margin_min"))
    margin_hi = _parse_opt_float(raw.get("current_profit_margin_max"))
    margin_lo, margin_hi = _fix_float_pair(margin_lo, margin_hi)

    msg = raw.get("message")
    if not isinstance(msg, str) or not msg.strip():
        msg = "Showing plants matching your filters."
    return {
        "fuel_type": fuel,
        "fuel_types": fuel_types,
        "state": state,
        "states": states,
        "emm_region": emm,
        "min_stranded_gap": min_gap,
        "max_stranded_gap": max_gap,
        "plant_name_contains": _text_opt(raw.get("plant_name_contains")),
        "operator_contains": _text_opt(raw.get("operator_contains")),
        "county_contains": _text_opt(raw.get("county_contains")),
        "balancing_auth_contains": _text_opt(raw.get("balancing_auth_contains")),
        "status_contains": _text_opt(raw.get("status_contains")),
        "commission_year_min": cy_lo,
        "commission_year_max": cy_hi,
        "planned_retirement_year_min": pr_lo,
        "planned_retirement_year_max": pr_hi,
        "projected_retirement_year_min": pry_lo,
        "projected_retirement_year_max": pry_hi,
        "projected_stranded_year_min": psy_lo,
        "projected_stranded_year_max": psy_hi,
        "nameplate_mw_min": nm_lo,
        "nameplate_mw_max": nm_hi,
        "min_capacity_factor": cf_lo,
        "max_capacity_factor": cf_hi,
        "current_cost_per_mwh_min": cost_lo,
        "current_cost_per_mwh_max": cost_hi,
        "current_revenue_per_mwh_min": rev_lo,
        "current_revenue_per_mwh_max": rev_hi,
        "current_profit_margin_min": margin_lo,
        "current_profit_margin_max": margin_hi,
        "sort_by": sort_by,
        "sort_order": order,
        "message": msg.strip(),
    }


def run_nl_query(user_text: str) -> dict[str, Any]:
    """
    Returns a dict:
      - filters_applied: dict | None — pass to GET /api/plants when not None
      - message: str — user-facing interpretation or guardrail text
      - fallback: bool — True if Claude failed and defaults were used
    """
    text = (user_text or "").strip()
    if not text:
        return {
            "filters_applied": None,
            "message": "Enter a question or filter in plain language.",
            "fallback": False,
        }

    if not settings.anthropic_api_key.strip():
        return {
            "filters_applied": {
                "fuel_type": "all",
                "sort_by": "stranded_gap",
                "sort_order": "desc",
            },
            "message": (
                "Natural language search needs ANTHROPIC_API_KEY in backend/.env. "
                "Showing all plants by stranded gap until it is configured."
            ),
            "fallback": True,
        }

    client = Anthropic(api_key=settings.anthropic_api_key)

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            temperature=0,
            system=SYSTEM_PROMPT,
            tools=[LIST_PLANTS_TOOL],
            messages=[{"role": "user", "content": text}],
        )
    except Exception as exc:  # noqa: BLE001 — return safe fallback
        return {
            "filters_applied": {
                "fuel_type": "all",
                "sort_by": "stranded_gap",
                "sort_order": "desc",
            },
            "message": (
                f"Could not reach the language model ({exc!s}). "
                "Showing all plants sorted by stranded gap — try again later."
            ),
            "fallback": True,
        }

    # Tool use: first block with type tool_use
    tool_input: dict[str, Any] | None = None
    text_blocks: list[str] = []
    for block in msg.content:
        btype = getattr(block, "type", None)
        if btype == "tool_use" and getattr(block, "name", "") == "list_plants":
            raw = getattr(block, "input", None)
            if isinstance(raw, dict):
                tool_input = _coerce_tool_input(raw)
        elif btype == "text":
            t = getattr(block, "text", "") or ""
            if t.strip():
                text_blocks.append(t.strip())

    if tool_input is not None:
        filters = {k: v for k, v in tool_input.items() if k != "message"}
        return {
            "filters_applied": filters,
            "message": tool_input["message"],
            "fallback": False,
        }

    # Off-topic or model returned only text
    explanation = " ".join(text_blocks) if text_blocks else (
        "Try asking which coal or gas plants have the largest stranded gap, or narrow by state or region."
    )
    return {
        "filters_applied": None,
        "message": explanation,
        "fallback": False,
    }


def filters_applied_json(filters: dict[str, Any] | None) -> str:
    """Stable JSON for tests / logging."""
    return json.dumps(filters, sort_keys=True) if filters else "null"
