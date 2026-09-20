# Product Scope

## Purpose

Build a public engineering portfolio demonstrating a reliable consumer AI assistant. Monetization is not a phase-one goal. The long-term product is a single entry point for personal health questions, records, planning, and authorized actions; response depth depends on evidence, risk, and available integrations.

## Initial audience

Adults seeking everyday exercise, nutrition, sleep, and routine support. Include both experienced exercisers and people starting with walking or other ordinary activity. Do not assume weight loss is the user's goal. Specialized pregnancy, rehabilitation, and complex chronic-condition interventions require separately reviewed modules.

## Phase-one requirements

| ID | Capability | Acceptance criteria |
| --- | --- | --- |
| P01 | Account and onboarding | Users can start with minimal information; identity, units, and time zone are explicit; accounts are isolated. |
| P02 | Conversation | Streaming responses, history, cancellation, and partial-plan edits preserve unrelated constraints. Repository and initial UI language are English; multilingual behavior is a later evaluated extension. |
| P03 | Personal memory | Users inspect, correct, and delete facts; distinguish confirmed facts, temporary observations, goals, and unconfirmed inferences; preserve source and timestamps. |
| P04 | Evidence | Health factual claims are supported by relevant retrievable passages; missing or conflicting evidence is reported; citations are not invented. |
| P05 | Exercise | Plans specify activity, duration or sets, intensity guidance, alternatives, and recovery; account for experience, equipment, time, and relevant limitations. |
| P06 | Nutrition | Suggestions respect confirmed allergies, preferences, budget, and cooking access; calorie counting is optional; estimates disclose assumptions. |
| P07 | Sleep and routines | Plans support overnight schedules, weekday differences, and manual sleep or energy records without claiming to diagnose sleep disorders. |
| P08 | Integrated planning | Weekly plans have immutable versions; edits preserve completed history; conflicting constraints trigger clarification rather than silent relaxation. |
| P09 | Calendar | Read authorized availability, preview changes, obtain confirmation, create/update/cancel owned events, and reconcile uncertain outcomes without duplicate writes. |
| P10 | Reflection | Separate proposed activities from reported completion; missing records remain unknown; weekly summaries explain proposed adjustments. |
| P11 | User control | Provide data export, deletion, memory controls, connection revocation, and notification preferences with documented retention behavior. |

## Interface

Responsive web application with Assistant, Today, Plan, Records, and Settings surfaces. Use conversation for intent, cards for comparison and confirmation, and structured views for plans, memory, and execution status. Never require users to infer operation success from generated prose.

## First end-to-end scenario

1. A synthetic user supplies availability, dietary restrictions, and an exercise goal.
2. The assistant asks only necessary follow-up questions and proposes a weekly plan.
3. The user changes one activity; other constraints remain intact.
4. The user approves explicit calendar changes.
5. A provider timeout is reconciled before any retry.
6. The user reports a missed session and a temporary scheduling change.
7. A revised plan preserves history and updates only confirmed affected events.

## Health boundaries

Common symptom questions may receive general information and help-seeking guidance with necessary clarification. Never assume a symptom is minor. Urgent situations take precedence over ordinary planning. Medication changes, definitive diagnosis, and individualized treatment are outside phase one. Specialist review is required before claiming clinically validated behavior.

## Exclusions from phase one

Native mobile apps, voice, wearable sync, system alarms, camera-based exercise analysis, precise nutrition estimation from photos, medical-record ingestion, clinical scheduling, payments, autonomous outreach, and clinician-facing workflows.

## Long-term scope

| Phase | Extension | Entry conditions |
| --- | --- | --- |
| 2 | Mobile, voice, opt-in reminders, platform alarms, activity and sleep data | Platform feasibility, granular consent, source reconciliation, and revocation tests |
| 3 | Health documents, symptom timelines, medication lists, existing-instruction reminders, visit summaries | Extraction verification, original units/ranges, correction flows, and reviewed information boundaries |
| 4 | Specialized chronic-condition, rehabilitation, women's health, older-adult, and emotional-support modules | Independent applicability criteria, qualified review, domain evaluations, and escalation design |
| 5 | Appointment services, professional collaboration, delegated caregiver access | Provider agreements, explicit permissions, audit trails, and recovery/cancellation contracts |

Future coverage includes movement, nutrition, sleep, body trends, stress, symptoms, medications, preventive care, reports, and health services. Broad question coverage does not imply autonomous clinical authority. No later-phase feature is promised until its integration and validation requirements are satisfied.

## External dependencies

Phase one requires no paid health-data API. Start with curated, permitted health information and manual records. Calendar execution requires a user-authorized provider account. Model usage and hosting are separate operating costs. Do not scrape restricted sources or assume access to medical systems.
