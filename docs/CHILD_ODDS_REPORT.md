# CHILD odds engineering report

State: **PARTIAL / EXPERIMENTAL**. Timestamped market contracts and numerical methods are implemented and synthetically tested. Real odds ingestion, historical market benchmarks and demonstrated market forecasting remain blocked. No profit or model-superiority claim is made.

## Implemented boundary

[odds.py](../src/dragonhydra/child/odds.py) accepts finite decimal HOME/DRAW/AWAY prices above one, explicit quote/kickoff times, source URL, parser/policy versions, raw hash, availability contract and a separate synthetic label. Quote time cannot follow kickoff; availability cannot precede the quote. Reconstructed snapshots remain RECONSTRUCTION, with the original policy metadata retained.

Proportional normalization divides implied probabilities by their sum. The power method finds a positive exponent such that the powered implied probabilities sum to one. Both support overround and underround inputs. These are mathematical transformations, not proof of true outcome probability. The method reference is [Clarke, Kovalchik and Ingram (2017)](https://sciencepublishinggroup.com/article/10.11648/j.ajss.20170506.12). No statistical package was added.

Public market selection, first/latest retained quotes, consensus and trajectories require an explicit as-of time and temporal mode. Consensus uses one latest eligible quote per bookmaker. Future quotes and later-available observations cannot enter earlier calculations. Mixed fixtures, unresolved schedule revisions and mixtures of synthetic/real observations are rejected. A first retained quote is not claimed to be the market opening; a latest retained quote is not claimed to be the closing price without an explicit closing-evidence reference.

Trajectory velocity reports probability change per hour. The bounded future extrapolation is labeled HYPOTHESIS and states that it is not a validated forecasting model. It cannot become an observed fact in the [temporal continuum](CHILD_TEMPORAL_CONTINUUM_REPORT.md). No bookmaker execution exists.

Equal provider quote timestamps are ordered by actual availability before any identity tie-break. Corrections with the same quote time therefore replace earlier-known values only from their own availability onward. Conflicting prices with identical quote/availability clocks fail closed. Trajectory velocity uses the latest eligible revision at each distinct quote time. Captures reject quote timestamps after their observation clock. Exported consensus reports, retained-price summaries, trajectories and future hypotheses preserve input availability policies, reconstruction labels, source hashes and synthetic status; the bare `consensus()` function remains a numerical primitive.

Provider, bookmaker and market identities are deterministic hashes of explicit provider-scoped keys, independent of display names. Market identity includes the canonical fixture and regulation H/D/A contract; it does not depend on kickoff time. No fuzzy resolution engine is added. Cross-provider bookmaker consensus is refused until an explicit crosswalk prevents duplicate aliases being counted twice.

## Source review, 2026-09-24

| Candidate | Evidence | CHILD decision |
| --- | --- | --- |
| Football-Data | Its official [data page](https://football-data.co.uk/data.php) restricts use by automated bots/scrapers/AI and data-training products. The page also cautions about stale Pinnacle prices. | TERMS_BLOCKED for this automated modeling workflow; no dataset downloaded. |
| The Odds API | Official [terms](https://the-odds-api.com/terms-and-conditions.html), updated 2026-08-31, permit retention, research and statistical/model use while restricting standalone raw-data redistribution; registered access uses a private key. | AUTH_REQUIRED. No key provisioned or API data fetched in this block. Future approval must retain source-policy and timestamp semantics. |

This source review is not legal advice or a transferable sports-data license. Repository code policy and external-data permission remain separate. Robots permission does not override terms. Credentials and raw captures never belong in Git.

## Validation and limitations

[Intelligence contract tests](../tests/test_child_intelligence.py) cover decimal validity, normalization, known answers, underround handling, as-of leakage, consensus deduplication, equal-quote revision replay, reconstruction metadata retention, future-hypothesis labels, source-policy refusal and ledger integrity. The scoped suite has 25 passing tests under Python 3.14 with no new dependencies. An initial exact floating-point equality assertion differed at the final decimal digit; it was corrected to a numerical tolerance. This did not change the production calculation.

There are **zero real odds observations in this implementation evidence**. Synthetic prices exist solely in tests. A genuine lawful market source, actual quote history, empirically evaluated demargin choices and market benchmark comparisons remain necessary before the V7 external gate can pass.

NEXT_EXACT_ACTION: provision owner-authorized access to one permitted odds source, retain its terms/policy snapshot and acquisition timestamps, then demonstrate a bounded real snapshot without publishing restricted raw data.
