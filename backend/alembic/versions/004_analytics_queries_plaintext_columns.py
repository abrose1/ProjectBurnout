"""Ensure analytics_queries has readable columns (migrate legacy hash-only rows).

Revision ID: 004_analytics_plaintext
Revises: 003_analytics
Create Date: 2026-03-30

Adds ``query_text``, ``nl_message``, ``filters_applied_json`` and drops ``query_sha256`` /
``query_length`` when an older ``003`` revision created the hash-only schema.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "004_analytics_plaintext"
down_revision: str | None = "003_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    if "analytics_queries" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("analytics_queries")}
    if "query_text" in cols:
        return
    op.add_column("analytics_queries", sa.Column("query_text", sa.Text(), nullable=True))
    op.add_column("analytics_queries", sa.Column("nl_message", sa.Text(), nullable=True))
    op.add_column("analytics_queries", sa.Column("filters_applied_json", sa.Text(), nullable=True))
    if "query_sha256" in cols:
        op.drop_column("analytics_queries", "query_sha256")
    if "query_length" in cols:
        op.drop_column("analytics_queries", "query_length")
    op.execute(text("UPDATE analytics_queries SET query_text = '' WHERE query_text IS NULL"))
    op.execute(text("UPDATE analytics_queries SET nl_message = '' WHERE nl_message IS NULL"))
    op.alter_column(
        "analytics_queries",
        "query_text",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "analytics_queries",
        "nl_message",
        existing_type=sa.Text(),
        nullable=False,
    )


def downgrade() -> None:
    raise NotImplementedError
