# CHILD source acquisition report

Status: **PARTIAL / EXPERIMENTAL**, inspected 2026-09-24. Two providers have genuine CHILD captures: OpenFootball fixtures/results and MET Norway weather forecasts. They do not establish two independent fixture feeds, complete league intelligence or useful weather predictors.

| Provider | Captured scope and policy | Evidence limits |
| --- | --- | --- |
| OpenFootball | One reviewed 2026–27 English Premier League JSON endpoint; 380 fixture entries per accepted snapshot; CC0-1.0 under the [retained source policy](../config/web_sources.json). Two genuine validated captures. | Community dataset; provider publication time and local kickoff timezone remain unknown. Canonical IDs use declared provider names and round/team keys. No invented UTC kickoff or historically backdated capture. |
| MET Norway | One exact London coordinate query; 65 future forecast points captured at `2026-09-24T20:51:26.041046+00:00`; reviewed research use and CC BY 4.0 attribution. [Curated capture evidence](evidence/child-weather-summary.json). | London is a coordinate proxy, not a verified stadium. Values are HYPOTHESIS. STRICT_PIT describes capture availability, not observation of future weather. No predictive benefit is demonstrated. |

Forecast data from [MET Norway](https://api.met.no/weatherapi/locationforecast/2.0/documentation), licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Changes: selected future times and normalized temperature/precipitation units. No endorsement is implied. MET's [terms](https://api.met.no/doc/TermsOfService) and [license](https://api.met.no/doc/License) have retained reviewed hashes.

## Preserved blocks

Open-Meteo's API robots policy returned `Disallow: /`; its receipt remains ROBOTS_BLOCKED and the forecast endpoint was not requested. MET Norway has its own independently reviewed endpoint/policy; it does not bypass that refusal.

Football-Data's official [data page](https://football-data.co.uk/data.php) excludes the automated bot/scraper/AI and data-training workflow contemplated here: TERMS_BLOCKED, no odds dataset downloaded. [The Odds API terms](https://the-odds-api.com/terms-and-conditions.html) permit research/storage/model use with restrictions on standalone raw-data redistribution, but registered access needs a private key: AUTH_REQUIRED. No real odds have been acquired. See the [odds report](CHILD_ODDS_REPORT.md). Unreviewed or blocked inherited source candidates remain disabled; raw public accessibility is not ingestion approval.

## Measured acquisition and validation

At inspection, OpenFootball's immutable attempt receipts show **4 attempts, 4 successful transports, 2 validated acquisitions and 2 local parser/gate failures**. Transport availability is 1.0; validated-acquisition rate is 0.5. The two failed local attempts are retained rather than charged to provider uptime or removed from the denominator. Mean attempt latency is approximately 2.87 seconds. The accepted captures have identical content hashes: zero observed content revisions. This short commissioning history cannot estimate long-term reliability, correction accuracy or entity-resolution accuracy.

The [acquisition module](../src/dragonhydra/child/acquisition.py) records deterministic MEDUSA reason codes. A labeled synthetic challenge detected all seven engineered faults: invalid entity, future timestamp, stale evidence, schema mutation, missing provenance, duplicate and conflicting observation. One valid control was accepted; zero false positives occurred in that control. **Seven engineered faults are not a real-world detection-rate estimate.** Stale/conflicting cases are quarantined; invalid cases are rejected.

Accepted evidence preserves raw content-addressed bytes, source/policy hashes, parser version, actual observed/retrieved/available clocks and append-only snapshot identity. SQL Server stores structured revisions; MariaDB caches presentation. [Database ownership and replay evidence](CHILD_DATABASE_REPORT.md) distinguish these roles.

## Bounded operation

[Fixture acquisition](../src/dragonhydra/child/acquisition.py) uses an exclusive lock, at least 60 seconds between attempts, at most four attempts per rolling day, one exact data endpoint and no automatic retry. Policy/robots checks precede acquisition. The [weather adapter](../src/dragonhydra/child/weather.py) permits one fixed coordinate query, daily and provider-Expires gates, conditional GET, a 30-day policy-review lifetime and no retry. MET attempts are bounded to four logical requests and eight wire requests including narrowly allowed redirects; compressed and expanded bodies are size-bounded. Other coordinates or arbitrary endpoints are rejected.

The [scheduler manager](../scripts/Manage-ChildScheduler.ps1) binds the daily `DRAGONHYDRACHILD-Prospective` task to CHILD, Python 3.14 and [the collector entry point](../scripts/child_collect.py). It uses interactive owner logon, limited privilege, no stored account password, a three-minute execution limit and no concurrent instances. The owner must be signed in. Disable with `scripts/Manage-ChildScheduler.ps1 -Action Disable`.

A current multi-stage invocation completed at `2026-09-24T21:05:24.438679+00:00`: fixtures and weather correctly returned NOT_DUE, while analysis/prediction/scoring/presentation completed using retained evidence. This verifies bounded reuse, not a new capture or sustained daily operation. The commissioning task previously reported last result 0; future scheduled-day history remains an external gate.

LOCAL EVIDENCE PATHS: `runtime/child/acquisition`, `runtime/prospective/met-norway-london`, `runtime/child/job-runs/3a469a23bdec4b21af109fa2ddd91a2e.json`. These ignored paths are deliberately not repository hyperlinks.

NEXT_EXACT_ACTION: verify the next due scheduled capture and append/replay behavior, then investigate one permitted source for the highest-priority real information gap. Do not invent missing odds, players, lineups or timezone evidence.
