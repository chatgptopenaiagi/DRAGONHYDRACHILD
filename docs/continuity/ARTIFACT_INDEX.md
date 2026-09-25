# Important artifact index

This is a selected map, not a recursive machine or repository inventory. [Machine-readable entries](manifests/important-artifacts.json) record classification, purpose, priority and publication boundary.

| Category | Artifacts | Purpose |
| --- | --- | --- |
| AUTHORITATIVE | [Working rules](../../AGENTS.md), [mission](../CHILD_MISSION.md), [master roadmap](../DRAGONHYDRA_MASTER_ROADMAP.md), [decisions](../CHILD_DECISIONS.md) | Scope, laws and recorded decisions |
| AUTHORITATIVE | [V2 architecture](../COGNITIVE_AWARENESS_V2.md), [security](../COGNITIVE_SECURITY_MODEL.md), [LocalAI harvest](../LOCALAI_GENETIC_HARVEST.md) | Current architecture and preserved ancestor |
| AUTHORITATIVE | [Next action](NEXT_ACTION.md), [resume manifest](manifests/resume-manifest.json) | Conservative continuation contract |
| EVIDENCE | [V2 measurements](../evidence/cognitive_v2_validation.json), [recovery replay](../evidence/localai_replay_summary.json), [CHILD summary](../evidence/child-validation-summary.json) | Sanitized measured claims |
| DERIVED | [V2 architecture map](../evidence/cognitive_v2_architecture.json), [capability map](../evidence/cognitive_v2_capabilities.json) | Reviewable implementation projections |
| SOURCE | [Cognitive package](../../src/dragonhydra/cognitive_v2/__init__.py), [ARX package](../../src/dragonhydra/machine/__init__.py), [LocalAI package](../../src/dragonhydra/localai/__init__.py) | Implemented contracts and boundaries |
| PRIVATE_LOCAL / EVIDENCE | `runtime/checkpoints/cognitive-awareness-v2-20260925T214532Z/` | Full final handoff, test logs, preservation receipts and baseline inventories |
| PRIVATE_LOCAL / RUNTIME | `runtime/cognitive-v2/` and `runtime/localai/` | Snapshots, actor results, memory, receipts and operational state; secret-bearing files excluded from capsules |
| PRIVATE_LOCAL / EVIDENCE | `runtime/child/predictions/00000001.json` | Original immutable forecast; never rewritten |
| PRIVATE_LOCAL / CHECKPOINT | `runtime/continuity/capsules/` | Small immutable continuity capsules with references, not backups of models/databases |
| PRIVATE_LOCAL / EXTERNAL_DEPENDENCY | Preserved LocalAI tree and both GGUF files | Known paths/metadata only in capsule; no copying or rehashing for this mission |
| EPHEMERAL | Current PIDs, current resource readings and displayed snapshot age | Reobserve before reliance |
| DEPRECATED | No component newly designated deprecated by this mission | Historical source is retained; deferral is not deletion |

For exact files created/modified by V2, use `git show --name-status 8cfde5e7ca903cf187f646b6d43a3af283965e86` or the local final handoff's `files` field. That record contains 42 additions and six modifications. Do not substitute a broad directory copy for this provenance.
