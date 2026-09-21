"""The corpus is public knowledge, stored with enough provenance to cite it."""

from datetime import date

import pytest
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from health_assistant.adapters.persistence import unit_of_work
from health_assistant.application.evidence import search_evidence
from health_assistant.domain.evidence import Candidates, distinct_terms
from health_assistant.domain.identifiers import RetrievalId, SourceId
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

    assert {passage.passage_id for passage in matching.passages} == {"p-sleep", "p-both"}
    assert not matching.truncated
    assert unrelated.passages == ()


async def test_searching_twice_returns_the_same_order(engine: AsyncEngine) -> None:
    await _seed(engine)

    async with unit_of_work(engine) as work:
        first = await search_evidence(
            work, "walking and sleep", retrieval_id=RetrievalId("r-1"), at=at()
        )
    async with unit_of_work(engine) as work:
        second = await search_evidence(
            work, "walking and sleep", retrieval_id=RetrievalId("r-2"), at=at()
        )

    assert [item.passage.passage_id for item in first.results] == [
        "p-both",
        "p-sleep",
        "p-walking",
    ]
    assert [item.passage.passage_id for item in second.results] == [
        item.passage.passage_id for item in first.results
    ]
    assert first.is_complete


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

    assert [passage.passage_id for passage in by_old_term.passages] == []
    assert [passage.passage_id for passage in by_new_term.passages] == ["p-sleep"]


async def test_removing_a_source_removes_its_passages(engine: AsyncEngine) -> None:
    await _seed(engine)

    async with unit_of_work(engine) as work:
        await work.connection.execute(
            text("DELETE FROM evidence_sources WHERE source_id = 'source-1'")
        )

    async with unit_of_work(engine) as work:
        assert await work.evidence.candidates(distinct_terms("walking")) == Candidates(
            passages=(), truncated=False
        )


async def test_the_corpus_has_no_owner(engine: AsyncEngine) -> None:
    """Public knowledge is structurally distinct from anything a user owns."""
    async with engine.connect() as connection:
        sources = await connection.run_sync(_columns, "evidence_sources")
        passages = await connection.run_sync(_columns, "evidence_passages")
        plans = await connection.run_sync(_columns, "plans")

    assert "owner_id" not in sources
    assert "owner_id" not in passages
    assert "owner_id" in plans, "the owned tables still carry one"


async def test_a_cutoff_is_reported_rather_than_silent(engine: AsyncEngine) -> None:
    """Narrowing orders by identifier, so a bound can drop the best passage."""
    async with unit_of_work(engine) as work:
        await work.evidence.add_source(make_source())
        for index in range(200):
            await work.evidence.add_passage(make_passage(f"a-{index:03d}", "Walking is pleasant."))
        await work.evidence.add_passage(
            make_passage("z-best", "Walking, sleep and nutrition together support energy.")
        )

    async with unit_of_work(engine) as work:
        retrieval = await search_evidence(
            work, "walking sleep nutrition", retrieval_id=RetrievalId("r-cut"), at=at()
        )

    assert retrieval.truncated
    assert not retrieval.is_complete
    assert retrieval.candidates_considered == 200

    async with unit_of_work(engine) as work:
        stored = await work.evidence.retrieval(RetrievalId("r-cut"))
    assert stored is not None
    assert stored.truncated, "the record must say the search saw a partial corpus"


async def test_a_retrieval_is_recorded_and_can_be_read_back(engine: AsyncEngine) -> None:
    await _seed(engine)

    async with unit_of_work(engine) as work:
        performed = await search_evidence(
            work, "walking and sleep", retrieval_id=RetrievalId("r-1"), at=at(hours=2)
        )
    async with unit_of_work(engine) as work:
        stored = await work.evidence.retrieval(RetrievalId("r-1"))

    assert stored == performed
    assert stored is not None
    assert stored.retrieved_at == at(hours=2)
    # "and" counts as a match. The scorer weighs words, including common ones,
    # which ADR 0007 records as a known weakness of the baseline rather than
    # something this test should pretend away.
    assert stored.results[0].matched_terms == {"walking", "sleep", "and"}


async def test_a_retrieval_record_outlives_the_passage_it_quoted(
    engine: AsyncEngine,
) -> None:
    """Otherwise curating the corpus would quietly erase the basis of past claims."""
    await _seed(engine)
    async with unit_of_work(engine) as work:
        await search_evidence(work, "walking and sleep", retrieval_id=RetrievalId("r-1"), at=at())

    async with unit_of_work(engine) as work:
        await work.connection.execute(
            text("DELETE FROM evidence_sources WHERE source_id = 'source-1'")
        )

    async with unit_of_work(engine) as work:
        assert await work.evidence.candidates(distinct_terms("walking")) == Candidates(
            passages=(), truncated=False
        )
        stored = await work.evidence.retrieval(RetrievalId("r-1"))

    assert stored is not None
    assert stored.results[0].passage.text.startswith("Walking outdoors")
