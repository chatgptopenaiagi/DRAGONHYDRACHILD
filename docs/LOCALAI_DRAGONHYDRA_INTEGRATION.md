# Bounded LocalAI integration with DRAGONHYDRACHILD

The restored path is **controlled CHILD analysis → sanitized snapshot → authenticated loopback gateway → preserved Qwen runtime → validated advisory response → immutable operation receipt**. It does not write evidence, revise a forecast, acquire a source, or execute a proposed action. Parent DRAGONHYDRA remains a future consumer; this recovery does not modify or merge its feature branch.

The project-side implementation is [contracts](../src/dragonhydra/localai/contracts.py), [snapshot projection](../src/dragonhydra/localai/snapshot.py), [client](../src/dragonhydra/localai/client.py), [gateway](../src/dragonhydra/localai/gateway.py), [runtime launcher](../src/dragonhydra/localai/runtime.py), and [Windows process restriction](../src/dragonhydra/localai/windows_process.py). Historical architecture and its limitations are recorded separately in [the reconstructed architecture](LOCALAI_RECONSTRUCTED_ARCHITECTURE.md) and [security boundaries](LOCALAI_SECURITY_BOUNDARIES.md).

## Engineering lifecycle

Use the existing canonical Python 3.14 interpreter. On this recovered Windows machine, launch from the owner's authorized elevated engineering PowerShell session: the Windows token/process APIs must be permitted to derive and start the restricted child. The launcher does not request elevation, register a service, create an account, or fall back to an ordinary elevated model process if a restriction fails. The engineering Python supervisor retains its caller's authority; the native inference child is independently restricted and checked.

Start the default 4B model in an existing engineering terminal:

```powershell
Set-Location -LiteralPath 'C:\xampp\DRAGONHYDRACHILD'
& 'C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe' -B scripts/localai_service.py --model qwen3-4b
```

Omitting `--model` also selects `qwen3-4b`. The alternative is `--model qwen3-coder-30b`; `--cpu-only` explicitly selects CPU execution. Run one service at a time. The foreground command reports readiness and remains active until stopped or its session quota is reached. There is no boot registration, automatic restart, or autonomous model switching.

Request orderly shutdown from a second engineering terminal:

```powershell
Set-Location -LiteralPath 'C:\xampp\DRAGONHYDRACHILD'
& 'C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe' -B scripts/localai_service.py --stop
```

The stop command creates an explicit marker for the session named by `runtime/localai/active.json`; the running supervisor observes it and stops its own backend. An in-flight bounded analysis may finish before that marker is processed. Confirm the supervisor has exited and ports 8082/8083 are free before starting another model or replay. Ctrl+C in the foreground terminal also invokes owned-process cleanup. Neither command operates on historical LocalAI Windows services.

The launcher hashes the model and all manifest-pinned runtime executable/DLL files before inference, uses a fresh CHILD runtime session directory, and rejects path traversal or linked runtime paths. New authentication files receive owner/SYSTEM access. Historical LocalAI files, service configuration, registry state, and ACLs are not rewritten. Native inference uses a restricted token, Medium integrity, denied administrator groups, reduced privileges, a private desktop, explicit inherited handles, and a job that forbids child processes and kills the owned process on closure. This is privilege reduction, not complete filesystem or network isolation; see the security document for the remaining boundary.

## Endpoints and authentication

| Surface | Binding | Authentication and purpose |
| --- | --- | --- |
| CHILD cognitive gateway | `127.0.0.1:8083` | Owner client reads the existing `runtime/localai/gateway.key`; analysis-only protocol below. |
| Preserved llama backend | `127.0.0.1:8082` | Separate per-session `backend.key`, used by the gateway. CHILD consumers use the cognitive gateway. |
| CHILD dashboard | Existing CHILD XAMPP presentation | Reads only an allowlisted status artifact; does not receive either token. |

All five gateway routes require bearer authentication and the exact loopback Host. Browser Origin headers, duplicate authorization headers, unsupported routes and external clients are rejected. There is no proxy or redirect following. Tokens are not printed, included in command lines, placed in model context, or stored in receipts.

