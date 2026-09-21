"""Ports the application depends on, stated without naming an implementation."""

from datetime import datetime
from typing import Protocol

from health_assistant.domain.approvals import Approval
from health_assistant.domain.constraints import Constraint, ConstraintSet
from health_assistant.domain.evidence import (
    Candidates,
    EvidencePassage,
    EvidenceRetrieval,
    EvidenceSource,
)
from health_assistant.domain.identifiers import (
    ApprovalId,
    OperationId,
    PlanId,
    RetrievalId,
    SourceId,
    UserId,
)
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

    async def latest(
        self, *, owner_id: UserId, plan_id: PlanId, for_update: bool = False
    ) -> PlanVersion | None:
        """Return the highest-numbered version owned by ``owner_id``, or None.

        ``for_update`` holds the plan so a concurrent revision serializes
        against this read instead of landing between it and the commit.
        """
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

    async def get(
        self, *, owner_id: UserId, approval_id: ApprovalId, for_update: bool = False
    ) -> Approval | None:
        """Load an approval, optionally holding it for the rest of the transaction."""
        ...


class OperationRepository(Protocol):
    """Storage for external operations and the worker's view of the queue."""

    async def add(self, operation: ToolOperation) -> None:
        """Record a newly proposed operation, refusing to overwrite an existing one."""
        ...

    async def advance(self, operation: ToolOperation, *, previous: ToolOperation) -> None:
        """Apply a transition only if the stored row is still ``previous``.

        A write built on a snapshot another transaction has advanced past is
        refused, so it cannot undo committed work such as a live lease.
        """
        ...

    async def get(self, *, owner_id: UserId, operation_id: OperationId) -> ToolOperation | None: ...

    async def claim_next(self) -> ToolOperation | None:
        """Lock and return the oldest queued operation across all users.

        Together with ``expired_leases`` this is one of the two access paths
        that are not owner-scoped, because a worker serves every queue. They
        return operations to work on and no user content; the caller loads the
        rest with each operation's own owner.
        """
        ...

    async def expired_leases(
        self, *, now: datetime, limit: int = 50
    ) -> tuple[ToolOperation, ...]: ...


class EvidenceRepository(Protocol):
    """Storage for the curated corpus.

    Nothing here takes an owner. These are published documents, identical for
    every user, and the absence of an owner parameter is the point rather than
    an omission.
    """

    async def add_source(self, source: EvidenceSource) -> None: ...

    async def add_passage(self, passage: EvidencePassage) -> None: ...

    async def candidates(self, terms: frozenset[str], *, limit: int = 200) -> Candidates:
        """Return passages sharing at least one term, and say if the bound cut in.

        This narrows, it does not rank, so a cutoff can discard the passage that
        would have ranked first. The caller is told rather than left to assume.
        """
        ...

    async def record_retrieval(self, retrieval: EvidenceRetrieval) -> None:
        """Store what a search asked, found, and could not see."""
        ...

    async def retrieval(self, retrieval_id: RetrievalId) -> EvidenceRetrieval | None: ...

    async def source(self, source_id: SourceId) -> EvidenceSource | None: ...


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

    @property
    def evidence(self) -> EvidenceRepository: ...
