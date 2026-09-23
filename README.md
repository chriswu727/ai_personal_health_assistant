# Personal Health Assistant

A personal AI assistant for evidence-informed exercise, nutrition, sleep, and daily routines, with user-controlled memory and verified calendar actions.

**Status: tested domain package with database-backed plan storage. There is no
application, web interface, calendar integration, clinical validation, or
deployed service yet.**

This engineering portfolio project explores a practical question: how can an assistant turn a changing personal goal into an actionable plan while preserving user constraints, explaining its evidence, and recovering correctly when an external service fails?

## The intended experience

> "I want to start exercising, eat more consistently, and improve my sleep. I have two free evenings each week and no gym membership."

The assistant clarifies relevant constraints, proposes a weekly plan, and explains its recommendations. The user can revise individual activities before approving calendar changes. Later feedback updates the plan without rewriting completed history or duplicating external events.

## Phase one

- Exercise guidance for beginners, regular exercisers, and everyday activity.
- Nutrition guidance grounded in preferences, allergies, budget, and cooking access.
- Sleep and routine planning that respects real availability and time zones.
- Inspectable, editable personal memory with provenance and expiration.
- Source-backed health information with explicit uncertainty and scope limits.
- Versioned weekly plans and manual progress records.
- Google Calendar integration with confirmation, reconciliation, and cancellation.
- Reproducible evaluations for constraints, memory, tool execution, and recovery.

All product capabilities above are **planned**, not implemented.

What exists today is the deterministic core the later adapters must obey: typed
plan versions whose revisions preserve reported history, constraint checking
that runs without a model, approvals bound to an exact payload, and an external
operation lifecycle that refuses to retry a write whose outcome is unknown. See
[what is implemented](#what-is-implemented).

## Documentation

| Document | Purpose |
| --- | --- |
| [Product scope](docs/PRODUCT_SCOPE.md) | Phase-one requirements, exclusions, and long-term vision |
| [Architecture](docs/ARCHITECTURE.md) | Proposed boundaries, data model, and failure semantics |
| [Roadmap](docs/ROADMAP.md) | Incremental delivery and milestone exit criteria |
| [Sprint board](docs/SPRINTS.md) | Task status, acceptance criteria, and completion evidence |
| [Engineering standards](CONTRIBUTING.md) | Coding, review, testing, and documentation conventions |
| [AI engineering rules](AGENTS.md) | Mandatory workflow for AI contributors and tool entry points |
| [Development handoff](docs/HANDOFF.md) | Current context and the next concrete action |
| [Decision records](docs/decisions/README.md) | Accepted architectural choices and their consequences |
| [Evaluation strategy](docs/EVALUATION.md) | Evidence required before reliability or scale claims |
| [Security policy](SECURITY.md) | Sensitive data handling and vulnerability reporting |

## Engineering focus

Start with a modular monolith and a durable background worker. Introduce infrastructure when a measured requirement justifies it. Keep model decisions separate from authorization, validation, and external execution. Publish limitations alongside results.

Repository documentation, code, comments, commit messages, and review discussions use English. The project is designed to demonstrate engineering judgment through working software and reproducible experiments rather than unverified production-readiness claims.

## Health scope

The intended product provides general wellness information and planning support. It does not independently diagnose conditions, prescribe treatment, or change medication doses. Potentially urgent symptoms require an appropriate help-seeking response rather than continuation of routine coaching. Public examples and evaluation data must be synthetic.

## What is implemented

`src/health_assistant/domain` is a standard-library-only package with no HTTP
client, database session, model SDK, or user interface. Four properties are
enforced in code and covered by offline tests:

- **Revisions preserve history.** A plan version is immutable. Revising it
  produces a successor; an item whose outcome the user reported cannot be
  edited, removed, or re-reported. A concurrent edit against a stale version is
  rejected rather than merged.
- **Constraints are checked deterministically before approval.** Matching uses
  normalized tokens and interval overlap, never a model call. A confirmed hard
  constraint blocks approval; the same constraint unconfirmed forces a
  clarification instead of a silent decision either way.
- **Approval is bound to exact content and one action.** A confirmation names
  its owner, plan version, the external action approved for each item, an
  expiry, and a hash of that payload. Any later revision invalidates it,
  including a change to an item outside its scope, and a confirmation to create
  an event never authorizes cancelling one. Authorization is checked again at
  the execution boundary, so a confirmation that expires or is revoked while the
  work sits in the queue stops it.
- **Stored plans keep their history and their isolation.** Plans, constraints,
  approvals, and operations live in PostgreSQL behind repositories that scope
  every read to the owner, so a request for another user's data returns nothing.
  A plan version must be written onto its own stored parent, so a lost update is
  a rejected write rather than a silent overwrite.
- **A citation can be reproduced.** The curated corpus is public knowledge, with
  no owner, stored with the source, publisher, publication date, locator, and
  the permission under which it may be quoted. Retrieval narrows in the database
  and ranks in the domain by a total order, so the same query returns the same
  passages in the same order anywhere, and the record says whether the search saw
  the whole corpus or stopped early. Each record keeps the cited document's
  provenance with it, so curating the corpus later cannot rewrite the basis of a
  past answer, and the record belongs to the user who asked, because a question
  can say something about them. The ranking is a plain word-overlap
  baseline: it will not find a passage about peanuts from a question about satay,
  and it weighs a word like "and" as heavily as the subject of the question.
  Checking that a passage actually supports a claim is separate work, still to
  come.
- **Queued work is re-authorized against current records before it runs.** A
  worker takes the oldest operation no other worker holds, then loads that
  operation's owner's **current** plan and its approval and asks the domain
  whether it may still execute. A plan revised, or a confirmation expired or
  revoked, while the work waited cancels the operation with the reason recorded
  rather than leaving it to spin. A write built on a stale read is refused, so a
  late save cannot erase a live lease. A worker that stops reporting has its
  lease released to an unknown outcome, never to a failure.
- **An unknown outcome is not a failure.** A lost response or an expired worker
  lease moves an operation to `outcome_unknown`, from which only reconciliation
  against the provider produces a terminal state. Retrying it directly raises
  rather than risking a duplicate external write, and every attempt of one
  operation presents the same idempotency key.

`tests/test_scenario_first_journey.py` walks the whole journey from the product
scope: a violated allergy blocks approval, the user edits one activity, the
provider response is lost after the write lands, and reconciliation adopts the
existing event instead of creating a second one.

Known limitation: constraint matching is exact on declared attributes. It does
not know that "satay" implies peanut. An ingredient taxonomy belongs to the
evidence work in Sprint 3.

## Getting started

Requires [uv](https://docs.astral.sh/uv/). The pinned interpreter is Python
3.12; `uv` installs it if it is absent.

```bash
uv sync --locked
uv run pytest
```

Run every quality gate exactly as CI runs it:

```bash
./scripts/verify.sh
```

Database tests need PostgreSQL and are skipped without it; see
[Contributing](CONTRIBUTING.md). There is no application to start. Sprint 2 is
complete: storage, ownership, worker claiming, restart recovery. Sprint 3 is
under way, starting with the evidence corpus; editable memory, a bounded model
adapter, and orchestration to a validated plan follow.
