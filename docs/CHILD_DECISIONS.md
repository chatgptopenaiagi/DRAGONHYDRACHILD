# CHILD decision log

All entries dated 2026-09-24. Donor decisions remain historical truth.

| Decision | Reason and alternative | Evidence / trade-offs | Status |
| --- | --- | --- | --- |
| Independent private history; donor read-only | Owner isolates experiment; parent branch modification prohibited. | 179 authored hashes/Git state checked; deliberate duplicate maintenance. | COMPLETE |
| Separate SQL/Maria databases and four identities | Shared donor writes would violate isolation. | Seven denials; donor SQL access 0. Existing services reused, fresh-machine bootstrap unproved. | COMPLETE |
| Preserve roadmap; override cadence only | Attempt V0–V10 without falsifying gates. | Four laws unchanged; advanced code remains experimental. | COMPLETE |
| Actual-time versioned alias registry | Provider lacks numeric team IDs; names can change. | 20 UUIDs preserved; ambiguity unresolved; source-scoped declarations are not global team verification. | COMPLETE |
| Archive exact source/config for later calculations | Hash alone cannot recreate uncommitted code. | Retention test passes; first forecast remains limited and unchanged. | COMPLETE |
| CPU default; GPU measured | Small batches lose to overhead. | Largest measured batch 8.37× speedup; no predictive gain inferred. | COMPLETE |
| Bounded JSONL export; no new engine | Current workload does not justify analytical infrastructure. | SQL-as-of export tested; 2,000-row ceiling requires future scale gate. | COMPLETE |
| Keep real odds blocked | Terms/auth boundaries override completion pressure. | Tested arithmetic, no fabricated market records. | BLOCKED |
| One limited interactive daily task | Start capture clock without new daemon/stored password. | Commissioning/full cycle succeeds; owner must be signed in; duration gate remains. | PARTIAL |
| No release at closure | Important gates remain unproved. | Coherent tested commits; no production/version-completion claim. | COMPLETE |

See the [final report](FINAL_DRAGONHYDRACHILD_REPORT.md) and [component removal/measurement register](CHILD_ARCHITECTURE_SCORECARD.md).
