# Development Handoff

This file provides session context; [SPRINTS.md](SPRINTS.md) remains the source of truth for delivery status. Update this file when a work session changes repository behavior, governance, or verification state. Keep context concise and never include credentials or personal health data.

## Current state

- Canonical repository: `chriswu727/ai_personal_health_assistant`.
- Sprint 0 foundation: Done. Sprint 1 domain slice: Done, merged as `e00c949`.
- Sprint 2: In Progress on `sprint-2/persistence-foundation`. Tasks S2-01 and
  S2-02 are underway; S2-03 through S2-08 are Planned.
- Runtime and checks: Python 3.12 pinned, dependencies locked with `uv`, and
  format, lint, strict type, test, and build gates running locally through
  `./scripts/verify.sh` and in GitHub Actions on `ubuntu-latest`.

## Latest change

Closed Sprint 1 on the board with a review and retrospective, refined Sprint 2
into tasks S2-01 through S2-08, and implemented part one: the PostgreSQL schema,
the initial Alembic migration, a plan repository, a minimal user repository, and
the transactional boundary. Ownership is a query predicate on every read, and a
plan version's primary key makes a lost update a rejected write rather than a
silent overwrite. See [ADR 0004](decisions/0004-persistence-stack.md).

In [pull request #2](https://github.com/chriswu727/ai_personal_health_assistant/pull/2), awaiting review.

## Verification

Local run on macOS 15.7.4 arm64 with Python 3.12.13:

- `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`: passed,
  53 files, 33 source files, strict mode.
- `uv run pytest`: 98 passed, 8 skipped. The skips are the database tests.
- `uv build`: passed.

CI additionally ran the 8 database tests against a `postgres:17` service
container: all passed. [CI run](https://github.com/chriswu727/ai_personal_health_assistant/actions/runs/35537147290).

**No database test has ever run on this machine.** There is no PostgreSQL and no
container runtime here, so local results say nothing about persistence. Read the
`integration` job for that. Its first execution failed and found a real defect:
a version conflict was detected from an insert's reported row count, which is
not a guaranteed signal.

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
belongs to Sprint 3. There is no runnable app, live calendar integration,
evaluation result, or production-readiness claim. Do not mark Sprint 1 tasks
complete until the change is on main and their individual acceptance criteria
pass.
