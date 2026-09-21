"""Retrieving evidence: narrow in the database, rank in the domain."""

from datetime import datetime

from health_assistant.application.ports import UnitOfWork
from health_assistant.domain.evidence import (
    RetrievedPassage,
    distinct_terms,
    rank_passages,
)

DEFAULT_RESULT_LIMIT = 5


async def search_evidence(
    work: UnitOfWork,
    query: str,
    *,
    at: datetime,
    limit: int = DEFAULT_RESULT_LIMIT,
) -> tuple[RetrievedPassage, ...]:
    """Return the passages a query matches, best first, with their provenance.

    The database narrows to passages sharing a term; the domain decides the
    order. Splitting it that way keeps the ordering a citation depends on
    testable offline and identical on every machine.
    """
    terms = distinct_terms(query)
    if not terms:
        return ()
    candidates = await work.evidence.candidates(terms)
    return rank_passages(candidates, query, at=at, limit=limit)
