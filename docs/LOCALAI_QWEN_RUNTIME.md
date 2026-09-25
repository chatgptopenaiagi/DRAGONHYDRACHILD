# Recovered Qwen runtime

The preserved llama runtime and both preserved GGUF models now answer through the bounded CHILD gateway on the replacement Windows machine. Strict frozen-input replay and all 19 live checks passed; actual Windows process tokens showed Medium integrity with administrator groups disabled/deny-only. This establishes a working analysis service, not long-duration stability, predictive benefit or unrestricted authority.

Evidence is retained locally under `runtime/checkpoints/localai-recovery-20260925T205830Z`: `critical-hashes-before.json`, `gguf-metadata.json`, `machine-before.json`, `4b-cli-result.json`, `4b-cli.stdout.txt`, `llama-cli-version.txt`, `llama-devices.txt`, `qwen3-4b-endpoint.json`, `qwen3-coder-30b-endpoint.json` and `commissioning.json`. Final strict replay is in `runtime/checkpoints/localai-replay-20260925T211843834651Z/replay.json`; the complete test suite receipt is `runtime/checkpoints/child-full-tests-20260925T212121401374Z/tests.json`. Source-backed interpretation follows [the archaeology](LOCALAI_ARCHAEOLOGY.md) and [Windows reconciliation](LOCALAI_WINDOWS_RECONCILIATION.md). No model, binary, private runtime log or authentication material belongs in Git.

## Model identity and integrity

**OBSERVED:** Files were read and hashed without conversion, rename or modification.

| Field | Preserved 4B model | Preserved 30B model |
| --- | --- | --- |
| Filename | `Qwen3-4B-Q4_K_M.gguf` | `Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf` |
| Original directory | `C:\LocalAI\models\Qwen3-4B-Q4_K_M` | `C:\LocalAI\models\Qwen3-Coder-30B-A3B-Instruct-Q4_K_M` |
| Size | 2,497,280,256 bytes | 18,556,689,568 bytes |
| SHA-256 | `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5` | `fadc3e5f8d42bf7e894a785b05082e47daee4df26680389817e2093056f088ad` |
| GGUF version / tensors | Version 3 / 398 | Version 3 / 579 |
| Embedded architecture | `qwen3` | `qwen3moe` |
| Embedded name | `Qwen3 4B Instruct Awq` | `Qwen3-Coder-30B-A3B-Instruct` |
| Embedded finetune / size | `Instruct-awq` / `4B` | `Instruct` / `30B-A3B` |
| Quantization evidence | `general.file_type=15`, quantization version 2; CLI reports `Q4_K - Medium` | `general.file_type=15`, quantization version 2; filename declares Q4_K_M |
| Metadata context length | 40,960 | 262,144 |
| Recovery server context | 4,096 | 4,096 |
| Block count | 36 | 48 |
| MoE metadata | Not present | 128 experts; 8 used; these are metadata values, not action-authority controls |
| Historical hash comparison | UNKNOWN: Phase 4B explicitly records `hash_performed=false` | MATCH: preserved `config/qwen-model.sha256`, startup gate and phase-0 reconciliation SHA-256 |

**OBSERVED discrepancy:** `audit/Phase4B-20260830-090128/PHASE4B-VERDICT.json` attributes the 4B candidate to `Qwen/Qwen3-4B-GGUF`, while its current embedded identity says `Qwen3 4B Instruct Awq` / `Instruct-awq`. That historical receipt did not hash the model. The evidence therefore establishes a current readable, working file with a new exact recovery hash, not verified upstream provenance or equality to a historically hashed 4B file. Neither corruption nor an unauthorized replacement is inferred from this discrepancy. The file remains unchanged.

**OBSERVED:** The 30B metadata names Unsloth as quantizer and records Qwen base-model identifiers. Metadata is a file assertion; the recovery's independent integrity comparison is the matching SHA-256. Declared maximum context is not the context allocated for these tests.

## Preserved runtime

Runtime path: `C:\LocalAI\runtime\llama-b10665`. **OBSERVED:** `llama-cli --version` reports `0.3.0-dev`, build 10665, commit `ca3d5a3e1`, built with Clang 20.1.8 for Windows x86_64. The recovery identity is `llama-b10665-ca3d5a3e1`.

