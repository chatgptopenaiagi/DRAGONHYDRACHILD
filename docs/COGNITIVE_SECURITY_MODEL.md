# Cognitive V2 security model

Status: **PARTIAL**, analysis and proposal authority only. This document describes implemented boundaries and their limits. Current measured results belong in [V2 progress](COGNITIVE_V2_PROGRESS.md). A validated contract is not a claim of complete Windows isolation or scientifically useful prediction.

## Authority and evidence

HYDRA acquires external observations; MEDUSA validates external evidence; ARX captures bounded machine observations. Qwen and Codex produce advisory conclusions, hypotheses, research needs and proposals. They cannot insert source captures, outcomes, accepted evidence or machine observations through the cognitive API. `ResearchNeed` requires HYDRA and MEDUSA; `ActionDecision` cannot set execution authority. Machine mutation classes remain disabled in the [policy registry](../src/dragonhydra/cognitive_v2/policy.py).

The accepted path is `hypothesis -> ResearchNeed -> permitted HYDRA acquisition -> MEDUSA validation -> evidence -> memory -> recalculation`. Existing STRICT_PIT, RECONSTRUCTED_PIT, HYPOTHESIS, PREDICTION, SIMULATION, OBSERVATION and SYNTHETIC labels remain distinct. Original forecasts are immutable. A later recalculation or measured feedback record never replaces the original forecast.

Engineering Codex can carry out owner-authorized repository work. Runtime CODEX is an artifact identity with bounded proposal authority. The presence of the former does not grant the latter a shell. The cognitive runtime contains no generic command executor, registry editor, service controller, database administrator, browser-cookie reader or source-policy override.

## Model boundary

The [V2 adapter](../src/dragonhydra/cognitive_v2/adapter.py) accepts only a typed cognitive snapshot. It projects selected levels 0–2 facts into at most 6,500 bytes and 48 facts, retaining full-state and projection hashes. Raw database rows, raw web pages, arbitrary files, process command lines, paths, credentials and free recommendation prose are excluded. Bounded hardware identity labels are data. A declared omission count prevents a reduced view from masquerading as the complete state.

Model requests contain one fixed system prompt and JSON data. The response grammar permits at most three conclusions using explicit subject, position, epistemic-state and confidence enums with supplied reference identifiers. Response validation runs again after inference. Tool calls, reasoning fields, truncation, unknown references, arbitrary prose fields and invalid JSON fail closed. No supplied string is evaluated as a command, script or SQL expression. Prompts reinforce this separation; absent execution capabilities and validation enforce it.

Only explicit conclusions, short fixed summaries, assumptions where supported by the contract, reason codes, references, hashes and numeric telemetry are retained. Hidden chain-of-thought, scratchpads, reasoning traces and raw model envelopes are excluded. Malformed output is not stored as a successful answer.

Requests pin model identity and the complete GGUF SHA-256, runtime identity and the launcher SHA-256. The inherited [engineering runtime launcher](../src/dragonhydra/localai/runtime.py) separately verifies the exact runtime EXE/DLL set and hashes against the [54-binary manifest](../config/localai_runtime_manifest.json). It never downloads or replaces the historical runtime. Hashes identify bytes; they are not signatures, source-provenance proof or a defense against a hostile administrator racing trusted files.

## Transport and resource limits

The existing gateway binds `127.0.0.1:8083`; its backend uses `127.0.0.1:8082`. V2 adds a fixed `/v2/analyze` route without a new listener. Both HTTP paths require the existing bearer credential, an exact loopback Host header and a loopback peer. Browser Origin headers, duplicate authentication/Host headers, chunked requests and unsupported content types are rejected. Client URLs cannot contain credentials, arbitrary paths, queries, redirects or non-loopback hosts.

V2 admits at most 8,192 request bytes, 512 generated tokens, the existing 4,096-token model context and a 120-second inference deadline. The backend response read is bounded. V2 admits at most 128 requests in its engine session, within the inherited service's request/storage limits. Request IDs use exclusive receipt creation; an existing request receipt prevents repeat inference in that receipt directory. This is session-scoped replay protection, not a global anti-replay service across unrelated recovery sessions.

