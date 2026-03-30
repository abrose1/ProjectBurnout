"""Pydantic models for REST API responses (distinct from SQLAlchemy models in app.models.schemas)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlantProjectionBrief(BaseModel):
    model_config = {"from_attributes": True}

    projected_stranded_year: int | None = None
    stranded_gap_years: int | None = None
    current_cost_per_mwh: float | None = None
    current_revenue_per_mwh: float | None = None
    current_profit_margin: float | None = None
    computed_at: datetime | None = None


class PlantListItem(BaseModel):
    model_config = {"from_attributes": True}

    plant_id: str
    plant_name: str
    state: str
    county: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    emm_region: str | None = None
    primary_fuel: str
    nameplate_mw: float
    commission_year: int | None = None
    planned_retirement_year: int | None = None
    projected_retirement_year: int | None = None
    latest_capacity_factor: float | None = None
    latest_metric_year: int | None = None
    projection: PlantProjectionBrief | None = None


class PlantListResponse(BaseModel):
    items: list[PlantListItem]
    total: int
    limit: int
    offset: int


class PlantMetricRow(BaseModel):
    model_config = {"from_attributes": True}

    year: int
    net_generation_mwh: float | None = None
    capacity_factor: float | None = None
    fuel_consumption_mmbtu: float | None = None
    fuel_cost_per_mwh: float | None = None
    heat_rate: float | None = None


class PlantDetailResponse(BaseModel):
    plant_id: str
    plant_name: str
    state: str
    county: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    emm_region: str | None = None
    balancing_auth: str | None = None
    primary_fuel: str
    nameplate_mw: float
    commission_year: int | None = None
    operator_name: str | None = None
    status: str | None = None
    planned_retirement_year: int | None = None
    projected_retirement_year: int | None = None
    updated_at: datetime | None = None
    metrics: list[PlantMetricRow] = Field(default_factory=list)
    projection: PlantProjectionBrief | None = None


class RegionItem(BaseModel):
    emm_region: str
    plant_count: int
    avg_stranded_gap_years: float | None
    renewable_pct_latest: float | None = None
    renewable_data_year: int | None = None


class RegionsResponse(BaseModel):
    items: list[RegionItem]


class DataFreshness(BaseModel):
    last_plant_inventory_refresh: datetime | None = None
    last_projection_computed: datetime | None = None


class StatsResponse(BaseModel):
    total_plants: int
    avg_stranded_gap_coal: float | None = None
    avg_stranded_gap_gas: float | None = None
    plants_at_risk_count: int = 0
    highest_risk_region: str | None = None
    highest_risk_region_avg_gap: float | None = None
    data_freshness: DataFreshness


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)


class FiltersApplied(BaseModel):
    """Subset of GET /api/plants query params after NL translation (flat keys)."""

    model_config = ConfigDict(extra="ignore")

    fuel_type: str = "all"
    sort_by: str = "stranded_gap"
    sort_order: str = "desc"
    state: str | None = None
    states: list[str] | None = None
    fuel_types: list[str] | None = None
    emm_region: str | None = None
    min_stranded_gap: int | None = None
    max_stranded_gap: int | None = None
    plant_name_contains: str | None = None
    operator_contains: str | None = None
    county_contains: str | None = None
    balancing_auth_contains: str | None = None
    status_contains: str | None = None
    commission_year_min: int | None = None
    commission_year_max: int | None = None
    planned_retirement_year_min: int | None = None
    planned_retirement_year_max: int | None = None
    projected_retirement_year_min: int | None = None
    projected_retirement_year_max: int | None = None
    projected_stranded_year_min: int | None = None
    projected_stranded_year_max: int | None = None
    nameplate_mw_min: float | None = None
    nameplate_mw_max: float | None = None
    min_capacity_factor: float | None = None
    max_capacity_factor: float | None = None
    current_cost_per_mwh_min: float | None = None
    current_cost_per_mwh_max: float | None = None
    current_revenue_per_mwh_min: float | None = None
    current_revenue_per_mwh_max: float | None = None
    current_profit_margin_min: float | None = None
    current_profit_margin_max: float | None = None


class QueryResponse(BaseModel):
    message: str
    filters_applied: FiltersApplied | None = None
    fallback: bool = False
