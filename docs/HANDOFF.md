# Development Handoff

This file provides session context; [SPRINTS.md](SPRINTS.md) remains the source of truth for delivery status. Update this file when a work session changes repository behavior, governance, or verification state. Keep context concise and never include credentials or personal health data.

## Current state

- Canonical repository: `chriswu727/ai_personal_health_assistant`.
- Sprint 0 foundation: Done.
- Sprint 1: Planned; no application implementation has started.
- Runtime, dependencies, and local application checks: not yet configured. Hosted CI is intentionally excluded at the maintainer's request to conserve quota.
- Current work: maintainer-requested governance follow-up to Sprint 0, not an application sprint.

## Latest change

Updated the AI agreement, contributor standards, and Sprint 1 task S1-06 to require reproducible local verification instead of hosted CI. Do not add, enable, or trigger hosted workflows unless the maintainer explicitly changes this policy. Existing Claude, GitHub Copilot, and Cursor entry points inherit the canonical agreement. No application functionality was introduced.

## Verification

- `git diff --check`: passed.
- PowerShell validation of 14 Markdown/instruction files: local Markdown targets exist and no CJK prose was found; passed. This is a limited language check, not a general language detector.
- Manual review: tool entry points reference one canonical agreement; Sprint 1 remains Planned; no product capabilities are marked implemented.

No application tests can run at this stage. Tool-specific entry points are instruction files; they are not proof that every AI client loads or obeys them. Local executable quality gates remain Sprint 1 task S1-06. These results describe documentation checks, not application correctness.

## Next action

When Sprint 1 implementation is authorized, read the required documents, mark Sprint 1 and S1-01 In Progress, and implement S1-01: choose a supported Python runtime and strict type checker, establish a locked package setup, and document reproducible verification commands. Keep the domain slice offline and independent of model providers, databases, and UI frameworks.

## Blockers and limitations

No blocker is known for planning the first code slice. There is no runnable app, live calendar integration, evaluation result, or production-readiness claim. Do not mark Sprint 1 tasks complete until their individual acceptance criteria pass.
