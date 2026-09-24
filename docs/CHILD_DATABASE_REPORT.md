# CHILD database isolation and ownership

Status: **COMPLETE** for independent provisioning, bounded identities, append/version replay and operational cache capability. The real-source V1 end-to-end gate is reported separately in the CHILD completion matrix; this report does not turn a synthetic storage test into external evidence.

On 2026-09-24, Python 3.14.7 provisioned new SQL Server database `DRAGONHYDRACHILD_LAB`, schema `child`, and MariaDB database `dragonhydrachild_ops`. Provisioning first checked that neither database nor any CHILD login existed. It created new CHILD-only data files and credentials; it did not reset an existing object, copy donor credentials, change shared service settings or restart services.

| Store | Primary owner of | Runtime grants |
| --- | --- | --- |
| SQL Server | Sources, immutable snapshots, fixture revisions, entities, immutable predictions, evaluation records | Ingestion: SELECT/INSERT on six fixed tables. Read: SELECT. Both explicitly denied UPDATE/DELETE; neither receives a server role or db_owner. |
| MariaDB | Job state and replaceable presentation summaries | Ops: SELECT/INSERT/UPDATE on two fixed tables. Web: SELECT on presentation_cache only. No DELETE, DDL or administrative grant. |
| Filesystem JSONL | Bounded immutable derived analytical export | Source-of-truth ownership stays with SQL Server. Each export includes an as-of cursor, record IDs, SHA256 and row count. No DuckDB/Parquet component is needed for the measured small workload. |

Independent credentials live only under `runtime/secrets/child-*.local.json`. Directory inheritance is disabled; only the current Windows administrator and SYSTEM can read secrets. SQL data files remain under CHILD `runtime/sqlserver-lab`, with separate MSSQLSERVER service modify rights. No credential value or authentication hash is included in repository reports. PHP reads the CHILD web account locally; it receives no SQL Server ingestion credential.

Both SQL runtime accounts report `HAS_DBACCESS('DRAGONHYDRA_LAB') = 0`. SQL permissions and MariaDB grant scope headers were inspected without exposing secret hashes. Seven zero-row native permission probes passed: SQL ingest UPDATE/DELETE denied; SQL read INSERT/UPDATE/DELETE denied; MariaDB ops DELETE denied; MariaDB web UPDATE denied. These test native grants without relying on a read-only transaction to hide elevated permissions.

The adapter validates offset-aware timestamps, refuses future availability, preserves actual ingestion time separately, and queries only rows whose `available_at` **and** `created_at` are no later than the requested cursor. Its live canary appended two labelled synthetic entity revisions. Replay between the two returned v1; later replay returned v2. The fixture ID is an independent supplied canonical key. Snapshots and predictions may be retried idempotently, but the same ID cannot acquire a different payload. Reconstructed fixtures cannot be relabelled as strict live observations.

The initial storage-validation run had **12 portable tests and 3 local integration tests; 15 passed, 0 failed, 0 skipped**. A subsequent narrow MET Norway query/epistemic-label regression adds one portable test (13 portable, 3 integration). The first local replay run revealed the pinned ODBC driver's lack of native datetimeoffset result conversion. Returning ISO8601 strings explicitly from SQL corrected the adapter; subsequent replay tests passed. Synthetic capability rows stay visibly labelled and are not sports-source counts or real entity-resolution evidence.

LOCAL FORENSIC EVIDENCE PATH: `runtime/checkpoints/child-v0-storage-20260924T203800.266786Z-2b05560f/storage-proof.json`.

LOCAL FORENSIC EVIDENCE PATH: `runtime/checkpoints/child-v0-storage-validation-20260924T204019.284033+0000-d73e9bba/storage-proof.json` and sibling `tests.txt`.

Repository-safe evidence belongs in `docs/evidence`; full local checkpoints, database files and credentials remain excluded from Git. [Storage adapter](../src/dragonhydra/child/storage.py), [explicit administrative provisioner](../scripts/provision_child.py), [configuration](../config/child-storage.toml), and [tests](../tests/test_child_storage.py) are reviewable repository files.