| Critical file | SHA-256 captured before recovery |
| --- | --- |
| `llama-server.exe` | `20a83f9ed723c6307749863842657da86918e8b612a3eaa44fe635d147341550` |
| `llama-cli.exe` | `7ae8bb7afbf6413bd014bc7e128bb1cda16afbe04ef453bf32bd3fe192a88d41` |
| `llama-bench.exe` | `2bd2b5b69238488a4fb79c444d2dcc29417f23a8f01b92a4757734d61fcce594` |
| `ggml-cuda.dll` | `0732c5bc96e9dcbfb1632557ecbad92233bd6c4535d2151039fa2ebcd1aca39d` |
| `cublas64_13.dll` | `f1d500d0cd892f5b8c6b6cdbffd82d0c55d5f5427215668e7ceb55aeeccc1b63` |
| `cublasLt64_13.dll` | `b592cd016d7673e9cb97716a22b27c4010ee635377a3ba28f37070a9bdb76a68` |
| `cudart64_13.dll` | `b00ca6f53699120da815bf3e06e2e4285fae2f201235b883dcbb50eec51e2a2a` |

**OBSERVED:** The native device query reports CUDA0, NVIDIA GeForce RTX 3050, 6143 MiB with 5166 MiB free at that query. Initial `nvidia-smi` reports driver 616.92 and CUDA UMD 13.4. Driver visibility and successful model inference are measured; a separately installed CUDA developer toolkit is not required or inferred. No side-by-side replacement or package installation was necessary for these tests.

## Initial native validation

| Test | Result | Measured values | Scope / limitation |
| --- | --- | --- | --- |
| 4B CLI launch/model/GPU/inference/exit | COMPLETE | Returned `12` for `7 + 5`; exit 0; no timeout; total 2.129 s. CLI reports prompt 575.9 tokens/s and generation 43.5 tokens/s. | One short deterministic prompt; not a benchmark or cognitive quality evaluation. |
| CLI GPU samples | COMPLETE observations | Device-wide used VRAM sampled at 490 MiB, then 2935 MiB; GPU utilization 5%, then 46%. | Samples are not an exact process peak and do not separately attribute every allocation. |
| 4B localhost server health/identity/inference | COMPLETE native probe | Startup 2.228 s; request 0.653 s; 8 generated tokens; runtime-reported generation 47.50 tokens/s; output `{"answer":12}`. | Startup timer excludes prelaunch file hashing. One response does not establish sustained stability. |
| 30B localhost server health/identity/inference | COMPLETE native probe | Startup 2.494 s; request 3.455 s; 3 generated tokens; runtime-reported generation 13.49 tokens/s; output `12`. | Correct arithmetic, but scalar output does not satisfy the requested object shape. |
| Native endpoint process lifecycle | Scoped launcher exercised | Probe receipts record owned process IDs and total execution durations of 4.399 s / 17.088 s. | Final process/listener absence must be checked separately; a duration alone is not shutdown evidence. |
| Strict bounded cognitive gateway | COMPLETE in later replay | Both models returned schema-validated conclusions for identical sanitized input; all 19 live checks passed. | Initial native probes remain distinct historical evidence; details below. |
| Restricted Windows launch | COMPLETE privilege-reduction check | Both GPU/hybrid processes and CPU-only test measured Medium integrity, administrator groups deny-only/disabled, one remaining privilege. | Filesystem read isolation and OS network sandboxing remain explicitly false. |
| RAM/CPU attribution | COMPLETE bounded replay measurement | Owned-process working set/CPU time and whole-device GPU samples recorded. | Resource sampling is not a long-duration stability test. |
| Long-duration stability | UNKNOWN | Short native tests, strict replay and commissioning only. | No multi-day service/boot-persistence claim. |

The 4B CLI used context 2048, output ceiling 32 tokens, six threads, batch 128, requested GPU layers 99, fit disabled, flash attention enabled, offline mode, single turn, reasoning disabled/budget zero, temperature zero and seed 42. The arithmetic prompt was fixed and contained no machine or project secrets. The CLI's interactive file commands are not exposed through the CHILD analysis interface.

