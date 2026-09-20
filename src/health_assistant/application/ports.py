"""Ports the application depends on, stated without naming an implementation."""

from datetime import datetime
from typing import Protocol

from health_assistant.domain.identifiers import PlanId, UserId
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


class UnitOfWork(Protocol):
    """One transactional boundary exposing the repositories it spans."""

    @property
    def plans(self) -> PlanRepository: ...

    @property
    def users(self) -> UserRepository: ...
