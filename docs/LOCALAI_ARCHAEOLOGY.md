# LocalAI archaeology

Recovery review date: 2026-09-25. This document records surviving historical evidence, not a claim that the old installation is currently running. `C:\LocalAI` is preserved source material. No historical service executable or action script was executed during the archaeology review; no original file was rewritten. The recovery checkpoint is recorded as a local evidence path: `runtime/checkpoints/localai-recovery-20260925T205830Z`.

## Evidence language

| Classification | Meaning |
| --- | --- |
| OBSERVED | Directly present in a read source, configuration, receipt, log, or measured file comparison. A historical receipt proves that the receipt survives; its reported result is historical. |
| STRONGLY_INFERRED | Several observed implementation details support the conclusion, but no direct surviving statement or new execution proves it. |
| WEAKLY_INFERRED | A plausible interpretation with insufficient independent corroboration. |
| UNKNOWN | Not established; deliberately not replaced with a success claim. |

Machine-readable claims, components, edges and source references are in [the architecture map](evidence/localai_architecture_map.json). The [reconstructed architecture](LOCALAI_RECONSTRUCTED_ARCHITECTURE.md) separates historical operation from the minimal restoration design.

## What survived

**OBSERVED:** This is the owner's custom Windows LocalAI architecture, explicitly distinguished from the unrelated public product of the same name in `Broker/LocalAI.BrokerService.cs:206-207`. Its surviving sources describe both an earlier Python/SQLite agent and a later Windows-service/SQL Server control plane. They must not be collapsed into one presumed deployment.

| Evidence stratum | Observed material and meaning | Primary references, relative to `C:\LocalAI` |
| --- | --- | --- |
| Earlier agent | Python builds context from machine facts, validated skills, indexed repository evidence and recent receipts; posts chat requests to a model alias. Separate policy file has action allow/deny rules. | `agent/context_builder.py:128-154`; `agent/llm_bridge.py:21-77`; `agent/policy.py:26-56`; `config/settings.json:6-31` |
| Model launch gate | Startup script checks the 30B model SHA-256, discovers a server binary, then launches a loopback endpoint. | `start-qwen.ps1:9-10,33-53,59-64,84-94` |
| Service control plane | Qwen and Sentinel supervisors, telemetry Observer, SQL-backed Broker, Node MCP bridge, bounded planner and Codex tooling. | Four component `.cs` files; `MCP/server.mjs`; `Tools/Invoke-LocalAIEngineeringPlanner.ps1` |
| Phase receipts | Phase 2–6 receipts record service identities, endpoints, configuration and historical tests. | `audit/Phase2-20260830-084840/PHASE2-VERDICT.json`; `audit/Phase3-20260830-085512/PHASE3-VERDICT.json`; `audit/Phase4B-20260830-090128/PHASE4B-VERDICT.json`; `audit/Phase5-20260830-091437/PHASE5-VERDICT.json`; `audit/Phase6-20260830-092505/PHASE6-VERDICT.json` |
| Golden baseline | Frozen source copies and reported service/task/mission state exist. They provide comparison evidence, not authority to restart services. | `GoldenBaselines/Phase8-Golden-20260830-115838/live-snapshot`; corresponding `state/services.txt` |
| Later governed actions | Productization architecture describes separate authorization, single-use tickets, fixed executors, verification and recovery. Privileged scope is narrow. | `Productization/Docs/Architecture/ARCHITECTURE.md:9-25,45`; action-policy review is recorded separately in recovery security documentation. |
| Product candidate | Report records reboot persistence, unsigned package and unfinished independent clean-machine acceptance. | `Productization/PRODUCTIZATION-FINAL-REPORT.md:3,14-29,40-42` |
| Last surviving service logs | Model startup and later SQL connection failures are recorded; a previous PASS is not the final observed service state. | `logs/Qwen30B/service.log`; `logs/Sentinel/service.log`; `logs/Broker/broker-service.log`; `logs/Observer/observer-service.log` |

## Source reconciliation

**OBSERVED:** Read-only SHA-256 comparisons on 2026-09-25 found the following live source files identical to their Phase 8 Golden copies. The four C# sources also match their Productization staged runtime copies under `Productization/Package/Stage-20260831-145720/Runtime`. MCP files were not present at that corresponding package path; this is not a claim that every package copy was searched.

| Source | SHA-256 | Phase 8 match | Staged runtime match |
| --- | --- | --- | --- |
| `Orchestrator/LocalAI.QwenService.cs` | `1315441183c726bbca94bbc42bae2f68d8d029e49c60f2fb5080e553572f1982` | Yes | Yes |
| `Broker/LocalAI.BrokerService.cs` | `a86f59dcf7705ae674e5cf422c707429ef7f3b7caca7d38f9c0e8166708f52cf` | Yes | Yes |
| `Observer/LocalAI.ObserverService.cs` | `3d57c70c7997a8694e36102c22e412f3fd54f38b54651c983054bd5a88a969ab` | Yes | Yes |
| `Sentinel/LocalAI.SentinelService.cs` | `21b476bc0b86798127a9d9e0dcd54bcbb9b245a66753ba7c5a68b49713ca0747` | Yes | Yes |
| `MCP/server.mjs` | `645808a222b668cc9d02fcf20a4174f68694535d1dfc82b37edded32bc00f688` | Yes | Not at compared path |
| `MCP/bridge/Invoke-LocalAIMcpBridge.ps1` | `87f7a60f04fa7dd042bf9b48bce5b63fb5bae679820265bbbb652d1be497e32a` | Yes | Not at compared path |

**UNKNOWN:** Source equality does not prove source-to-binary reproducibility or binary provenance. No historical service executable was loaded to infer behavior. Native llama runtime validation and model integrity are separate recovery tests.

