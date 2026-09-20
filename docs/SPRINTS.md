# Sprint Board

This file is the source of truth for delivery status. The [roadmap](ROADMAP.md) defines milestone order; [product scope](PRODUCT_SCOPE.md) defines intended behavior.

## Current position

- Completed: Sprint 0, the repository and design foundation. Sprint 1, the tested
  domain slice, merged in [pull request #1](https://github.com/chriswu727/ai_personal_health_assistant/pull/1).
- Active sprint: Sprint 2, persistence and ownership enforcement. Part one, plan
  storage with ownership and ancestry, is merged as `5deeaa2`. Part two, constraint,
  approval, and operation storage with worker leases, is underway.
- Application release: none. There is no runnable application or service.

## Working method

Each sprint has a goal, bounded tasks, acceptance criteria, and a review. Sprint numbers express sequence rather than a promised time estimate. Refine later outlines before execution.

| Status | Meaning |
| --- | --- |
| Planned | Defined work that has not started |
| In Progress | Implementation or verification is underway |
| Blocked | Cannot advance; record the dependency and required unblock action |
| Done | Acceptance criteria passed and completion evidence is recorded |

Keep at most one sprint In Progress. Update task status alongside implementation. Done requires work on main, passing applicable checks, updated documentation, and traceable evidence. Code being written or a passing mock alone does not establish end-to-end completion.

Link the implementation commit or merged PR, local verification reports, and applicable CI results once configured. Record commands, environment, and results. Standard GitHub-hosted runners are authorized for this public repository; default to `ubuntu-latest`. Larger/paid runners and paid services require explicit authorization. For the closing change itself, refer to its enclosing commit rather than inventing a future hash. Distinguish offline, simulated-provider, and live integration results. Record checks not run.

A sprint closes only when its committed acceptance criteria are met. Record the reason and destination of any deferred work before closure. Never silently remove required phase-one functionality to make a sprint appear complete.

## Sprint overview

| Sprint | Goal | Status | Depends on | Exit evidence |
| --- | --- | --- | --- | --- |
| 0 | Establish the public project foundation | Done | None | Published documents and repository checks |
| 1 | Model plans, approvals, and operation lifecycles | Done | 0 | [Merged in #1](https://github.com/chriswu727/ai_personal_health_assistant/pull/1); 98 offline tests, local and CI checks green |
| 2 | Persist and isolate user workflows | In Progress | 1 | Migrations, ownership-enforcing repositories, concurrency and recovery tests |
| 3 | Add grounded reasoning and personal memory | Planned | 2 | Retrieval, memory, and orchestration evaluations |
| 4 | Deliver the conversational web experience | Planned | 3 | Accessible journeys and cancellation/reconnect checks |
| 5 | Execute verified calendar changes | Planned | 4 | Live test-account flow and ambiguous-write recovery |
| 6 | Complete the exercise, nutrition, and sleep loop | Planned | 5 | Domain evaluations, progress records, and weekly adjustments |
| 7 | Validate and publish the showcase release | Planned | 6 | Reproducible demo, privacy checks, and measured load/failure reports |

## Sprint 0: Project foundation

Goal: publish English engineering documentation without claiming unimplemented capabilities.

| Task | Deliverable and acceptance | Status | Evidence |
| --- | --- | --- | --- |
| S0-01 | Public repository with initial English documentation | Done | [Foundation commit](https://github.com/chriswu727/ai_personal_health_assistant/commit/9b9b9db89cf8ec7ab94016fa38518994c33495c9); visibility and matching local/remote SHA verified through GitHub CLI |
| S0-02 | Phase-one requirements and long-term boundaries | Done | [Product scope](PRODUCT_SCOPE.md), P01-P11 and later-phase entry conditions |
| S0-03 | Proposed architecture and external-action recovery semantics | Done | [Architecture](ARCHITECTURE.md), explicitly labeled as proposed |
| S0-04 | Coding/review conventions and evaluation requirements | Done | [Contributing](../CONTRIBUTING.md), [evaluation strategy](EVALUATION.md), and [security policy](../SECURITY.md) |

Review: 12 initial files were published; local documentation-link and English-content checks passed, as did Git whitespace checks. There is no application runtime, application test suite, or clinical validation. Retrospective: retain the separation between proposed capabilities and demonstrated results; introduce executable quality gates in Sprint 1.

## Sprint 1: Tested domain foundation

Status: Done. Merged in [pull request #1](https://github.com/chriswu727/ai_personal_health_assistant/pull/1) as `e00c949`.

Goal: implement deterministic plan and approval behavior that future model and calendar adapters must obey.

Scope: backend domain package, development tooling, offline tests, reproducible local quality gates, and standard-runner GitHub Actions. Excludes paid runners, UI, live model calls, calendar credentials, and deployment infrastructure.

| Task | Deliverable | Acceptance criteria | Status | Evidence |
| --- | --- | --- | --- | --- |
| S1-01 | Runtime/tooling decision and package setup | Record supported Python version and strict type-checking choice; lock dependencies; document reproducible installation and verification commands | Done | Python 3.12 pinned in `.python-version`; `pyproject.toml` and `uv.lock`; rationale in [ADR 0001](decisions/0001-python-runtime-and-tooling.md) |
| S1-02 | Typed plans and revisions | No framework/SDK dependencies in domain code; revisions preserve unrelated constraints and completed history; invalid input and stale edits are rejected | Done | `domain/plans.py`, `domain/constraints.py`, `domain/validation.py`; `tests/test_plans.py`, `tests/test_validation.py` |
| S1-03 | Approval model | Bind owner, exact payload/version, scope, and expiration; changed, expired, revoked, and wrong-owner approvals cannot authorize execution | Done | `domain/approvals.py`, `domain/actions.py`; `tests/test_approvals.py`. Scope binds an action per item and the fingerprint covers it ([ADR 0003](decisions/0003-authorization-boundary.md)) |
| S1-04 | Operation state machine | Define allowed transitions and ambiguous outcomes; test terminal/cancellation behavior; unknown results cannot authorize blind retries | Done | `domain/operations.py`; `tests/test_operations.py`. Each entry point names its source state, and authorization is revalidated when work is claimed |
| S1-05 | Behavioral tests | Synthetic fixtures cover invariants, invalid transitions, revision conflicts, approval invalidation, and deterministic time; tests run offline | Done | 98 offline tests with synthetic fixtures and an injected fixed clock; `tests/test_scenario_first_journey.py` covers the product-scope journey; four review findings have regression tests |
| S1-06 | Local and CI quality gates | Documented commands run formatting checks, linting, strict type checking, tests, and package build with locked dependencies; the same checks pass locally and on standard GitHub-hosted `ubuntu-latest`; record results; no paid runners or paid API calls | Done | `scripts/verify.sh` and `.github/workflows/ci.yml` run identical commands; both the local run and the [CI run on `ubuntu-latest`](https://github.com/chriswu727/ai_personal_health_assistant/actions/runs/35530164477) passed, recorded below |
| S1-07 | Review and documentation | Record implemented contracts, reproducible examples, validation evidence, limitations, and the next sprint breakdown | Done | README implementation section, updated architecture, [ADR 0001](decisions/0001-python-runtime-and-tooling.md) and [ADR 0002](decisions/0002-first-class-constraints.md) |

Definition of Done: S1-01 through S1-07 pass acceptance, changes are on main, and the review records evidence. The domain package runs without a model provider, network, database, or personal data. Domain tests do not establish persistent recovery or live calendar reliability.

Scope change: `Constraint` and deterministic pre-approval validation were added
to the domain slice. The product scope already required allergy adherence (P06)
and clarification over silent relaxation (P08), but no entity or component owned
that check. The reasoning and the alternatives considered are recorded in
[ADR 0002](decisions/0002-first-class-constraints.md).

### Review round 1

Review of [pull request #1](https://github.com/chriswu727/ai_personal_health_assistant/pull/1)
reported four P1 authorization defects. All four were reproduced against the
reviewed commit before any change, and all four are now blocked with the
legitimate path unaffected:

| Finding | Reproduced behavior | Resolution |
| --- | --- | --- |
| `retry()` bypassed confirmation | Unconfirmed operation reached EXECUTING with `approval_id=None` | Each transition names its source state; `retry()` accepts only a verified failure |
| Cross-owner confirmation | One user's approval queued another user's operation | `authorize_operation` compares owner, plan, version, and item content |
| A create approval authorized a cancel | `cancel_event` queued under a `create_event` confirmation | Approval scope and fingerprint bind the action per item |
| Expired approval still executed | Claimed at minute 31 under a 30-minute confirmation | Authorization is revalidated at the execution boundary |

The common cause was that each function validated only its own local
preconditions, and the tests mirrored that shape rather than crossing entry
points.

### Review round 2

The reviewer verified three of the four findings as fixed and kept the approval
binding open: the action kind was bound, but the compensation target was not.
Reproduced on that commit, then fixed:

| Finding | Reproduced behavior | Resolution |
| --- | --- | --- |
| Compensation target substitution | Replacing `compensates` on a confirmed cancellation still reached EXECUTING under the original approval | `ApprovedAction` carries the target; both the approval fingerprint and the operation's idempotency key derive from the same canonical action payload |

An approval to cancel must now name the write it undoes; an untargeted
cancellation approval no longer authorizes a targeted one. A retry of the
identical authorized operation still succeeds with an unchanged idempotency key,
which the review asked to preserve and which is covered by a test.

Reasoning and consequences for both rounds are recorded in
[ADR 0003](decisions/0003-authorization-boundary.md).

### Verification

Local verification, macOS 15.7.4 arm64, Python 3.12.13, Ruff 0.16.8, mypy 2.3.1,
pytest 9.1.1, commit as reviewed on the branch:

| Check | Command | Result |
| --- | --- | --- |
| Format | `uv run ruff format --check .` | Pass, 37 files |
| Lint | `uv run ruff check .` | Pass |
| Types | `uv run mypy` | Pass, 20 source files, strict mode |
| Tests | `uv run pytest` | Pass, 98 tests, offline |
| Build | `uv build` | Pass, sdist and wheel |

The same six checks passed on a standard GitHub-hosted `ubuntu-latest` runner:
[CI run](https://github.com/chriswu727/ai_personal_health_assistant/actions/runs/35530164477), reporting 35 files formatted, lint clean, 19 source files
type-checked, 79 tests passed, and both distributions built. Later commits on the
branch run the workflow again; results are visible on the pull request.

Not run: any live provider call, and any persistence, concurrency, or recovery
test against a real database. These domain tests establish deterministic
contracts only. They do not establish persistent recovery, live calendar
reliability, or clinical validity.

### Sprint review

Delivered: a standard-library-only domain package covering immutable plan
versions with revision rules, first-class constraints with deterministic
pre-approval validation, approvals bound to owner, version, payload, action, and
action target, and an external operation lifecycle in which an unknown outcome
must be reconciled before any retry. 98 offline tests, reproducible local and CI
quality gates, and three decision records.

Verification: recorded above. Two review rounds reported five P1 authorization
defects; all five were reproduced before any change, fixed, and re-checked.
Merged as `e00c949`.

Unverified: persistent recovery, concurrent access, live calendar reliability,
and clinical validity. None of these is claimed.

Retrospective. The first implementation passed every check it had and still
shipped a broken consent boundary. Two causes, both worth carrying forward:

1. Each function validated only its own local preconditions, and nothing checked
   that an operation, a plan, and an approval described one proposal. Shared
   machinery, in this case the transition table, let one entry point perform
   another's transition and skip its checks.
2. The tests mirrored the shape of the code. Every function had its own failure
   cases covered, and no test crossed two entry points, which is exactly where
   all five defects lived.

Action for Sprint 2 onward: alongside the per-unit tests, write adversarial
probes that try to reach a protected state by an unintended path, and treat a
passing suite as evidence about the paths it exercises rather than about the
property it is named after. Recorded as task S2-07.

Carryover: none. Blockers: none.

## Sprint 2: Persistent service

Status: In Progress.

Goal: give the domain a durable home in which ownership is enforced on every
access path and concurrent revisions cannot silently overwrite each other.

Scope: PostgreSQL schema and migrations, repositories, a unit-of-work boundary,
durable operations with worker leases, and a simulated provider. Excludes HTTP
delivery, model providers, calendar credentials, and deployment infrastructure.

| Task | Deliverable | Acceptance criteria | Status | Evidence |
| --- | --- | --- | --- | --- |
| S2-01 | Persistence stack and test harness | Record the database, driver, and migration tool with alternatives; add a schema and a reversible initial migration; integration tests require an explicit database URL and are skipped without one; the default suite stays offline; CI runs both against a standard-runner service container | Done | [ADR 0004](decisions/0004-persistence-stack.md); `adapters/persistence/schema.py`, `migrations/versions/0001_initial_schema.py`, `tests/integration/` |
| S2-02 | Plan persistence with version checks | Store plan versions and items losslessly, including time zones, attribute tokens, and completion status; a concurrent insert of the same version is rejected as a stale revision rather than merged | Done | `adapters/persistence/plans.py`, `mapping.py`; `tests/integration/test_plan_repository.py` |
| S2-03 | Ownership enforcement | Every repository read and write is scoped by owner; a cross-user identifier returns nothing rather than another user's row; no access path omits the owner | Done | Owner column on every user-owned table; `test_another_user_reads_nothing`, `test_writing_into_another_users_plan_is_refused` |
| S2-04 | Constraint and approval persistence | Round-trip constraints, approvals, approved actions, and their targets; a stored approval authorizes exactly what the in-memory one did | In Progress | `adapters/persistence/constraints.py`, `approvals.py`; database round-trip tests |
| S2-05 | Durable operations and worker leases | Persist the operation lifecycle; claim work with a lease so two workers cannot hold one operation; an expired lease returns work for reconciliation rather than marking it failed | In Progress | `adapters/persistence/operations.py`, `application/worker.py`; lease and claim tests |
| S2-06 | Restart and transaction boundaries | A failure mid-transaction leaves no partial plan version or half-queued operation; work in flight when a worker dies is recoverable after restart | Planned | Pending |
| S2-07 | Adversarial path probes | Alongside per-unit tests, probes attempt to reach a protected state by an unintended path: cross-user access, a revision that skips the version check, and a claim that bypasses authorization. Carried from the Sprint 1 retrospective | Planned | Pending |
| S2-08 | Review and documentation | Record the implemented contracts, verification evidence separated by where it ran, limitations, and the Sprint 3 breakdown | Planned | Pending |

Definition of Done: S2-01 through S2-08 pass acceptance, changes are on main, and
the review records evidence. Integration results must state which ran locally and
which ran in CI. A simulated provider is used throughout; live calendar
integration remains Sprint 5.

### Review round 1, part one

Review of [pull request #2](https://github.com/chriswu727/ai_personal_health_assistant/pull/2) reported three defects and a documentation
inconsistency. All three were reproduced before any change:

| Finding | Reproduced behavior | Resolution |
| --- | --- | --- |
| Ancestry was never checked | Saving version 3 onto a stored version 1 succeeded, and version 2 could open an empty plan, leaving a version with no persisted history | `save` requires the successor's own stored parent, and a self-referencing foreign key enforces it in the schema so no future code path can bypass it |
| The stale-revision error contradicted itself | The loser of a concurrent revision was told "expected plan version 2, found 2" | The error now reports the base version the writer actually revised |
| Windows could not run the database path | psycopg's async mode rejects the ProactorEventLoop, the Windows default, before reaching the server | Entry points select a selector loop; an offline test asserts the chosen loop is never a proactor loop, so a Windows run cannot mask it |

The domain invariant was tightened alongside the schema: a version's parent must
be the version immediately before it, so the rule is one rule rather than two
that could drift.

### Review round 2, part one

The reviewer verified the ancestry and Windows runtime fixes, the latter on
native Windows, and reported that the Windows fix had introduced a quality-gate
regression of its own.

| Finding | Reproduced behavior | Resolution |
| --- | --- | --- |
| The platform branch broke type checking on Windows | `sys.platform == "win32"` is statically known, so the return after it was unreachable and `warn_unreachable` failed the gate on Windows while Linux stayed green | The branch is gone: `asyncio.SelectorEventLoop` exists on every platform and is already the POSIX default, so one factory serves both |

`uv run mypy --platform win32` is now part of the gate, locally and in CI. It
reproduces a Windows-only typing regression from Linux or macOS, which is how
this one was confirmed and then confirmed fixed, and it needs no extra runner.

Documentation was out of step with the code: the README and architecture still
said persistence did not exist, the handoff disagreed with the board, and two
places described the earlier row-count conflict detection. All are corrected.

### Verification, part one

Merged in [pull request #2](https://github.com/chriswu727/ai_personal_health_assistant/pull/2) as `5deeaa2` after two review rounds. S2-01,
S2-02, and S2-03 are Done.


| Check | Where | Result |
| --- | --- | --- |
| Format, lint, mypy strict | Local and CI | Pass, 35 source files, checked for both the native platform and `win32` |
| Offline tests | Local and CI | Pass, 101 tests |
| Database tests | Local and CI | Pass, 11 tests against PostgreSQL 17 |
| Build | Local and CI | Pass, sdist and wheel |

Local run on macOS 15.7.4 arm64, Python 3.12.13, against PostgreSQL 17 in a
container: 112 tests pass with the database configured, and 101 pass with 11
skipped without it. The database was dropped and recreated first, so the
migration was applied from empty rather than onto an already-migrated schema.

Three defects in this sprint were found only because the tests run against a
real PostgreSQL server rather than a substitute: the row-count conflict signal,
the missing `greenlet` dependency, and the schema drift left by amending an
already-applied migration. Each supports the decision in
[ADR 0004](decisions/0004-persistence-stack.md) to reject a substitute database.

Not run: any live provider call, any overlapping-transaction test, worker leases,
and restart recovery. Those are S2-05 and S2-06.

### Review round 1, part two

Three P1 findings, all reproduced against PostgreSQL before any change and all
blocked after it. Each was a write or a read that trusted a snapshot which had
already moved on:

| Finding | Reproduced behavior | Resolution |
| --- | --- | --- |
| The worker authorized against a historical plan | The worker reloaded the version the operation was queued under, so the domain compared that version against itself and a plan revised in the meantime never invalidated the confirmation | The plan is loaded at its newest version, and the plan row is read for update so a revision orders itself against the claim |
| A stale save undid a revocation | Saving a pre-revocation snapshot after a revocation wrote `NULL` back over the timestamp, restoring consent | Revocation is monotonic in storage, and the worker reads the approval for update |
| A stale save erased a live lease | Saving a pre-claim snapshot reset state, attempts, and lease, letting a second worker take work the first still held | Insertion and advancement are separate, and an advance applies only if the stored row still matches the snapshot it was built on |

The last one is worth stating plainly: `SKIP LOCKED` orders two simultaneous
claims and does nothing about a write arriving later with an older view. The
concurrency test that passed was testing the case that was already safe.

Documentation corrected alongside: the ADR claimed `claim_next` was the only
access path not scoped to an owner, and `expired_leases` is a second one.

### Verification, part two

Part two covers S2-04 and S2-05 and is awaiting review.

| Check | Where | Result |
| --- | --- | --- |
| Format, lint, mypy strict | Local | Pass, 44 source files, native platform and `win32` |
| Offline tests | Local | Pass, 101 tests |
| Database tests | Local | Pass, 38 tests against PostgreSQL 17 |
| Build | Local | Pass, sdist and wheel |

139 tests pass locally with the database configured, 101 with 38 skipped
without it. CI results are recorded on the pull request.

The concurrency claim is tested rather than asserted: two transactions open at
once each call `claim_next`, and the second returns nothing, which is what
`SKIP LOCKED` is for. Lease expiry is tested through the worker use case and
lands in `outcome_unknown` without consuming another attempt.

Not run: restart recovery across a real process exit, overlapping-transaction
tests beyond the claim path, and the adversarial probes. Those are S2-06 and
S2-07.

Review: pending. Blockers: none identified. Carryover: none.

## Later sprint outlines

These outlines are not started tasks. Expand each into task IDs, acceptance criteria, and evidence fields before moving it to In Progress.

### Sprint 3: Evidence and memory

Deliver curated retrieval with provenance, editable memory, contradiction/expiration handling, a model adapter, and bounded orchestration producing validated plans. Verify citation support, deletion across sessions, retrieved prompt injection resistance, and missing-evidence behavior. Create held-out synthetic evaluations; keep paid calls opt-in.

### Sprint 4: Web experience

Deliver Assistant, Today, Plan, Records, and Settings foundations, visible memory controls, and action previews. Verify streaming, cancellation, reconnect, keyboard navigation, mobile layouts, and partial edits. Distinguish proposed and completed actions. Calendar previews remain explicitly simulated until Sprint 5.

### Sprint 5: Calendar execution

Deliver OAuth connection/revocation, availability reads, neutral titles, exact confirmation, owned-event create/update/cancel, and reconciliation. Verify real test-account actions plus timeout-after-write, duplicate delivery, revocation, and partial success. Keep personal calendar data out of reports.

### Sprint 6: Integrated wellness loop

Complete exercise, nutrition, sleep, routines, manual observations, weekly reflection, export, and deletion. Verify hard constraints, time-zone/DST behavior, observation-versus-goal semantics, and appropriate out-of-scope responses. Map P01-P11 to implementation and acceptance evidence; close coverage gaps before release.

### Sprint 7: Showcase release

Deliver reproducible deployment, a synthetic demo, redacted telemetry, fault injection, bounded load experiments, cost measurements, and limitations. Document retention/backup deletion, permissions, and source licenses. Separate live-provider and simulated-provider measurements. Freeze evaluation configuration and publish failures alongside successes.

## Sprint review template

At each sprint close, record:

- Goal and delivered user/engineering outcomes.
- Completed task IDs and commit/PR links.
- Checks executed, results, environment, and evidence locations.
- Unverified behavior and known limitations.
- Scope changes, blockers, and explicitly assigned carryover.
- A short retrospective and the next sprint's concrete tasks.
