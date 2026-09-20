"""Initial schema for users, plans, plan versions, and plan items.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("time_zone", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "plans",
        sa.Column("plan_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("plan_id"),
    )
    op.create_index("ix_plans_owner_id", "plans", ["owner_id"])
    op.create_table(
        "plan_versions",
        sa.Column("plan_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("parent_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_plan_versions_version_positive"),
        sa.CheckConstraint(
            "(version = 1) = (parent_version IS NULL)",
            name="ck_plan_versions_first_has_no_parent",
        ),
        sa.CheckConstraint(
            "parent_version IS NULL OR parent_version < version",
            name="ck_plan_versions_parent_precedes",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.plan_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("plan_id", "version"),
    )
    op.create_index("ix_plan_versions_owner_id", "plan_versions", ["owner_id"])
    op.create_table(
        "plan_items",
        sa.Column("plan_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_zone", sa.Text(), nullable=False),
        sa.Column("attributes", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("completion", sa.Text(), nullable=False),
        sa.CheckConstraint("ends_at > starts_at", name="ck_plan_items_window_ordered"),
        sa.ForeignKeyConstraint(
            ["plan_id", "version"],
            ["plan_versions.plan_id", "plan_versions.version"],
            name="fk_plan_items_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("plan_id", "version", "item_id"),
    )
    op.create_index("ix_plan_items_owner_id", "plan_items", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_plan_items_owner_id", table_name="plan_items")
    op.drop_table("plan_items")
    op.drop_index("ix_plan_versions_owner_id", table_name="plan_versions")
    op.drop_table("plan_versions")
    op.drop_index("ix_plans_owner_id", table_name="plans")
    op.drop_table("plans")
    op.drop_table("users")
