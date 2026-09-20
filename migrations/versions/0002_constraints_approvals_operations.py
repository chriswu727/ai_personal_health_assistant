"""Constraints, approvals, approved actions, and durable operations.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_table(
        "user_constraints",
        sa.Column("constraint_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("window_starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_time_zone", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(subject <> '') <> (window_starts_at IS NOT NULL)",
            name="ck_user_constraints_token_or_window",
        ),
        sa.CheckConstraint(
            "(window_starts_at IS NULL) = (window_ends_at IS NULL)"
            " AND (window_starts_at IS NULL) = (window_time_zone IS NULL)",
            name="ck_user_constraints_window_complete",
        ),
        sa.CheckConstraint(
            "window_ends_at IS NULL OR window_ends_at > window_starts_at",
            name="ck_user_constraints_window_ordered",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("constraint_id"),
    )
    op.create_index("ix_user_constraints_owner_id", "user_constraints", ["owner_id"])

    op.create_table(
        "approvals",
        sa.Column("approval_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("plan_id", sa.Text(), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("payload_fingerprint", sa.Text(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("expires_at > granted_at", name="ck_approvals_expiry_after_grant"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["plan_id", "plan_version"],
            ["plan_versions.plan_id", "plan_versions.version"],
            name="fk_approvals_plan_version",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("approval_id"),
    )
    op.create_index("ix_approvals_owner_id", "approvals", ["owner_id"])

    op.create_table(
        "approval_actions",
        sa.Column("approval_id", sa.Text(), nullable=False),
        sa.Column("item_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("compensates", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.approval_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("approval_id", "item_id", "kind", "compensates"),
    )

    op.create_table(
        "tool_operations",
        sa.Column("operation_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("plan_id", sa.Text(), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("compensates", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("approval_id", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("retry_budget", sa.Integer(), nullable=False),
        sa.Column("lease_worker_id", sa.Text(), nullable=True),
        sa.Column("lease_acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_ref", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_tool_operations_attempts_non_negative"),
        sa.CheckConstraint("retry_budget >= 1", name="ck_tool_operations_budget_positive"),
        sa.CheckConstraint(
            "(lease_worker_id IS NULL) = (lease_acquired_at IS NULL)"
            " AND (lease_worker_id IS NULL) = (lease_expires_at IS NULL)",
            name="ck_tool_operations_lease_complete",
        ),
        sa.CheckConstraint(
            "lease_expires_at IS NULL OR lease_expires_at > lease_acquired_at",
            name="ck_tool_operations_lease_ordered",
        ),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.approval_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["plan_id", "plan_version"],
            ["plan_versions.plan_id", "plan_versions.version"],
            name="fk_tool_operations_plan_version",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("operation_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_tool_operations_idempotency_key"),
    )
    op.create_index("ix_tool_operations_owner_id", "tool_operations", ["owner_id"])
    op.create_index("ix_tool_operations_state_created", "tool_operations", ["state", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_tool_operations_state_created", table_name="tool_operations")
    op.drop_index("ix_tool_operations_owner_id", table_name="tool_operations")
    op.drop_table("tool_operations")
    op.drop_table("approval_actions")
    op.drop_index("ix_approvals_owner_id", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("ix_user_constraints_owner_id", table_name="user_constraints")
    op.drop_table("user_constraints")