The model router is deterministic and advisory. Unavailable models, insufficient RAM, occupancy and latency policy are explicit. It cannot stop owner processes, load another model or silently return a mock. A CPU fallback is an engineering launch proposal; no CPU/GPU setting changes arise from model output.

## Windows process boundary

The reused [restricted launcher](../src/dragonhydra/localai/windows_process.py) creates a Medium-integrity process, makes administrator membership deny-only, disables removable privileges, verifies the actual suspended child token and then resumes it. A job limits subprocess creation and terminates the owned model when its owner closes the job. Explicit inherited handles and a restricted environment avoid passing ordinary engineering credentials through environment inheritance. Runtime cache/temp files remain in ignored CHILD runtime directories.

This is **privilege reduction, not a complete OS sandbox**. The native model process retains ordinary same-user filesystem and network access. The trusted engineering supervisor can run with the owner's administrative rights. No claim is made that a native llama/CUDA vulnerability, hostile administrator or compromised operating system is contained. Qwen itself has no exposed filesystem, network, shell or SQL tool interface.

No historical Observer, Broker, Sentinel, QwenService or PrivilegedBroker is required for V2 inference. Their source is evidence, not authority to execute their binaries. No historical Windows service, registry configuration, DPAPI blob or service identity is reactivated by the cognitive API.

## Observation, clocks and artifacts

ARX runs fixed read-only probes under explicit engineering control. Probe output carries provenance, observation/availability/creation/as-of clocks, TTL, bounded attributes and failure receipts. It never recursively exports a filesystem or passes raw process command lines to a model. A failed probe remains failed; a remembered value does not become a fresh observation.

Proposal state hashes must match the current relevant snapshot. Expired machine/project state and invalid preconditions cause denial. Normal V2 inference also checks machine/project expiry and request/state age. Explicit `replay_mode` permits a recorded historical comparison; it is hashed and receipted and never changes action freshness requirements.

The [artifact store](../src/dragonhydra/cognitive_v2/artifacts.py) permits fixed categories below CHILD runtime, rejects path traversal and linked paths, verifies content hashes and refuses quota overflow. Default storage limits are 4,096 artifacts and 256 MiB; individual artifacts are bounded. The [event journal](../src/dragonhydra/machine/journal.py) preserves hash-linked rotated segments and stops at its configured event/segment quota. The [memory store](../src/dragonhydra/cognitive_v2/memory.py) retains a bounded hash chain; expiry and supersession alter lookup eligibility without deleting history. Capacity requires a reviewed archival operation, not automatic evidence deletion.

These stores are tamper-evident engineering artifacts, not an external trusted ledger. Truncation or hostile replacement of an entire store cannot be ruled out by an unanchored local hash chain alone. Expected checkpoint roots and preservation receipts provide comparison anchors. Path checks reduce accidental redirection; they are not a claim of race-free confinement against an adversarial administrator.

Memory, source material and imported artifacts remain data. CODEX handoff is an explicit frozen snapshot/request/result contract, with no private IPC or automatic engineering loop. An existing reference proves identity/membership, not claim truth. Narrow ARX process-transition checks can flag unsupported claims; general truth still requires independent observation.

## Cockpit and preservation

The CHILD XAMPP/Joomla surface reads a sanitized status artifact and escapes displayed values. It has no approval, service-control, shell or arbitrary query buttons. Model credentials and raw receipts are not dashboard payloads. Uncertainty, stale state and operational failures remain visible.

The owner has explicitly identified manual Ollama on `127.0.0.1:11434`, manual llama on `127.0.0.1:11435`, and the preserved recovery Modelfile as authorized parallel work. ARX records their identity and state without classifying them as hostile or granting itself termination authority. A newly observed listener is a change requiring interpretation; unfamiliarity is not proof of compromise.

Publication requires portable and local tests, negative transport/schema tests, repository secret/path/size checks, staged Markdown links, ignored runtime artifacts, and preservation comparisons for the parent, historical LocalAI assets and original CHILD forecast. No GGUF, secret, raw historical log or private runtime receipt enters Git. See [LocalAI harvest](LOCALAI_GENETIC_HARVEST.md) for inherited controls and deliberately deferred machinery.
