"""Tie approvals and operations to a plan version's owner, and require approval.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_plan_versions_owner_identity",
        "plan_versions",
        ["plan_id", "version", "owner_id"],
    )

    op.drop_constraint("fk_approvals_plan_version", "approvals", type_="foreignkey")
    op.create_foreign_key(
        "fk_approvals_plan_version",
        "approvals",
        "plan_versions",
        ["plan_id", "plan_version", "owner_id"],
        ["plan_id", "version", "owner_id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("fk_tool_operations_plan_version", "tool_operations", type_="foreignkey")
    op.create_foreign_key(
        "fk_tool_operations_plan_version",
        "tool_operations",
        "plan_versions",
        ["plan_id", "plan_version", "owner_id"],
        ["plan_id", "version", "owner_id"],
        ondelete="CASCADE",
    )

    op.create_check_constraint(
        "ck_tool_operations_approved_before_execution",
        "tool_operations",
        "state IN ('proposed', 'awaiting_confirmation', 'cancelled') OR approval_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_tool_operations_approved_before_execution",
        "tool_operations",
        type_="check",
    )
    op.drop_constraint("fk_tool_operations_plan_version", "tool_operations", type_="foreignkey")
    op.create_foreign_key(
        "fk_tool_operations_plan_version",
        "tool_operations",
        "plan_versions",
        ["plan_id", "plan_version"],
        ["plan_id", "version"],
        ondelete="CASCADE",
    )
    op.drop_constraint("fk_approvals_plan_version", "approvals", type_="foreignkey")
    op.create_foreign_key(
        "fk_approvals_plan_version",
        "approvals",
        "plan_versions",
        ["plan_id", "plan_version"],
        ["plan_id", "version"],
        ondelete="CASCADE",
    )
    op.drop_constraint("uq_plan_versions_owner_identity", "plan_versions", type_="unique")
