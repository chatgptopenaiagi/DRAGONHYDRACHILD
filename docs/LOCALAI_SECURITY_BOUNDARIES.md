# LocalAI recovery security boundaries

Date: 2026-09-25. Scope: the analysis-only LocalAI recovery in DRAGONHYDRACHILD. Historical assets under `C:\LocalAI` are preserved evidence; historical service state, test results and permissions are not current-machine proof. This document records source review and required boundaries. Current execution and validation results belong in [the recovery audit](LOCALAI_RECOVERY_AUDIT.md).

## Evidence vocabulary

**OBSERVED** means directly present in a surviving file or a newly recorded machine observation. An observed historical receipt proves what that receipt records, not present operation. **STRONGLY_INFERRED** means supported by several sources without direct execution proof. **WEAKLY_INFERRED** means a plausible incomplete explanation. **UNKNOWN** means evidence is insufficient. None of these labels substitutes for CHILD's `STRICT_PIT`, `RECONSTRUCTED_PIT`, `HYPOTHESIS`, `PREDICTION`, `SIMULATION`, `OBSERVATION` or `SYNTHETIC` states.

## Recovered design and its limits

The old system separated planning, policy, authorization, privilege, execution and verification. This is **OBSERVED** in `C:\LocalAI\Productization\Docs\Architecture\ARCHITECTURE.md`, lines 5, 25 and 45, and corroborated by the action and approval source below. Its phrase "Intelligence does not imply authority" remains applicable.

| Historical control | Evidence under `C:\LocalAI` | Interpretation |
| --- | --- | --- |
| Qwen creates a bounded plan from supplied evidence; it does not execute | `Tools\Invoke-LocalAIEngineeringPlanner.ps1:296-323` | OBSERVED role prompt and constrained plan shape; a prompt alone is not an enforcement boundary |
| Deterministic governor chooses final route independently of the model suggestion | `Tools\Invoke-LocalAIEngineeringPlanner.ps1:471-516` | OBSERVED routing code |
| Sentinel critiques a plan and may block steps | `Tools\Invoke-LocalAIEngineeringPlanner.ps1:527-574` | OBSERVED model review; not a replacement for deterministic policy |
| Policy defaults to DENY and recognizes explicit classes | `Phase9\LocalAI.PolicyEngine.Common.ps1:52-83,125-218` | OBSERVED decisions; eligibility does not mean execution authority |
| Approval records are distinct from execution | `Tools\Approve-LocalAIAction.ps1:49-73`; `Tools\Evaluate-LocalAIAction.ps1:54-90` | OBSERVED Phase 9A/9C behavior |
| Later approvals bind a current action snapshot, hash, expiry and consumption | `Tools\Request-LocalAIActionApproval.ps1:85-250`; `Tools\Consume-LocalAIActionApproval.ps1:38-42,142-148,183-190,321` | OBSERVED serializable locking and validation design; current SQL deployment is not established here |
| Privileged broker supports only Observer restart | `Build\Phase10B-PrivilegedBroker-R2-20260831-130508\Program.cs:12-25,323-365,515-607` | OBSERVED fixed target/capability, three transition procedures, SCM query/stop/start, Running precondition and changed-PID check |
| Recovery uses fresh authorization and refuses capability expansion | `Phase10\LocalAI.PrivilegedRecovery.Common.ps1:32-37,46-80`; `Phase13\LocalAI.RecoveryManager.Common.ps1:4-10` | OBSERVED: stopped Observer is blocked because service.start is not authorized; unrelated failures preserve evidence and stop |
| MCP invokes a fixed bridge with discrete native arguments | `MCP\server.mjs:8-27,116-151`; `MCP\bridge\Invoke-LocalAIMcpBridge.ps1:5,164-205` | OBSERVED bounded tool schema and durable ai_jobs queue; no arbitrary shell argument supplied by the model |

The historical service manifest records Broker, Observer and Sentinel using service SIDs, PrivilegedBroker Manual/Stopped, and Qwen30B running as **LocalSystem**. Source: `GoldenBaselines\Golden-Baseline-2-20260831-142925\GOLDEN-BASELINE-2-MANIFEST.json:120-158`. This is an **OBSERVED historical deployment**, not the restored identity. The LocalSystem Qwen deployment is not copied. Loopback binding and a narrow HTTP API alone do not establish a restricted Windows process token.