| Route | Result |
| --- | --- |
| `GET /health` | `schema_version`, `status` (`READY` or `UNAVAILABLE`), `model_id`, `model_hash`, `runtime_id`. |
| `GET /model` | `schema_version`, `model_id`, `model_hash`, `runtime_id`; checked against client pins. |
| `GET /capabilities` | The three permitted task kinds, request byte limit, and an empty `action_capabilities` list. |
| `POST /analyze` | Strict `AnalysisRequest` accepted as bounded JSON; typed `AnalysisResponse` returned. |
| `GET /metrics` | Request/success/failure counts, last success timestamp, last latency, and last failure code. |

The backend uses runtime identity `llama-b10665-ca3d5a3e1`. Available model identities are `qwen3-4b` and `qwen3-coder-30b`; their complete file hashes and provenance limitations are in [runtime evidence](LOCALAI_QWEN_RUNTIME.md). Health is operational evidence about a process, not evidence supporting a football prediction.

## Controlled context and contracts

`from_child_analysis()` projects an existing CHILD analysis through an explicit field allowlist. It requires the CHILD project marker, `STRICT_PIT` analysis/evidence, an accepted validation verdict, valid forecasts, and evidence availability no later than the as-of cursor. Raw source bodies, arbitrary extra fields, credentials and instructions are not copied. This producer assumes upstream HYDRA/MEDUSA validation; parsing a user-supplied object is not itself external evidence validation.

The general `Snapshot` contract contains exactly:

- `schema_version`, `as_of_at`, `temporal_mode`, `fixture_id`.
- `evidence`: `evidence_id`, `source_id`, `content_hash`, `provenance_ids`, `epistemic_state`, `available_at`.
- `uncertainty`: controlled `dimension` and a finite `score` between zero and one.
- `forecasts`: `model_id`, three probabilities in HOME/DRAW/AWAY order summing to one, and `epistemic_state=PREDICTION`.
- `missing_evidence`: controlled evidence-category enums.

Temporal modes are `STRICT_PIT`, `RECONSTRUCTED_PIT`, and `SYNTHETIC`. Evidence summaries in each mode respectively retain `OBSERVATION`, `RECONSTRUCTED_PIT`, or `SYNTHETIC`; the contract rejects mixed relabeling and future evidence availability. A future fixture known at the cursor may be described by accepted schedule evidence; its eventual result is not thereby observed. Forecasts remain predictions.

Dimensions are `LINEUP`, `INJURY`, `MARKET`, `WEATHER`, `IDENTITY`, `TIMING`, `MODEL_DISAGREEMENT`, `SOURCE_RELIABILITY`, `HISTORY`, `OUTCOME`, and `GENERAL`. Missing-evidence categories are `LINEUP`, `INJURY`, `ODDS`, `WEATHER`, `IDENTITY`, `KICKOFF_TIME`, `HISTORY`, `OUTCOME`, and `SOURCE_VALIDATION`.

| Contract | Exact fields |
| --- | --- |
| `AnalysisRequest` | `schema_version`, `request_id`, `created_at`, `model_id`, `model_hash`, `runtime_id`, `task_kind`, `snapshot`, `input_hash`. |
| `AnalysisResponse` | `schema_version`, `request_id`, `created_at`, `model_id`, `model_hash`, `runtime_id`, `input_hash`, `output_hash`, `task_kind`, `result_status`, `failure_state`, `latency_ms`, `reason_codes`, `conclusions`. |
| Each conclusion | `epistemic_state`, `dimension`, `priority`, `reason_code`. |

Task kinds are `ANALYZE_UNCERTAINTY`, `CRITIQUE_STATE`, and `SUGGEST_RESEARCH`. Conclusion states are `HYPOTHESIS`, `INTERPRETATION`, `CRITIQUE`, `RESEARCH_PROPOSAL`, or `ANOMALY_REPORT`; priorities are `LOW`, `MEDIUM`, or `HIGH`. Conclusion reasons are `MISSING_EVIDENCE`, `HIGH_UNCERTAINTY`, `MODEL_DISAGREEMENT`, `SOURCE_FAILURE`, `TEMPORAL_GAP`, `INSUFFICIENT_EVIDENCE`, `RESEARCH_RECOMMENDED`, or `NO_ACTION_REQUIRED`. Version 1 deliberately has no free-form rationale, chain-of-thought, source text, action, shell, tool-call, or SQL field. All unknown fields are rejected.

