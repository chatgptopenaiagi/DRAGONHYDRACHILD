# LocalAI inheritance for future ARX

Date: 2026-09-25. Scope: preserve the useful architectural inheritance of `C:\LocalAI` while restoring only bounded analysis in CHILD. This is a design assessment, not authorization to enable runtime machine actions or modify parent DRAGONHYDRA. [Security boundaries](LOCALAI_SECURITY_BOUNDARIES.md) distinguish source observations from current runtime proof; [the recovery audit](LOCALAI_RECOVERY_AUDIT.md) records actual restoration results.

## What the surviving system teaches

**OBSERVED:** LocalAI separated observation, reasoning, deterministic routing, action policy, authorization, fixed-profile execution, verification, recovery and audit. The architecture text states this in `C:\LocalAI\Productization\Docs\Architecture\ARCHITECTURE.md:25,45`; the implementation evidence below corroborates substantial parts of it.

**STRONGLY_INFERRED:** the owner's "AI tunnel" describes a restricted task/context and authority pipeline. MCP submitted bounded questions through a durable job queue; Qwen planned from supplied evidence; a deterministic governor selected routes; Sentinel reviewed; Codex received an explicit evidence/preanalysis packet; action executors were separate. **UNKNOWN:** a mechanism exposing only a physical portion of a neural model. Task restriction and model architecture must not be conflated.

The future ARX live machine state fabric can inherit reconstructable observations and capability receipts. DRAGONHYDRA can consume sanitized project state without receiving machine authority. These are different scopes, joined through explicit versioned artifacts. Neither model beliefs nor old service PASS records become present observations.

## Concept disposition register

Paths below are relative to the preserved `C:\LocalAI` tree. These decisions concern concepts and future implementation; they do not remove or alter any historical asset.