**OBSERVED failure boundary:** JSON mode alone is insufficient. The initial 30B raw probe returned a JSON scalar `12`; the intended answer object was not produced. That initial schema limitation is retained. It was resolved for the bounded cognitive contract by requesting a strict schema and independently validating the parsed result; the later 30B strict replay returned a valid structured response. The successful later result does not rewrite the earlier probe.

## Strict frozen-input replay and commissioning

**OBSERVED:** The deterministic no-AI baseline abstained. Both Qwen profiles analyzed the exact same sanitized input hash `ed01b79db6849f71c3e98e6f3343edddde4e2ad0feaac2f624f9361c8d2f51a0` and snapshot hash `f67e504bc355fabb721dec872c6d14b54c9f99a08891ee673249a272325196e2`. Responses, parameters, identities, hashes and resources are frozen in the replay receipt. No new external evidence or accuracy gain is inferred.

| Final strict replay measurement | Qwen3-4B GPU | Qwen3-Coder-30B hybrid |
| --- | --- | --- |
| Result | SUCCESS; two validated `HYPOTHESIS` conclusions | SUCCESS; one `HYPOTHESIS`, one `ANOMALY_REPORT` |
| Startup after prelaunch validation | 2.343 s | 2.572 s |
| Analysis latency | 9.413 s | 45.784 s |
| Prompt / generated tokens | 1031 / 68 | 1027 / 104 |
| Runtime-reported generation rate | 9.934 tokens/s | 5.007 tokens/s |
| Maximum sampled process peak working set | 3,607,547,904 bytes / 3.360 GiB | 18,054,864,896 bytes / 16.815 GiB |
| Sampled process CPU time, first → last | 3.172 → 18.953 CPU-seconds | 5.766 → 147.781 CPU-seconds |
| Last resource-sample elapsed time | 8.468 s | 44.879 s |
| Whole-device VRAM used, sample range | 5718–5767 MiB | 4046–4321 MiB |
| Whole-device GPU utilization, sample range | 93–99% | 4–99% |
| Owned process exit check | PASS | PASS |

CPU time is accumulated across process threads, so it can exceed elapsed wall time. Working-set samples belong to the owned runtime process. GPU samples describe the entire device, including other workload/display allocation; they are not isolated model VRAM or exact peak measurements. Concurrent Ollama and separate llama processes were subsequently identified outside this recovery's owned process set, so contention is an observed limitation rather than merely a hypothetical one. These different prompt/output lengths and short runs are not a model-quality ranking or controlled performance benchmark.

**OBSERVED:** The separate 4B CPU-only test used `-ngl 0 --device none`, returned `12`, and passed. It reported generation 13.243 tokens/s for three generated tokens and a process peak working set of 5,133,287,424 bytes. This safely exercises operation without GPU use; it does not simulate every physical driver/GPU failure.

The 19 live checks passed: health, identity, validated analysis and identical input for each model; owned-process exit for each model; unauthenticated request rejection; browser-Origin rejection; absent shell route; oversized-body rejection; invalid-schema rejection; model-hash mismatch; empty action-capability list; backend-crash fail-closed behavior; and CPU-only inference. The full CHILD suite separately passed 423 tests (410 portable + 13 local), with zero failures, errors or skips. These are separate counts.

**OBSERVED commissioning:** At `2026-09-25T21:23:23Z`, the 4B gateway reported READY and returned a validated response in 9.986 s. The CHILD dashboard and read-only status route returned HTTP 200 and exposed the LocalAI status panel. The parent dashboard also returned HTTP 200. These are timestamped commissioning observations, not proof of indefinite availability or final preservation of every asset.

## Recovery profiles and bounded service

Implementation: [runtime launcher](../src/dragonhydra/localai/runtime.py), [Windows process restriction](../src/dragonhydra/localai/windows_process.py), [gateway](../src/dragonhydra/localai/gateway.py), [contracts](../src/dragonhydra/localai/contracts.py), [CHILD client](../src/dragonhydra/localai/client.py). These links describe project-side code, not permission to execute model-generated commands.

