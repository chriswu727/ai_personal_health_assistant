# Development Handoff

This file provides session context; [SPRINTS.md](SPRINTS.md) remains the source of truth for delivery status. Update this file when a work session changes repository behavior, governance, or verification state. Keep context concise and never include credentials or personal health data.

## Current state

- Canonical repository: `chriswu727/ai_personal_health_assistant`.
- Sprint 0 foundation: Done. Sprint 1 domain slice: Done, merged as `e00c949`.
- Sprint 2: Done, closed by `83d4ce6`.
- Sprint 3, evidence and memory: In Progress. S3-01, the evidence corpus and
  retrieval, is complete on `sprint-3/evidence-corpus` and awaiting review, so it
  stays In Progress until that change is on main. S3-02 through S3-09 are
  Planned.
- Milestone M2 is **partly met**. Sprint 2 delivered its persistence, isolation,
  durable jobs, and recovery; the API and identity integration it also names
  arrive in Sprint 4. The roadmap records this rather than redefining M2.
- Storage: PostgreSQL through asynchronous SQLAlchemy and psycopg, with Alembic
  migrations. Users, plans, plan versions, plan items, constraints, approvals,
  approved actions, and operations are persisted.
- Runtime and checks: Python 3.12 pinned, dependencies locked with `uv`, and
  format, lint, strict type, test, and build gates running locally through
  `./scripts/verify.sh` and in GitHub Actions on `ubuntu-latest`.

## Latest change

Added the curated evidence corpus and a deterministic retriever. Passages store
their normalized terms so the database can narrow by overlap; ranking is a pure
function in the domain with a total order, so the same query against the same
corpus returns the same passages in the same order and a citation can be
reproduced. The corpus carries no owner, because a published document is the
same for every user. Migration 0004 adds the two tables. See
[ADR 0007](decisions/0007-deterministic-retrieval.md).

## Verification

Local run on macOS 15.7.4 arm64 with Python 3.12.13, against PostgreSQL 17 in a
container:

- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`, and
  `uv run mypy --platform win32`: passed, 82 files, 56 source files, strict mode.
- `uv run pytest` with `HEALTH_ASSISTANT_TEST_DATABASE_URL` set: 174 passed.
- `uv run pytest` without it: 115 passed, 59 skipped, which are the database tests.
- `uv build`: passed.

Not established: retrieval quality. The ranker matches words, so it will not
find a passage about peanuts from a question about satay. That is recorded in
ADR 0007 and in the README rather than left for a reader to assume otherwise.

## Next action

Once S3-01 is on main, mark it Done and start S3-02: checking that a retrieved
passage actually supports the claim attached to it, that a resolvable locator
alone never counts as support, and that missing or conflicting evidence is
reported rather than smoothed over. S3-02 is what keeps the deliberately plain
ranker from turning into an unsupported claim, so it should not be deferred.

## Blockers and limitations

No blocker is known.

What the tests do not establish, stated so the next session does not assume
otherwise:

- Nothing here measures throughput or behavior under contention. The concurrency
  tests establish the correctness of ordering, not capacity. That is Sprint 7.
- The crash tests kill a worker process, not the database, and do not cover a
  connection lost mid-commit, where the client cannot tell whether the
  transaction landed. That is the same shape of problem as an ambiguous provider
  response and deserves its own treatment.
- Constraint matching is exact on declared attributes and does not infer that
  one ingredient implies another; an ingredient taxonomy belongs to Sprint 3.
- The evidence corpus is empty on a fresh install. Storage and retrieval exist;
  curating real permitted sources is S3-10, which is Blocked on the maintainer
  naming them. Nothing has been checked for whether a passage supports a claim.
- Retrieval ranks by word overlap only. It weighs a common word as heavily as
  the subject of a question and cannot connect related words.
- There is no runnable app, model provider, live calendar integration,
  evaluation result, or production-readiness claim. The provider is simulated
  throughout.

Do not mark a Sprint 2 task complete until the change is on main and its
individual acceptance criteria pass.
