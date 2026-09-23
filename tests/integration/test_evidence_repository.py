"""The corpus is public knowledge; the record of consulting it belongs to a user."""

from datetime import date

import pytest
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from health_assistant.adapters.persistence import unit_of_work
from health_assistant.application.evidence import search_evidence
from health_assistant.domain.evidence import Candidates, distinct_terms
from health_assistant.domain.identifiers import RetrievalId, SourceId
from tests.integration.support import register_users
from tests.support import OTHER_USER, OWNER, at, make_passage, make_source

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
QUERY = "walking and sleep"


async def _seed(engine: AsyncEngine) -> None:
    await register_users(engine, OWNER, OTHER_USER)
    async with unit_of_work(engine) as work:
        await work.evidence.add_source(make_source(published_on=date(2025, 3, 1)))
        for passage in (BOTH, SLEEP, WALKING):
            await work.evidence.add_passage(passage)


async def _search(engine: AsyncEngine, retrieval_id: str, *, hours: float = 0) -> None:
    async with unit_of_work(engine) as work:
        await search_evidence(
            work,
            QUERY,
            owner_id=OWNER,
            retrieval_id=RetrievalId(retrieval_id),
            at=at(hours=hours),
        )


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
            work, QUERY, owner_id=OWNER, retrieval_id=RetrievalId("r-1"), at=at()
        )
    async with unit_of_work(engine) as work:
        second = await search_evidence(
            work, QUERY, owner_id=OWNER, retrieval_id=RetrievalId("r-2"), at=at()
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


async def test_the_corpus_has_no_owner_but_the_history_does(engine: AsyncEngine) -> None:
    """Public knowledge is structurally distinct from anything a user owns."""
    async with engine.connect() as connection:
        sources = await connection.run_sync(_columns, "evidence_sources")
        passages = await connection.run_sync(_columns, "evidence_passages")
        history = await connection.run_sync(_columns, "evidence_retrievals")

    assert "owner_id" not in sources
    assert "owner_id" not in passages
    assert "owner_id" in history, "what a user asked is theirs, even if the corpus is not"


async def test_a_cutoff_is_reported_rather_than_silent(engine: AsyncEngine) -> None:
    """Narrowing orders by identifier, so a bound can drop the best passage."""
    await register_users(engine, OWNER)
    async with unit_of_work(engine) as work:
        await work.evidence.add_source(make_source())
        for index in range(200):
            await work.evidence.add_passage(make_passage(f"a-{index:03d}", "Walking is pleasant."))
        await work.evidence.add_passage(
            make_passage("z-best", "Walking, sleep and nutrition together support energy.")
        )

    async with unit_of_work(engine) as work:
        retrieval = await search_evidence(
            work,
            "walking sleep nutrition",
            owner_id=OWNER,
            retrieval_id=RetrievalId("r-cut"),
            at=at(),
        )

    assert retrieval.truncated
    assert not retrieval.is_complete
    assert retrieval.candidates_considered == 200

    async with unit_of_work(engine) as work:
        stored = await work.evidence.retrieval(owner_id=OWNER, retrieval_id=RetrievalId("r-cut"))
    assert stored is not None
    assert stored.truncated, "the record must say the search saw a partial corpus"


async def test_a_retrieval_is_recorded_and_can_be_read_back(engine: AsyncEngine) -> None:
    await _seed(engine)

    async with unit_of_work(engine) as work:
        performed = await search_evidence(
            work, QUERY, owner_id=OWNER, retrieval_id=RetrievalId("r-1"), at=at(hours=2)
        )
    async with unit_of_work(engine) as work:
        stored = await work.evidence.retrieval(owner_id=OWNER, retrieval_id=RetrievalId("r-1"))

    assert stored is not None
    assert stored.retrieved_at == at(hours=2)
    assert stored.owner_id == OWNER
    # "and" counts as a match. The scorer weighs words, including common ones,
    # which ADR 0007 records as a known weakness of the baseline rather than
    # something this test should pretend away.
    assert stored.results[0].matched_terms == {"walking", "sleep", "and"}
    assert [item.passage for item in stored.results] == [item.passage for item in performed.results]
    # The snapshot's recording instant is the retrieval instant, by design.
    assert [item.source.title for item in stored.results] == [
        item.source.title for item in performed.results
    ]


async def test_another_user_cannot_read_a_retrieval(engine: AsyncEngine) -> None:
    """A query can say something about the person who asked it."""
    await _seed(engine)
    await _search(engine, "r-1")

    async with unit_of_work(engine) as work:
        theirs = await work.evidence.retrieval(owner_id=OTHER_USER, retrieval_id=RetrievalId("r-1"))
        mine = await work.evidence.retrieval(owner_id=OWNER, retrieval_id=RetrievalId("r-1"))

    assert theirs is None
    assert mine is not None


async def test_deleting_the_user_removes_their_history_and_keeps_the_corpus(
    engine: AsyncEngine,
) -> None:
    await _seed(engine)
    await _search(engine, "r-1")

    async with unit_of_work(engine) as work:
        await work.connection.execute(
            text("DELETE FROM users WHERE user_id = :owner"), {"owner": OWNER}
        )

    async with unit_of_work(engine) as work:
        remaining = await work.connection.execute(
            text("SELECT count(*) FROM evidence_retrieval_results")
        )
        corpus = await work.evidence.candidates(distinct_terms("walking"))

    assert remaining.scalar_one() == 0
    assert len(corpus.passages) == 2


async def test_a_retrieval_record_keeps_its_provenance_after_the_source_changes(
    engine: AsyncEngine,
) -> None:
    """Curating the corpus must not quietly rewrite the basis of a past claim."""
    await _seed(engine)
    await _search(engine, "r-1")

    async with unit_of_work(engine) as work:
        await work.evidence.add_source(
            make_source(
                title="A different title entirely",
                publisher="Some Other Publisher",
                locator="https://example.invalid/moved",
                license_note="terms changed later",
                published_on=date(2026, 1, 1),
            )
        )

    async with unit_of_work(engine) as work:
        stored = await work.evidence.retrieval(owner_id=OWNER, retrieval_id=RetrievalId("r-1"))

    assert stored is not None
    cited = stored.results[0].source
    assert cited.title == "Everyday activity and sleep, synthetic edition"
    assert cited.publisher == "Synthetic Health Press"
    assert cited.locator == "https://example.invalid/synthetic/activity"
    assert cited.license == "synthetic fixture, redistributable"
    assert cited.published_on == date(2025, 3, 1)


async def test_a_retrieval_record_outlives_the_source_it_quoted(
    engine: AsyncEngine,
) -> None:
    await _seed(engine)
    await _search(engine, "r-1")

    async with unit_of_work(engine) as work:
        await work.connection.execute(
            text("DELETE FROM evidence_sources WHERE source_id = 'source-1'")
        )

    async with unit_of_work(engine) as work:
        assert await work.evidence.candidates(distinct_terms("walking")) == Candidates(
            passages=(), truncated=False
        )
        stored = await work.evidence.retrieval(owner_id=OWNER, retrieval_id=RetrievalId("r-1"))

    assert stored is not None
    assert stored.results[0].passage.text.startswith("Walking outdoors")
    assert stored.results[0].source.publisher == "Synthetic Health Press"
