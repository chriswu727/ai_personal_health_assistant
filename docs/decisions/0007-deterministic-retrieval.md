# 0007. A deterministic baseline retriever

Status: Accepted (Sprint 3, task S3-01)

## Context

Retrieval has to satisfy three things at once. The same query against the same
corpus must return the same passages in the same order, or a citation cannot be
reproduced and is worth little. The default test suite must make no network
call. And every result must carry enough provenance to say where it came from
and why the project may quote it.

Retrieval quality is not one of the three. It matters, but it is not what this
task is for, and it cannot be improved honestly before Sprint 3's held-out
evaluations can measure it.

## Alternatives

- **Embedding search over a vector index.** Better recall, and the obvious
  modern choice. It needs a model to embed both corpus and query, which means a
  paid call or a local model in the default suite, and results that shift with
  the embedding model's version. Both conflict with the requirements above.
- **PostgreSQL full-text search with `ts_rank`.** Free, fast, and far better
  than term overlap. Ranking would then live in SQL, where it depends on the
  server's text search configuration and version, and could not be tested
  without a database. The ordering a citation depends on would become the one
  thing the offline suite cannot check.
- **A hand-written BM25 in the domain.** Deterministic and offline, with
  noticeably better ranking. It is also considerably more code, tuned by
  parameters nothing yet measures. Worth doing when there is a number to move.

## Decision

Narrow in the database, rank in the domain.

Each passage stores its normalized terms in an array with a GIN index, and a
query fetches the passages sharing at least one term. That is a filter, not a
ranking. The domain then orders them by distinct query terms present, then by
how often those terms occur, then by passage identifier.

The last key is the one that matters most here. Without it, two equally good
passages could come back in either order, and a citation recorded today would
not be reproducible tomorrow. Scoring ties are expected in a small corpus, so
the tiebreak is part of the contract rather than an implementation detail.

Every search is recorded: the query, the instant, the ranked results, and
whether the bound cut in. Results copy the passage **and its source's
provenance** rather than pointing at the corpus, with no foreign key back to it,
so the record still describes the retrieval after the corpus has been curated
again. A snapshot that kept the passage but lost the document it came from would
not be a citation either; title, publisher, locator, licence, and publication
date travel with each result.

The corpus is public, but the record of consulting it is not. A query can carry
personal health information, so each retrieval belongs to the user who made it,
is readable only with their identifier, and is removed with their account. This
is the one place in the evidence design where ownership applies, and it applies
for the same reason it applies everywhere else in the project: the data says
something about a person.

A citation that cannot be checked against what was actually retrieved is a
claim, not a citation.

The bound on candidates is reported rather than merely documented. Narrowing
orders by identifier, so a cutoff is perfectly capable of discarding the passage
that would have ranked first; one extra row is fetched to detect that, and the
result says so. A silent cutoff turns a weak answer into a wrong one.

The corpus tables carry no owner column and no repository method scopes them.
Published documents are identical for every user, and the absence is deliberate
and visible in the code, not only in a document.

## Consequences

Ranking is weak and should be described that way. It matches words, so a
passage about peanuts will not answer a question about satay, and a plural will
not match its singular. It also has no notion of which words carry meaning: a
common word like "and" scores exactly as much as the subject of the question, so
a wordy query ranks partly by noise. A test asserts that behavior rather than
pretending it away, and the README says so rather than leaving a reader to
assume otherwise.

That weakness is contained by what comes next rather than by hoping it is small.
Task S3-02 checks that a retrieved passage actually supports the claim it is
attached to, so poor retrieval produces a missing-evidence answer rather than an
unsupported one. Weak retrieval and a confident citation is the failure that
would matter; weak retrieval and an honest "not enough evidence" is a worse
answer, not a wrong one.

Replace the ranker when a held-out evaluation shows retrieval is the limiting
factor, and record what the number was. Not before.

The candidate fetch is bounded, which suits a curated corpus and would not suit
a large one. A corpus big enough for the bound to cut in is the trigger to move
ranking closer to the data. Until then the cutoff is reported on every result
and stored on every record, so a caller can tell a complete search from a
partial one instead of being given a confident-looking answer either way.

Recording every search writes a row on a read path. That is the intended trade:
the point of retention is that a past citation can be audited, and a retrieval
nobody recorded cannot be. High-volume automated querying would change the
arithmetic and is the trigger to revisit.
