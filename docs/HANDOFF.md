# Development Handoff

This file provides session context; [SPRINTS.md](SPRINTS.md) remains the source of truth for delivery status. Update this file when a work session changes repository behavior, governance, or verification state. Keep context concise and never include credentials or personal health data.

## Current state

- Canonical repository: `chriswu727/ai_personal_health_assistant`.
- Sprint 0 foundation: Done. Sprint 1 domain slice: Done, merged as `e00c949`.
- Sprint 2: In Progress. S2-01 through S2-03 are Done, merged as `5deeaa2`;
  S2-04 and S2-05 are Done, merged as `ecafaf3`. S2-06 and S2-07 are complete on
  `sprint-2/restart-recovery`, in [pull request #4](https://github.com/chriswu727/ai_personal_health_assistant/pull/4)
  and awaiting review, so they stay In Progress until that change is on main.
  S2-08, the sprint review and the Sprint 3 breakdown, is Planned.
- Storage: PostgreSQL through asynchronous SQLAlchemy and psycopg, with Alembic
  migrations. Users, plans, plan versions, plan items, constraints, approvals,
  approved actions, and operations are persisted.
- Runtime and checks: Python 3.12 pinned, dependencies locked with `uv`, and
  format, lint, strict type, test, and build gates running locally through
  `./scripts/verify.sh` and in GitHub Actions on `ubuntu-latest`.

## Latest change

Added restart recovery and adversarial path probes, closing out the
implementation work for Sprint 2. A worker subprocess is killed mid-flight, both
after committing a claim and inside the transaction, and the tests assert what
the database is left holding in each case. Migration 0003 adds owner-consistent
references and requires a recorded approval past confirmation; `advance` checks
the transition table as well. See
[ADR 0006](decisions/0006-invariants-below-the-domain.md).

## Verification

Local run on macOS 15.7.4 arm64 with Python 3.12.13, against PostgreSQL 17 in a
container:

- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`, and
  `uv run mypy --platform win32`: passed, 75 files, 51 source files, strict mode.
- `uv run pytest` with `HEALTH_ASSISTANT_TEST_DATABASE_URL` set: 152 passed.
- `uv run pytest` without it: 103 passed, 49 skipped, which are the database tests.
- `uv build`: passed.

Covered: claiming under contention, lease expiry, authorization against current
records, refusal of writes built on stale reads, a worker process killed both
before and after committing, transaction boundaries across related writes, and
eight probes that take unintended routes to protected states.

Not covered: any live provider call, and throughput or contention measurement
under load. Those belong to Sprint 5 and Sprint 7.

## Next action

Once part three is on main, mark S2-06 and S2-07 Done and close Sprint 2 with
S2-08: the sprint review, the limitations, and the Sprint 3 breakdown. Sprint 3
adds curated evidence retrieval with provenance, editable memory, a model
adapter, and bounded orchestration producing validated plans.

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
- There is no runnable app, model provider, evidence retrieval, live calendar
  integration, evaluation result, or production-readiness claim. The provider is
  simulated throughout.

Do not mark a Sprint 2 task complete until the change is on main and its
individual acceptance criteria pass.
