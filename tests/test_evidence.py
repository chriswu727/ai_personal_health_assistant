"""Retrieval must return the same passages in the same order every time.

A citation that cannot be reproduced is not a citation, so ordering is a
property under test rather than an implementation detail.
"""

import random

import pytest

from health_assistant.domain.errors import ValidationError
from health_assistant.domain.evidence import (
    EvidencePassage,
    RetrievedPassage,
    distinct_terms,
    rank_passages,
    tokenize,
)
from health_assistant.domain.identifiers import PassageId, SourceId
from tests.support import at, make_passage, make_source

SOURCE = make_source()
SOURCES = {SOURCE.source_id: SOURCE}
WALKING = make_passage(
    "p-walking",
    "Walking briskly most days supports cardiovascular health for adults.",
)
SLEEP = make_passage(
    "p-sleep",
    "Adults who keep a consistent sleep schedule report better daytime energy.",
)
BOTH = make_passage(
    "p-both",
    "Walking outdoors in daylight supports both sleep timing and daytime energy.",
)
CORPUS = (WALKING, SLEEP, BOTH)


def test_tokenizing_normalizes_case_and_drops_punctuation() -> None:
    assert tokenize("Walking, briskly!") == ("walking", "briskly")
    assert distinct_terms("Sleep sleep SLEEP") == {"sleep"}


def test_a_source_must_state_where_it_came_from_and_why_it_may_be_used() -> None:
    with pytest.raises(ValidationError):
        make_source(title="   ")
    with pytest.raises(ValidationError):
        make_source(publisher="   ")
    with pytest.raises(ValidationError):
        make_source(locator="   ")
    with pytest.raises(ValidationError):
        make_source(license_note="   ")


def test_a_passage_must_carry_text_and_a_locator() -> None:
    with pytest.raises(ValidationError):
        EvidencePassage(
            passage_id=PassageId("p-1"),
            source_id=SourceId("source-1"),
            locator="section-1",
            text="   ",
        )


def test_matching_passages_come_back_best_first() -> None:
    results = rank_passages(CORPUS, "walking and sleep", sources=SOURCES, at=at())

    assert [item.passage.passage_id for item in results] == ["p-both", "p-sleep", "p-walking"]
    assert [item.rank for item in results] == [1, 2, 3]


def test_the_order_does_not_depend_on_the_order_passages_arrive_in() -> None:
    expected = [
        item.passage.passage_id
        for item in rank_passages(CORPUS, "walking sleep", sources=SOURCES, at=at())
    ]

    shuffled = list(CORPUS)
    # Seeded and not cryptographic: this shuffles test input to show the
    # result does not depend on arrival order.
    generator = random.Random(20260921)  # noqa: S311
    for _ in range(20):
        generator.shuffle(shuffled)
        actual = [
            item.passage.passage_id
            for item in rank_passages(shuffled, "walking sleep", sources=SOURCES, at=at())
        ]
        assert actual == expected


def test_passages_matching_equally_well_are_ordered_by_identifier() -> None:
    """Without a total order two good passages could swap places between runs."""
    first = make_passage("p-alpha", "Daily walking helps.")
    second = make_passage("p-beta", "Daily walking helps.")

    results = rank_passages([second, first], "walking", sources=SOURCES, at=at())

    assert [item.passage.passage_id for item in results] == ["p-alpha", "p-beta"]


def test_more_occurrences_of_the_same_term_rank_higher() -> None:
    sparse = make_passage("p-sparse", "Sleep matters.")
    dense = make_passage("p-dense", "Sleep, and more sleep, and sleep again.")

    results = rank_passages([sparse, dense], "sleep", sources=SOURCES, at=at())

    assert [item.passage.passage_id for item in results] == ["p-dense", "p-sparse"]


def test_a_passage_that_matches_nothing_is_not_returned() -> None:
    assert rank_passages(CORPUS, "kayaking", sources=SOURCES, at=at()) == ()


def test_an_empty_query_returns_nothing_rather_than_everything() -> None:
    assert rank_passages(CORPUS, "   ", sources=SOURCES, at=at()) == ()
    assert rank_passages(CORPUS, "!!!", sources=SOURCES, at=at()) == ()


def test_the_limit_is_respected_and_must_be_positive() -> None:
    assert (
        len(rank_passages(CORPUS, "walking sleep energy", sources=SOURCES, at=at(), limit=2)) == 2
    )
    with pytest.raises(ValidationError):
        rank_passages(CORPUS, "walking", sources=SOURCES, at=at(), limit=0)


def test_a_result_records_what_matched_and_when() -> None:
    instant = at(hours=3)
    results = rank_passages(CORPUS, "walking kayaking", sources=SOURCES, at=instant)

    assert results[0].matched_terms == {"walking"}
    assert results[0].query == "walking kayaking"
    assert results[0].retrieved_at == instant


def test_common_words_count_as_matches() -> None:
    """A known weakness of the baseline, asserted so it cannot drift unnoticed.

    Scoring weighs every word equally, so a query full of common ones ranks by
    noise. ADR 0007 records why the ranker stays plain until an evaluation gives
    a number to improve, and S3-02 is what stops a weak match from becoming a
    confident claim.
    """
    results = rank_passages(CORPUS, "walking and sleep", sources=SOURCES, at=at())

    assert results[0].matched_terms == {"walking", "and", "sleep"}


def test_a_result_carries_the_document_it_came_from() -> None:
    """A citation that names a passage but has lost its document is not a citation."""
    results = rank_passages(CORPUS, "walking", sources=SOURCES, at=at())

    assert results[0].source == SOURCE
    assert results[0].source.license == "synthetic fixture, redistributable"


def test_a_matching_passage_with_no_known_source_is_an_error_not_a_blank() -> None:
    orphan = make_passage("p-orphan", "Walking is fine.", source_id="source-missing")

    with pytest.raises(ValidationError):
        rank_passages([orphan], "walking", sources=SOURCES, at=at())


def test_a_retrieved_passage_must_carry_its_own_source() -> None:
    other = make_source("source-2")
    with pytest.raises(ValidationError):
        RetrievedPassage(
            passage=WALKING,
            source=other,
            query="walking",
            matched_terms=frozenset({"walking"}),
            rank=1,
            retrieved_at=at(),
        )
