# DRAGONHYDRACHILD local operations

This runbook is for the independent experimental CHILD at `C:\xampp\DRAGONHYDRACHILD`. The parent at `C:\xampp\DRAGONHYDRA` remains read-only. CHILD does not supersede its parent. These commands describe the verified local laboratory; portable CI does not establish a clean-machine database/XAMPP/CUDA installation.

## Environment and entry points

Use PowerShell and the existing Python 3.14 interpreter. These examples are specific to this Windows machine:

```powershell
Set-Location C:\xampp\DRAGONHYDRACHILD
$childPython = 'C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
& $childPython -B --version
```

The measured interpreter is Python 3.14.7. Existing NumPy 2.5.3, PyTorch 2.14.0+cu132 and CUDA 13.2 were retained; the CHILD did not replace the Conda environment or add modeling dependencies. The GPU regression and controlled CPU/GPU experiment are distinct from predictive model validation.

The pinned project-local directories `runtime/vendor/pymysql-1.2.3`, `runtime/vendor/pyodbc-5.3.0`, and `runtime/vendor/pypdf-6.19.0` were copied for laboratory continuity. They remain ignored, alongside inherited dependency provenance and checkpoint records. Driver loaders verify distribution version and loaded-module location. Those checks are not a new publisher-signature verification or a hash of every installed file.

Preserved publisher wheel hashes for the two database drivers are:

| Wheel | SHA256 |
| --- | --- |
| `pymysql-1.2.3-py3-none-any.whl` | `14f1c68e2ed859243ae5ca41ffbe677027fc46bc136a9f0be8a4e928e5e7415a` |
| `pyodbc-5.3.0-cp314-cp314-win_amd64.whl` | `58635a1cc859d5af3f878c85910e5d7228fe5c406d4571bffcdd281375a54b39` |

See the inherited [driver provenance](../research/dual-database-driver-sources.md) and [package research](../research/genesis-compatibility-sources.md). A fresh checkout does not contain these ignored installed wheels, credentials, database files or raw data. If reconstruction is needed, obtain the exact official Python 3.14-compatible artifacts, verify recorded hashes, and install only into the CHILD vendor directories with dependency resolution disabled. Do not copy a parent's credential files or silently downgrade Python. End-to-end fresh-machine installation remains a separate gate.

## Provisioning and ownership

The CHILD provisioner has already run on this machine. Routine jobs use bounded accounts and must not rerun administrative provisioning. [provision_child.py](../scripts/provision_child.py) refuses database, login, credential and data-file collisions; it has no reset/drop mode.

For a new, explicitly prepared CHILD laboratory only, the administrative entry point is:

```powershell
& $childPython -B scripts/provision_child.py
```

It requires the existing authorized Windows SQL administrator and local MariaDB bootstrap access. It creates only CHILD names, stores generated credentials in local protected files, and then proves runtime denials. Do not run inherited `provision_sqlserver_lab.py`, `provision_web_sql.py`, `provision_handoff_bridge.py` or `provision-probe.php` as CHILD setup: their historical targets and identities belong to the donor deployment.

| Owner | Dataset and access boundary |
| --- | --- |
| SQL Server `DRAGONHYDRACHILD_LAB`, schema `child` | Append/version-oriented sources, snapshots, fixtures, entities, immutable predictions and evaluation records. Ingest has SELECT/INSERT; read has SELECT. UPDATE/DELETE are denied. Both runtime identities have no donor database access. |
| MariaDB `dragonhydrachild_ops` | Replaceable presentation cache and operational jobs. Ops has SELECT/INSERT/UPDATE on its two tables; dashboard web identity has SELECT on presentation_cache only. |
| Local filesystem | Raw source bytes, acquisition receipts, prediction hash-chain artifacts, analytical JSONL exports and forensic checkpoints. Exports do not change SQL Server's structured-data ownership. |
| `docs/evidence` | Small sanitized repository evidence supporting public repository claims; no raw dataset, database file or credential. |

