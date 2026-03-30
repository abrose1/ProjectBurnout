"""
EIA Annual Energy Outlook (reference case) → ``fuel_price_projections``, ``regional_price_projections``,
``regional_renewables``.

Uses AEO electricity market module (EMM) region names in ``emm_region`` / regional PK columns so the
projection layer can map plants (future: state/BA → EMM) consistently.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models.schemas import FuelPriceProjection, RegionalPriceProjection, RegionalRenewable, utcnow
from app.projection_horizon import AEO_DATA_LAST_YEAR, PROJECTION_END_YEAR
from app.services.eia_client import EIAClient

logger = logging.getLogger(__name__)

AEO_SCENARIO = "ref2025"
TABLE_EMM = "62"  # AEO API tableId — electric power projections by EMM region
TABLE_RENEW = "67"  # AEO API tableId — renewable capacity by fuel (wind/solar facets)
TABLE_NATIONAL = "3"  # Energy prices — national fuel
REGION_US = "1-0"

SERIES_NG_US = "prce_nom_elep_NA_ng_NA_NA_ndlrpmbtu"
SERIES_COAL_US = "prce_nom_elep_NA_stc_NA_NA_ndlrpmbtu"

UPSERT_BATCH = 400

SOURCE_LABEL = "AEO2025 ref2025"


def _parse_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _clip(s: str, max_len: int) -> str:
    t = str(s).strip()
    if len(t) > max_len:
        t = t[:max_len]
    return t.rstrip()


def _cents_kwh_to_mwh(cents_per_kwh: float) -> float:
    """Nominal cents/kWh → nominal $/MWh (same numeric factor as metrics_refresh)."""
    return cents_per_kwh * 10.0


def _gw_to_mw(gw: float) -> float:
    return gw * 1000.0


def _aeo_facet_table_regions(release: str, table_id: str) -> list[tuple[str, str]]:
    """Return (regionId, regionName) from EIA facet metadata."""
    client = EIAClient()
    try:
        body = client.get(
            f"aeo/{release}/facet/regionId",
            [("facets[tableId][]", table_id)],
        )
    finally:
        client.close()
    err = body.get("error")
    if err:
        raise RuntimeError(str(err))
    facets = (body.get("response") or {}).get("facets") or []
    out: list[tuple[str, str]] = []
    for row in facets:
        rid = row.get("id")
        name = row.get("name")
        if rid and name:
            out.append((str(rid), str(name)))
    return out


def _emm_regions(regions: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Keep EMM regions (5-x) only; drop U.S. aggregates and non-EMM rows."""
    return [(rid, name) for rid, name in regions if rid.startswith("5-") and rid != "5-0"]


def _prefer_projection(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """If duplicate keys, keep PROJECTION over HISTORY."""
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            row.get("seriesId"),
            row.get("regionId"),
            row.get("period"),
        )
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = row
            continue
        if prev.get("history") != "PROJECTION" and row.get("history") == "PROJECTION":
            by_key[key] = row
    return list(by_key.values())


def _fetch_region_table(
    client: EIAClient,
    *,
    release: str,
    table_id: str,
    region_id: str,
) -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = []
    for row in client.iter_data(
        f"aeo/{release}",
        frequency="annual",
        data_fields=["value"],
        facets={
            "scenario": [AEO_SCENARIO],
            "tableId": [table_id],
            "regionId": [region_id],
        },
        page_size=5000,
        start="2025",
        end=str(AEO_DATA_LAST_YEAR),
    ):
        raw.append(row)
    return _prefer_projection(raw)


