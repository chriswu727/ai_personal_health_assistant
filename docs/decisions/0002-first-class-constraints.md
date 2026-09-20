# 0002. First-class constraints and deterministic pre-approval validation

Status: Accepted (Sprint 1, tasks S1-02 and S1-03)

## Context

The product scope requires that nutrition suggestions respect confirmed
allergies (P06), that conflicting constraints trigger clarification rather than
silent relaxation (P08), and that confirmed facts stay distinct from unconfirmed
inferences (P03). The architecture already required invariants to be enforced in
executable code rather than in prompts.

The original data model listed `MemoryFact`, `Observation`, and `Goal` but no
constraint entity, and named no component responsible for checking a proposed
plan against one. For a health assistant, serving a meal that violates a stated
allergy is the most consequential failure available, so the check that prevents
it should not be an implicit property of a prompt.

## Alternatives

- **Treat constraints as a subtype of `MemoryFact` and check them inside the
  orchestration prompt.** Cheapest to build, but the safety property would then
  depend on model behavior and would be untestable offline.
- **Check constraints inside the calendar adapter, at the point of execution.**
  Too late: by then the user has already been shown and has approved a plan that
  should never have been offered.
- **Use a single `blocking` flag instead of separate severity and confirmation.**
  Simpler, but it forces an unconfirmed allergy to be either silently enforced
  or silently ignored. Both are wrong.

## Decision

`Constraint` is a distinct domain entity carrying two independent properties:
`severity` (how damaging a violation is) and `source` (whether the user stated
the fact or the system inferred it). `validate_plan` checks every still-proposed
item against every active constraint using exact token and interval matching
only, with no model call in the path.

The two properties combine into three outcomes:

| Severity | Source | Outcome | Blocks approval |
| --- | --- | --- | --- |
| Hard | User stated | `VIOLATED` | Yes |
| Hard | Inferred | `REQUIRES_CLARIFICATION` | Yes |
| Soft | Either | `ADVISORY` | No |

`grant_approval` runs this validation itself and raises `PlanNotApprovableError`
on any blocking finding. Validation is therefore not a step a caller can forget:
no code path can obtain an approval for a plan that violates a hard constraint.

Items with a reported outcome are history and are not validated, so recording a
new allergy today does not retroactively invalidate what already happened.

## Consequences

The safety property is testable offline and deterministically, which the
constraint matrix in `tests/test_validation.py` does.

An inferred hard constraint blocks approval until the user resolves it. This is
deliberate friction: the alternative is choosing silently between enforcing and
ignoring something the user never confirmed.

Matching is exact on normalized tokens. It will not recognize that "satay"
implies peanut. Closing that gap requires a curated ingredient taxonomy, which
belongs to the evidence and memory work in Sprint 3; until then the domain
detects only what the item explicitly declares. This limitation is recorded in
the README rather than hidden behind a passing test suite.
