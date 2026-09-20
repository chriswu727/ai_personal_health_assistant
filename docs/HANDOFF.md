# Development Handoff

This file provides session context; [SPRINTS.md](SPRINTS.md) remains the source of truth for delivery status. Update this file when a work session changes repository behavior, governance, or verification state. Keep context concise and never include credentials or personal health data.

## Current state

- Canonical repository: `chriswu727/ai_personal_health_assistant`.
- Sprint 0 foundation: Done. Sprint 1 domain slice: Done, merged as `e00c949`.
- Sprint 2: In Progress on `sprint-2/persistence-foundation`. Tasks S2-01, S2-02
  and S2-03 are underway in [pull request #2](https://github.com/chriswu727/ai_personal_health_assistant/pull/2);
  S2-04 through S2-08 are Planned.
- Storage: PostgreSQL through asynchronous SQLAlchemy and psycopg, with Alembic
  migrations. Users, plans, plan versions, and plan items are persisted;
  constraints, approvals, and operations are not yet.
- Runtime and checks: Python 3.12 pinned, dependencies locked with `uv`, and
  format, lint, strict type, test, and build gates running locally through
  `./scripts/verify.sh` and in GitHub Actions on `ubuntu-latest`.

## Latest change

Closed Sprint 1 on the board with a review and retrospective, refined Sprint 2
into tasks S2-01 through S2-08, and implemented part one: the PostgreSQL schema,
the initial Alembic migration, a plan repository, a minimal user repository, and
the transactional boundary, all asynchronous. Ownership is a query predicate on
every read, and a
plan version's primary key makes a lost update a rejected write rather than a
silent overwrite. See [ADR 0004](decisions/0004-persistence-stack.md).

In [pull request #2](https://github.com/chriswu727/ai_personal_health_assistant/pull/2), awaiting review.

## Verification

Local run on macOS 15.7.4 arm64 with Python 3.12.13, against PostgreSQL 17 in a
container:

- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`, and
  `uv run mypy --platform win32`: passed, 55 files, 35 source files, strict mode.
- `uv run pytest` with `HEALTH_ASSISTANT_TEST_DATABASE_URL` set: 112 passed.
- `uv run pytest` without it: 101 passed, 11 skipped, which are the database tests.
- `uv build`: passed.

CI runs the same checks, with the database tests against a `postgres:17` service
container. [Pull request #2](https://github.com/chriswu727/ai_personal_health_assistant/pull/2).

Not run: any live provider call, overlapping-transaction tests, worker leases,
and restart recovery.

## Next action

After part one is reviewed and on main, continue Sprint 2 with S2-04 through
S2-07: persist constraints, approvals and their approved actions including the
compensation target; persist the operation lifecycle and claim work with a
lease so two workers cannot hold one operation and an expired lease returns work
for reconciliation; then the adversarial path probes carried from the Sprint 1
retrospective.

## Blockers and limitations

No blocker is known. Constraint matching is exact on declared attributes and
does not infer that one ingredient implies another; an ingredient taxonomy
belongs to Sprint 3. Overlapping-transaction behavior, worker leases, and
restart recovery are not yet covered; they are S2-05 and S2-06. There is no
runnable app, live calendar integration, evaluation result, or
production-readiness claim. Do not mark a Sprint 2 task complete until the
change is on main and its individual acceptance criteria pass.