| Concept | Decision | Evidence | Future treatment |
| --- | --- | --- | --- |
| Observation/action separation | REUSE | `Productization\Docs\Architecture\ARCHITECTURE.md:5,25,45` | Keep intelligence independent of authority; machine observation cannot silently imply action permission |
| Deny-by-default action capability classes | REUSE | `Phase9\LocalAI.PolicyEngine.Common.ps1:52-83,125-218` | Preserve explicit READ_ONLY, SAFE_WRITE, PRIVILEGED, NETWORK, DESTRUCTIVE and RELEASE distinctions; present recovery permits analysis only |
| Qwen bounded planner | ADAPT | `Tools\Invoke-LocalAIEngineeringPlanner.ps1:296-323` | Use closed typed cognitive requests and non-evidence responses; no direct executor access |
| Deterministic route governor | ADAPT | `Tools\Resolve-LocalAIRoute.ps1:16-38`; `Tools\Invoke-LocalAIEngineeringPlanner.ps1:471-516` | Preserve model suggestion versus actual policy decision; replace loose task-keyword routing where stronger typed tasks exist |
| Sentinel independent critique | ADAPT | `Tools\Invoke-LocalAIEngineeringPlanner.ps1:527-574` | Retain optional critique and disagreement; never treat another model as the deterministic security boundary |
| Compact Codex context packet | ADAPT | `Tools\Get-LocalAICodexContext.ps1:62-137` | Project sanitized measured state and separate model preanalysis; retain temporal cursor, provenance and missing fields |
| Explicit Codex invocation/handoff | ADAPT | `Tools\Invoke-LocalAICodex.ps1:85-98,129-160` | Preserve read-only default and discrete arguments; use supported explicit artifacts, no private IPC or automatic recursive engineering |
| Durable request/job/receipt ledger | ADAPT | `MCP\bridge\Invoke-LocalAIMcpBridge.ps1:164-205` | Preserve auditable lifecycle and failures without requiring old SQL Server schema for inference |
| Snapshot-bound approval, expiry and one-use consumption | REUSE | `Tools\Request-LocalAIActionApproval.ps1:85-250`; `Tools\Consume-LocalAIActionApproval.ps1:38-42,142-148,183-190,321` | Preserve semantics for any future action; independently authenticate authority and atomically claim execution |
| SQL-specific action machinery | REIMPLEMENT | `Phase9\LocalAI.Action.Common.ps1:4-20`; `Tools\Evaluate-LocalAIAction.ps1:54-90` | Reimplement only when an action requirement exists; do not reinstall old SQL identities merely for inference |
| Broad read-only filesystem executor | REIMPLEMENT | `Phase9\LocalAI.ReadOnlyExecutor.Common.ps1:24-60`; `Tools\Invoke-LocalAIReadOnlyAction.ps1:110-120,180-207` | Replace raw reads/log tails with approved state projections, confidential-field exclusion and stricter path confinement |
| Sandbox writes with stale-state checks and rollback | ADAPT; execution DEFER | `Tools\Invoke-LocalAISandboxWriteAction.ps1:75-84,110-157,178-201`; `Phase9\LocalAI.SandboxWrite.Common.ps1:117-145` | Preserve before/after hashes, tracked-file constraints, narrow roots, rollback evidence and reparse checks; review races and authorization before reuse |
| Manual rollback refusing changed targets | ADAPT; execution DEFER | `Tools\Undo-LocalAISandboxWriteAction.ps1:43-74` | Preserve refusal of ambiguous rollback and post-restore verification; independently revalidate identity and paths |
| Fixed test/build profiles | ADAPT; execution DEFER | `Tools\Invoke-LocalAIControlledTestAction.ps1:7-10,27-48`; `Tools\Invoke-LocalAIControlledBuildAction.ps1:7-14,25-41` | Keep pinned task profiles, strict arguments, timeout/output limits; fix pre-claim restore and explicit offline policy |
| Narrow service recovery broker | DEFER | `Build\Phase10B-PrivilegedBroker-R2-20260831-130508\Program.cs:12-25,323-365,515-607` | Useful least-privilege ancestor, unnecessary for asking Qwen questions; preserve source/binary and keep inactive |
| Fresh-state recovery without authority expansion | REUSE | `Phase10\LocalAI.PrivilegedRecovery.Common.ps1:32-37,46-80`; `Phase13\LocalAI.RecoveryManager.Common.ps1:4-10` | Reconstruct actual state after failure; preserve failed receipts; require fresh authorization; stop outside capability scope |
| Golden baselines, hashes and verification receipts | REUSE | `GoldenBaselines\Phase8-Golden-20260830-115838\README-GOLDEN-BASELINE.txt:3-21`; `Productization\Docs\Security\THREAT-MODEL.md:13-20,28-32` | Preserve evidence and compare drift; checksums identify content but do not prove publisher authenticity or current correctness |
| Local read-only dashboard | ADAPT | `Productization\Docs\Architecture\ARCHITECTURE.md:45`; `Productization\Docs\Security\THREAT-MODEL.md:18` | Expose operational summaries with no control authority; keep CHILD/XAMPP separate from model process |
| Historical service installation and product installer | DEFER | `Productization\PRODUCTIZATION-FINAL-REPORT.md:23-29,38-42` | Clean-machine service/SQL/ACL integration was historically unproven; minimal inference does not require restoring it |
| LocalSystem inference identity | REJECT for restored deployment | `GoldenBaselines\Golden-Baseline-2-20260831-142925\GOLDEN-BASELINE-2-MANIFEST.json:136-143` | Replaced by a restricted current-user token with Medium integrity and administrator SIDs deny-only; this reduces privilege but is not a full OS sandbox |
| Arbitrary model-selected machine execution | REJECT as a new capability | `Productization\Docs\Architecture\ARCHITECTURE.md:25,45`; `Phase9\LocalAI.PolicyEngine.Common.ps1:52-69` | It conflicts with the recovered separation law; do not introduce it while recreating a tunnel |

## Rejection and loss accounting

Complexity alone is not a reason to reject the old system. Deferred components remain valuable engineering evidence. No deletion is proposed.

