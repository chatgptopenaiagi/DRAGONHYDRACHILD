# Cognitive state contracts — V2

Status: COMPLETE foundation; scientific maturity remains EXPERIMENTAL. The implementation is [contracts.py](../src/dragonhydra/cognitive_v2/contracts.py). A contract proves structure and boundary checks, not the truth of an observation supplied by a trusted producer.

`CognitiveStateSnapshot` joins eight bounded domains without opening database, filesystem or source-content access to a model:

| Contract | Contents and authority |
| --- | --- |
| `WorldState` | As-of evidence references, source states, prediction/feature/simulation references; no raw articles or database connection. |
| `MachineState` | Independent ARX snapshot hash, explicit observation/availability/expiry clocks, bounded component summaries and health. |
| `ProjectState` | Project identity, branch, commit, clean/dirty state and original forecast hash. |
| `ModelState` | Model status, model/runtime hashes and forecast/disagreement references. |
| `MemoryState` | References into the five explicit memory layers. |
| `UncertaintyState` / `UncertaintyMap` | Unknown or supported bounded scores, provenance, resolution needs and freshness. |
| `CapabilityState` | Registered advisory proposal classes and policy requirements. |
| `CognitiveState` | Alias of the complete snapshot; no second conflicting representation. |

All contracts are frozen, keyword-only dataclasses with schema version `2`, strict `from_dict`, deterministic `to_dict` and SHA-256 `digest`. Unknown fields, incorrect primitive types, non-finite values, oversized collections, suspicious secret/path/instruction strings and unsupported states fail closed. Collections are limited to 128 members per field; whole contracts are limited to 256 KiB; short text is limited to 500 characters. Runtime model projection applies a smaller independent context budget.

`Metric` contains a named numeric value or null, unit and provenance. `StateLabel` holds a bounded categorical value. `ComponentState` combines labels, metrics, status and references. These are controlled projections of selected fields, not arbitrary configuration dictionaries. String scanning is defense in depth; the main safety boundary is the explicit projection and the absence of execution tools.

## Clocks and hashes

`observed_at` is when a producer observed a value. `available_at` is when it became available. `created_at` is artifact creation. `as_of_at` is the active temporal cursor. `expires_at` bounds use as present state. All clocks require UTC offsets; availability cannot precede observation. Future observations cannot enter a past world cursor. A FUTURE snapshot cannot contain observed world evidence.

The snapshot `state_hash` excludes its incidental ID and creation clock, and excludes machine/project capture clocks. It includes the temporal cursor, projected semantic state and ARX semantic hash. The full artifact `digest` includes all clocks. Thus a repeated capture can preserve semantic identity while retaining a new audit timestamp. Freshness is checked separately with `assert_fresh(now)` or `ensure_fresh(snapshot, now)`; an unchanged hash never renews expired data. Failed machine health fails closed.

## Advisory products

`CognitiveActorResult` identifies QWEN_4B, QWEN_30B, CODEX, SYSTEM, HUMAN, HYDRA or MEDUSA explicitly. Its conclusions, hypotheses, research needs and proposals remain advisory. A Qwen success requires model identity/hash, runtime identity/hash, input hash and output hash. Failed or blocked results cannot contain fabricated conclusions. Embedded proposals/hypotheses must bind to the same state and actor.

`Conclusion` has an explicit subject and position, short summary, references, assumptions, confidence and non-evidence epistemic state. It cannot be an OBSERVATION. `Hypothesis`, `ResearchNeed`, `ExpectedInformationValue`, `ActionProposal`, `ActionDecision`, `CognitiveReconciliation`, `LearningFeedback`, `SystemSelfModel` and `CognitiveCycleReceipt` retain the same separation. No contract has a hidden-reasoning or chain-of-thought field.

An actor's text cannot create a MEDUSA acceptance, machine probe receipt, source capture, outcome or validated evidence. Those require separate trusted acquisition/validation producers. Constructor validation does not substitute for those producers.

## Replay and failures

Cycle receipts retain snapshot, semantic state, machine snapshot, routing, actor result, reconciliation and memory hashes. Reconciliation compares actors on the same frozen state. Artifact replays retain original timestamps and do not claim to be a fresh observation.

Explicit failure codes include COGNITIVE_STATE_STALE, MACHINE_STATE_STALE, MACHINE_PROBE_FAILED, MODEL_UNAVAILABLE, MODEL_HASH_MISMATCH, RUNTIME_HASH_MISMATCH, QWEN_RESPONSE_INVALID, CODEX_RESPONSE_UNAVAILABLE, RECONCILIATION_INSUFFICIENT, REQUEST_TOO_LARGE, CAPABILITY_DENIED, STATE_CHANGED_SINCE_PROPOSAL, UNSUPPORTED_TASK, UNTRUSTED_CONTEXT, MEMORY_REFERENCE_MISSING, HYDRA_REQUIRED and MEDUSA_REQUIRED.

Portable behavioral checks are in [test_cognitive_v2_core.py](../tests/test_cognitive_v2_core.py). See [memory](COGNITIVE_MEMORY.md), [hypotheses and research](HYPOTHESIS_RESEARCH_ENGINE.md) and [uncertainty](UNCERTAINTY_MAP.md).
