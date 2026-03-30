"""
HTTP client for EIA Open Data API v2 (https://api.eia.gov/v2/).

Operating generator inventory uses monthly frequency; filter by energy_source_code and status.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

EIA_BASE = "https://api.eia.gov/v2"

# Coal + gas codes used for fossil plant inventory (per implementation plan)
COAL_ENERGY_CODES = ("BIT", "SUB", "LIG", "RC")
GAS_ENERGY_CODES = ("NG",)

DEFAULT_PAGE = 5000
# Enough for transient 504s/timeouts without long retry storms if EIA is down.
MAX_RETRIES = 4
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
_BACKOFF_CAP_S = 30.0


def _default_timeout() -> httpx.Timeout:
    """Long read timeout for large AEO /data/ pulls; connect stays bounded."""
    return httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)


class EIAClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: httpx.Timeout | float | None = None,
    ) -> None:
        self._api_key = (api_key or settings.eia_api_key or "").strip()
        t = timeout if timeout is not None else _default_timeout()
        self._client = httpx.Client(timeout=t)

    def _get(self, path: str, params: list[tuple[str, str]]) -> dict[str, Any]:
        """path: relative to v2, e.g. electricity/operating-generator-capacity/data/"""
        url = f"{EIA_BASE}/{path.lstrip('/')}"
        full: list[tuple[str, str]] = [("api_key", self._api_key), *params]
        for attempt in range(MAX_RETRIES):
            try:
                r = self._client.get(url, params=full)
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError as e:
                code = e.response.status_code if e.response is not None else 0
                if code in RETRYABLE_STATUS and attempt < MAX_RETRIES - 1:
                    wait = min(2**attempt + random.uniform(0.0, 1.0), _BACKOFF_CAP_S)
                    logger.warning(
                        "EIA HTTP %s (attempt %s/%s), retry in %.1fs: %s",
                        code,
                        attempt + 1,
                        MAX_RETRIES,
                        wait,
                        url[:120],
                    )
                    time.sleep(wait)
                    continue
                raise
            except httpx.RequestError as e:
                if attempt < MAX_RETRIES - 1:
                    wait = min(2**attempt + random.uniform(0.0, 1.0), _BACKOFF_CAP_S)
                    logger.warning(
                        "EIA request error (attempt %s/%s), retry in %.1fs: %s — %s",
                        attempt + 1,
                        MAX_RETRIES,
                        wait,
                        url[:120],
                        e,
                    )
                    time.sleep(wait)
                    continue
                raise

    def get(self, path: str, params: list[tuple[str, str]] | None = None) -> dict[str, Any]:
        """GET ``/v2/{path}`` with retries (facets, metadata, or /data/)."""
        return self._get(path, params or [])

    def get_latest_facility_fuel_annual_year(self) -> int:
        """Latest calendar year available for ``electricity/facility-fuel`` (annual)."""
        meta_body = self.get_route_metadata("electricity/facility-fuel")
        err = meta_body.get("error")
        if err:
            raise RuntimeError(str(err))
        r = meta_body.get("response") or meta_body
        end = r.get("endPeriod")
        if isinstance(end, str) and len(end) >= 4:
            try:
                return int(end[:4])
            except ValueError:
                pass
        sample = self.fetch_data(
            "electricity/facility-fuel",
            frequency="annual",
            data_fields=["generation"],
            facets={"fuel2002": ["ALL"]},
            length=1,
            offset=0,
            sort=[("period", "desc")],
        )
        if sample.get("error"):
            raise RuntimeError(str(sample["error"]))
        rows = (sample.get("response") or {}).get("data") or []
        if not rows:
            raise RuntimeError("Could not determine latest facility-fuel annual year")
        p = rows[0].get("period")
        if not p:
            raise RuntimeError("EIA row missing period")
        return int(str(p)[:4])

    def get_latest_inventory_period(self) -> str:
        """Latest ``YYYY-MM`` period for operating-generator-capacity (route metadata)."""
        meta_body = self.get_route_metadata("electricity/operating-generator-capacity")
        err = meta_body.get("error")
        if err:
            raise RuntimeError(str(err))
        r = meta_body.get("response") or meta_body
        end = r.get("endPeriod")
        if isinstance(end, str) and len(end) >= 7:
            return end[:7]
        # Fallback: one-row query sorted by period
        sample = self.fetch_data(
            "electricity/operating-generator-capacity",
            frequency="monthly",
            data_fields=["nameplate-capacity-mw"],
            facets={"energy_source_code": ["NG"], "status": ["OP"]},
            length=1,
            offset=0,
            sort=[("period", "desc")],
        )
        if sample.get("error"):
            raise RuntimeError(str(sample["error"]))
        rows = (sample.get("response") or {}).get("data") or []
        if not rows:
            raise RuntimeError("Could not determine latest inventory period")
        p = rows[0].get("period")
        if not p:
            raise RuntimeError("EIA row missing period")
        return str(p)[:7]

    def get_route_metadata(self, route: str) -> dict[str, Any]:
        """GET route root (no /data/) — facets, data field ids, frequency list."""
        path = route.rstrip("/") + "/"
        return self._get(path, [])

    def fetch_data(
        self,
        route: str,
        *,
        frequency: str,
        data_fields: list[str] | None = None,
        facets: dict[str, list[str]] | None = None,
        length: int = DEFAULT_PAGE,
        offset: int = 0,
        sort: list[tuple[str, str]] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        """One page of /data/ for a route.

        For monthly routes, ``start`` / ``end`` use ``YYYY-MM`` (inclusive) to
        restrict the inventory snapshot to a single month.
        """
        path = route.rstrip("/") + "/data/"
        params: list[tuple[str, str]] = [
            ("frequency", frequency),
            ("length", str(length)),
            ("offset", str(offset)),
        ]
        if start:
            params.append(("start", start))
        if end:
            params.append(("end", end))
        if data_fields:
            for i, field in enumerate(data_fields):
                params.append((f"data[{i}]", field))
        if facets:
            for facet_name, values in facets.items():
                for v in values:
                    params.append((f"facets[{facet_name}][]", v))
        if sort:
            for i, (col, direction) in enumerate(sort):
                params.append((f"sort[{i}][column]", col))
                params.append((f"sort[{i}][direction]", direction))
        return self._get(path, params)

    def iter_data(
        self,
        route: str,
        *,
        frequency: str,
        data_fields: list[str] | None = None,
        facets: dict[str, list[str]] | None = None,
        page_size: int = DEFAULT_PAGE,
        max_rows: int | None = None,
        start: str | None = None,
        end: str | None = None,
    ):
        """Yield rows across all pages (optionally cap total rows)."""
        offset = 0
        yielded = 0
        while True:
            body = self.fetch_data(
                route,
                frequency=frequency,
                data_fields=data_fields,
                facets=facets,
                length=page_size,
                offset=offset,
                start=start,
                end=end,
            )
            err = body.get("error")
            if err:
                raise RuntimeError(str(err))
            resp = body.get("response") or {}
            rows = resp.get("data") or []
            total = int(resp.get("total") or 0)
            for row in rows:
                yield row
                yielded += 1
                if max_rows is not None and yielded >= max_rows:
                    return
            offset += len(rows)
            if not rows or offset >= total:
                break

    def ping_operating_generators(self) -> dict[str, Any]:
        """
        Lightweight connectivity check: route metadata + 2 rows of operable natural gas.
        Does not paginate the full dataset.
        """
        if not self._api_key:
            return {"ok": False, "error": "EIA_API_KEY is not set"}

        meta_body = self.get_route_metadata("electricity/operating-generator-capacity")
        meta_err = meta_body.get("error")
        if meta_err:
            return {"ok": False, "error": meta_err}

        meta = meta_body.get("response") or meta_body
        data_body = self.fetch_data(
            "electricity/operating-generator-capacity",
            frequency="monthly",
            data_fields=[
                "nameplate-capacity-mw",
                "latitude",
                "longitude",
                "operating-year-month",
                "planned-retirement-year-month",
                "county",
            ],
            facets={"energy_source_code": ["NG"], "status": ["OP"]},
            length=2,
            offset=0,
            sort=[("period", "desc")],
        )
        derr = data_body.get("error")
        if derr:
            return {"ok": False, "error": derr}

        dresp = data_body.get("response") or {}
        return {
            "ok": True,
            "route_id": meta.get("id"),
            "frequency": meta.get("frequency"),
            "total_matching_rows": dresp.get("total"),
            "sample_rows": dresp.get("data") or [],
        }

    def close(self) -> None:
        self._client.close()
