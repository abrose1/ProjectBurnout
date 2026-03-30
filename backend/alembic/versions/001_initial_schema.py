"""Initial schema: plants, metrics, projections, regional, refresh log.

Revision ID: 001_initial
Revises:
Create Date: 2025-03-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plants",
        sa.Column("plant_id", sa.String(length=32), nullable=False),
        sa.Column("plant_name", sa.String(length=512), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("county", sa.String(length=128), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("nerc_region", sa.String(length=64), nullable=True),
        sa.Column("balancing_auth", sa.String(length=128), nullable=True),
        sa.Column("primary_fuel", sa.String(length=16), nullable=False),
        sa.Column("nameplate_mw", sa.Float(), nullable=False),
        sa.Column("commission_year", sa.Integer(), nullable=True),
        sa.Column("operator_name", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("planned_retirement_year", sa.Integer(), nullable=True),
        sa.Column("projected_retirement_year", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("plant_id"),
    )
    op.create_table(
        "fuel_price_projections",
        sa.Column("fuel_type", sa.String(length=16), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("price_per_mmbtu", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("fuel_type", "year"),
    )
    op.create_table(
        "regional_price_projections",
        sa.Column("nerc_region", sa.String(length=64), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("wholesale_price_per_mwh", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("nerc_region", "year"),
    )
    op.create_table(
        "regional_renewables",
        sa.Column("nerc_region", sa.String(length=64), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("total_capacity_mw", sa.Float(), nullable=True),
        sa.Column("renewable_capacity_mw", sa.Float(), nullable=True),
        sa.Column("renewable_pct", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("nerc_region", "year"),
    )
    op.create_table(
        "refresh_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("plant_count", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "plant_metrics",
        sa.Column("plant_id", sa.String(length=32), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("net_generation_mwh", sa.Float(), nullable=True),
        sa.Column("capacity_factor", sa.Float(), nullable=True),
        sa.Column("fuel_consumption_mmbtu", sa.Float(), nullable=True),
        sa.Column("fuel_cost_per_mwh", sa.Float(), nullable=True),
        sa.Column("heat_rate", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["plant_id"],
            ["plants.plant_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("plant_id", "year"),
    )
    op.create_table(
        "plant_projections",
        sa.Column("plant_id", sa.String(length=32), nullable=False),
        sa.Column("projected_stranded_year", sa.Integer(), nullable=True),
        sa.Column("stranded_gap_years", sa.Integer(), nullable=True),
        sa.Column("current_cost_per_mwh", sa.Float(), nullable=True),
        sa.Column("current_revenue_per_mwh", sa.Float(), nullable=True),
        sa.Column("current_profit_margin", sa.Float(), nullable=True),
        sa.Column("computed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["plant_id"],
            ["plants.plant_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("plant_id"),
    )


def downgrade() -> None:
    op.drop_table("plant_projections")
    op.drop_table("plant_metrics")
    op.drop_table("refresh_log")
    op.drop_table("regional_renewables")
    op.drop_table("regional_price_projections")
    op.drop_table("fuel_price_projections")
    op.drop_table("plants")
