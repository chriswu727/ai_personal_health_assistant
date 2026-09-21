"""PostgreSQL schema for user-owned planning data.

Every user-owned table carries an owner column so that repository queries can
filter on it at every access path rather than relying on reachability through a
join. Instants are stored as ``timestamptz``; the originating IANA zone is kept
in its own column because an offset alone cannot survive a DST change.
"""

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY as POSTGRES_ARRAY

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("user_id", Text, primary_key=True),
    Column("time_zone", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

plans = Table(
    "plans",
    metadata,
    Column("plan_id", Text, primary_key=True),
    Column("owner_id", Text, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_plans_owner_id", "owner_id"),
)

plan_versions = Table(
    "plan_versions",
    metadata,
    Column("plan_id", Text, ForeignKey("plans.plan_id", ondelete="CASCADE"), primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("owner_id", Text, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
    Column("parent_version", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("version >= 1", name="ck_plan_versions_version_positive"),
    # The first version is the only one without a parent, and a parent always precedes.
    CheckConstraint(
        "(version = 1) = (parent_version IS NULL)",
        name="ck_plan_versions_first_has_no_parent",
    ),
    CheckConstraint(
        "parent_version IS NULL OR parent_version = version - 1",
        name="ck_plan_versions_parent_is_predecessor",
    ),
    # Self-referencing: a successor cannot exist without the version it revises.
    # A NULL parent is not matched, so the first version is exempt.
    ForeignKeyConstraint(
        ["plan_id", "parent_version"],
        ["plan_versions.plan_id", "plan_versions.version"],
        name="fk_plan_versions_parent",
    ),
    # Lets other tables reference a version together with its owner, so a row
    # cannot claim a plan version that belongs to somebody else.
    UniqueConstraint("plan_id", "version", "owner_id", name="uq_plan_versions_owner_identity"),
    Index("ix_plan_versions_owner_id", "owner_id"),
)

plan_items = Table(
    "plan_items",
    metadata,
    Column("plan_id", Text, primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("item_id", Text, primary_key=True),
    Column("owner_id", Text, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
    Column("category", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("starts_at", DateTime(timezone=True), nullable=False),
    Column("ends_at", DateTime(timezone=True), nullable=False),
    Column("time_zone", Text, nullable=False),
    Column("attributes", ARRAY(Text), nullable=False),
    Column("completion", Text, nullable=False),
    ForeignKeyConstraint(
        ["plan_id", "version"],
        ["plan_versions.plan_id", "plan_versions.version"],
        ondelete="CASCADE",
        name="fk_plan_items_version",
    ),
    CheckConstraint("ends_at > starts_at", name="ck_plan_items_window_ordered"),
    Index("ix_plan_items_owner_id", "owner_id"),
)

user_constraints = Table(
    "user_constraints",
    metadata,
    Column("constraint_id", Text, primary_key=True),
    Column("owner_id", Text, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
    Column("kind", Text, nullable=False),
    Column("severity", Text, nullable=False),
    Column("source", Text, nullable=False),
    Column("subject", Text, nullable=False),
    Column("window_starts_at", DateTime(timezone=True), nullable=True),
    Column("window_ends_at", DateTime(timezone=True), nullable=True),
    Column("window_time_zone", Text, nullable=True),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    # A constraint matches either a token or a time window, never both and never
    # neither, which is the same rule the domain enforces.
    CheckConstraint(
        "(subject <> '') <> (window_starts_at IS NOT NULL)",
        name="ck_user_constraints_token_or_window",
    ),
    CheckConstraint(
        "(window_starts_at IS NULL) = (window_ends_at IS NULL)"
        " AND (window_starts_at IS NULL) = (window_time_zone IS NULL)",
        name="ck_user_constraints_window_complete",
    ),
    CheckConstraint(
        "window_ends_at IS NULL OR window_ends_at > window_starts_at",
        name="ck_user_constraints_window_ordered",
    ),
    Index("ix_user_constraints_owner_id", "owner_id"),
)

approvals = Table(
    "approvals",
    metadata,
    Column("approval_id", Text, primary_key=True),
    Column("owner_id", Text, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
    Column("plan_id", Text, nullable=False),
    Column("plan_version", Integer, nullable=False),
    Column("payload_fingerprint", Text, nullable=False),
    Column("granted_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["plan_id", "plan_version", "owner_id"],
        ["plan_versions.plan_id", "plan_versions.version", "plan_versions.owner_id"],
        ondelete="CASCADE",
        name="fk_approvals_plan_version",
    ),
    CheckConstraint("expires_at > granted_at", name="ck_approvals_expiry_after_grant"),
    Index("ix_approvals_owner_id", "owner_id"),
)

approval_actions = Table(
    "approval_actions",
    metadata,
    Column(
        "approval_id",
        Text,
        ForeignKey("approvals.approval_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("item_id", Text, primary_key=True),
    Column("kind", Text, primary_key=True),
    # An empty string rather than NULL for "no target": PostgreSQL treats NULLs
    # as distinct in a key, so a nullable column would admit duplicate rows.
    Column("compensates", Text, primary_key=True, nullable=False),
)

tool_operations = Table(
    "tool_operations",
    metadata,
    Column("operation_id", Text, primary_key=True),
    Column("owner_id", Text, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
    Column("plan_id", Text, nullable=False),
    Column("plan_version", Integer, nullable=False),
    Column("item_id", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("compensates", Text, nullable=True),
    Column("idempotency_key", Text, nullable=False),
    Column("state", Text, nullable=False),
    Column(
        "approval_id",
        Text,
        ForeignKey("approvals.approval_id", ondelete="RESTRICT"),
        nullable=True,
    ),
    Column("attempts", Integer, nullable=False),
    Column("retry_budget", Integer, nullable=False),
    Column("lease_worker_id", Text, nullable=True),
    Column("lease_acquired_at", DateTime(timezone=True), nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("external_ref", Text, nullable=True),
    Column("last_error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["plan_id", "plan_version", "owner_id"],
        ["plan_versions.plan_id", "plan_versions.version", "plan_versions.owner_id"],
        ondelete="CASCADE",
        name="fk_tool_operations_plan_version",
    ),
    # One key per external write: a duplicate would let two operations present
    # the same key to a provider and defeat its deduplication.
    UniqueConstraint("idempotency_key", name="uq_tool_operations_idempotency_key"),
    # Nothing gets past confirmation without a recorded approval. Cancellation
    # is the one way out of the states before it, so it is exempt.
    CheckConstraint(
        "state IN ('proposed', 'awaiting_confirmation', 'cancelled') OR approval_id IS NOT NULL",
        name="ck_tool_operations_approved_before_execution",
    ),
    CheckConstraint("attempts >= 0", name="ck_tool_operations_attempts_non_negative"),
    CheckConstraint("retry_budget >= 1", name="ck_tool_operations_budget_positive"),
    CheckConstraint(
        "(lease_worker_id IS NULL) = (lease_acquired_at IS NULL)"
        " AND (lease_worker_id IS NULL) = (lease_expires_at IS NULL)",
        name="ck_tool_operations_lease_complete",
    ),
    CheckConstraint(
        "lease_expires_at IS NULL OR lease_expires_at > lease_acquired_at",
        name="ck_tool_operations_lease_ordered",
    ),
    Index("ix_tool_operations_owner_id", "owner_id"),
    # Supports the worker's claim scan without a sequential table read.
    Index("ix_tool_operations_state_created", "state", "created_at"),
)


# Public knowledge, not personal data. These two tables carry no owner column
# and no repository method scopes them, because no user owns a published source.
# Keeping them visibly separate from the owned tables is the point: a passage is
# text somebody else wrote, quotable and citable, never a private fact and never
# an instruction.
evidence_sources = Table(
    "evidence_sources",
    metadata,
    Column("source_id", Text, primary_key=True),
    Column("title", Text, nullable=False),
    Column("publisher", Text, nullable=False),
    Column("locator", Text, nullable=False),
    Column("license", Text, nullable=False),
    Column("published_on", Date, nullable=True),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
)

evidence_passages = Table(
    "evidence_passages",
    metadata,
    Column("passage_id", Text, primary_key=True),
    Column(
        "source_id",
        Text,
        ForeignKey("evidence_sources.source_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("locator", Text, nullable=False),
    Column("text", Text, nullable=False),
    # Stored rather than derived on read so the overlap index has something to
    # work on; the domain is what computes them, from the same function.
    Column("terms", POSTGRES_ARRAY(Text), nullable=False),
    Index("ix_evidence_passages_source_id", "source_id"),
    Index("ix_evidence_passages_terms", "terms", postgresql_using="gin"),
)


evidence_retrievals = Table(
    "evidence_retrievals",
    metadata,
    Column("retrieval_id", Text, primary_key=True),
    Column("query", Text, nullable=False),
    Column("retrieved_at", DateTime(timezone=True), nullable=False),
    Column("candidates_considered", Integer, nullable=False),
    Column("truncated", Boolean, nullable=False),
    Index("ix_evidence_retrievals_retrieved_at", "retrieved_at"),
)

# A snapshot, not a reference. The passage columns are copied rather than
# joined, and there is deliberately no foreign key to evidence_passages: the
# record has to survive the corpus being curated afterwards, which is the whole
# reason for keeping it.
evidence_retrieval_results = Table(
    "evidence_retrieval_results",
    metadata,
    Column(
        "retrieval_id",
        Text,
        ForeignKey("evidence_retrievals.retrieval_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("rank", Integer, primary_key=True),
    Column("passage_id", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    Column("passage_locator", Text, nullable=False),
    Column("passage_text", Text, nullable=False),
    Column("matched_terms", POSTGRES_ARRAY(Text), nullable=False),
    CheckConstraint("rank >= 1", name="ck_evidence_retrieval_results_rank_positive"),
)