The six SQL tables are not duplicated wholesale into MariaDB. The dashboard cache is a derived human-facing summary. SQL connections remain encrypted with an explicit loopback-only certificate-trust exception; this is not a remote-production certificate policy. Details and permission evidence are in [CHILD_DATABASE_REPORT.md](CHILD_DATABASE_REPORT.md).

## Routine collector and scheduler

The bounded entry point collects permitted current fixtures and weather forecasts, persists any new capture, recomputes the observatory, freezes a prediction when eligible, checks for newly available final outcomes, and refreshes presentation:

```powershell
& $childPython -B scripts/child_collect.py
```

This is not an unrestricted crawler. A `NOT_DUE` source result is a normal rate-gate outcome. A blocked stage produces an immutable job receipt with its failure state; the job exits nonzero for a partial run. A zero exit code means the bounded job completed, not that every roadmap success gate passed or a future match outcome was observed.

The existing Windows task is `DRAGONHYDRACHILD-Prospective`. It runs the exact CHILD script with Python `-B`, CHILD as working directory, limited privilege, and **Interactive** logon. The owner must remain signed in. No Windows account password is stored. Settings allow one instance, a three-minute execution ceiling, and a daily trigger; collector rate gates still apply. On 2026-09-24, the inspected task was Ready and its most recent invocation returned 0. That is invocation evidence, not proof of uninterrupted multi-day service.

```powershell
.\scripts\Manage-ChildScheduler.ps1 -Action Status
.\scripts\Manage-ChildScheduler.ps1 -Action Start
.\scripts\Manage-ChildScheduler.ps1 -Action Disable
.\scripts\Manage-ChildScheduler.ps1 -Action Enable
```

`Disable` stops future scheduled launches; let an already running bounded invocation finish. If immediate termination is necessary, `Stop-ScheduledTask -TaskName 'DRAGONHYDRACHILD-Prospective'` affects only this task. Inspect the last receipt and collector lock before restarting after forced termination; never erase a lock or failed receipt merely to make status green. `Install` is only for an absent CHILD task, and the helper refuses an existing task with a different action. Re-enable with `Enable`, not by repeatedly installing new tasks.

## Two acquired providers and their limits

| Provider | Acquired evidence | Rate and policy boundary |
| --- | --- | --- |
| OpenFootball | Current English Premier League 2026/27 fixture/team/result-report documents | One exact current-season URL; at least 60 seconds between attempts and at most four acquisition attempts per rolling day. Each attempt separately checks robots and fetches the document with the inherited bounded transport. The normal scheduler is daily. Source terms/licence review is checked before acquisition and expires after 30 days. |
| MET Norway | Future forecast values for one London coordinate proxy | One exact latitude/longitude query; one attempt per 24 hours and never before the provider's Expires time. Reuses reviewed policy bytes, preserves Last-Modified and sends conditional GET when available. At most four logical requests for an attempt including missing policy material; each permits at most one redirect to an already reviewed MET URL. Identifying user agent names CHILD and its GitHub owner. |

OpenFootball's review timestamp is `2026-09-24T17:56:38.881836+00:00`; MET's is `2026-09-24T20:48:09.491610+00:00`. Review expiry blocks collection until a fresh review is recorded. Do not work around expiry by changing only the date: inspect the current official policy, preserve its evidence/hash, and update the explicit policy version or reviewed record as appropriate. Exact historical source-policy paths in inherited metadata are lineage, not authorization to write to or use the parent as scratch space.

