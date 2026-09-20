# Development Handoff

This file provides session context; [SPRINTS.md](SPRINTS.md) remains the source of truth for delivery status. Update this file when a work session changes repository behavior, governance, or verification state. Keep context concise and never include credentials or personal health data.

## Current state

- Canonical repository: `chriswu727/ai_personal_health_assistant`.
- Sprint 0 foundation: Done.
- Sprint 1: In Progress. The domain slice is in [pull request #1](https://github.com/chriswu727/ai_personal_health_assistant/pull/1) and is
  awaiting review. No Sprint 1 task is Done until the change is on main.
- Runtime and checks: Python 3.12 pinned, dependencies locked with `uv`, and
  format, lint, strict type, test, and build gates configured. They run locally
  through `./scripts/verify.sh` and in GitHub Actions on `ubuntu-latest`.
- Current work: Sprint 1 tasks S1-01 through S1-07.

## Latest change

Implemented the first tested domain slice: typed immutable plan versions with
revision rules, first-class constraints with deterministic pre-approval
validation, approvals bound to an exact payload fingerprint, and an external
operation state machine in which an unknown outcome must be reconciled before
any retry. Added the packaging, lockfile, local verification script, CI
workflow, MIT license, and two decision records.

The domain package imports the standard library only. There is still no
application, API, database, user interface, model provider, or calendar
integration.

## Verification

Local run on macOS 15.7.4 arm64 with Python 3.12.13, Ruff 0.16.8, mypy 2.3.1,
and pytest 9.1.1:

- `uv run ruff format --check .`: passed, 32 files.
- `uv run ruff check .`: passed.
- `uv run mypy`: passed, 19 source files, strict mode.
- `uv run pytest`: passed, 79 tests, offline with synthetic fixtures.
- `uv build`: passed, source distribution and wheel.

The same checks passed on a standard GitHub-hosted `ubuntu-latest` runner:
[CI run](https://github.com/chriswu727/ai_personal_health_assistant/actions/runs/35530164477).

Not run: any live provider call, and any persistence, concurrency, or recovery
test against a real database. These results describe deterministic domain
contracts. They do not establish persistent recovery, live calendar reliability,
or clinical validity.

## Next action

After this change is reviewed and on main, mark Sprint 1 tasks Done with the
merged commit as evidence, close the sprint with a retrospective, then expand
Sprint 2 into task IDs and acceptance criteria before starting it. Sprint 2
adds identity, ownership enforcement at every access path, migrations, plan
persistence with version checks, durable operations, and worker leases, using a
simulated provider. Live calendar integration remains Sprint 5.

## Blockers and limitations

No blocker is known. Constraint matching is exact on declared attributes and
does not infer that one ingredient implies another; an ingredient taxonomy
belongs to Sprint 3. There is no runnable app, live calendar integration,
evaluation result, or production-readiness claim. Do not mark Sprint 1 tasks
complete until the change is on main and their individual acceptance criteria
pass.