**OBSERVED source configuration:** Backend defaults to `127.0.0.1:8082`; the selected cognitive gateway port is `127.0.0.1:8083`. Historical model ports 8080/8081 remain distinct. The launcher verifies the selected model hash and the complete 54-file native EXE/DLL set against [the runtime manifest](../config/localai_runtime_manifest.json), rejecting missing/extra native files or hash mismatch. It uses a CHILD-local working/log directory, disables web UI and its MCP proxy, disables slots endpoint and RAM prompt cache, selects offline operation, and uses a separate backend authentication key. No runtime download or replacement was required. Model analysis has no runtime-launch capability.

**OBSERVED security:** Windows launch uses a restricted token with administrator SIDs deny-only, maximum privileges disabled, Medium integrity, explicit inherited handles, an owned process job and no ordinary/elevated fallback. Live token inspection confirms Medium integrity (`S-1-16-8192`), both administrator groups disabled/deny-only and one privilege for all three tested runtime modes. Gateway/backend authentication keys are separately generated and kept in new ignored recovery files with restricted ACLs; their values are neither printed nor included in receipts. This reduces privileges but does not isolate all filesystem reads or impose an OS network sandbox. Model requests expose no file, shell, service-control or network action mechanism.

| Profile | Recovery setting |
| --- | --- |
| Both models | Context 4096, one slot, six threads, batch and microbatch 128; no automatic fitting; flash attention on |
| `qwen3-4b` | GPU layers 99 requested; execution identity `GPU` |
| `qwen3-coder-30b` | GPU layers 10 requested plus CPU MoE; execution identity `HYBRID_CPU_GPU` |
| Explicit CPU test mode | GPU layers 0 and device `none`; does not imply uninstalling/disabling the GPU |
| Reasoning output | Reasoning off, reasoning budget 0; gateway rejects hidden-reasoning fields and tool-call output |
| Inference request | Temperature 0, seed 42, maximum 256 generated tokens, no streaming, no prompt caching, strict conclusion schema |
| Context envelope | Sanitized snapshot ceiling 6000 bytes; request ceiling 8192 bytes; response ceiling 16384 bytes |
| Analysis kinds | `ANALYZE_UNCERTAINTY`, `CRITIQUE_STATE`, `SUGGEST_RESEARCH` |
| Model conclusions | `HYPOTHESIS`, `INTERPRETATION`, `CRITIQUE`, `RESEARCH_PROPOSAL`, `ANOMALY_REPORT`; never observations |

**OBSERVED source boundary:** Authenticated routes are `GET /health`, `/model`, `/capabilities`, `/metrics`, and `POST /analyze`. The capability response exposes an empty action-capability list. The HTTP server requires an exact loopback Host and bearer authentication, rejects browser Origin and unsupported routes, and accepts only bounded JSON requests. Calls do not use a proxy or redirects. Conclusion fields are enums rather than executable or freeform source text. Request identity/hash checks, response validation and exclusive receipt creation fail closed.

**OBSERVED source behavior:** Receipts retain request/response hashes, snapshot hash, model/runtime identity, parameters, latency and allowlisted numeric inference telemetry. They exclude authentication material, raw hidden reasoning and arbitrary runtime output. Operational failures return explicit failure states instead of invented analysis. A fixed seed and identical input facilitate replay; they do not guarantee bitwise identical inference across hardware, threads or runtime builds.

**OBSERVED preservation qualification:** The final comparison in `runtime/checkpoints/localai-recovery-20260925T205830Z/preservation-after.json` found no original-file size/last-write changes, no critical/model hash changes, no removed files, no parent authored/Git changes and no frozen-prediction changes. It also found one new 61-byte `C:\LocalAI\recovery\ollama-qwen4b\Modelfile`, two new directories and changed root-directory mtime, so exact whole-tree equality is false. The addition's actor is UNKNOWN. Foreign Ollama on loopback port 11434 and separate llama processes were not started or adopted by this pipeline; they remain untouched. The final audit does not claim content hashing of every historical file or preservation of last-access time.

**Remaining gates:** Strict replay, bounded failure checks, sampled resources, owned-process exit and commissioning have evidence above. Attribution/reconciliation of the concurrent activity remains unresolved. Long-duration stability, predictive advantage, measured research benefit and outcome accuracy gain remain unproved. The initial results remain part of the record; successful later validation does not hide earlier schema limitations. No unrestricted autonomy is enabled.
