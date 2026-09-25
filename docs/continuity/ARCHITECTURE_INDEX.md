# Architecture index

These references are authoritative for the preserved V2 foundation. Validation shorthand **V2** means [V2 progress](../COGNITIVE_V2_PROGRESS.md) and [sanitized measurements](../evidence/cognitive_v2_validation.json); **CHILD** means [CHILD final report](../FINAL_DRAGONHYDRACHILD_REPORT.md). A contract's implementation does not close an external scientific gate.

| Concept | Authority | Status / description | Dependencies | Validation |
| --- | --- | --- | --- | --- |
| World, HYDRA, MEDUSA and evidence | [Master roadmap](../DRAGONHYDRA_MASTER_ROADMAP.md), [CHILD matrix](../CHILD_V0_V10_COMPLETION_MATRIX.md) | PARTIAL; lawful observation, validation, provenance and temporal distinctions | Source policies, controlled storage | CHILD |
| Cognitive state | [Contracts](../COGNITIVE_STATE_CONTRACTS.md), [snapshot builder](../../src/dragonhydra/cognitive_v2/snapshot.py) | COMPLETE scoped foundation; bounded world/machine projection | Validated CHILD inputs, ARX | V2 |
| ARX / machine state | [ARX](../ARX_MACHINE_STATE_FABRIC.md), [probes](../../src/dragonhydra/machine/probes.py) | COMPLETE scoped read-only snapshots/deltas/events | Fixed probes, clocks, receipts | V2; ARX 8/8 |
| Memory | [Memory](../COGNITIVE_MEMORY.md), [store](../../src/dragonhydra/cognitive_v2/memory.py) | COMPLETE five-layer contract | References, hash chains, retention bounds | V2 |
| Uncertainty | [Map](../UNCERTAINTY_MAP.md) | COMPLETE explicit UNKNOWN representation; scientific resolution PARTIAL | Evidence and measurable disagreement | V2 |
| Self-model | [V2 architecture](../COGNITIVE_AWARENESS_V2.md), [snapshot builder](../../src/dragonhydra/cognitive_v2/snapshot.py) | COMPLETE bounded operational description | Current components/capabilities | V2 |
| Model routing | [Routing](../QWEN_ROUTING.md), [router](../../src/dragonhydra/cognitive_v2/router.py) | COMPLETE advisory 4B/30B selection; thresholds heuristic | Task, bounded resource state | V2 |
| Codex / reconciliation | [Reconciliation](../QWEN_CODEX_RECONCILIATION.md), [implementation](../../src/dragonhydra/cognitive_v2/reconciliation.py) | COMPLETE explicit actors and preserved disagreement | Identical state binding, references | V2 frozen comparison |
| Hypotheses / research | [Research engine](../HYPOTHESIS_RESEARCH_ENGINE.md) | COMPLETE contracts; measured research gain BLOCKED | HYDRA, MEDUSA, later evidence | V2 |
| Learning feedback | [Contracts](../COGNITIVE_STATE_CONTRACTS.md), [memory](../COGNITIVE_MEMORY.md) | COMPLETE later-observation contract; no predictive gain claimed | Original expectations, later observed evidence | V2 ARX comparison |
| Capability / security | [Security](../COGNITIVE_SECURITY_MODEL.md), [registry](../evidence/cognitive_v2_capabilities.json) | PARTIAL OS isolation; proposal-only authority implemented | Freshness, schemas, authentication | V2 boundary 12/12 |
| LocalAI | [Recovery audit](../LOCALAI_RECOVERY_AUDIT.md), [runtime](../LOCALAI_QWEN_RUNTIME.md), [operations](../LOCALAI_DRAGONHYDRA_INTEGRATION.md) | COMPLETE bounded inference; historical restoration PARTIAL | Preserved GGUF/runtime, restricted launcher | Recovery 19/19; V2 |
| Dashboard / cockpit | [Cockpit](../COGNITIVE_COCKPIT.md) | COMPLETE read-only presentation; observations become stale | Fixed sanitized artifact, XAMPP | V2 |
| Historical ancestor | [Harvest](../LOCALAI_GENETIC_HARVEST.md), [archaeology](../LOCALAI_ARCHAEOLOGY.md) | Reviewed reuse/adapt/defer register; originals retained | Surviving source and audit records | V2 source review |
| Preservation | [Continuity overview](README.md), [resume protocol](RESUME_PROTOCOL.md), [security](SECURITY_BOUNDARY.md) | Bounded continuity foundation; no automatic restore | GitHub indexes, local immutable capsule | Current preservation handoff |