## New process restriction and observed proof

The engineering launcher in `src/dragonhydra/localai/windows_process.py` now creates a restricted copy of the current Windows token, sets the Administrators and local-administrator membership SIDs to deny-only, applies `DISABLE_MAX_PRIVILEGE`, and sets Medium integrity. It verifies the derived token and the actual suspended child's token before resuming execution. It has no ordinary/elevated-process fallback. These operations follow Microsoft's [restricted-token API](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-createrestrictedtoken) and [process creation API](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessasuserw).

Only the new derived token's default object DACL grants the same user and SYSTEM access. No existing filesystem, registry, desktop or service ACL is modified. An ephemeral private window station and desktop separate the child from the interactive desktop. Explicit handle inheritance includes only stdin from the null device and the selected output streams. A Windows job kills the process when the owner closes the job and, by default, permits only one process, preventing subprocess creation. This follows the documented [job object limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information).

**OBSERVED local proof:** canonical Python 3.14 ran with Medium integrity, both administrator SIDs deny-only and one remaining privilege; an attempted child process was denied. A separate synchronization-handle test proved termination on job closure. The preserved `llama-cli --version` ran successfully under the restricted launcher and reported build 10665, commit `ca3d5a3e1`. Ten portable launcher contract tests passed. These establish launcher behavior, not model inference or prediction quality.

LOCAL EVIDENCE PATHS: `runtime/localai/token-proof-58e198825b/receipt.json`, `runtime/localai/token-proof-b034e63182/receipt.json`, `runtime/localai/job-proof-0e669c3ab0/receipt.json`, and `runtime/localai/restricted-llama-version-94ebb5ec43/receipt.json`. Earlier initialization failures remain preserved: disabling administrator groups initially made the inherited default DACL unsuitable; setting a DACL on the new token corrected this. An early job-close probe incorrectly used continued token-object accessibility as a liveness test; its false result remains in the receipt, superseded by the process synchronization-handle test.

The reviewed runtime launcher validates the exact set and hashes of all 54 preserved runtime EXE/DLL files, including implementation and CUDA DLLs, against `config/localai_runtime_manifest.json`, and verifies the selected model hash. It constructs a small environment instead of inheriting the engineering environment's secrets, redirects temporary/cache locations into CHILD runtime, disables CUDA disk caching and sets offline operation. Hash checks detect drift; a privileged host can still race or replace trusted code, so this is not protection from a hostile administrator.

**Limit:** the restricted token is privilege reduction, not complete filesystem read isolation or an OS network sandbox. It retains the same user's ordinary access. Analysis-only API schemas and absence of tools prevent model-selected file, shell, SQL and network operations; they do not prove containment of a native-runtime exploit. Initial high-integrity engineering inference probes were stopped; the final runtime path uses the restricted launcher. The recovery audit records final live model and service evidence separately.

## Analysis-only recovery contract

The new interface's permitted operation is sanitized structured request -> local model inference -> validated structured response -> audit receipt. It must expose no runtime action executor. These are recovery requirements, with implemented behavior and test outcomes reported separately in the recovery audit.

