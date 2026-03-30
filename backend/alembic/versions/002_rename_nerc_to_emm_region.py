"""Rename nerc_region to emm_region (EIA EMM / AEO market regions).

Revision ID: 002_emm_region
Revises: 001_initial
Create Date: 2025-03-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_emm_region"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("plants", "nerc_region", new_column_name="emm_region")
    op.alter_column("regional_renewables", "nerc_region", new_column_name="emm_region")
    op.alter_column("regional_price_projections", "nerc_region", new_column_name="emm_region")


def downgrade() -> None:
    op.alter_column("plants", "emm_region", new_column_name="nerc_region")
    op.alter_column("regional_renewables", "emm_region", new_column_name="nerc_region")
    op.alter_column("regional_price_projections", "emm_region", new_column_name="nerc_region")
