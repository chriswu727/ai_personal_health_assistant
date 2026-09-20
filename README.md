# Personal Health Assistant

A personal AI assistant for evidence-informed exercise, nutrition, sleep, and daily routines, with user-controlled memory and verified calendar actions.

**Status: design foundation. No application, clinical validation, or production service is available yet.**

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

All capabilities above are **planned**, not implemented.

## Documentation

| Document | Purpose |
| --- | --- |
| [Product scope](docs/PRODUCT_SCOPE.md) | Phase-one requirements, exclusions, and long-term vision |
| [Architecture](docs/ARCHITECTURE.md) | Proposed boundaries, data model, and failure semantics |
| [Roadmap](docs/ROADMAP.md) | Incremental delivery and milestone exit criteria |
| [Sprint board](docs/SPRINTS.md) | Task status, acceptance criteria, and completion evidence |
| [Engineering standards](CONTRIBUTING.md) | Coding, review, testing, and documentation conventions |
| [Evaluation strategy](docs/EVALUATION.md) | Evidence required before reliability or scale claims |
| [Security policy](SECURITY.md) | Sensitive data handling and vulnerability reporting |

## Engineering focus

Start with a modular monolith and a durable background worker. Introduce infrastructure when a measured requirement justifies it. Keep model decisions separate from authorization, validation, and external execution. Publish limitations alongside results.

Repository documentation, code, comments, commit messages, and review discussions use English. The project is designed to demonstrate engineering judgment through working software and reproducible experiments rather than unverified production-readiness claims.

## Health scope

The intended product provides general wellness information and planning support. It does not independently diagnose conditions, prescribe treatment, or change medication doses. Potentially urgent symptoms require an appropriate help-seeking response rather than continuation of routine coaching. Public examples and evaluation data must be synthetic.

## Getting started

Read the product scope and architecture before implementation. There is no executable application or installation command at this milestone. The next deliverable is the first tested domain slice described in the roadmap.
