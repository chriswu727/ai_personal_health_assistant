# 0004. Persistence stack and database test strategy

Status: Accepted (Sprint 2, task S2-01)

## Context

The domain package is pure and offline. Sprint 2 gives it durable storage in
which ownership is enforced on every access path and concurrent revisions cannot
silently overwrite each other. That needs a database, a driver, a migration tool,
and a way to test against a real server without making the default test suite
depend on one.

The architecture already names PostgreSQL and a separately runnable worker, so
the open questions are the Python-side stack, whether to be synchronous or
asynchronous, and how database tests run locally and in CI.

## Alternatives

- **SQLAlchemy ORM with mapped domain classes.** Removes the mapping module, but
  the domain would have to inherit from a persistence base class or be
  instrumented, which breaks the boundary the domain was built to keep.
- **psycopg alone with hand-written SQL and a home-grown migration runner.**
  Fewer dependencies and full control, but re-implements schema versioning,
  which is the part with the most ways to go quietly wrong.
- **A synchronous stack, deferring async until the delivery layer needs it.**
  Simpler to read and to test, and nothing in this slice demonstrates a
  concurrency requirement on its own. Rejected: `async` is viral through call
  sites, so deferring means rewriting every adapter, repository, and application
  service later rather than writing them once. The cost of the change grows with
  the amount of code above it, and that code has not been written yet.
- **SQLite for tests, PostgreSQL in production.** Tests would run anywhere with
  no service. It would also test a different database: no `ON CONFLICT` row-count
  semantics, no `timestamptz`, no array columns, and different locking. The
  concurrency guarantees under test are exactly the ones that differ.

## Decision

PostgreSQL, reached through SQLAlchemy 2.0 Core and the psycopg 3 driver, with
Alembic for migrations. SQLAlchemy is used for connection handling, typed table
metadata, and query construction, not as an object-relational mapper: domain
objects are converted in one mapping module that is the only code aware of both
shapes.

The stack is asynchronous: `create_async_engine`, `AsyncConnection`, and
psycopg's async API, with Alembic driving migrations through `run_sync` on an
async engine. The architecture already commits to streaming responses and to
bounded provider concurrency per user and per provider, both of which are
asynchronous by nature, and every adapter and application service written
between now and then would otherwise have to be converted.

The domain stays synchronous and performs no I/O, so this decision does not
reach the tested core. That boundary is what makes the choice cheap: the 98
domain tests are unaffected by it.

Database tests are marked `integration` and read
`HEALTH_ASSISTANT_TEST_DATABASE_URL`. They skip when it is unset, which keeps
the default suite deterministic and offline. Once it is set they never skip: a
connection or migration failure is an error, so a misconfigured run cannot be
mistaken for a passing one. CI runs them against a `postgres:17` service
container on the same standard GitHub-hosted runner, which involves no paid
service.

A test compares the migrated schema against the declared metadata and fails on
any difference, so a hand-written migration cannot drift from the schema module.
Another downgrades to base and upgrades again, so the initial migration is
reversible rather than only assumed to be.

## Consequences

Contributors need PostgreSQL to run the database tests. Those who do not have it
still get a green offline suite, and CI covers what they skipped. The cost is
that a local pass is weaker evidence than a CI pass, so delivery evidence must
record which tests ran where.

SQLAlchemy's async support requires `greenlet`, which the `asyncio` extra pulls
in. Anything that calls into the database must be awaited, including test
fixtures, and Alembic's own entry point runs `asyncio.run`, so async callers
reach it through a worker thread. These are the ordinary costs of the choice and
are visible in `tests/integration/conftest.py`.

Using `ON CONFLICT DO NOTHING` with a row-count check, rather than catching an
integrity error, keeps the transaction usable after a conflict. An aborted
transaction cannot answer what the current version is, which is the one fact the
stale-revision error needs to report.

Keeping SQLAlchemy at Core level means writing an explicit mapping module. That
is the intended cost: it is the only place that knows both the row shape and the
domain shape, and the domain stays free of persistence concerns.
