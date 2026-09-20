# 0006. Which invariants are repeated below the domain

Status: Accepted (Sprint 2, task S2-07)

## Context

The Sprint 1 retrospective recorded that the defects which shipped lived between
entry points rather than inside them, and that a test suite mirroring the shape
of the code never crosses that boundary. Task S2-07 acts on it: probes that try
to reach a protected state by a route nobody designed.

Writing those probes raises a question the domain alone cannot answer. The
domain enforces the operation lifecycle, ownership, and approval rules, but the
domain is not the only thing that can write to the database. A repository, a
migration, a future admin script, or an object built with `dataclasses.replace`
can all put a row in place that no domain function would have produced.

## Alternatives

- **Enforce only in the domain.** One source of truth, no drift. It also means
  every guarantee rests on every writer going through the domain, forever, and a
  single adapter that forgets is enough to undo it silently.
- **Enforce only in the schema.** Impossible for most of it: the schema cannot
  express that an approval's fingerprint matches a plan's content, and its
  errors say nothing a user could act on.
- **Mirror every domain rule in constraints.** Maximum defense and maximum
  drift. Every rule would then have two definitions that must be changed
  together, and the second one is the one people forget.

## Decision

A rule is repeated below the domain only when it is structural, cheap to state
in SQL, and damaging if violated. That currently means:

- **Referential ownership.** `approvals` and `tool_operations` reference a plan
  version together with its owner, against a unique key on
  `(plan_id, version, owner_id)`. A row cannot claim a plan version belonging to
  somebody else, whatever code inserted it.
- **Approval before execution.** An operation in any state past confirmation,
  except cancellation, must carry an `approval_id`.
- **Plan ancestry.** A version's parent must exist and be the version
  immediately before it ([ADR 0002](0002-first-class-constraints.md) covers the
  related constraint work; the foreign key is in the initial migration).
- **Shape rules** that would otherwise admit nonsense: a lease is complete or
  absent, a constraint carries a token or a window but not both.

Everything else stays in the domain, including anything requiring a fingerprint
comparison, an expiry decision, or a message a person will read.

The repository additionally checks the state machine when advancing an
operation. It is the one place an object built outside the domain functions can
enter storage, and `ALLOWED_TRANSITIONS` is already data, so the check reuses
the domain's own table rather than restating it.

## Consequences

The duplication is deliberate and bounded, and the probes in
`tests/integration/test_adversarial_paths.py` are what keep it honest: each one
asserts the specific constraint the server named, so a probe cannot pass because
some unrelated rule happened to fire.

Adding a state to the operation lifecycle now means updating the approval check
in a migration as well as the domain. That is the cost, and it is the reason the
list above is short rather than exhaustive.

A constraint violation surfaces as an `IntegrityError`, which is not a message
for a user. That is acceptable because these paths are ones the application
should never take; if one becomes reachable through normal use, the rule belongs
in the domain where it can be explained.
