# Roadmap

Milestones advance on evidence, not calendar dates. All application milestones are currently pending.

| Milestone | Deliverable | Exit criteria |
| --- | --- | --- |
| M0: Foundation | Scope, architecture, standards, evaluation plan | English documentation is internally consistent and clearly distinguishes plans from implementation. |
| M1: Domain slice | Typed plan revisions, approval binding, operation state machine | Tests cover stale approval, invalid transitions, preservation of unrelated constraints, and synthetic fixtures. |
| M2: Persistent service | API, identity, database migrations, durable jobs | User isolation, concurrent revisions, restart recovery, and migration checks pass. |
| M3: Agent and client | Web conversation, evidence retrieval, editable memory, structured plans | A user can create and revise a plan; citations and memory behavior pass held-out evaluation. |
| M4: Calendar execution | OAuth, previews, confirmed writes, update/cancel, reconciliation | Real test-account flow works; duplicate delivery, lost responses, revocation, and partial failure are tested. |
| M5: Wellness loop | Exercise, nutrition, sleep, progress records, weekly reflection | All phase-one product requirements have evidence and known limitations. |
| M6: Showcase release | Reproducible deployment, demo, evaluation and load reports | Documented threat review, deletion checks, failure experiments, and measured performance; no unsupported claims. |

The first coding task is M1. Implement one small, tested domain slice before adding UI scaffolding, cloud infrastructure, or multiple provider integrations.

Later expansion follows the entry conditions in [Product Scope](PRODUCT_SCOPE.md). Do not silently enlarge phase one to include wearables or clinical features.
