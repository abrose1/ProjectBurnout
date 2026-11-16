"""Analytics: visits + NL query log (readable query text and structured filters).

Revision ID: 003_analytics
Revises: 002_emm_region
Create Date: 2026-03-30

Legacy hash-only ``analytics_queries`` (from an older deploy) is upgraded by **004_analytics_plaintext**.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "003_analytics"
down_revision: str | None = "002_emm_region"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    names = insp.get_table_names()

    if "analytics_visits" not in names:
        op.create_table(
            "analytics_visits",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("visitor_id", sa.String(length=36), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("event_type", sa.String(length=32), nullable=False),
            sa.Column("user_agent_snippet", sa.String(length=256), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_analytics_visits_visitor_occurred",
            "analytics_visits",
            ["visitor_id", "occurred_at"],
        )
        op.create_index("ix_analytics_visits_occurred_at", "analytics_visits", ["occurred_at"])

    if "analytics_queries" not in names:
        op.create_table(
            "analytics_queries",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("visitor_id", sa.String(length=36), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("query_text", sa.Text(), nullable=False),
            sa.Column("nl_message", sa.Text(), nullable=False),
            sa.Column("filters_applied_json", sa.Text(), nullable=True),
            sa.Column("ok", sa.Boolean(), nullable=False),
            sa.Column("status_code", sa.Integer(), nullable=False),
            sa.Column("fallback", sa.Boolean(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_analytics_queries_visitor_occurred",
            "analytics_queries",
            ["visitor_id", "occurred_at"],
        )
        op.create_index("ix_analytics_queries_occurred_at", "analytics_queries", ["occurred_at"])


def downgrade() -> None:
    raise NotImplementedError("Analytics downgrade not supported")
