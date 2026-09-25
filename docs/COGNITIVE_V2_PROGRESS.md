# Cognitive V2 progress

Status: PARTIAL / EXPERIMENTAL. The bounded cognitive foundation is implemented; scientific utility and unattended operation are not established. Validation and publication results are recorded below when measured.

Starting branch: `feature/localai-qwen-recovery`, commit `6c7c3ba401a7d103acbad2df3e173f5db2234b1d`, clean local/remote equality and successful recovery CI. New branch: `feature/cognitive-machine-awareness-v2`. Parent branch `feature/cognitive-awareness-foundation` at `adefc700a54bff9dc486fefcacfd0014eba27da1` remains read-only.

The local checkpoint `cognitive-awareness-v2-20260925T214532Z` contains the full before inventory, model/runtime/source hashes, parent tracked-file hashes, original forecast hash, listeners and redacted process ownership. This checkpoint is intentionally ignored by Git.

## Measured validation

- ARX controlled process experiment: 8/8 checks passed. Owned Python PID 22408 appeared and disappeared; no unrelated process was stopped.
- Qwen 4B consumed only the structured experiment delta and identified both process transitions with valid references. All four interpretation checks passed. These are machine-operation observations, not sports accuracy measurements.
- Full CHILD suite: **694 passed**, comprising **681 portable + 13 local integration**, **0 failures/errors/skips**. There are **271 new V2 tests** above the recovery baseline. The guarded portable run reported zero attempted live dependency accesses. The 37 inherited donor deployment tests remain explicitly outside CHILD scope.
- Both Qwen models completed the same frozen state and identical projection (`7bbec6e4b974b797346dff1cb07aaf6fef2b07e1642f222a6a2dd77254cc12f1`). 4B inference was 25.091 seconds; 30B was 75.149 seconds. Both supplied two structured conclusions with valid reference membership. Membership does not prove semantic truth.
- An independent Codex artifact, produced without reading Qwen results, supplied seven conclusions, one falsifiable hypothesis and one research need. Codex also saw the full state; its wall time and richer context are not a controlled model-speed benchmark. Deterministic baseline abstained about change without a comparison snapshot.
- Reconciliation results for 4B/30B, 4B/Codex and 30B/Codex were DISAGREEMENT, INSUFFICIENT_EVIDENCE and DISAGREEMENT. No winner was invented. [Sanitized measurements](evidence/cognitive_v2_validation.json) preserve identities, parameters, memory use, hashes and limitations.
- Authenticated HTTP V2 cycle succeeded and produced an immutable receipt. Its status is PARTIAL when no separate Codex result accompanies that particular fresh snapshot; that is an honest handoff state, not failed Qwen inference.
- LocalAI preservation: 260,493 files, 27,531 directories and 53,339,414,121 bytes have identical metadata; all 71 critical SHA-256 checks match, including both models. Parent's 199 tracked files and Git state match. Original prediction file hash remains `6b75463280f886a878265ace675de776f5657ec4325a37b96a2f443181fdd66e`.
- Owner manual processes retained their executable identities and start times. Apache, MariaDB and SQL Server remained running; scheduled collector was Ready, last result 0. No Windows services were installed by this work; global service-installation delta is UNKNOWN because the starting checkpoint lacked a complete service inventory.
- Repository safety scan found no blocking secret/path/size findings after clearly synthetic test values were constructed without misleading credential literals. Protected database files remain outside Git and unreadable to the scanner while open; this is explicitly reported, not treated as source coverage.
- Live transport/cockpit boundaries: 12/12 checks passed, including authentication, Origin/Host rejection, unsupported action routes, invalid/oversized requests and cockpit sanitization. One earlier concurrent health probe timed out while inference occupied the serial gateway; retry after inference passed. The gateway intentionally serializes requests, so concurrent health responsiveness remains a limitation.

Machine-readable [architecture](evidence/cognitive_v2_architecture.json) and [capability registry](evidence/cognitive_v2_capabilities.json) are published. Full machine captures, model products, clocks and receipts stay in ignored local storage. Feature publication uses exact staged-index portable tests, staged link checks and remote workflow dispatch; the final local handoff records immutable commit and CI identities.

## Remaining gates

BLOCKED / UNKNOWN: lawful real odds, later outcome for the original frozen forecast, measured targeted-research benefit, complete player/lineup/injury evidence, exact kickoff timezone, cross-provider identity, multi-day prospective history, independent clean-machine reproduction, and historical publisher provenance of the preserved 4B model. None is resolved by successful local inference.

PARTIAL: on-demand machine probes and cycles; finite model projection with explicit omissions; typed categorical model interpretations; heuristic routing thresholds; semantic truth of arbitrary natural-language claims; sustained resource contention; external research execution and measured research value. Machine mutation remains disabled by design.

No dependencies, model downloads, Windows services, registry changes, firewall changes or parent code changes are required by this block. Original LocalAI files and prospective forecast remain immutable. Feature work will be pushed without merge.
