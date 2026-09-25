# LocalAI recovery audit — 2026-09-25

**COMPLETE: bounded local inference and CHILD integration. PARTIAL: historical-system restoration.** Both preserved models produced validated, non-evidence cognitive responses from the same frozen CHILD snapshot. The old privileged/control services were studied and remain inactive. No unrestricted autonomy or predictive improvement is claimed.

The recovery started from clean CHILD `main` at `69922c7b2deda5e0242f819d5d48b0b77d712b22`, equal to GitHub main with both workflows successful. Work belongs to `feature/localai-qwen-recovery`; it is not a merge. The parent started clean on `feature/cognitive-awareness-foundation` at `adefc700a54bff9dc486fefcacfd0014eba27da1` and remains protected.

## Preservation checkpoint and concurrent activity

**OBSERVED:** The before-change inventory contained 260,492 files, 27,529 directories and 53,339,414,060 bytes under `C:\LocalAI`. Last-write range: 1996-05-21 through 2026-09-14. Full metadata, critical source/configuration/binary hashes, both GGUF hashes, machine/service/listener inventory, parent authored-file hashes and the frozen CHILD forecast hash are in ignored `runtime/checkpoints/localai-recovery-20260925T205830Z`.

**OBSERVED:** The after-check found no original file removed or changed in size/last-write timestamp; every critical content hash, including both GGUF files, matched. Parent Git identity, tags, remotes, working tree and all inventoried authored files matched. CHILD's existing `runtime/child/predictions/00000001.json` remained byte-identical. The daily collector had independently completed at 22:45 Vienna with result 0; this recovery did not run source acquisition or issue a forecast.

**UNKNOWN actor / preserved concurrent addition:** The entire LocalAI tree is not byte-for-byte identical to the initial inventory. `C:\LocalAI\recovery\ollama-qwen4b\Modelfile` (61 bytes, created 21:07:29 UTC) and two directories appeared during this mission. Its content references the preserved 4B model. This team did not create it. An independently started `C:\ollama-windows-amd64\ollama.exe` process listens on loopback 11434; additional foreign llama processes were observed, including one configured for loopback 11435. They were not stopped or changed. The owner was asked asynchronously about concurrent recovery work. Attribution remains UNKNOWN unless confirmed; original-asset preservation and whole-tree equality are separate results. The raw preservation receipt correctly reports `passed: false` for exact tree equality.

Metadata comparison covers size and last-write timestamps, not every original file's content or last-access timestamp. Critical files and both models were fully rehashed. No secret/DPAPI contents were inspected. No all-machine immutability claim is made.

## Restored path and evidence

`controlled CHILD analysis -> deterministic field projection -> authenticated loopback gateway -> preserved llama runtime/Qwen -> strict non-evidence conclusions -> immutable receipt -> read-only cockpit`

- **RECOVERED / REUSED:** Preserved llama build 10665 (`ca3d5a3e1`), both GGUFs and existing NVIDIA/CUDA compatibility. No replacement/download was necessary.
- **REBUILT:** Standard-library Python 3.14 contracts, client, deterministic snapshot projection, gateway, explicit engineering launcher and Windows reduced-privilege process wrapper. The launcher checks a manifest of all 54 runtime EXE/DLL files and the selected model's full SHA-256.
- **UNCHANGED:** Historical source, configuration, binaries, models, old secret material, parent repository, existing forecast, Python environment, shared services and Joomla core.
- **NOT_REQUIRED / DEFERRED:** Old SQL job queue, PostgreSQL, Python 3.12 environment, Node MCP, QwenService, Observer, Broker, Sentinel, PrivilegedBroker, action executors, installers and automatic service startup.
- **UNKNOWN:** 4B publisher provenance; its metadata names an Instruct-awq variant while the historical receipt names Qwen's GGUF repository and explicitly says no hash was performed. The 30B hash matches the historical manifest. DPAPI decryptability and old identity/grant equivalence remain untested.

See [archaeology](LOCALAI_ARCHAEOLOGY.md), [architecture](LOCALAI_RECONSTRUCTED_ARCHITECTURE.md), [Windows reconciliation](LOCALAI_WINDOWS_RECONCILIATION.md), [runtime measurements](LOCALAI_QWEN_RUNTIME.md), [integration operations](LOCALAI_DRAGONHYDRA_INTEGRATION.md), [security boundaries](LOCALAI_SECURITY_BOUNDARIES.md), and [ARX harvesting decisions](LOCALAI_NEXT_GENERATION_ARX_NOTES.md).

## Validation

**OBSERVED:** 423 applicable CHILD tests pass: 410 portable plus 13 local; zero failures, errors or skips. This includes 74 new portable LocalAI tests. The 37 inherited donor deployment tests remain explicitly outside CHILD scope. The portable guard observed zero prohibited network/live dependencies.

**OBSERVED:** The frozen replay completed 19/19 live checks, including 4B and 30B structured responses, model/hash binding, identical input hash, authentication and browser-origin rejection, invalid/oversized request rejection, no command route, empty action capabilities, a deliberately terminated owned backend failing closed, process shutdown and explicit CPU-only inference. The no-AI baseline abstains; it is not fabricated inference. Receipts retain parameters, model hashes, usage, latency, CPU time, RAM and sampled GPU telemetry. See the [sanitized replay](evidence/localai_replay_summary.json) and [frozen input](evidence/localai_replay_input.json).

**OBSERVED:** Model processes were independently inspected: Medium integrity, administrator SIDs deny-only, one remaining privilege. A Windows job blocks subprocesses and terminates the backend on owner-handle closure; dedicated smoke tests proved both. This is privilege reduction, not complete OS filesystem/network isolation. The trusted engineering supervisor still runs in the owner's administrative session; it exposes only the bounded analysis API. Inherited environment secrets are not passed to the model process.

**OBSERVED:** The default 4B service was commissioned on `127.0.0.1:8083`, with a separately authenticated backend at `127.0.0.1:8082`. CHILD analysis, health/model endpoints, the read-only dashboard and parent dashboard returned successful results. The owned service completed an explicit stop/restart test. No Windows service, registry setting, firewall rule, package, runtime installation or global environment configuration was added or modified by this team. New authentication ACLs apply only to new recovery files.

Repository publication requires the final staged-index portable run, staged Markdown link audit, secret/path/size audit, matching remote HEAD and explicit branch workflow dispatch. Exact final publication receipts remain in ignored checkpoints; a document inside its own commit cannot contain that commit's resulting hash. Two negative-test lines containing dummy credentials are individually reviewed by source-line digest in the existing audit mechanism; this is not a blanket test-file exemption.

## Limitations and next action

This is a single-machine, short-duration integration proof. Inference is not guaranteed bitwise deterministic across devices/runtime versions. GPU memory/utilization are device-wide samples; concurrently observed foreign model processes prevent an isolated performance claim. No accuracy gain, real research benefit, lawful odds access, later fixture outcome, complete player identity or exact kickoff timezone has been established.

The gateway has no action authority and no automatic HYDRA acquisition. It accepts three analysis tasks and enum-only conclusions. Sessions stop after 256 analyses or 64 MiB of session files; there is no silent deletion, service restart or reboot persistence. The dashboard marks old heartbeats STALE after three minutes. Authentication protects the local interface; it is not a multi-user hostile-host sandbox.

**Exact next action:** Reconcile the independently running Ollama/llama work with the owner, then run a bounded analysis cycle on a newly validated CHILD snapshot and compare the retained Qwen conclusions with measurable state and Codex's independent assessment. Any research proposal must still pass the existing HYDRA/MEDUSA path. Keep both feature branches unmerged.
