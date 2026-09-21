"""Curated public sources and the passages retrieval matches on.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "evidence_sources",
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("publisher", sa.Text(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("license", sa.Text(), nullable=False),
        sa.Column("published_on", sa.Date(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_id"),
    )
    op.create_table(
        "evidence_passages",
        sa.Column("passage_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("terms", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["evidence_sources.source_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("passage_id"),
    )
    op.create_index("ix_evidence_passages_source_id", "evidence_passages", ["source_id"])
    op.create_index(
        "ix_evidence_passages_terms",
        "evidence_passages",
        ["terms"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_passages_terms", table_name="evidence_passages")
    op.drop_index("ix_evidence_passages_source_id", table_name="evidence_passages")
    op.drop_table("evidence_passages")
    op.drop_table("evidence_sources")
