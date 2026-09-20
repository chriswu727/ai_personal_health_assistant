"""Ports the application depends on, stated without naming an implementation."""

from datetime import datetime
from typing import Protocol

from health_assistant.domain.approvals import Approval
from health_assistant.domain.constraints import Constraint, ConstraintSet
from health_assistant.domain.identifiers import ApprovalId, OperationId, PlanId, UserId
from health_assistant.domain.operations import ToolOperation
from health_assistant.domain.plans import PlanVersion


class PlanRepository(Protocol):
    """Storage for immutable plan versions.

    Every method takes the acting owner. Ownership is a query predicate rather
    than a check performed after loading, so a request for another user's plan
    returns nothing instead of returning a row that a caller must remember to
    reject.
    """

    async def save(self, version: PlanVersion) -> None:
        """Persist a new version, rejecting one that already exists."""
        ...

    async def get(self, *, owner_id: UserId, plan_id: PlanId, version: int) -> PlanVersion | None:
        """Return one version owned by ``owner_id``, or None."""
        ...

    async def latest(self, *, owner_id: UserId, plan_id: PlanId) -> PlanVersion | None:
        """Return the highest-numbered version owned by ``owner_id``, or None."""
        ...


class UserRepository(Protocol):
    """Storage for the user records that owned data references."""

    async def ensure(self, *, user_id: UserId, time_zone: str, created_at: datetime) -> None: ...

    async def exists(self, user_id: UserId) -> bool: ...


class ConstraintRepository(Protocol):
    """Storage for the restrictions a plan must respect."""

    async def save(self, constraint: Constraint) -> None: ...

    async def all_for(self, owner_id: UserId) -> ConstraintSet: ...

    async def active_at(self, owner_id: UserId, at: datetime) -> ConstraintSet: ...


class ApprovalRepository(Protocol):
    """Storage for user confirmations and the actions they authorize."""

    async def save(self, approval: Approval) -> None: ...

    async def get(self, *, owner_id: UserId, approval_id: ApprovalId) -> Approval | None: ...


class OperationRepository(Protocol):
    """Storage for external operations and the worker's view of the queue."""

    async def save(self, operation: ToolOperation) -> None: ...

    async def get(self, *, owner_id: UserId, operation_id: OperationId) -> ToolOperation | None: ...

    async def claim_next(self) -> ToolOperation | None:
        """Lock and return the oldest queued operation across all users.

        This is the one access path that is not owner-scoped, because a worker
        serves every queue. It returns an operation to work on and no user
        content; the caller loads the rest with that operation's owner.
        """
        ...

    async def expired_leases(
        self, *, now: datetime, limit: int = 50
    ) -> tuple[ToolOperation, ...]: ...


class UnitOfWork(Protocol):
    """One transactional boundary exposing the repositories it spans."""

    @property
    def plans(self) -> PlanRepository: ...

    @property
    def users(self) -> UserRepository: ...

    @property
    def constraints(self) -> ConstraintRepository: ...

    @property
    def approvals(self) -> ApprovalRepository: ...

    @property
    def operations(self) -> OperationRepository: ...