## What “AI tunneling” meant

**OBSERVED:** The implemented inference path is an explicit funnel:

```text
Codex or engineering tool
  -> six-tool stdio MCP interface / fixed PowerShell bridge action
  -> parameterized SQL job
  -> deterministic Broker routing
  -> selected machine context and role prompt
  -> loopback llama chat endpoint
  -> SQL response, message and job status
  -> bounded presentation to caller
```

The MCP `ask_local_ai` schema limits prompts to 20,000 characters, targets to `auto`, `sentinel` or `qwen30b`, and timeout to 30–600 seconds (`MCP/server.mjs:115-151`). Its process call selects one fixed bridge file with argument arrays, a 660-second timeout and 16 MiB output ceiling (`MCP/server.mjs:8-25`). The bridge accepts only `status`, `snapshot`, `history`, `ask`, `job`, `recentjobs`; it inserts prompt/target using SQL parameters (`MCP/bridge/Invoke-LocalAIMcpBridge.ps1:5,165-179`). The Broker uses one system and one user message, temperature 0.2, `max_tokens=1024`, and no streaming (`Broker/LocalAI.BrokerService.cs:353-368`).

**OBSERVED:** The planner is explicitly instructed that it executes nothing; it produces at most four steps by default, proposes routes and returns JSON. A deterministic credit governor chooses the final route; Sentinel reviews scope/safety; durable records retain both model job IDs (`Tools/Invoke-LocalAIEngineeringPlanner.ps1:10,296-347,471-516,527-572,689-705`). Local pre-analysis and machine summaries are passed to Codex as a structured packet, while Codex itself is started in read-only or workspace-write mode with the prompt on standard input (`Tools/Get-LocalAICodexContext.ps1:62-137`; `Tools/Invoke-LocalAICodex.ps1:85-96,129-174`).

**STRONGLY_INFERRED:** The owner's “tunnel” description refers to constrained input/context, role-specific reasoning, model routing, output budgets and a separate authority pipeline. This interpretation is supported by the implementation above and the principle “Intelligence does not imply authority” in `Productization/Docs/Architecture/ARCHITECTURE.md:5`.

**UNKNOWN:** No separate encrypted network tunnel, special partial-model API, or mechanism disabling a chosen percentage of intelligence was established in the reviewed implementation. The model name `30B-A3B`, quantization, partial GPU offload and single-slot/context limits describe different computational choices. They do not themselves establish an authority boundary. The historical script's `-cmoe` option is an observed launch argument, not proof of the owner's intended meaning.

## Historical sequence and discrepancies

| Classification | Finding | Evidence |
| --- | --- | --- |
| OBSERVED | Initial launcher uses context 4096, automatic GPU layers, CPU MoE, flash attention, Jinja and an alias. | `start-qwen.ps1:84-94` |
| OBSERVED | Later service configuration uses context 8192, ten GPU layers, ten threads, batch 256 and one slot. | `config/qwen30b-service.conf:5-19`; `logs/Qwen30B/service.log`, last startup 2026-09-01 04:39:50 |
| STRONGLY_INFERRED | Service configuration and repeated startup log arguments are the stronger evidence for the last 30B service profile; the older launcher should not be treated as its exact replacement. | Above configuration and log, plus `audit/Phase2-20260830-084840/PHASE2-VERDICT.json:17-23` |
| OBSERVED | A 9,554-token request exceeded the 8,192-token service context and was rejected twice. | `logs/Qwen30B/llama.log:358,363` |
| OBSERVED | Product report claims successful authorized reboot persistence but explicitly leaves independent clean-machine acceptance unfinished. | `Productization/PRODUCTIZATION-FINAL-REPORT.md:14-29` |
| OBSERVED | Later preserved Broker and Observer logs end on 2026-09-01 around 10:28 with SQL Server unavailable / Named Pipes error 40. | `logs/Broker/broker-service.log`, final recorded error 10:28:45; `logs/Observer/observer-service.log`, final sample error 10:28:52 |
| UNKNOWN | Cause of the historical SQL outage, exact reinstall chronology and state after the last surviving log entry. | No causal evidence established in reviewed material. |
| OBSERVED | The historical dashboard imports `public/status.json`; its visible “LIVE SNAPSHOT” is a generated artifact. | `Dashboard/app/page.tsx:1-3` |
| UNKNOWN | End-to-end refresh cadence of that dashboard in the last running installation. | Reading the rendering source alone does not prove updater operation. |

## Recovery implications

**STRONGLY_INFERRED:** Asking Qwen a bounded question requires model bytes, compatible llama runtime, a fixed localhost transport and controlled context/response handling. It does not require restoration of SQL Server's historical `LocalAI` schema, Windows service identities, PrivilegedBroker, the old PostgreSQL experiment, the Python 3.12 PyTorch environment or the old dashboard. The evidence is the direct HTTP clients and the fact that Qwen/Sentinel supervisors have no SQL call path.

**OBSERVED:** Several old boundaries need stronger implementations before reuse: Broker permits effectively unbounded JSON deserialization and reads the entire response; malformed chat envelopes fall back to raw text (`Broker/LocalAI.BrokerService.cs:351,387-415`). The earlier Python bridge prints an unavailable-server message and returns success on URL errors (`agent/llm_bridge.py:101-107`). Planner repository text and machine context are included in prompts, but no general secret sanitizer is established by that inclusion alone. The new interface must reject invalid/oversized responses, distinguish operational failure from analysis, and keep model text inert.

**OBSERVED:** This archaeology does not reactivate any old action authority. Recovery may reuse proven concepts while rebuilding the narrow inference interface in CHILD. Historical policy, model output and old PASS receipts remain data; none is an instruction to execute or a present-tense validation result.
