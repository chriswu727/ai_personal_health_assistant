# Development Handoff

This file provides session context; [SPRINTS.md](SPRINTS.md) remains the source of truth for delivery status. Update this file when a work session changes repository behavior, governance, or verification state. Keep context concise and never include credentials or personal health data.

## Current state

- Canonical repository: `chriswu727/ai_personal_health_assistant`.
- Sprint 0 foundation: Done. Sprint 1 domain slice: Done, merged as `e00c949`.
- Sprint 2: S2-01 through S2-07 are Done, merged as `5deeaa2`, `ecafaf3`, and
  `4e3f60e`. S2-08, the sprint review and the Sprint 3 breakdown, is this change
  and stays In Progress until it is on main.
- Sprint 3, evidence and memory, is refined into S3-01 through S3-09 and Planned.
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

Closed Sprint 2 with its review and retrospective, refined Sprint 3 into S3-01
through S3-09 with acceptance criteria, and corrected the roadmap where a
milestone had been mapped to a single sprint that never covered all of it.

No application behavior changed.

## Verification

This is a documentation change, so the evidence that matters is consistency
rather than test counts:

- Relative-link check across every Markdown file: passed.
- `git diff --check`: passed.
- The configured gates still pass unchanged: format, lint, `mypy`, `mypy
  --platform win32`, 103 offline tests, and the build. With
  `HEALTH_ASSISTANT_TEST_DATABASE_URL` set, 152 tests pass against PostgreSQL 17.

Not run, and not applicable: nothing here exercises application behavior, and no
result below is evidence about the product.

## Next action

Once this change is on main, mark S2-08 Done, close Sprint 2, and start Sprint 3
at S3-01: the evidence corpus and retrieval with provenance, deterministic for a
fixed corpus and query, with no network call in the default suite. Read the
Sprint 3 section before starting; it carries an action from the Sprint 2
retrospective about naming the window between reading state and acting on it.

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
