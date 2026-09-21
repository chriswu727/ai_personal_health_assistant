"""Curated public knowledge, and a deterministic way to retrieve it.

Two things separate this from personal memory. It is public: no user owns a
source or a passage, and nothing here is scoped to an owner. And it is
untrusted: a passage is text somebody else wrote, so it is data that may be
quoted and cited, never an instruction and never a reason to act.

Ranking is a pure function of the corpus and the query. That is the point: the
same question against the same corpus returns the same passages in the same
order on any machine, so a citation can be reproduced rather than taken on
trust. The scoring itself is a deliberately plain baseline, described in
[ADR 0007](../../../docs/decisions/0007-deterministic-retrieval.md).
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from health_assistant.domain.errors import ValidationError
from health_assistant.domain.identifiers import PassageId, SourceId, require_identifier
from health_assistant.domain.scheduling import require_utc

_WORD = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> tuple[str, ...]:
    """Split text into the normalized words retrieval matches on."""
    return tuple(_WORD.findall(text.casefold()))


def distinct_terms(text: str) -> frozenset[str]:
    return frozenset(tokenize(text))


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    """A document the project is permitted to quote, with the provenance to say so."""

    source_id: SourceId
    title: str
    publisher: str
    locator: str
    license: str
    recorded_at: datetime
    published_on: date | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", require_identifier(self.source_id, "source_id"))
        for field in ("title", "publisher", "locator", "license"):
            value = getattr(self, field).strip()
            if not value:
                # A source without a stated permission is not one we may quote,
                # so the absence is rejected here rather than discovered later.
                raise ValidationError(f"evidence source {field} must not be blank")
            object.__setattr__(self, field, value)
        object.__setattr__(self, "recorded_at", require_utc(self.recorded_at, "recorded_at"))


@dataclass(frozen=True, slots=True)
class EvidencePassage:
    """One quotable span of a source, with where inside it the span sits."""

    passage_id: PassageId
    source_id: SourceId
    locator: str
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "passage_id", require_identifier(self.passage_id, "passage_id"))
        object.__setattr__(self, "source_id", require_identifier(self.source_id, "source_id"))
        object.__setattr__(self, "locator", require_identifier(self.locator, "locator"))
        text = self.text.strip()
        if not text:
            raise ValidationError("evidence passage text must not be blank")
        object.__setattr__(self, "text", text)

    @property
    def terms(self) -> frozenset[str]:
        return distinct_terms(self.text)


@dataclass(frozen=True, slots=True)
class RetrievedPassage:
    """A passage as it was returned for one query at one instant.

    This is the provenance record: what matched, how well, in what position, and
    when. It is what a citation later points at.
    """

    passage: EvidencePassage
    query: str
    matched_terms: frozenset[str]
    rank: int
    retrieved_at: datetime

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValidationError("rank starts at 1")
        if not self.matched_terms:
            raise ValidationError("a retrieved passage must have matched something")
        object.__setattr__(self, "retrieved_at", require_utc(self.retrieved_at, "retrieved_at"))


def _score(passage: EvidencePassage, terms: frozenset[str]) -> tuple[int, int]:
    """Return (distinct query terms present, total occurrences of them)."""
    tokens = tokenize(passage.text)
    matched = terms & frozenset(tokens)
    occurrences = sum(1 for token in tokens if token in matched)
    return (len(matched), occurrences)


def rank_passages(
    passages: Iterable[EvidencePassage],
    query: str,
    *,
    at: datetime,
    limit: int = 10,
) -> tuple[RetrievedPassage, ...]:
    """Return the passages a query matches, best first, the same way every time.

    Ordering is by distinct query terms present, then by how often they occur,
    then by passage identifier. The last key is what makes the result total:
    without it two equally good passages could come back in either order and a
    citation would not be reproducible.
    """
    if limit < 1:
        raise ValidationError("limit must be at least 1")
    terms = distinct_terms(query)
    if not terms:
        return ()

    scored: list[tuple[tuple[int, int], EvidencePassage]] = []
    for passage in passages:
        score = _score(passage, terms)
        if score[0]:
            scored.append((score, passage))
    scored.sort(key=lambda entry: (-entry[0][0], -entry[0][1], entry[1].passage_id))

    instant = require_utc(at, "at")
    return tuple(
        RetrievedPassage(
            passage=passage,
            query=query,
            matched_terms=terms & passage.terms,
            rank=position,
            retrieved_at=instant,
        )
        for position, (_, passage) in enumerate(scored[:limit], start=1)
    )


def corpus_terms(passages: Sequence[EvidencePassage]) -> frozenset[str]:
    """Every term the corpus can match, for tests and for index checks."""
    return frozenset().union(*(passage.terms for passage in passages)) if passages else frozenset()
