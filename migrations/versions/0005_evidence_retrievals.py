"""Records of what was retrieved, when, and whether the search saw everything.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "evidence_retrievals",
        sa.Column("retrieval_id", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("candidates_considered", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("retrieval_id"),
    )
    op.create_index("ix_evidence_retrievals_retrieved_at", "evidence_retrievals", ["retrieved_at"])
    op.create_table(
        "evidence_retrieval_results",
        sa.Column("retrieval_id", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("passage_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("passage_locator", sa.Text(), nullable=False),
        sa.Column("passage_text", sa.Text(), nullable=False),
        sa.Column("matched_terms", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.CheckConstraint("rank >= 1", name="ck_evidence_retrieval_results_rank_positive"),
        sa.ForeignKeyConstraint(
            ["retrieval_id"], ["evidence_retrievals.retrieval_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("retrieval_id", "rank"),
    )


def downgrade() -> None:
    op.drop_table("evidence_retrieval_results")
    op.drop_index("ix_evidence_retrievals_retrieved_at", table_name="evidence_retrievals")
    op.drop_table("evidence_retrievals")
