"""Storage for the curated corpus and for each user's record of consulting it.

The corpus methods take no owner. Sources and passages are published documents,
identical for every user, and scoping them to one would be meaningless. The
owned tables and the corpus are deliberately different shapes so the
distinction is visible in the code rather than only in a document.

Retrieval history is the opposite case. A query can carry personal health
information, so every record belongs to the user who searched, is read only
with their identifier, and is removed with their account.
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from health_assistant.adapters.persistence.schema import (
    evidence_passages,
    evidence_retrieval_results,
    evidence_retrievals,
    evidence_sources,
)
from health_assistant.domain.evidence import (
    Candidates,
    EvidencePassage,
    EvidenceRetrieval,
    EvidenceSource,
    RetrievedPassage,
)
from health_assistant.domain.identifiers import PassageId, RetrievalId, SourceId, UserId

DEFAULT_CANDIDATE_LIMIT = 200


class SqlEvidenceRepository:
    """Corpus and retrieval-history persistence scoped to one transaction."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add_source(self, source: EvidenceSource) -> None:
        """Store or replace a source. Corpus curation is an administrative act."""
        statement = insert(evidence_sources).values(
            source_id=source.source_id,
            title=source.title,
            publisher=source.publisher,
            locator=source.locator,
            license=source.license,
            published_on=source.published_on,
            recorded_at=source.recorded_at,
        )
        await self._connection.execute(
            statement.on_conflict_do_update(
                index_elements=["source_id"],
                set_={
                    column: statement.excluded[column]
                    for column in (
                        "title",
                        "publisher",
                        "locator",
                        "license",
                        "published_on",
                        "recorded_at",
                    )
                },
            )
        )

    async def add_passage(self, passage: EvidencePassage) -> None:
        statement = insert(evidence_passages).values(
            passage_id=passage.passage_id,
            source_id=passage.source_id,
            locator=passage.locator,
            text=passage.text,
            terms=sorted(passage.terms),
        )
        await self._connection.execute(
            statement.on_conflict_do_update(
                index_elements=["passage_id"],
                set_={
                    column: statement.excluded[column]
                    for column in ("source_id", "locator", "text", "terms")
                },
            )
        )

    async def candidates(
        self, terms: frozenset[str], *, limit: int = DEFAULT_CANDIDATE_LIMIT
    ) -> Candidates:
        """Return passages sharing at least one term, and say if the bound cut in.

        This narrows; it does not rank. Narrowing orders by identifier, so a
        bound that cuts in can discard the passage that would have ranked first.
        One extra row is fetched purely to detect that, because a silent cutoff
        turns a weak answer into a wrong one.
        """
        if not terms:
            return Candidates(passages=(), truncated=False)
        result = await self._connection.execute(
            select(evidence_passages)
            .where(evidence_passages.c.terms.overlap(sorted(terms)))
            .order_by(evidence_passages.c.passage_id)
            .limit(limit + 1)
        )
        found = tuple(
            EvidencePassage(
                passage_id=PassageId(row["passage_id"]),
                source_id=SourceId(row["source_id"]),
                locator=row["locator"],
                text=row["text"],
            )
            for row in result.mappings()
        )
        return Candidates(passages=found[:limit], truncated=len(found) > limit)

    async def sources(self, source_ids: frozenset[SourceId]) -> dict[SourceId, EvidenceSource]:
        """Return the named sources that exist, keyed by identifier."""
        if not source_ids:
            return {}
        result = await self._connection.execute(
            select(evidence_sources).where(evidence_sources.c.source_id.in_(sorted(source_ids)))
        )
        found = (_to_source(dict(row)) for row in result.mappings())
        return {source.source_id: source for source in found}

    async def source(self, source_id: SourceId) -> EvidenceSource | None:
        result = await self._connection.execute(
            select(evidence_sources).where(evidence_sources.c.source_id == source_id)
        )
        row = result.mappings().one_or_none()
        return None if row is None else _to_source(dict(row))

    async def record_retrieval(self, retrieval: EvidenceRetrieval) -> None:
        """Store what a user's search asked, found, and could not see.

        Result rows copy the passage and its source's provenance rather than
        pointing at the corpus, so the record still describes the retrieval
        after the corpus is curated again.
        """
        await self._connection.execute(
            insert(evidence_retrievals).values(
                retrieval_id=retrieval.retrieval_id,
                owner_id=retrieval.owner_id,
                query=retrieval.query,
                retrieved_at=retrieval.retrieved_at,
                candidates_considered=retrieval.candidates_considered,
                truncated=retrieval.truncated,
            )
        )
        if not retrieval.results:
            return
        await self._connection.execute(
            insert(evidence_retrieval_results),
            [
                {
                    "retrieval_id": retrieval.retrieval_id,
                    "rank": item.rank,
                    "passage_id": item.passage.passage_id,
                    "source_id": item.passage.source_id,
                    "passage_locator": item.passage.locator,
                    "passage_text": item.passage.text,
                    "source_title": item.source.title,
                    "source_publisher": item.source.publisher,
                    "source_locator": item.source.locator,
                    "source_license": item.source.license,
                    "source_published_on": item.source.published_on,
                    "matched_terms": sorted(item.matched_terms),
                }
                for item in retrieval.results
            ],
        )

    async def retrieval(
        self, *, owner_id: UserId, retrieval_id: RetrievalId
    ) -> EvidenceRetrieval | None:
        """Load one of the owner's past retrievals from its own record, joining nothing."""
        header = await self._connection.execute(
            select(evidence_retrievals).where(
                evidence_retrievals.c.retrieval_id == retrieval_id,
                evidence_retrievals.c.owner_id == owner_id,
            )
        )
        row = header.mappings().one_or_none()
        if row is None:
            return None
        results = await self._connection.execute(
            select(evidence_retrieval_results)
            .where(evidence_retrieval_results.c.retrieval_id == retrieval_id)
            .order_by(evidence_retrieval_results.c.rank)
        )
        retrieved_at = row["retrieved_at"]
        return EvidenceRetrieval(
            retrieval_id=RetrievalId(row["retrieval_id"]),
            owner_id=UserId(row["owner_id"]),
            query=row["query"],
            retrieved_at=retrieved_at,
            results=tuple(
                RetrievedPassage(
                    passage=EvidencePassage(
                        passage_id=PassageId(item["passage_id"]),
                        source_id=SourceId(item["source_id"]),
                        locator=item["passage_locator"],
                        text=item["passage_text"],
                    ),
                    source=EvidenceSource(
                        source_id=SourceId(item["source_id"]),
                        title=item["source_title"],
                        publisher=item["source_publisher"],
                        locator=item["source_locator"],
                        license=item["source_license"],
                        # The snapshot has no recording instant of its own; the
                        # retrieval instant is when this provenance was captured.
                        recorded_at=retrieved_at,
                        published_on=item["source_published_on"],
                    ),
                    query=row["query"],
                    matched_terms=frozenset(item["matched_terms"]),
                    rank=item["rank"],
                    retrieved_at=retrieved_at,
                )
                for item in results.mappings()
            ),
            candidates_considered=row["candidates_considered"],
            truncated=row["truncated"],
        )


def _to_source(row: Mapping[str, Any]) -> EvidenceSource:
    return EvidenceSource(
        source_id=SourceId(row["source_id"]),
        title=row["title"],
        publisher=row["publisher"],
        locator=row["locator"],
        license=row["license"],
        recorded_at=row["recorded_at"],
        published_on=row["published_on"],
    )