Open-Meteo remains `ROBOTS_BLOCKED`; its forecast endpoint was not requested. MET Norway is an independent provider with its own allowed robots policy, terms and licence. [Official MET terms](https://api.met.no/doc/TermsOfService) and [licensing policy](https://api.met.no/doc/License) support the reviewed identified and cached use. Weather displays must retain adjacent attribution to MET Norway, a CC BY 4.0 link, and the normalization/proxy notice. Two providers do not mean two independent fixture corroborators or any real odds provider.

`STRICT_PIT` labels the genuine capture clock. A MET forecast remains `HYPOTHESIS` about future weather; it is not observed weather or a verified stadium condition. No predictive weather effect is validated. OpenFootball publication times and kickoff timezones remain unverified; bare score arrays are preserved as ambiguous and are not silently converted into final scores.

## Frozen prediction and outcome lifecycle

The collector invokes [observatory.py](../src/dragonhydra/child/observatory.py). It constructs present-time inputs from genuine CHILD captures, refuses stale capture inputs older than two days, and chooses a future fixture only when a conservative global calendar-date lower bound is still ahead. That bound is explicitly not a verified UTC kickoff.

The first eligible prediction retains model outputs, feature/evidence snapshots, code fingerprint and an immutable analysis artifact, then appends the prediction to the local hash chain and CHILD SQL. Later dashboard refreshes may show new calculations; they do not replace the frozen original. The current KNN inference route explicitly falls back to a uniform prior when genuine historical training-feature frames are absent.

On later scheduled captures, outcome scoring requires an explicit source full-time score and later genuine observation. It appends an outcome/evaluation event and never rewrites the prediction. Until a qualifying final report arrives, the correct state remains `FROZEN_AWAITING_OUTCOME`. An observed-by capture bound is not an invented exact final-whistle timestamp. Controlled/synthetic ledger tests do not score the real future match.

Local paths: `runtime/child/predictions`, `runtime/child/analysis`, `runtime/child/job-runs`, `runtime/child/acquisition`, `runtime/child/snapshots`, `runtime/prospective/met-norway-london`. These are inline local evidence paths, not repository links.

## Historical experiment and replay

The historical command uses already retained, hash-verified OpenFootball bytes and copied capture metadata inside CHILD. It performs no new source acquisition and makes no database writes:

```powershell
& $childPython -B -m dragonhydra.child.research_run
```

It creates a new unique `runtime/checkpoints/child-v3-v6-science-...` directory. An explicit `--output` is supported only for a new directory under CHILD `runtime/checkpoints`; an existing checkpoint is never overwritten. The required historical bytes are ignored local material, so a fresh Git clone alone cannot run this experiment. Missing raw bytes fail explicitly; do not substitute a fresh download while pretending to preserve an old capture.

The historical input contains 380 matches and the declared walk-forward demonstration scores 321 matches. It is `RECONSTRUCTED_PIT`, uses the declared day-start UTC proxy and publication-delay assumptions, and has zero genuine strict historical records at those old decision times. These results do not establish profitable or superior models.

For an existing frozen research checkpoint, use the public replay function without changing original timestamps:

```powershell
@'
from pathlib import Path
import json
from dragonhydra.child.research_run import replay_checkpoint
saved = Path('runtime/checkpoints/REPLACE_WITH_EXISTING_CHILD_SCIENCE_CHECKPOINT')
print(json.dumps(replay_checkpoint(saved), indent=2))
'@ | & $childPython -B -
```

Choose a real existing CHILD checkpoint from the previous run. Replay verifies saved manifest hashes and reports whether the prediction replay hash and metrics match. Computation time is new; source capture times remain original.

## Test tiers

```powershell
& $childPython -B -S scripts/run_ci.py
& $childPython -B scripts/run_child_tests.py
```

The first command is portable, Python 3.14-only, and guards against live network, optional compute/database imports and local credential access. GitHub Windows/Ubuntu CI uses this tier. The second runs applicable portable tests plus CHILD local database/XAMPP and unchanged compute regressions; it writes a unique local checkpoint.

The final measured 2026-09-24 suite has **336 portable + 13 local integration/compute = 349 tests passed**, with zero failures, errors or skips. The local runner explicitly reports **37 inherited donor-deployment tests as NOT_APPLICABLE_TO_CHILD**. They remain in source and are not counted as passed or silently skipped. Do not use the inherited `scripts/run_tests.py`, `Run-DualDatabase.ps1` or other donor launchers as the CHILD full test runner.

Local tests require the generated CHILD credentials, two genuine fixture captures already persisted, MariaDB cache, the separately deployed dashboard and the canonical GPU environment. They do not fetch external sports data. The local replay/export tests create clearly labelled capability evidence and new immutable analytical export files.

LOCAL EVIDENCE PATH: `runtime/checkpoints/child-full-tests-20260924T210546339168Z/tests.json`. Counts are a dated result, not a promise about future changes; inspect the newest test checkpoint after each modification.

## Dashboard deployment and verification

The CHILD page is a separate directory under the existing local Joomla laboratory web root; Joomla core is unchanged:

`http://localhost/joomla-codex-lab/dragonhydrachild/`

JSON representation: `http://localhost/joomla-codex-lab/dragonhydrachild/?format=json`.

The PHP page reads only `runtime/secrets/child-maria-web.local.json` through an explicit local path outside htdocs. It queries the `child-intelligence` presentation-cache entry with the SELECT-only CHILD MariaDB web identity. No SQL ingestion credential is deployed or referenced. The three published assets are `.htaccess`, `index.php`, and `dashboard.css`.

After reviewing a dashboard change, update only those three CHILD assets:

```powershell
$childWeb = 'C:\xampp\htdocs\joomla-codex-lab\dragonhydrachild'
New-Item -ItemType Directory -Path $childWeb -Force | Out-Null
Copy-Item -LiteralPath 'web\child-dashboard\index.php' -Destination (Join-Path $childWeb 'index.php')
Copy-Item -LiteralPath 'web\child-dashboard\dashboard.css' -Destination (Join-Path $childWeb 'dashboard.css')
Copy-Item -LiteralPath 'web\child-dashboard\.htaccess' -Destination (Join-Path $childWeb '.htaccess')
& $childPython -B -m unittest discover -s tests -p test_child_runtime.py -v
```

Do not copy the project root, runtime tree or credential files into htdocs. Both Apache `Require local` and the PHP remote-address gate limit this page to localhost. The HTTP/JSON integration test checks HTTP 200, cache parity, no-store headers, actual protected-secret byte exclusion and prohibited credential fields. The audit also verified that tested secret URL paths returned 404 and that the deployed PHP matched the authored source. This is local application evidence, not a comprehensive firewall/security certification.

## Browser handoff boundary

The inherited `BrowserHandoffEnvelope` contract, schema and portable validation/security tests remain available. The published schema's `project_root` now names CHILD, and the Python contract derives its root from the current checkout. These facts do **not** migrate the inherited live consumer's storage.

The inherited `handoff/store.py` still loads legacy SQL configuration, references `dragonhydra` tables and expects donor bridge identities. The legacy SQL/MariaDB adapters still contain donor-specific database boundaries. No corresponding donor credential files were copied into CHILD. Do not run the inherited live handoff consumer or provisioners, and do not satisfy a missing-credential error by copying donor credentials. A later bridge migration must explicitly connect the validated envelope to CHILD-owned storage and prove its own end-to-end gate.

Genuine Codex Desktop browser production remains unverified because the recorded IAB surface was unavailable. CHILD has not reclassified that failure as browser success. Its validated operational ingestion route is the bounded Python/API collector into independent CHILD storage and presentation. Portable handoff contracts are useful inherited capabilities; they are not proof of a working Desktop-to-CHILD database path.

## Evidence and recovery boundaries

**LOCAL FORENSIC EVIDENCE = `runtime/checkpoints`** and other ignored runtime ledgers/raw stores. Preserve full receipts, raw hashes, failed attempts, manifests and synthetic labels. **REPOSITORY-SAFE EVIDENCE = `docs/evidence`**. Only curated small summaries belong there. A file being present locally does not make an ignored runtime path a valid GitHub documentation target.

Before publishing a milestone, run the repository secret/forbidden-path checks and the link audit against the staged file set. Do not commit runtime, vendor binaries, credentials, database files, raw forecasts or private browser material. Never overwrite old checkpoint evidence to remove an error; record a new repair/validation result.

Known operational/scientific breaks remain explicit: no lawful real odds snapshot, no verified cross-provider fixture/player identity, no verified kickoff timezone, no real lineup-research benefit, no prospective outcome yet for the frozen future match, no multi-day availability guarantee, and no clean-machine full-laboratory bootstrap proof. The system has no wagering execution, account bypass, CAPTCHA bypass, rate-limit evasion or guaranteed-profit mode.
