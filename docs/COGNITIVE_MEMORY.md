# Explicit cognitive memory

Status: COMPLETE bounded local foundation. [memory.py](../src/dragonhydra/cognitive_v2/memory.py) implements five layers. They are provenance-bearing records, not an unrestricted historical-file search interface.

| Layer | Purpose | Temporal treatment |
| --- | --- | --- |
| `WorkingMemory` | Current task/session context. | Expiry mandatory; expired records remain auditable but cannot be returned as active. |
| `EpisodeMemory` | Important bounded completed cycles. | Durable until explicit supersession; no in-place update. |
| `DecisionMemory` | Accepted/rejected architectural or policy decisions. | Provenance and reason codes preserved. |
| `LearningMemory` | A measurable later observation compared with an earlier expectation. | Requires the matching typed `LearningFeedback`; changed prose is insufficient. |
| `KnownLimitationMemory` | Unresolved uncertainty, blockers and scientific limitations. | Explicit supersession when later evidence changes the limitation. |

Every item records ID, creation time, source references, input hashes, reason codes, epistemic state, confidence and a short summary. Expiry and supersession are explicit. Source references must already be in the bounded producer-supplied reference set when appended. Missing references fail with MEMORY_REFERENCE_MISSING.

`MemoryStore` writes immutable JSON records using exclusive creation. Each record contains a sequence number, previous-record hash, typed item and record hash. Loading verifies file identity, sequence, hash chain, schema and unique memory IDs. Existing IDs cannot be overwritten. A superseding item must reference an existing item of the same kind. Superseded and expired records are retained and omitted from active lookup.

The default store limit is 2,048 records and 16 MiB; each record is at most 32 KiB. Capacity exhaustion stops writes with REQUEST_TOO_LARGE. There is no automatic deletion of decisions or learning receipts. Rotation/archive is an explicit engineering operation; this first version deliberately does not prune important history to make room. Model requests cannot choose the store's path.

The store is confined to the installed CHILD repository's `runtime/cognitive-v2` directory. Traversal, outside targets, symlinks and Windows junction ancestors are rejected; no runtime caller can override this boundary. Parent and historical LocalAI paths are therefore unavailable as memory destinations.

Hash chains detect accidental or partial tampering; they are not signatures against a privileged attacker capable of rewriting the entire store. Writers are serialized by an exclusive process-visible lock. A concurrent writer fails with AUDIT_FAILURE; a crash-left lock requires explicit engineering inspection and is never automatically stolen. There is no distributed consensus, encrypted storage or remote backup in this foundation. An external cycle receipt anchors a retained memory-record hash; an isolated chain cannot by itself prove that its final records were not removed.

## Learning from difference

`LearningFeedback` requires an earlier expectation hash, a strictly later observation hash, observation and availability clocks, source references, expected/observed/difference summaries, contributor and next test. Machine observations require ARX; world observations and outcomes require MEDUSA. These actor labels describe the trusted producer contract; caller-supplied labels alone do not manufacture valid evidence.

A claimed prediction accuracy gain additionally requires a referenced observed outcome, prior and later scores, a supported scoring method and a checked score difference. The controlled process experiment may demonstrate a measured machine expectation; it cannot demonstrate forecast accuracy or sports research benefit.

Learning memory retains the feedback hash and requires the matching feedback object at append. The original forecast, hypothesis and observation remain separate immutable artifacts. No model weight update, source reliability update or code change is performed automatically.

See [state contracts](COGNITIVE_STATE_CONTRACTS.md) and [uncertainty](UNCERTAINTY_MAP.md).
