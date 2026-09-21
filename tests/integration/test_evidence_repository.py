"""The corpus is public knowledge, stored with enough provenance to cite it."""

from datetime import date

import pytest
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from health_assistant.adapters.persistence import unit_of_work
from health_assistant.application.evidence import search_evidence
from health_assistant.domain.evidence import distinct_terms
from health_assistant.domain.identifiers import SourceId
from tests.support import at, make_passage, make_source

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WALKING = make_passage(
    "p-walking", "Walking briskly most days supports cardiovascular health for adults."
)
SLEEP = make_passage(
    "p-sleep", "Adults who keep a consistent sleep schedule report better daytime energy."
)
BOTH = make_passage(
    "p-both", "Walking outdoors in daylight supports both sleep timing and daytime energy."
)


async def _seed(engine: AsyncEngine) -> None:
    async with unit_of_work(engine) as work:
        await work.evidence.add_source(make_source(published_on=date(2025, 3, 1)))
        for passage in (BOTH, SLEEP, WALKING):
            await work.evidence.add_passage(passage)


def _columns(connection: Connection, table: str) -> set[str]:
    return {column["name"] for column in inspect(connection).get_columns(table)}


async def test_a_source_round_trips_with_its_provenance(engine: AsyncEngine) -> None:
    original = make_source(published_on=date(2025, 3, 1))

    async with unit_of_work(engine) as work:
        await work.evidence.add_source(original)
    async with unit_of_work(engine) as work:
        stored = await work.evidence.source(SourceId("source-1"))

    assert stored == original
    assert stored is not None
    assert stored.license == "synthetic fixture, redistributable"


async def test_a_source_may_have_no_publication_date(engine: AsyncEngine) -> None:
    async with unit_of_work(engine) as work:
        await work.evidence.add_source(make_source())
    async with unit_of_work(engine) as work:
        stored = await work.evidence.source(SourceId("source-1"))

    assert stored is not None
    assert stored.published_on is None


async def test_candidates_narrow_to_passages_sharing_a_term(engine: AsyncEngine) -> None:
    await _seed(engine)

    async with unit_of_work(engine) as work:
        matching = await work.evidence.candidates(distinct_terms("sleep"))
        unrelated = await work.evidence.candidates(distinct_terms("kayaking"))

    assert {passage.passage_id for passage in matching} == {"p-sleep", "p-both"}
    assert unrelated == ()


async def test_searching_twice_returns_the_same_order(engine: AsyncEngine) -> None:
    await _seed(engine)

    async with unit_of_work(engine) as work:
        first = await search_evidence(work, "walking and sleep", at=at())
    async with unit_of_work(engine) as work:
        second = await search_evidence(work, "walking and sleep", at=at())

    assert [item.passage.passage_id for item in first] == ["p-both", "p-sleep", "p-walking"]
    assert [item.passage.passage_id for item in second] == [
        item.passage.passage_id for item in first
    ]


async def test_a_replaced_passage_updates_the_terms_it_matches_on(
    engine: AsyncEngine,
) -> None:
    """A stale term index would keep answering for text that is no longer there."""
    await _seed(engine)
    async with unit_of_work(engine) as work:
        await work.evidence.add_passage(
            make_passage("p-sleep", "Swimming laps is a low-impact option for many adults.")
        )

    async with unit_of_work(engine) as work:
        by_old_term = await work.evidence.candidates(distinct_terms("schedule"))
        by_new_term = await work.evidence.candidates(distinct_terms("swimming"))

    assert [passage.passage_id for passage in by_old_term] == []
    assert [passage.passage_id for passage in by_new_term] == ["p-sleep"]


async def test_removing_a_source_removes_its_passages(engine: AsyncEngine) -> None:
    await _seed(engine)

    async with unit_of_work(engine) as work:
        await work.connection.execute(
            text("DELETE FROM evidence_sources WHERE source_id = 'source-1'")
        )

    async with unit_of_work(engine) as work:
        assert await work.evidence.candidates(distinct_terms("walking")) == ()


async def test_the_corpus_has_no_owner(engine: AsyncEngine) -> None:
    """Public knowledge is structurally distinct from anything a user owns."""
    async with engine.connect() as connection:
        sources = await connection.run_sync(_columns, "evidence_sources")
        passages = await connection.run_sync(_columns, "evidence_passages")
        plans = await connection.run_sync(_columns, "plans")

    assert "owner_id" not in sources
    assert "owner_id" not in passages
    assert "owner_id" in plans, "the owned tables still carry one"
