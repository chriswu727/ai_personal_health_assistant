# Roadmap

Milestones advance on evidence, not calendar dates. M0 and M1 are met; M2 is partly met. M3 onward are pending.

The [Sprint board](SPRINTS.md) is the single source of truth for task and sprint status. Sprint 0 covers M0; Sprint 1 covers M1; Sprints 2 and 4 together cover M2; Sprints 3 and 4 cover M3; Sprints 5, 6, and 7 cover M4, M5, and M6. Refine each sprint before starting it and close it with acceptance evidence.

M2 originally read as one sprint's work. It is not. Sprint 2 delivered its
migrations, durable jobs, user isolation, concurrent revisions, and restart
recovery, and its refined scope explicitly excluded HTTP delivery. The API and
the identity integration M2 also names arrive with the web experience in Sprint
4, so **M2 stays open until then** rather than being quietly redefined as what
Sprint 2 happened to deliver.

| Milestone | Deliverable | Exit criteria |
| --- | --- | --- |
| M0: Foundation | Scope, architecture, standards, evaluation plan | English documentation is internally consistent and clearly distinguishes plans from implementation. **Met**: Sprint 0. |
| M1: Domain slice | Typed plan revisions, approval binding, operation state machine | Tests cover stale approval, invalid transitions, preservation of unrelated constraints, and synthetic fixtures. **Met**: Sprint 1, merged `e00c949`. |
| M2: Persistent service | API, identity, database migrations, durable jobs | User isolation, concurrent revisions, restart recovery, and migration checks pass **and** an authenticated HTTP API serves the stored workflows, with identity supplied by the chosen provider rather than by a caller-provided identifier. **Partly met**: Sprint 2 delivered persistence, isolation, durable jobs, and recovery; the API and identity criteria are untested and are Sprint 4's. |
| M3: Agent and client | Web conversation, evidence retrieval, editable memory, structured plans | A user can create and revise a plan; citations and memory behavior pass held-out evaluation. |
| M4: Calendar execution | OAuth, previews, confirmed writes, update/cancel, reconciliation | Real test-account flow works; duplicate delivery, lost responses, revocation, and partial failure are tested. |
| M5: Wellness loop | Exercise, nutrition, sleep, progress records, weekly reflection | All phase-one product requirements have evidence and known limitations. |
| M6: Showcase release | Reproducible deployment, demo, evaluation and load reports | Documented threat review, deletion checks, failure experiments, and measured performance; no unsupported claims. |

M1 was the first coding task, and it was done before any UI scaffolding, cloud infrastructure, or provider integration existed. Keep that order for what remains.

Later expansion follows the entry conditions in [Product Scope](PRODUCT_SCOPE.md). Do not silently enlarge phase one to include wearables or clinical features.
