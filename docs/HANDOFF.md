# Development Handoff

This file provides session context; [SPRINTS.md](SPRINTS.md) remains the source of truth for delivery status. Update this file when a work session changes repository behavior, governance, or verification state. Keep context concise and never include credentials or personal health data.

## Current state

- Canonical repository: `chriswu727/ai_personal_health_assistant`.
- Sprint 0 foundation: Done. Sprint 1 domain slice: Done, merged as `e00c949`.
- Sprint 2: In Progress. S2-01 through S2-03 are Done, merged as `5deeaa2`.
  S2-04 and S2-05 are underway on `sprint-2/durable-operations`; S2-06 through
  S2-08 are Planned.
- Storage: PostgreSQL through asynchronous SQLAlchemy and psycopg, with Alembic
  migrations. Users, plans, plan versions, plan items, constraints, approvals,
  approved actions, and operations are persisted.
- Runtime and checks: Python 3.12 pinned, dependencies locked with `uv`, and
  format, lint, strict type, test, and build gates running locally through
  `./scripts/verify.sh` and in GitHub Actions on `ubuntu-latest`.

## Latest change

Added constraint, approval, and operation storage, and the worker's claiming use
cases. Claiming uses `SELECT ... FOR UPDATE SKIP LOCKED`, so a second worker
passes over a held row rather than waiting behind it; whether a claimed row may
execute stays the domain's decision. An operation whose confirmation expired or
was revoked while it waited is cancelled with the reason recorded rather than
left in the queue, and an expired lease is released to an unknown outcome rather
than to a failure. See [ADR 0005](decisions/0005-worker-claiming.md).

Migration 0002 adds the four new tables. It is a new migration rather than an
amendment to 0001, which is now on main.

## Verification

Local run on macOS 15.7.4 arm64 with Python 3.12.13, against PostgreSQL 17 in a
container:

- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`, and
  `uv run mypy --platform win32`: passed, 65 files, 44 source files, strict mode.
- `uv run pytest` with `HEALTH_ASSISTANT_TEST_DATABASE_URL` set: 139 passed.
- `uv run pytest` without it: 101 passed, 38 skipped, which are the database tests.
- `uv build`: passed.

Covered: claiming under contention through two simultaneous transactions, lease
expiry through the worker use case, authorization against current records, and
refusal of writes built on stale reads.

Not covered: restart recovery across a real process exit, which the lease tests
simulate by advancing the clock rather than by killing a worker; concurrency
beyond the claim and stale-write paths; any live provider call; and the
adversarial path probes. Those are S2-06 and S2-07.

## Next action

Continue Sprint 2 with S2-06 and S2-07: transaction-boundary and restart
recovery tests, including work in flight when a worker dies, and then the
adversarial path probes carried from the Sprint 1 retrospective. S2-08 closes the
sprint with the review and the Sprint 3 breakdown.

## Blockers and limitations

No blocker is known. Constraint matching is exact on declared attributes and
does not infer that one ingredient implies another; an ingredient taxonomy
belongs to Sprint 3. Overlapping-transaction behavior, worker leases, and
restart recovery are not yet covered; they are S2-05 and S2-06. There is no
runnable app, live calendar integration, evaluation result, or
production-readiness claim. Do not mark a Sprint 2 task complete until the
change is on main and its individual acceptance criteria pass.
