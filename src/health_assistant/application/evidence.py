"""Retrieving evidence: narrow in the database, rank in the domain, keep the record."""

from datetime import datetime

from health_assistant.application.ports import UnitOfWork
from health_assistant.domain.evidence import (
    EvidenceRetrieval,
    distinct_terms,
    rank_passages,
)
from health_assistant.domain.identifiers import RetrievalId

DEFAULT_RESULT_LIMIT = 5


async def search_evidence(
    work: UnitOfWork,
    query: str,
    *,
    retrieval_id: RetrievalId,
    at: datetime,
    limit: int = DEFAULT_RESULT_LIMIT,
) -> EvidenceRetrieval:
    """Search the corpus and record what the search saw.

    The database narrows to passages sharing a term; the domain decides the
    order. Splitting it that way keeps the ordering a citation depends on
    testable offline and identical on every machine.

    The record is written before returning, and that is deliberate: a citation
    that cannot be checked later against what was actually retrieved is a claim,
    not a citation. The record also carries whether the search saw the whole
    corpus, so a caller can tell a confident answer from a partial one.
    """
    terms = distinct_terms(query)
    candidates = await work.evidence.candidates(terms)
    retrieval = EvidenceRetrieval(
        retrieval_id=retrieval_id,
        query=query,
        retrieved_at=at,
        results=rank_passages(candidates.passages, query, at=at, limit=limit),
        candidates_considered=len(candidates.passages),
        truncated=candidates.truncated,
    )
    await work.evidence.record_retrieval(retrieval)
    return retrieval
