# ARX machine state fabric V0

ARX provides bounded read-only host observations to CHILD. It is an engineering-owned collector, not a shell tool exposed to Qwen or Codex cognitive proposals. A model can request a refresh through policy; it cannot supply probe code, paths or commands.

The implementation is [machine](../src/dragonhydra/machine/__init__.py), with [portable tests](../tests/test_machine_v2.py). Python 3.14 and the existing PowerShell, Git and NVIDIA utilities are reused. No service, task, registry, firewall or dependency is installed or changed by capture.

## Contracts and clocks

`MachineObservation`, `MachineSnapshot`, `MachineProbeReceipt`, `MachineHealth`, `MachineCapability`, `MachineDelta` and `MachineEvent` have strict JSON roundtrips and deterministic SHA-256 hashes. Unknown keys, secret-shaped values, paths, nested arbitrary content, duplicate entities, invalid clocks, invalid metrics and inspection levels above 2 are rejected.

Each observation carries the collection window start (`observed_at`), collection completion (`available_at`, `created_at`, `as_of_at`), a 120-second freshness TTL, probe identity, entity identity, status, reason codes and allowlisted scalar attributes. The window does not claim atomic simultaneous measurement across subsystems. Each receipt hashes the complete clock-bearing observations from its probe. Snapshot semantic hashes omit capture-clock and uptime drift; actual measured resource values remain part of state.

Freshness and health are distinct: expired or future observations cannot be fresh; failed probes make the snapshot unsuitable for freshness-dependent decisions. Missing optional tools or subsystems are represented as unavailable or explicit false presence, never invented healthy data. Snapshot health is HEALTHY, PARTIAL or FAILED. A HEALTHY collection means its configured probes succeeded; it does not mean every observed service is running.

## Observation hierarchy

The initial collector produces level 2 component rows; aggregation provides levels 0–1 for cockpit and cognitive summaries. Levels 3–4 configuration/deep inspection are outside this runtime interface. There is no recursive filesystem crawl or arbitrary file-content input.

| Probe | Bounded observable fields |
| --- | --- |
| OS | Name, build, version, architecture, boot time and uptime |
| CPU/RAM | Identity, core counts, load, total and available memory |
| GPU | NVIDIA identity, driver-visible CUDA version, total/used VRAM and utilization |
| Processes | Selected AI/database/Apache names, PID, start time, recognized Qwen identity, recognized bind/port, explicitly selected experiment PID |
| Services | Selected Apache, MariaDB/MySQL, SQL Server and historical LocalAI service state; no start/stop |
| Listeners | Loopback and wildcard local listeners, address/port/PID and exposure classification |
| Tools | Existing Node, Git, Codex, Ollama, Docker, WSL, PowerShell, Python, PHP, Apache and preserved llama runtime presence/version metadata |
| Conda | Names of up to 32 environments under the canonical environment directory; no private paths |
| WSL | Distribution names/state/version from bounded `wsl --list --verbose`; no distribution starts |
| Repositories | CHILD and parent HEAD, branch, dirty flag and status counts; no file paths, diffs or writes |
| Scheduled task | CHILD prospective task state, last result and last/next run |

Processes are filtered before export. Command lines are inspected locally only to extract recognized model/host/port flags; command lines and executable paths never enter the snapshot. The engineering caller can identify one experiment-owned PID to observe; this is not process-control authority. PID reuse is distinguished by process start time. An observed listener is not automatically hostile. The owner's manual Ollama/llama session is authorized and is not terminated by ARX.

Docker is presence/version metadata only: ARX never calls a potentially remote Docker daemon. CUDA visibility describes the NVIDIA driver, not proof of a separately installed toolkit. Tool file versions may be unknown; ARX does not start preserved LocalAI executables to ask them for versions. Ollama's absence from PATH does not contradict a separately observed running Ollama process.

The fixed PowerShell probe prefers installed PowerShell 7. Windows PowerShell 5.1 on the recovery machine rejects script execution under its existing policy; that policy is not changed or bypassed. If the permitted probe cannot run, failures remain explicit. Output is capped at 256 KiB and fixed commands have 8–30 second timeouts; both output streams are bounded while reading. Git uses `--no-optional-locks` and does not create a parent index refresh.

## Meaningful deltas

`compare_machine(before, after)` emits stable reason-coded events for process/runtime appearance and disappearance, model changes, service/database/XAMPP changes, listeners, repository branch/HEAD/dirty state, scheduled task changes and runtime configuration changes.

Small resource changes remain observations without noisy events. Default material thresholds are 256 MiB GPU memory and 1 GiB available RAM. CPU load drift and uptime drift do not emit events. Thresholds are explicit call parameters. GPU identity, driver, CUDA or availability changes emit GPU health events.

Both corresponding probe domains must have succeeded before disappearance or appearance is claimed. Probe failure emits `MACHINE_PROBE_FAILED`, not a fabricated process stop; probe recovery does not fabricate starts. Reverse-time comparisons are rejected. A state hash may change for measured load even when a material event threshold is not crossed.

## Bounded append-only journal

`EventJournal` writes canonical, hash-chained JSONL records only below CHILD `runtime/cognitive-v2`. Parent, LocalAI, traversal, symbolic-link, junction and reparse-point destinations are rejected; ancestors are checked again before reading/appending. Defaults: 64 KiB per segment, 16 segments, 2,048 events. Segments rotate without rewriting or deleting earlier segments. Every append verifies the existing chain. Duplicate identical events are idempotent; conflicting IDs are rejected.

Quota exhaustion fails closed as `JOURNAL_QUOTA_EXCEEDED`; archival/rotation into a newly approved journal is an explicit maintenance decision. A crashed writer may leave `.writer.lock`; capture does not silently break the lock or repair history. Important events can be selected as references for durable episode/decision/limitation memory through the cognitive layer. The journal itself never declares ordinary event text to be scientific learning.

## Verification and limits

Portable tests exercise strict roundtrips, deterministic semantic hashing, clock drift, freshness, secrets and untrusted fields, PID reuse, failed-probe semantics, resource thresholds, process lifecycle, service/database changes, repository state, journal tampering/rotation/quotas, output bounds and timeout/crash handling.

The initial live collection succeeded across all 12 configured probe domains. Live process A/B/C receipts are recorded by the mission checkpoint separately; a passing contract test alone is not a live observation. Portable CI never requires access to this Windows machine, GPU, databases, LocalAI or the network.

The [explicit ARX experiment](../scripts/cognitive_arx_experiment.py) subsequently passed eight live checks: the collector observed one newly created bounded Python sleep process, classified its appearance, observed its controlled shutdown and classified its disappearance. Only the process handle created by that experiment was terminated. Original snapshots, complete deltas and the isolated process delta are immutable cognitive artifacts; the two lifecycle events are retained in the bounded journal. Qwen interpretation of those observations is a separate non-evidence product.

ARX does not prove service internals, database query health, binary integrity or predictive quality from a process/service listing. Identity/hash binding for inference remains the LocalAI gateway's responsibility. A service reporting Running is a service-state observation, not an application-level success assertion. Freshness, semantic deltas and immutable receipts support future policy checks but grant no mutation authority.
