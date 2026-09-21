"""Storage for the curated corpus.

No method here takes an owner. These rows are published documents, the same for
every user, and scoping them to one would be meaningless. The owned tables and
this one are deliberately different shapes so the distinction is visible in the
code rather than only in a document.
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from health_assistant.adapters.persistence.schema import (
    evidence_passages,
    evidence_sources,
)
from health_assistant.domain.evidence import EvidencePassage, EvidenceSource
from health_assistant.domain.identifiers import PassageId, SourceId

DEFAULT_CANDIDATE_LIMIT = 200


class SqlEvidenceRepository:
    """Corpus persistence scoped to one transaction."""

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
    ) -> tuple[EvidencePassage, ...]:
        """Return passages sharing at least one term with the query.

        This narrows; it does not rank. Ranking is a pure function in the domain
        so that the order a citation depends on can be tested without a database
        and reproduced anywhere.
        """
        if not terms:
            return ()
        result = await self._connection.execute(
            select(evidence_passages)
            .where(evidence_passages.c.terms.overlap(sorted(terms)))
            .order_by(evidence_passages.c.passage_id)
            .limit(limit)
        )
        return tuple(
            EvidencePassage(
                passage_id=PassageId(row["passage_id"]),
                source_id=SourceId(row["source_id"]),
                locator=row["locator"],
                text=row["text"],
            )
            for row in result.mappings()
        )

    async def source(self, source_id: SourceId) -> EvidenceSource | None:
        result = await self._connection.execute(
            select(evidence_sources).where(evidence_sources.c.source_id == source_id)
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return EvidenceSource(
            source_id=SourceId(row["source_id"]),
            title=row["title"],
            publisher=row["publisher"],
            locator=row["locator"],
            license=row["license"],
            recorded_at=row["recorded_at"],
            published_on=row["published_on"],
        )
