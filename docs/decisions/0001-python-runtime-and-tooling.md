# 0001. Python runtime and quality tooling

Status: Accepted (Sprint 1, task S1-01)

## Context

The first implementation slice is a domain package with no framework, database,
or model provider. It needs a supported runtime, a strict type checker, a
linter, a test runner, and a reproducible installation that behaves identically
on a developer machine and on a standard GitHub-hosted runner.

## Alternatives

- **Poetry or PDM for dependency management.** Both lock dependencies well.
  Neither installs the interpreter itself, so the Python version would remain an
  unpinned property of the machine.
- **pip with a `requirements.txt` produced by pip-tools.** Fewer moving parts,
  but separate files for runtime and development dependencies, and no
  interpreter management.
- **Python 3.14.** Available locally, but newer than several typing and tooling
  ecosystems have settled on, which adds risk for no present benefit.
- **pyright instead of mypy.** Comparable strictness; requires Node.js in CI.

## Decision

Target Python 3.12 and pin it with `.python-version`. Manage dependencies and
the interpreter with `uv`, committing `uv.lock`. Use Ruff for both formatting
and linting, mypy in `strict` mode for type checking, pytest for tests, and
hatchling as the build backend.

The domain package depends on the standard library only. The sole runtime
dependency is `tzdata`, constrained to Windows, where Python has no system IANA
time-zone database to read.

`PLR0913` (too many arguments) is configured to allow eight. Domain entry points
take keyword-only parameters, so the positional-argument confusion the rule
guards against does not apply.

## Consequences

`./scripts/verify.sh` runs the same commands locally and in CI, and
`uv sync --locked` fails rather than silently resolving different versions.

Pinning 3.12 means newer language features are unavailable until a later record
supersedes this one. Committing a lockfile means dependency updates are explicit
changes that appear in review.
