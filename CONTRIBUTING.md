# Contributing

## Working agreement

AI contributors must follow [AGENTS.md](AGENTS.md), the canonical repository agreement. Tool-specific instruction files only point to that agreement. Every session reads the sprint board and handoff before making changes and updates them as work progresses. Repository instructions express requirements; executable checks enforce only the properties they actually validate.

Use English for code, identifiers, comments, documentation, commits, and pull requests. Deliver small, reviewable changes with a clear user or engineering outcome. Prefer explicit behavior and familiar patterns over cleverness. Standards are concrete project conventions, not a claim to satisfy every coding standard.

## Code conventions

- Use strict TypeScript and fully annotated Python public interfaces when those runtimes are introduced.
- Validate untrusted input at boundaries; enforce domain invariants in domain code.
- Prefer narrow types and explicit error categories. Do not silently catch failures or use untyped escape hatches without an explanation.
- Keep functions cohesive, names descriptive, and modules organized by responsibility.
- Keep business logic out of HTTP handlers and UI components.
- Inject time, randomness, and external dependencies where determinism matters.
- Use comments for intent and tradeoffs; public contracts need concise documentation.
- Avoid premature generic frameworks, speculative integrations, and unnecessary dependencies.
- Commit dependency lockfiles and select supported runtime versions during implementation.

## Quality gates

Introduce automated formatting, linting, strict type checks, relevant tests, and builds with the first executable slice. Python tooling should use Ruff and a selected strict type checker; TypeScript tooling should use ESLint and the TypeScript compiler. Record exact commands and versions once configured. No application quality checks are configured at the documentation-only milestone.

Tests should verify behavior: domain invariants, ownership, concurrency, provider contracts, and failure recovery. Use unit tests for deterministic rules, integration tests for persistence, contract tests for adapters, and a small number of end-to-end user journeys. Do not optimize for a coverage badge or tests that merely mirror implementation.

## Change review

Track delivery in [the Sprint board](docs/SPRINTS.md). Reference task IDs in implementation pull requests, update status alongside the work, and record acceptance evidence before marking Done. Close each sprint with a review. Later work stays Planned until the active sprint closes or is explicitly replanned.

A pull request explains the problem, resulting behavior, relevant design tradeoffs, validation, and remaining limitations. Changes to public contracts, migrations, permissions, and health boundaries require explicit review notes. Update documentation alongside behavior changes. Never report a planned check as passed.

Use concise imperative English commit messages, optionally prefixed with feat, fix, docs, test, refactor, or chore. Keep unrelated cleanup separate. Record consequential architectural choices in docs/decisions with context, alternatives, decision, and consequences.

## Data and credentials

Use synthetic fixtures only. Never commit personal health records, provider credentials, exported chats, or real calendar details. Use environment variables or an appropriate secret store for credentials. Paid calls and real external mutations must be opt-in in tests; the default suite must be deterministic and offline.
