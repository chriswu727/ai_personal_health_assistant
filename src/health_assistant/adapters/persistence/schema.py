"""PostgreSQL schema for user-owned planning data.

Every user-owned table carries an owner column so that repository queries can
filter on it at every access path rather than relying on reachability through a
join. Instants are stored as ``timestamptz``; the originating IANA zone is kept
in its own column because an offset alone cannot survive a DST change.
"""

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
)

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
        "parent_version IS NULL OR parent_version < version",
        name="ck_plan_versions_parent_precedes",
    ),
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