| Rejected deployment/capability | Evidence | Capability loss | Risk avoided | Replacement | Reversibility |
| --- | --- | --- | --- | --- | --- |
| Qwen runtime inheriting LocalSystem authority | Historical baseline manifest at lines 136-143 records that identity | Automatic privileged service hosting is not restored; local inference itself needs no such privilege | A runtime/model-server compromise would otherwise inherit broad Windows authority | Verified restricted current-user token, private desktop, one-process job and bounded analysis interface; ordinary user filesystem/network access remains a limitation | Original source, binary, config and receipt remain preserved; a future reviewed service design is possible without destroying this recovery |
| Arbitrary model-selected shell, SQL-admin, filesystem or service-control operation | Historical architecture separates fixed profiles and authority, and policy defaults to DENY; this is rejection of a proposed expansion, not a claim the mature old system exposed it | No autonomous arbitrary machine administration; no loss of bounded Qwen analysis | Prompt injection or mistaken model output gaining direct execution authority | Typed analysis and proposal artifacts; any future action uses a separate deterministic capability, authorization, executor and verifier | Capability register can be extended by a later reviewed requirement; historical files and policies remain unchanged |

## A measured future loop

The useful inheritance is `observe -> reconstruct state -> sanitize -> analyze -> propose -> decide -> execute only if authorized -> verify -> reconcile -> record feedback`. In this recovery the loop stops after analysis/proposal and receipt. No legacy action lane is activated.

ARX observations should carry acquisition time, observation time, source identity, collection method, input/output hashes, freshness, failure state and permitted capability scope. DRAGONHYDRA adds its fixture/as-of cursor, evidence provenance, model outputs, uncertainty and research needs. A model response is an interpretation of that bounded state and retains actor/model/runtime identity; it is not a new external fact.

Qwen and Codex may disagree. Retain their positions and measurable references instead of averaging prose. Compare a research proposal against subsequently acquired evidence, uncertainty change, cost, latency and an observed outcome when scoring prediction quality. A different answer is not itself learning; a test PASS is not predictive improvement. If no outcome exists, accuracy gain remains unknown.

A future machine-action block must first demonstrate a necessary capability that analysis cannot supply, then specify scope, authenticated authority, one-use contract, timeout, cost, replay behavior, failure semantics, rollback and independent verification. Recovery must preserve evidence of partial execution and must not broaden its own capability to repair a failure.

## Immediate inheritance boundary

The new Windows launcher independently verifies Medium integrity, disabled administrator authority and the remaining privilege count before resuming its child. It uses an ephemeral private window station/desktop, an explicit inherited handle list, and a job with kill-on-close and a one-process default limit. A default DACL is set only on the newly derived token so that the same user can access newly created child objects; historical objects are unchanged. Local smoke tests proved restricted Python execution, denial of subprocess creation, job-close termination and preserved llama-cli version execution. See [the scoped proof and its limitations](LOCALAI_SECURITY_BOUNDARIES.md).

The restricted process retains the same user's ordinary file access and is not an OS network sandbox. No future ARX safety claim may silently upgrade these controls to complete host isolation. The first infrastructure probes inherited the high-integrity engineering token and were stopped; restricted-token results are separate evidence. Runtime integrity now includes the full 54-file EXE/DLL manifest rather than only the small launcher executable, and the model process receives a deliberately small environment instead of inherited credentials. These are concrete recoveries of boundaries, not evidence of predictive benefit.

The active owner mission restores a local bounded Qwen service and CHILD adapter. It does not restore PrivilegedBroker, Observer, Broker, Sentinel, QwenService, Windows service registration, registry state, old database identities or Python 3.12. It does not merge a parent branch or alter frozen forecasts. These components remain historical evidence and may be reconsidered individually when a future measurable requirement justifies them.

Only the scoped launcher proof described above is asserted here. Full model/service validation, final test counts and preservation checks belong in the recovery checkpoint and [recovery audit](LOCALAI_RECOVERY_AUDIT.md). No model-quality gain or complete clean-machine reproduction follows from these controls.
