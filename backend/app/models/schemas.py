from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Plant(Base):
    __tablename__ = "plants"

    plant_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    plant_name: Mapped[str] = mapped_column(String(512), default="")
    state: Mapped[str] = mapped_column(String(2), default="")
    county: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    emm_region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    balancing_auth: Mapped[str | None] = mapped_column(String(128), nullable=True)
    primary_fuel: Mapped[str] = mapped_column(String(16), default="")
    nameplate_mw: Mapped[float] = mapped_column(Float, default=0.0)
    commission_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operator_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    planned_retirement_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    projected_retirement_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class PlantMetric(Base):
    __tablename__ = "plant_metrics"

    plant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("plants.plant_id", ondelete="CASCADE"),
        primary_key=True,
    )
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    net_generation_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    capacity_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    fuel_consumption_mmbtu: Mapped[float | None] = mapped_column(Float, nullable=True)
    fuel_cost_per_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    heat_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class RegionalRenewable(Base):
    __tablename__ = "regional_renewables"

    emm_region: Mapped[str] = mapped_column(String(64), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    total_capacity_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    renewable_capacity_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    renewable_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class FuelPriceProjection(Base):
    __tablename__ = "fuel_price_projections"

    fuel_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    price_per_mmbtu: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class RegionalPriceProjection(Base):
    __tablename__ = "regional_price_projections"

    emm_region: Mapped[str] = mapped_column(String(64), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    wholesale_price_per_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class PlantProjection(Base):
    __tablename__ = "plant_projections"

    plant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("plants.plant_id", ondelete="CASCADE"),
        primary_key=True,
    )
    projected_stranded_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stranded_gap_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_cost_per_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_revenue_per_mwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_profit_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class RefreshLog(Base):
    __tablename__ = "refresh_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="in_progress")
    plant_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