Limitations: database encryption uses the inherited explicit loopback-only certificate-trust exception. Administrative provisioning assumes the existing authorized Windows SQL administrator and local MariaDB root configuration; neither becomes a runtime identity. New-machine service installation and certificate provisioning are not demonstrated by portable CI. Immutable exports are bounded to 2,000 records; larger workloads must measure and justify pagination/analytical storage before expansion. Structured current capture does not prove that the same information was historically available. No donor live test requiring donor credentials was rerun against parent state.

Removal path: stop CHILD jobs, archive CHILD-only immutable evidence, then explicitly retire CHILD users/databases through a separate owner-authorized operation. The provisioner intentionally has no reset/drop path.

## Independent weather forecast evidence

Open-Meteo was reviewed as a private noncommercial candidate, but `api.open-meteo.com/robots.txt` returned `Disallow: /`. The adapter preserved `ROBOTS_BLOCKED` and did not request the forecast. The block is not bypassed. Its failed receipt and exact robots hash remain local evidence.

MET Norway is an independently reviewed second provider. Its [official terms](https://api.met.no/doc/TermsOfService), [data licence](https://api.met.no/doc/License), and robots policy permitted a bounded identified request. The separate [weather adapter](../src/dragonhydra/child/weather.py) captured 65 still-future London-proxy forecast points at `2026-09-24T20:51:26.041046+00:00`; raw SHA256 `37ce9dfc0a09891c55a5cac5db0e32de4dba9389513d8db3d6c7027f388b7ee7`. Two actual requests were made (robots and forecast); the exact reviewed policy bytes were reused locally. The collector preserves Expires and Last-Modified, enforces a daily/Expires acquisition gate, and supports conditional GET. MET requires compression and redirect support: decompression is bounded by compressed and expanded size, and a maximum of one redirect is accepted only to another exact reviewed MET resource. The general inherited fetcher is unchanged.

Forecast data from [MET Norway](https://api.met.no/weatherapi/locationforecast/2.0/documentation), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Changes: selected future times and normalized temperature/precipitation units; London is a coordinate proxy, not a verified stadium. No endorsement is implied. Every projection is `HYPOTHESIS`; `STRICT_PIT` describes when CHILD captured the provider's forecast. It does not make future weather an observation, establish venue relevance or establish predictive value.

The genuine forecast snapshot was appended to CHILD SQL Server as record `1d921a1fe8544f928e1cece15dd54576`, with zero fixture rows. A narrow validator exception allows only the exact reviewed MET query and requires hypothesis labels. No arbitrary-query acquisition was added. OpenFootball remains the fixture source; weather is not a second independent fixture corroboration source.

LOCAL FORENSIC EVIDENCE PATH: `runtime/checkpoints/child-v2-weather-policy-3c2eefdf563e`, `runtime/checkpoints/child-v2-weather-robots-8a0d3995fc03`, `runtime/checkpoints/child-v2-met-policy-454cfc113bdd`, `runtime/checkpoints/child-v2-met-sql-0a33eee19b65`, `runtime/prospective/met-norway-london/168183e273d04746b84a69f9ed89ab8d.json`.

The [repository-safe weather summary](evidence/child-weather-summary.json) contains metadata/hashes and no raw forecast rows. The weather test classes are `ChildWeatherTests` and `ChildMetWeatherTests`, both portable. The weather collector is integrated into the bounded daily task; commissioning succeeds with NOT_DUE reuse while its rate gate is active. Sustained multi-day collection remains unproved. Policy review expires after 30 days for MET; changed or unknown licensing requires another review.

The reviewed source-scoped [team alias registry](../config/child-entity-crosswalk.json) is an authored bootstrap specification, not an independent competing sports database. Its actual review clock and complete versioned mappings are appended into SQL `child.entities`; runtime source records continue to reference immutable canonical IDs. Twenty real team records are separate from labelled synthetic permission/replay canaries. Global cross-provider equivalence and provider-issued IDs are not inferred from the local alias declarations.