Successful responses contain one to four validated conclusions, `result_status=SUCCESS`, a null `failure_state`, and `reason_codes=["MODEL_ANALYSIS"]`. Failures contain no conclusions, `result_status=FAILURE`, and the failure code as their reason. Codes are `LOCALAI_UNAVAILABLE`, `MODEL_UNAVAILABLE`, `MODEL_HASH_MISMATCH`, `REQUEST_TOO_LARGE`, `INVALID_RESPONSE`, `TIMEOUT`, `RUNTIME_FAILURE`, `UNSUPPORTED_TASK`, `INVALID_REQUEST`, and `AUDIT_FAILURE`. Invalid local contracts raise `ContractError` before transport rather than manufacturing a response with a false identity. Gateway envelope errors are bounded HTTP 400/413 records; authentication errors are HTTP 403.

Hashes use SHA-256 over canonical JSON: sorted keys, compact separators, ASCII escapes, and no NaN/Infinity. `state_hash` covers the snapshot. `input_hash` covers `{snapshot, task_kind}`, so the same bounded question can be compared across models without changing the input hash. `output_hash` covers all response fields except itself, including model identity, timestamps and latency. It is an operation-integrity value, not a promise of identical inference output. UUID request identity, model/runtime pins and both hashes are checked by the client.

## Client use and bounded resources

The owner-side client reads only the explicit gateway credential and the chosen sanitized artifact. This example does not print either the token or raw model internals. Run it with the canonical interpreter and `src` on the Python import path while the 4B service is ready:

```python
import json
from pathlib import Path
from dragonhydra.localai import LocalAIClient, Snapshot
from dragonhydra.localai.runtime import MODEL_PROFILES, RUNTIME_ID

root = Path(r"C:\xampp\DRAGONHYDRACHILD")
snapshot = Snapshot.from_dict(json.loads(
    (root / "docs/evidence/localai_replay_input.json").read_text(encoding="utf-8")))
client = LocalAIClient(
    "http://127.0.0.1:8083",
    model_id="qwen3-4b",
    model_hash=MODEL_PROFILES["qwen3-4b"]["sha256"],
    runtime_id=RUNTIME_ID,
    token=(root / "runtime/localai/gateway.key").read_text(encoding="ascii").strip(),
    audit_dir=root / "runtime/localai/owner-client-receipts",
    timeout_seconds=110,
)
response = client.analyze(snapshot, "ANALYZE_UNCERTAINTY")
# Consume response.result_status, response.failure_state and typed conclusions.
```

Snapshot/request/response ceilings are 6000/8192/16384 bytes. Both models use context 4096, one slot, six threads and batch/microbatch 128. Inference uses temperature zero, seed 42 and at most 256 generated tokens with a constrained JSON schema. Model reasoning output and tool calls are rejected. These byte limits bound transport; a context/token failure remains a failure instead of triggering an unbounded retry.

The service engine has a 90-second backend request deadline. The reusable client defaults to 30 seconds and accepts an explicit bounded timeout; the example allows 110 seconds so the ordinary service deadline can return a structured failure first. The replay harness intentionally uses a 120-second engine deadline and a 140-second client deadline. Client and backend transports have wall-clock watchdogs as well as socket timeouts. There is no fabricated-output fallback.

The service supervisor stops the session after 256 counted analysis requests or when session files exceed 64 MiB, recording `SESSION_QUOTA_REACHED` in operational status. This check occurs between requests; it is a session stop threshold rather than an atomic filesystem quota. Restart requires a new explicit engineering launch. The threshold does not delete historical receipts or recovery files.

