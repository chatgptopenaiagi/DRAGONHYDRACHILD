# CHILD security boundary review

Status: **PARTIAL / EXPERIMENTAL**, inspected 2026-09-24. The evidence supports bounded local identities, acquisition controls and repository exclusions. It does not certify production security, arbitrary-secret absence, complete host isolation or regulatory compliance. The standing [security policy](../SECURITY.md) remains applicable.

## Repository and secret boundary

[Git exclusions](../.gitignore) cover all runtime, data and model trees, machine-local credentials, keys, logs, database files and model binaries. Curated [repository evidence](evidence/README.md) must contain only small reviewed summaries and hashes. Raw source data, private checkpoints, browser captures and generated credentials are local forensic material.

The recorded tracked-file audit at `2026-09-24T21:03:35.512811+00:00` scanned 213 files, including 206 recognized text files, with zero blocking findings/read errors. Three exact negative-test source lines were explicitly reviewed; there is no blanket test-directory waiver. This is a timestamped intermediate audit, not a claim that later files or every Git-history blob have already passed final checks.

The recorded all-local audit at `2026-09-24T21:02:35.276455+00:00` examined 1,156 files and compared four known generated credential values against 1,154 readable files without printing values. Expected credential matches remained in four ignored secret files; zero blocking findings were reported. **Two active ignored SQL files were OS-locked and unreadable:** `DRAGONHYDRACHILD_LAB.mdf` and `DRAGONHYDRACHILD_LAB_log.ldf`. Their unreadability is retained as a limitation, not reported as a successful scan.

[The scanner](../scripts/repository_audit.py) recognizes bounded literal/token patterns and checks known local credential byte sequences. It cannot prove absence of novel, encoded or unrecognized secrets; text scanning has an 8 MiB bound, and Git metadata/symlink targets are not scanned. Final staged-file review, staged-link checks and remote verification remain separate publication gates.

## Databases and local presentation

[Storage configuration](../config/child-storage.toml) binds CHILD clients to `127.0.0.1`, SQL database `DRAGONHYDRACHILD_LAB`/schema `child` and MariaDB `dragonhydrachild_ops`. Runtime configuration cannot supply another database or embedded username/password. [The adapter](../src/dragonhydra/child/storage.py) uses only CHILD-generated identities, fixed table allowlists, bounded batch/query sizes and parameterized values; it exposes no arbitrary SQL execution interface.

SQL ingestion has SELECT/INSERT on six tables and explicit UPDATE/DELETE denials. SQL readers have SELECT with INSERT/UPDATE/DELETE denied. Both measured SQL identities lack sysadmin/db_owner and reported no donor-database access. MariaDB operations can SELECT/INSERT/UPDATE only job state and presentation cache; the web account can SELECT only the cache. Seven zero-row permission-denial probes passed. [Database evidence](CHILD_DATABASE_REPORT.md) states the exact grants, tests and ownership boundaries.

Credentials remain under ACL-protected CHILD `runtime/secrets`, outside the web root, readable by SYSTEM/current administrator. [The CHILD PHP endpoint](../web/child-dashboard/index.php) uses only the CHILD MariaDB web identity, emits generic database failures, escapes HTML and provides a read-only JSON view. [Apache controls](../web/child-dashboard/.htaccess) require local access and disable directory listings; PHP also checks the client address. Local runtime validation passed four checks, including deployed-source hashing, absent credential values in HTTP/JSON, and HTTP 404 for two attempted secret paths. Endpoint: `http://localhost/joomla-codex-lab/dragonhydrachild/`.

These controls do not constitute authentication or proof of shared-service firewall/listener isolation. SQL encryption retains an explicit **loopback certificate-trust exception**; certificate authenticity is not verified by that exception. The dashboard's CSP allows inline script execution. No internet-facing or production-hardening claim follows from localhost HTTP success.

## Acquisition, execution and provenance

[Fixture fetching](../src/dragonhydra/web/fetch.py) pins public DNS addresses through hostname-validated TLS and rejects redirects, cookies/authentication, unexpected content and oversized responses. [Weather fetching](../src/dragonhydra/child/weather.py) separately permits only exact reviewed URLs, public addresses and a tightly bounded MET redirect/decompression policy. Source-policy/robots refusal, rate limits and CAPTCHA/authentication failures stop acquisition; no bypass exists. [Source report](CHILD_SOURCE_REPORT.md) preserves the real blocked providers and unproved reliability dimensions.

[The scheduler](../scripts/Manage-ChildScheduler.ps1) has no stored login password, uses limited interactive execution, rejects an existing task with another action and confines its entry point to CHILD. CI remains network-free; it does not run collectors, database provisioning or wagering. No dependency or storage service was added for these boundaries; Python 3.14 and inherited pinned driver/compute installations are retained.

[The prospective ledger](CHILD_TEMPORAL_CONTINUUM_REPORT.md) preserves actual issue clocks, input availability, analysis/code hashes and immutable append history. A chain checked against a retained head hash is tamper-evident, not signed external timestamp attestation. Administrative access can still modify local files; crash recovery and later outcome correction require explicit evidence-preserving procedures.

## Donor protection and remaining verification

[Donor provenance](PARENT_DONOR_PROVENANCE.md) records the initial 179-file hash inventory and comparison of parent HEAD, branch, status and remotes after copying. That comparison establishes its recorded scope/time; it is not continuous proof that no process ever changed any donor resource. The final donor comparison must be retained separately. CHILD runtime identities are isolated from donor data, and this review made no donor writes or new live database changes.

LOCAL EVIDENCE PATHS: `runtime/checkpoints/child-foundation-all-local.json`, `runtime/checkpoints/child-science-safety.json`, `runtime/checkpoints/child-runtime-validation-74481bb0f1a6/runtime-proof.json`, `runtime/checkpoints/child-v0-storage-validation-20260924T204019.284033+0000-d73e9bba/storage-proof.json`. Ignored forensic targets are not repository links.

Final closure evidence is retained in [validation](evidence/child-validation-summary.json) and [donor verification](evidence/child-parent-verification.json). The latter confirms all 179 authored hashes and Git identity remained unchanged. Publication checks are scoped to the exact commit identified in the [final report](FINAL_DRAGONHYDRACHILD_REPORT.md) and handoff; an earlier audit is not proof of later bytes.

NEXT_EXACT_ACTION: monitor the bounded collector and pending outcome without expanding privileges or silently rewriting evidence; review source policies when their review period expires.
