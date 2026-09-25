# Qwen routing V2

`ModelRouter` selects a proposed model from explicit task, resource and occupancy inputs. It never starts a process, unloads a model or executes a fallback. The engineering launcher remains separate from runtime cognitive authority.

| Actor | Role | Initial tasks |
| --- | --- | --- |
| QWEN_4B | Fast cognitive reflex | Classification, summary, change triage, health interpretation, uncertainty categorization, short evidence review, anomaly detection, complexity estimation |
| QWEN_30B | Deep cognitive analyst | Architecture review, cross-state comparison, hypothesis generation, research planning, disagreement analysis, uncertainty decomposition, source reconciliation, software review |

The implementation is [router.py](../src/dragonhydra/cognitive_v2/router.py). A deep task or HIGH complexity prefers 30B. HIGH urgency or a requested latency below 30 seconds prefers 4B. Those values are policy thresholds, not measured latency promises. RAM floors are 6,144 MiB for 4B and 28,672 MiB for 30B. Unknown RAM prevents deep selection. An occupied or unavailable model is excluded. CPU load at or above 90% excludes a new deep selection. Low VRAM produces `CPU_FALLBACK_REQUIRES_ENGINEERING_LAUNCH`; the router does not change GPU settings itself.

Each decision includes the selected model, an optional fallback, stable reason codes and a hash over the complete routing input and policy version. Changing measured load changes that hash even if the selected model stays the same. A completely unavailable selection is BLOCKED. A fallback is a declared option; failure never becomes fabricated mock output.

The [adapter](../src/dragonhydra/cognitive_v2/adapter.py) projects a typed `CognitiveStateSnapshot` into at most 6,500 bytes and 48 structured facts. It prioritizes state summary, machine event codes, uncertainties and selected machine components. Facts carry references. Bounded hardware/model labels are data. Free source text, recommendation prose, paths, command lines and configuration bodies are excluded. `omitted_fact_count` makes reduction explicit; omission does not prove external evidence is absent.

The complete frozen state hash and reduced projection hash are both retained. All actors can inspect the same frozen state artifact. Comparing actors must record when their bounded views differ; the Qwen grammar intentionally exposes categorical conclusions rather than unrestricted essays.

The authenticated gateway retains `/analyze` V1 and adds `POST /v2/analyze`. V2 uses the same loopback, Host, Origin, bearer authentication and 8,192-byte HTTP limits. No new listener is needed. The request pins model ID, full GGUF hash, runtime ID and launcher hash. The existing engineering launcher verifies the complete preserved binary manifest before starting a restricted model process.

Inference uses temperature 0, seed 42, at most 512 generated tokens, the existing 4,096-token context, and a maximum 120-second deadline. JSON-schema output is limited to three categorical conclusions with known reference IDs. The adapter validates the actual response again; grammar configuration alone is insufficient. Model interpretation remains HYPOTHESIS, INTERPRETATION, CRITIQUE, RESEARCH_PROPOSAL or ANOMALY_REPORT. No conclusion creates an observation or MEDUSA acceptance.

Machine/project expiry and a 120-second state/request age check apply to normal requests. A deliberately frozen experiment can set `replay_mode=true`; that flag is hashed and receipted and describes historical analysis, never current action authorization. Repeated request IDs cannot overwrite their receipts. The V2 engine admits at most 128 requests per session, within the existing service quota. Receipts contain normalized conclusions and numeric inference telemetry, not raw reasoning traces or authentication values.

Failures include unavailable model, hash mismatch, stale state, timeout, runtime failure, invalid response, replay rejection, quota rejection and audit failure. No live fallback or model replacement is automatic. See [security](COGNITIVE_SECURITY_MODEL.md), [reconciliation](QWEN_CODEX_RECONCILIATION.md), and [progress](COGNITIVE_V2_PROGRESS.md) for validation and current operating limits.
