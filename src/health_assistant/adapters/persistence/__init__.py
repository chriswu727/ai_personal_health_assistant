"""PostgreSQL persistence for user-owned planning data."""

from health_assistant.adapters.persistence.approvals import SqlApprovalRepository
from health_assistant.adapters.persistence.constraints import SqlConstraintRepository
from health_assistant.adapters.persistence.engine import create_database_engine, unit_of_work
from health_assistant.adapters.persistence.event_loops import new_database_event_loop
from health_assistant.adapters.persistence.evidence import SqlEvidenceRepository
from health_assistant.adapters.persistence.operations import SqlOperationRepository
from health_assistant.adapters.persistence.plans import SqlPlanRepository
from health_assistant.adapters.persistence.schema import metadata
from health_assistant.adapters.persistence.users import SqlUserRepository

__all__ = [
    "SqlApprovalRepository",
    "SqlConstraintRepository",
    "SqlEvidenceRepository",
    "SqlOperationRepository",
    "SqlPlanRepository",
    "SqlUserRepository",
    "create_database_engine",
    "metadata",
    "new_database_event_loop",
    "unit_of_work",
]