- Bind only to explicit loopback addresses. Reject arbitrary endpoint routing, redirects to other hosts and external model URLs. A local listener is not authentication against hostile local users or privileged host software.
- Accept only allowlisted analysis task kinds and closed schemas, with bounded request bytes, context, output bytes, generation and timeout. Do not accept commands, executable code, SQL, caller-selected files or general URLs as capabilities.
- Derive context from controlled CHILD summaries. Do not send arbitrary files, private logs, credentials, raw database content or historical machine inventories to the model. Reject unexpected secret-bearing fields and keep rejected payloads out of diagnostic logs.
- Bind request/response identity, input/output hashes, model identity/hash, runtime identity, parameters, status, latency and reason codes. A hash records content identity; it is not an authenticity signature or proof of truth.
- Fail closed for unavailable runtime/model, mismatched identity/hash, timeout, size violation, unsupported task, invalid schema or invalid model output. A failure receipt is an observation about the operation, not fabricated model analysis.
- Treat all model/source text as untrusted data. JSON validity alone does not make a proposed action authorized. No model text, web content or returned field is evaluated as Python, PowerShell, shell, SQL or executable instruction.
- Keep conclusions typed as non-evidence analysis, such as HYPOTHESIS or INTERPRETATION. Model output cannot insert accepted observations, mutate predictions or override HYDRA/MEDUSA validation.
- Preserve only structured conclusions, short rationale summaries, references and measurable outcomes. Do not persist hidden chain-of-thought as a cognitive contract field.
- Keep runtime artifacts in ignored CHILD runtime paths. Publish only reviewed small sanitized summaries. Model binaries, historical logs, database files, secrets and private checkpoints do not enter Git.
- Keep Joomla a read-only presentation surface. It must have no start/stop, approval, shell, database-admin or model-controlled action buttons.

Qwen may suggest that player availability is relevant. That remains HYPOTHESIS. Any resulting external fact must follow `ResearchNeed -> permitted HYDRA acquisition -> MEDUSA validation -> accepted evidence -> memory -> recalculation`. Future projections cannot become observations by assertion. Existing frozen CHILD forecasts remain immutable.

## Findings requiring adaptation before any future actions

These are **OBSERVED code properties**, not claims that the old installation was exploited.

| Finding | Exact evidence | Required treatment |
| --- | --- | --- |
| Read-only roots include all of LocalAI; no secret denylist is visible in this resolver | `Phase9\LocalAI.ReadOnlyExecutor.Common.ps1:24-60` | Do not expose this reader to recovered Qwen. Use explicit field projection from controlled state, not broad filesystem access |
| Read-only path validation rejects only the final reparse-point target | `Phase9\LocalAI.ReadOnlyExecutor.Common.ps1:49-53` | Future file capabilities need ancestor/handle-level confinement; contrast stronger ancestor checks in `Phase9\LocalAI.SandboxWrite.Common.ps1:117-145` |
| File reads and log tails return raw content | `Tools\Invoke-LocalAIReadOnlyAction.ps1:110-120,180-207` | Read-only does not imply confidentiality. Require sanitization and narrower approved artifacts |
| Early approval actor names are caller-supplied text | `Tools\Approve-LocalAIAction.ps1:4`; `Tools\Undo-LocalAISandboxWriteAction.ps1:4` | Audit labels do not authenticate a human. Future authorization must bind independently established identity and scope |
| Build restore occurs before the atomic execution claim | `Tools\Invoke-LocalAIControlledBuildAction.ps1:33-36` | Claim before side effects. `--ignore-failed-sources` is not an offline guarantee; explicitly constrain sources/network |
| Model review participates in plan acceptance | `Tools\Invoke-LocalAIEngineeringPlanner.ps1:527-574` | Retain it as critique while deterministic policy independently rejects forbidden capabilities |
| Existing package/permission claims concern an old machine | `Productization\PRODUCTIZATION-FINAL-REPORT.md:23-29,38-42` | Independent Windows/SQL/ACL/identity validation remains required; the historical report itself admits clean-machine integration was unproven |

The broker source requests narrow SCM rights, and product documentation describes procedure-only SQL permissions. Those source/design observations do not establish current installed ACLs or SQL grants. Administrators, Windows/kernel integrity, runtime binary integrity and local host access remain trust boundaries.

## Preservation and verification gate

No historical privileged component is needed for inference. Observer, Broker, Sentinel, QwenService, PrivilegedBroker, action executors, installers and recovery managers remain deliberately inactive unless a later separately justified mission restores them. The historical directory and secrets remain untouched; parent DRAGONHYDRA remains read-only.

Before publication, the recovery owner must correlate final test results and receipts for invalid schema, unsupported actions/tasks, oversized input, timeout, unavailable/crashed runtime, model identity mismatch, secret exclusion, response validation, loopback binds and process privilege. Preservation checks must compare historical critical-file hashes, frozen forecast hashes, parent state and service/listener inventory against the checkpoint. The scoped launcher proof above does not assert that every end-to-end gate has passed.
