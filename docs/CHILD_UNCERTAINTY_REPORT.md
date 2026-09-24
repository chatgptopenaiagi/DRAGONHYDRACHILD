# CHILD uncertainty and research report

State: **PARTIAL / EXPERIMENTAL**. A bounded research-request contract, sensitivity ranking and controlled validation/recalculation loop exist. There is no demonstrated real-world reduction in forecasting error or autonomous research system.

[uncertainty.py](../src/dragonhydra/child/uncertainty.py) records the fixture/entity/question, missing field, allowed sources, policy version, deadline, cost, expected latency and explicit conditional scenarios. Ranking reports hypothetical entropy change and maximum total-variation sensitivity. Sources must be approved, within the cost allowance and plausibly usable before the deadline. The priority score is a declared heuristic; it is not a learned or causally validated value-of-information estimate.

The controlled loop performs exactly one approved-source fetch, deterministic validation and recalculation through explicit callbacks. It records unavailable/blocked/deadline/rejection/quarantine states, enforces strict availability and source/field matching, and preserves evidence identity/hash. Policy checks precede fetching. An uncertain source is never approval to acquire data. There is no background worker or rate-limit evasion.

## Controlled experiment

The executable test uses an explicitly **synthetic** goalkeeper availability question. Its declared conditional model changes HOME/DRAW/AWAY from `(0.50, 0.25, 0.25)` to `(0.70, 0.20, 0.10)` after a synthetic answer passes validation. Entropy uses natural logarithms.

| Measurement | Before | After |
| --- | ---: | ---: |
| Predictive entropy, nats | 1.039720771 | 0.801818553 |
| Required-field completeness | 1 / 2 | 2 / 2 |

Entropy decreases by 0.237902218 nats in this declared scenario. That is a calculation under an assumed model, **not evidence that discovering a real lineup improves calibration, error or profit**. The output retains `synthetic=true`, `real_world_benefit_proven=false` and the controlled-experiment label. Another test increases entropy and verifies that the negative reduction remains visible. Lower entropy alone can mean unjustified confidence; later outcomes and proper scoring are required.

[Tests](../tests/test_child_intelligence.py) also prove blocked policy prevents fetching, failed validation prevents recalculation, future answers are rejected and deadlines/costs affect ranking. The shared intelligence suite has 25 passing tests under Python 3.14.

## Logical HYDRA capabilities

[registry.py](../src/dragonhydra/child/registry.py) defines thirteen logical capabilities: MATCH, PLAYER, TEAM, INJURY, LINEUP, COACH, WEATHER, TRAVEL, TACTICAL, NEWS, ODDS, MARKET and HISTORICAL. Every entry retains scope, data classes, source allowlist, contract version, bounded rate, failure policy, optional measured reliability, last observation, last failure and test evidence.

Maturity and operational status are separate. Defaults are CONCEPT / NOT_STARTED with unknown reliability, except PLAYER is SOURCE_UNAVAILABLE with `PLAYER_IDENTITY_DEFERRED_NO_APPROVED_SOURCE`. Player identity is blocked pending lawful evidence, not invented. ACTIVE requires an allowlisted source; VALIDATED/STABLE requires test evidence. Registering a head does not make its external acquisition operational. All heads share a future acquisition architecture; this module starts no process and creates no autonomous agents.

NEXT_EXACT_ACTION: run one permitted real information-gap experiment with frozen before/after predictions, validated evidence and subsequent proper-score evaluation. Preserve a negative result if research makes the forecast worse.