def _upsert_fuel_batch(session: Session, batch: list[dict[str, Any]]) -> None:
    if not batch:
        return
    stmt = pg_insert(FuelPriceProjection).values(batch)
    stmt = stmt.on_conflict_do_update(
        index_elements=["fuel_type", "year"],
        set_={
            "price_per_mmbtu": stmt.excluded.price_per_mmbtu,
            "source": stmt.excluded.source,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    session.execute(stmt)


def _upsert_regional_price_batch(session: Session, batch: list[dict[str, Any]]) -> None:
    if not batch:
        return
    stmt = pg_insert(RegionalPriceProjection).values(batch)
    stmt = stmt.on_conflict_do_update(
        index_elements=["emm_region", "year"],
        set_={
            "wholesale_price_per_mwh": stmt.excluded.wholesale_price_per_mwh,
            "source": stmt.excluded.source,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    session.execute(stmt)


def _upsert_renewable_batch(session: Session, batch: list[dict[str, Any]]) -> None:
    if not batch:
        return
    stmt = pg_insert(RegionalRenewable).values(batch)
    stmt = stmt.on_conflict_do_update(
        index_elements=["emm_region", "year"],
        set_={
            "total_capacity_mw": stmt.excluded.total_capacity_mw,
            "renewable_capacity_mw": stmt.excluded.renewable_capacity_mw,
            "renewable_pct": stmt.excluded.renewable_pct,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    session.execute(stmt)


def _forward_fill_fuel_rows(
    fuel_rows: list[dict[str, Any]],
    *,
    last_aeo_year: int,
    end_year: int,
    now: Any,
    source_label: str,
) -> None:
    """Append years ``last_aeo_year+1``..``end_year`` using prices from ``last_aeo_year``."""
    if end_year <= last_aeo_year:
        return
    sl = _clip(source_label, 128)
    by_fuel: dict[str, float] = {}
    for r in fuel_rows:
        if int(r["year"]) == last_aeo_year:
            by_fuel[str(r["fuel_type"])] = float(r["price_per_mmbtu"])
    for y in range(last_aeo_year + 1, end_year + 1):
        for ft, p in by_fuel.items():
            fuel_rows.append(
                {
                    "fuel_type": ft,
                    "year": y,
                    "price_per_mmbtu": p,
                    "source": sl,
                    "updated_at": now,
                }
            )


def _forward_fill_regional_rows(
    price_proj: list[dict[str, Any]],
    renew_proj: list[dict[str, Any]],
    *,
    last_aeo_year: int,
    end_year: int,
    now: Any,
    source_label: str,
) -> None:
    """Append wholesale + renewable rows for years beyond AEO using ``last_aeo_year`` values."""
    if end_year <= last_aeo_year:
        return
    sl = _clip(source_label, 128)
    w_by_region: dict[str, float] = {}
    for r in price_proj:
        if int(r["year"]) == last_aeo_year:
            w_by_region[str(r["emm_region"])] = float(r["wholesale_price_per_mwh"])
    for rname, wpm in w_by_region.items():
        for y in range(last_aeo_year + 1, end_year + 1):
            price_proj.append(
                {
                    "emm_region": rname,
                    "year": y,
                    "wholesale_price_per_mwh": wpm,
                    "source": sl,
                    "updated_at": now,
                }
            )
    renew_by_region: dict[str, dict[str, Any]] = {}
    for r in renew_proj:
        if int(r["year"]) == last_aeo_year:
            renew_by_region[str(r["emm_region"])] = r
    for rname, row in renew_by_region.items():
        for y in range(last_aeo_year + 1, end_year + 1):
            renew_proj.append(
                {
                    "emm_region": rname,
                    "year": y,
                    "total_capacity_mw": row["total_capacity_mw"],
                    "renewable_capacity_mw": row["renewable_capacity_mw"],
                    "renewable_pct": row["renewable_pct"],
                    "updated_at": now,
                }
            )


def refresh_aeo_projection_inputs(session: Session, *, aeo_release: str | None = None) -> dict[str, Any]:
    """
    Pull AEO reference-case fuel prices (national), wholesale generation price and capacities by EMM region.

    Commits on success; rolls back on error.
    """
    release = (aeo_release or settings.eia_aeo_release or "2025").strip()
    client = EIAClient()
    now = utcnow()
    try:
        regions = _emm_regions(_aeo_facet_table_regions(release, TABLE_EMM))
        if not regions:
            raise RuntimeError("No EMM regions returned from EIA AEO facets")

        # --- National fuel prices (US census) — table 3
        fuel_rows: list[dict[str, Any]] = []
        for fuel_type, series_id in (("gas", SERIES_NG_US), ("coal", SERIES_COAL_US)):
            body = client.fetch_data(
                f"aeo/{release}",
                frequency="annual",
                data_fields=["value"],
                facets={
                    "scenario": [AEO_SCENARIO],
                    "tableId": [TABLE_NATIONAL],
                    "seriesId": [series_id],
                    "regionId": [REGION_US],
                },
                length=5000,
                offset=0,
                start="2025",
                end=str(AEO_DATA_LAST_YEAR),
            )
            if body.get("error"):
                raise RuntimeError(str(body["error"]))
            for row in (body.get("response") or {}).get("data") or []:
                if row.get("history") == "HISTORY":
                    continue
                y = int(str(row.get("period"))[:4])
                p = _parse_float(row.get("value"))
                if p is None:
                    continue
                fuel_rows.append(
                    {
                        "fuel_type": fuel_type,
                        "year": y,
                        "price_per_mmbtu": p,
                        "source": _clip(SOURCE_LABEL, 128),
                        "updated_at": now,
                    }
                )

        _forward_fill_fuel_rows(
            fuel_rows,
            last_aeo_year=AEO_DATA_LAST_YEAR,
            end_year=PROJECTION_END_YEAR,
            now=now,
            source_label=f"{SOURCE_LABEL} fwd≤{PROJECTION_END_YEAR}",
        )

        for i in range(0, len(fuel_rows), UPSERT_BATCH):
            _upsert_fuel_batch(session, fuel_rows[i : i + UPSERT_BATCH])

        price_proj: list[dict[str, Any]] = []
        renew_proj: list[dict[str, Any]] = []

        for idx, (region_id, region_name) in enumerate(regions):
            if idx:
                time.sleep(0.2)
            key = _clip(region_name, 64)
            rows_62 = _fetch_region_table(client, release=release, table_id=TABLE_EMM, region_id=region_id)
            rows_67 = _fetch_region_table(client, release=release, table_id=TABLE_RENEW, region_id=region_id)

            wholesale_by_year: dict[int, float] = {}
            total_mw_by_year: dict[int, float] = {}
            wind_by_year: dict[int, float] = {}
            solar_by_year: dict[int, float] = {}

            for row in rows_62:
                if row.get("history") == "HISTORY":
                    continue
                sid = str(row.get("seriesId") or "")
                y = int(str(row.get("period"))[:4])
                if (
                    sid.startswith("prce_NA_elep_gen_elc_NA_")
                    and sid.endswith("_ncntpkwh")
                    and "y13" not in sid
                ):
                    v = _parse_float(row.get("value"))
                    if v is not None:
                        wholesale_by_year[y] = _cents_kwh_to_mwh(v)
                if sid.startswith("cap_NA_elep_NA_NA_NA_") and sid.endswith("_gw"):
                    sn = str(row.get("seriesName") or "")
                    if "Total Capacity" in sn and "Electric Power Sector" in sn:
                        v = _parse_float(row.get("value"))
                        if v is not None:
                            total_mw_by_year[y] = _gw_to_mw(v)

            for row in rows_67:
                if row.get("history") == "HISTORY":
                    continue
                sid = str(row.get("seriesId") or "")
                y = int(str(row.get("period"))[:4])
                v = _parse_float(row.get("value"))
                if v is None:
                    continue
                if sid.startswith("cap_gen_NA_NA_wnd_NA_") and sid.endswith("_gw"):
                    wind_by_year[y] = wind_by_year.get(y, 0.0) + _gw_to_mw(v)
                if sid.startswith("cap_gen_NA_NA_slr_NA_") and sid.endswith("_gw"):
                    solar_by_year[y] = solar_by_year.get(y, 0.0) + _gw_to_mw(v)

            for y, wpm in wholesale_by_year.items():
                price_proj.append(
                    {
                        "emm_region": key,
                        "year": y,
                        "wholesale_price_per_mwh": wpm,
                        "source": _clip(SOURCE_LABEL, 128),
                        "updated_at": now,
                    }
                )

            years = set(total_mw_by_year) | set(wind_by_year) | set(solar_by_year)
            for y in sorted(years):
                tot = total_mw_by_year.get(y)
                ren = wind_by_year.get(y, 0.0) + solar_by_year.get(y, 0.0)
                pct = (ren / tot) if tot and tot > 0 else None
                renew_proj.append(
                    {
                        "emm_region": key,
                        "year": y,
                        "total_capacity_mw": tot,
                        "renewable_capacity_mw": ren if ren > 0 else None,
                        "renewable_pct": pct,
                        "updated_at": now,
                    }
                )

        _forward_fill_regional_rows(
            price_proj,
            renew_proj,
            last_aeo_year=AEO_DATA_LAST_YEAR,
            end_year=PROJECTION_END_YEAR,
            now=now,
            source_label=f"{SOURCE_LABEL} fwd≤{PROJECTION_END_YEAR}",
        )

        for i in range(0, len(price_proj), UPSERT_BATCH):
            _upsert_regional_price_batch(session, price_proj[i : i + UPSERT_BATCH])
        for i in range(0, len(renew_proj), UPSERT_BATCH):
            _upsert_renewable_batch(session, renew_proj[i : i + UPSERT_BATCH])

        session.commit()
        return {
            "ok": True,
            "aeo_release": release,
            "emm_regions": len(regions),
            "fuel_price_rows": len(fuel_rows),
            "regional_price_rows": len(price_proj),
            "regional_renewables_rows": len(renew_proj),
        }
    except Exception:
        logger.exception("AEO projection refresh failed")
        session.rollback()
        raise
    finally:
        client.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    from app.models.database import get_session_factory

    sf = get_session_factory()
    with sf() as session:
        out = refresh_aeo_projection_inputs(session)
        print(out)


if __name__ == "__main__":
    main()
