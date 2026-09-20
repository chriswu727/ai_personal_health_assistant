# Evaluation Strategy

Status: specification only. No evaluation results have been produced.

## Suites

| Suite | Evidence required |
| --- | --- |
| Conversation | Correct intent, necessary clarification, multi-turn edits, and cancellation |
| Memory | Provenance, correction, expiration, deletion, contradictory facts, and owner isolation |
| Planning | Hard-constraint adherence, realistic availability, overnight schedules, DST, and partial edits |
| Health information | Source support, uncertainty, scope boundaries, and appropriate help-seeking responses |
| Tool execution | Exact approval scope, provider-result verification, deduplication, update, and cancellation |
| Recovery | Worker interruption, lost provider responses, expired leases, rate limits, and revoked credentials |
| Privacy | Cross-user access attempts, sensitive log leakage, deletion propagation, and malicious retrieved content |
| Performance | Queue delay, response latency, completion latency, throughput, errors, and cost under a specified load |

Use synthetic users and clearly marked provider test accounts. Separate development fixtures from held-out evaluations. An LLM judge is supplementary evidence, not the sole authority for safety or external execution correctness. Obtain qualified review before making clinical-validity claims.

## Reporting contract

Every published run records commit, environment, dataset version, provider/model version, configuration, repetition count, denominator, failures, and limitations. Report success, false completion, constraint violations, and cost separately. Include variability for nondeterministic runs. Retain redacted machine-readable results and reproduction instructions.

Fault injection and load tests can use deterministic provider substitutes, but report those results separately from live-provider measurements. Do not represent simulated throughput as production capacity. Define workload, concurrency, latency percentiles, and provider limits before setting service objectives.

## Release evidence

- One complete synthetic-user journey with verified calendar results.
- An ambiguous-write recovery example without duplicate events.
- A memory correction and deletion example across sessions.
- A held-out evaluation report including failed cases.
- A bounded load experiment explaining the observed bottleneck.
- A documented limitations and data-retention review.

Discovered critical ownership, unauthorized-write, false-completion, or health-boundary failures block a showcase release until resolved and covered by regression checks. Passing a finite evaluation does not establish universal correctness.