The gateway writes exclusive request-ID receipts under `runtime/localai/<session>/receipts`; repeated IDs do not overwrite history or repeat inference. The client writes a separate receipt to the explicit CHILD runtime audit directory. Receipt failure produces `AUDIT_FAILURE`. Stored material is limited to structured inputs, typed conclusions, identities, hashes, parameters, finite allowlisted telemetry and operation outcomes. Raw reasoning and authentication material are excluded.

## Replay and current evidence

The frozen [sanitized replay input](evidence/localai_replay_input.json) preserves the CHILD as-of cursor, one accepted evidence reference, seven model forecasts and explicit missing evidence. It is separate from the immutable original prospective forecast and does not edit that forecast.

With the ordinary service stopped and ports 8082/8083 free, run:

```powershell
Set-Location -LiteralPath 'C:\xampp\DRAGONHYDRACHILD'
& 'C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe' -B scripts/localai_replay.py
```

The [replay harness](../scripts/localai_replay.py) runs a deterministic no-AI abstention baseline, then restricted 4B and 30B inference on identical snapshot/task input. It records identities, hashes, parameters, validated conclusions, latency, measured process/GPU samples and token restrictions under a unique `runtime/checkpoints/localai-replay-<timestamp>` directory. It also checks authentication, schema, size, identity and absent privileged routes; deliberately crashes only its owned 4B backend to test failure behavior; and selects CPU-only 4B inference without disabling the owner's GPU. Each owned runtime is stopped in cleanup.

**OBSERVED in the restricted replay:** both models returned `SUCCESS`; the bounded 4B analysis took 9.413 seconds and 30B took 45.784 seconds. All 19 replay checks passed, including explicit CPU-only 4B inference returning `12` for `7 + 5`. The complete receipt is retained at `runtime/checkpoints/localai-replay-20260925T211843834651Z/replay.json`. These are individual operation measurements, not model-quality rankings or latency guarantees. No accuracy gain, actual-outcome observation, real research benefit, or bitwise inference determinism follows from a successful replay.

**OBSERVED validation:** the full CHILD suite passed 423 tests: 410 portable and 13 local integration, with zero failures, errors or skips. The recovery adds 74 portable tests. The machine-readable result is retained at `runtime/checkpoints/child-full-tests-20260925T212121401374Z/tests.json`. No package dependency, Windows service registration or registry change was needed. Final historical-tree and parent preservation verification is reported separately in the recovery audit.

**OBSERVED commissioning:** the final 4B service reported `READY`, returned its pinned model identity, and completed a validated CHILD analysis with `SUCCESS`. The CHILD dashboard, its status endpoint, and the parent dashboard each returned HTTP 200; the CHILD page contained the LocalAI panel. The status artifact reflected that successful operation. This is a commissioning observation, not a promise that a later process is still running. Evidence is retained at `runtime/checkpoints/localai-recovery-20260925T205830Z/commissioning.json`.

## Read-only XAMPP/Joomla cockpit

The existing CHILD dashboard adds a LocalAI panel through [its PHP status reader](../web/child-dashboard/localai-status.php) and [presentation page](../web/child-dashboard/index.php). The reader accepts only local requests and reads one fixed bounded file, `runtime/localai/status.json`. It projects a small field allowlist: status, model, hash abbreviation, runtime, heartbeat, execution mode, last success/latency, request count, last failure and adapter state. A heartbeat older than 180 seconds, missing/invalid time, or time over 30 seconds ahead is marked `STALE`; absent or unreadable state is `UNAVAILABLE`.

This is a read-only view of the latest artifact, not a privileged live control channel. Neither Joomla core nor the dashboard receives backend/gateway credentials, unrestricted SQL, model prompts, service-control buttons, or shell commands. Joomla remains the cockpit; inference remains a separate localhost process.

## Reconciliation boundary

Qwen conclusions can inform engineering or research review, including future Codex/Qwen reconciliation. They cannot become `OBSERVATION` or accepted evidence by assertion. A proposal requiring new information must traverse an explicitly permitted HYDRA acquisition, MEDUSA validation, temporal memory and recalculation before it can affect an evidential claim. This recovery exposes no acquisition or execution capability to the model and performs no automatic action dispatch, model-weight update, wagering, or prediction revision.
