# CHILD scientific report

DRAGONHYDRACHILD has demonstrated a reproducible historical comparison and frozen its first current forecast before a conservative future schedule bound. It has **not** demonstrated real-market superiority, profitable decisions, a real-world research benefit or prospective forecasting accuracy. Scientific status is **PARTIAL**, maturity **EXPERIMENTAL**.

The experiment preserves four different kinds of evidence:

| Evidence class | What was demonstrated | What it does not establish |
| --- | --- | --- |
| Retained historical results | 380 OpenFootball 2023/24 fixtures; 321 expanding-window evaluations | Genuine historical capture or exact historical publication/kickoff times |
| Current captured results | 45 explicit current-season final results available before present inference | Historical pre-match feature availability for those results |
| Prospective prediction | Immutable issue time, evidence/features/model references and stored analysis hash | Accuracy before its actual outcome is observed |
| Controlled research and faults | Synthetic validation/recalculation and engineered failure detection | Population detection accuracy or real predictive value of research |

## Historical evidence and protocol

The source is the retained OpenFootball English Premier League 2023/24 file, SHA-256 `03e13eafbf78dfe00d7e89dd3bf6643986eb6e8fd86c7664aeb8c5bc0bed88d0`. Its actual original observed/retrieved time is 2026-09-24T17:56:42.321374+00:00. CHILD constructed derived inputs at 2026-09-24T20:44:11.221548+00:00. Neither clock was changed to 2023 or 2024.

Every historical input is **RECONSTRUCTED_PIT**. The declared decision horizon is **DAY_START_UTC_PROXY**, not a verified kickoff. The inherited policy assumes a fixture schedule is available one day before its source calendar date, represents completion by the next UTC day boundary, and assumes final-result availability two days after the source date. Source-name and round/team identity mappings are explicitly reconstructed. Genuine historical STRICT_PIT record count is **zero**.

The expanding-window protocol requires at least 50 available completed results before a forecast. It evaluates 321 of 380 fixtures and excludes 59 for insufficient available training history. There is no random split. A result unavailable at a horizon cannot enter features, estimation or adaptive ensemble weights. Same-time matches cannot learn one another's outcome. The first supplied schedule determines replay horizons; absent historical schedule revisions are not invented.

All seven model methods use shared typed feature/evidence and probability contracts. Seven base methods, a KNN ablation, two ensembles and a uniform benchmark produce eleven comparison rows. Fixed hyperparameters were declared before this evaluation. The [model report](CHILD_MODEL_REPORT.md) describes the actual methods and distinguishes the bounded Dixon–Coles correction from the full original joint, time-weighted procedure.

## Historical results

All rows below have **321 evaluated fixtures**. Lower proper-score values are better for this sample.

| Method | Log loss | RPS | Multiclass Brier |
| --- | ---: | ---: | ---: |
| League empirical | 1.058500 | 0.234043 | 0.639600 |
| Venue empirical | 1.021001 | 0.214819 | 0.606150 |
| Elo | 0.989816 | 0.208012 | 0.587538 |
| Independent Poisson | 0.981222 | 0.205419 | 0.582089 |
| Dixon–Coles correction | 0.979420 | 0.205252 | 0.581084 |
| Poisson GLM | 0.973495 | 0.203170 | 0.577028 |
| KNN classifier | 1.030123 | 0.219457 | 0.613707 |
| KNN without form/rest/congestion | 0.995200 | 0.206458 | 0.588491 |
| Equal-weight ensemble | 0.991230 | 0.208641 | 0.588592 |
| Prior-loss-weighted ensemble | 0.990813 | 0.208496 | 0.588304 |
| Uniform benchmark | 1.098612 | 0.241433 | 0.666667 |

Log loss uses natural logarithms. RPS uses ordered HOME/DRAW/AWAY cumulative squared errors divided by two. Brier is the unscaled sum across three classes; per-class terms are reported separately and are not presented as a Murphy decomposition. Calibration output contains five-bin classwise counts, mean predicted probability and observed frequency. Accuracy is secondary.

The [curated historical summary](evidence/child-science-summary.json) retains every metric, Brier component, calibration summary and paired date-block interval. The GLM had the lowest sample log loss; its per-class Brier terms were 0.217471 / 0.170688 / 0.188870. Its HOME/DRAW/AWAY five-bin ECE was 0.080457 / 0.013777 / 0.060042. The independent Poisson ECE was 0.028315 / 0.002100 / 0.021114. Lowest log loss did not also mean lowest value of each binned calibration diagnostic.

Four hundred seeded date-block bootstrap resamples describe within-season sensitivity. The GLM's mean log-loss difference against league empirical was −0.085005, with descriptive interval [−0.116121, −0.050022]. KNN's corresponding interval [−0.066307, +0.012296] includes zero. These intervals do not solve cross-season dependence, model-selection multiplicity, availability-assumption error or generalization to a different competition. Every result remains **DEMONSTRATION_ONLY / INSUFFICIENT_SAMPLE_FOR_STRONG_INFERENCE**.

## Negative results and feature value

Adding form, rest and congestion to the KNN representation worsened observed log loss from 0.995200 to 1.030123 compared with their joint removal. This is evidence against assuming that a larger feature set automatically improves this method. It is a bundle ablation, not an individual causal attribution.

The equal-weight and adaptive ensembles did not achieve the lowest sample loss. Adaptive weighting made only a small descriptive difference relative to equal weights. Weather's forecasting contribution is unmeasured. No source-usefulness comparison is claimed from a single historical fixture provider. These results constrain further expansion; they do not justify retrospective removal of inconvenient observations or tuning on the same test period.

## Reproducibility and feature semantics

The initial CPU run took 25.454 seconds. A separate frozen-input replay took 26.693 seconds and reproduced **every metric and prediction hash exactly** across all 321 evaluations. The common replay hash is `17429689fa0ec638e53e1d8ad805a68ec6b6717bc1f85ac1481a258c224b60a3`. See the [replay verification](evidence/child-science-replay.json).

The feature factory emits 22 outputs: sixteen historical measurements or missing-history indicators, plus three absent external fields and three corresponding missingness indicators. Lineup continuity, injury burden and market movement remain null. Each snapshot preserves input identities, availability policies, calculation version, code hash, units, missingness and confidence. New derived-input construction receives a new actual ingestion time; exact replay preserves the original recorded input clocks and records a new computation time. These are different operations.

LOCAL EVIDENCE PATH: `runtime/checkpoints/child-v3-v6-science-20260924T204411Z-7664718c`. The full historical report and raw input details remain local; the curated repository JSON contains aggregates and hashes. LOCAL EVIDENCE PATH: `runtime/checkpoints/child-v3-v6-replay-20260924T204619Z-80e0bbd4`.

## Current evidence and the frozen forecast

At the documented observatory run, 45 explicitly reported current-season final results were genuinely known to CHILD before current inference. Their **STRICT_PIT** label describes present knowledge captured in 2026. It does not assert that CHILD possessed them before their historical fixtures. Features still disclose source calendar-date proxies and unverified final-whistle times.

The source reported Manchester United FC versus Tottenham Hotspur FC on 2026-10-10. Its source-local `17:30` time has no verified timezone in this pipeline. CHILD therefore used **2026-10-09T10:00:00+00:00**, the earliest global UTC+14 boundary for the source date, as a conservative deadline—not as the actual kickoff. The selected fixture remains a source-reported schedule subject to correction.

Prediction `9111f65c-7ff9-46fa-bce1-f0d904d72948` was frozen at **2026-09-24T20:55:34.109013+00:00**, before that lower bound. Its analysis artifact hash is `0da25b128e6c48fc8f1b04fc0220804a16fc9884f6f1574706d91aa53c404640` and ledger event hash is `cff53aff78df080d5e78b77adfcd3f31d19575a93e6108e7fa507d8422002b90`.

| Frozen output | Probability |
| --- | ---: |
| Home | 0.498324 |
| Draw | 0.228724 |
| Away | 0.272952 |

Seven methods and 22 feature outputs were calculated. Equal weights were used because sufficient prior prospective scoring evidence did not exist. KNN had no genuinely historical pre-match feature frames in this current route and explicitly used its uniform prior. This limitation remains visible. Predictive entropy was 1.038925 nats and Jensen–Shannon model disagreement 0.025431 nats. The declared evidence confidence 0.8 is a policy value, not empirically calibrated reliability.

The forecast is **FROZEN_AWAITING_OUTCOME**. Zero real outcomes were scored in this run. Recomputing a current dashboard must not replace the frozen forecast. Outcomes append later with genuinely captured explicit final scores; an observed-by completion bound is distinguished from the exact final whistle.

LOCAL EVIDENCE PATH: `runtime/checkpoints/child-v8-v10-observatory-20260924T205534Z/summary.json`. The final [validation summary](evidence/child-validation-summary.json) records the repository-safe closure evidence.

## Simulation, uncertainty and research

Independent and low-score-corrected score matrices expose truncated mass, goal marginals, scorelines, HOME/DRAW/AWAY and goal totals. Scenario mixtures and seeded Monte Carlo propagate declared conditional rate hypotheses. Monte Carlo Wilson intervals measure simulation sampling error, not full epistemic confidence or model credibility. Scenario weights are assumptions, not observed injuries or lineups.

The observatory's separate **synthetic controlled** availability experiment changed a declared hypothetical forecast from (0.40, 0.30, 0.30) to (0.60, 0.25, 0.15). Entropy changed from 1.088900 to 0.937637 nats, a reduction of **0.151263 nats**; required-field completeness changed from 1/2 to 2/2. Validation, provenance retention and recalculation executed. This synthetic answer was not incorporated as a real player fact into the frozen match forecast. It does not demonstrate a real-world reduction in forecasting error. The separate unit-test scenario described in the [uncertainty report](CHILD_UNCERTAINTY_REPORT.md) has different declared probabilities and therefore a different entropy change.

The system distinguishes outcome randomness, model disagreement, missing information and evidence limitations, but has not identified a statistically validated full aleatoric/epistemic decomposition. Lower entropy alone can mean misplaced confidence. Proper scoring after real outcomes remains mandatory.

## Sources, MEDUSA and GPU measurements

OpenFootball commissioning recorded four actual attempts: two accepted acquisitions and two local parser/validation failures. Transport succeeded on all four; validated acquisition rate was 0.5, mean elapsed attempt latency 2.873 seconds, and observed content revisions zero. These are commissioning measurements, not a long-term provider reliability estimate. The failed attempts remain evidence.

A second provider, MET Norway, supplied 65 future London-proxy forecast points. Capturing the provider forecast is genuine; its future weather values remain **HYPOTHESIS**, with no verified stadium mapping or demonstrated predictive effect. Open-Meteo remained robots-blocked and its forecast endpoint was not requested. See the [weather summary](evidence/child-weather-summary.json). There is no lawful real odds feed in this experiment, so market comparison is **BLOCKED** rather than filled with synthetic market data.

MEDUSA's controlled challenge detected seven of seven engineered faults: duplicate, invalid same-team identity, future timestamp, stale record, malformed timestamp/schema, conflicting observation and missing provenance. One valid control produced zero false positives. This small designed challenge does not estimate real-world catch rate or entity-resolution accuracy.

The optional GPU experiment used NumPy 2.5.3, PyTorch 2.14.0+cu132 and an NVIDIA GeForce RTX 3050, comparing float64 finite Poisson grids with identical CPU/GPU outputs to a maximum observed difference of 5.55×10⁻¹⁶. Medians use three repeats and GPU times include transfers.

| Batch | CPU median ms | GPU end-to-end median ms | CPU/GPU ratio | Faster measured path |
| ---: | ---: | ---: | ---: | --- |
| 1 | 0.133 | 1.791 | 0.074 | CPU |
| 256 | 0.254 | 1.861 | 0.136 | CPU |
| 4,096 | 4.139 | 2.417 | 1.712 | GPU |
| 32,768 | 40.924 | 4.891 | 8.368 | GPU |

The measured crossover lies somewhere between the tested batches 256 and 4,096; its exact location was not measured. The first timed CUDA operation cost 21.131 ms. Peak allocated GPU memory at batch 32,768 was 82,445,824 bytes; the CPU matrix-only estimate was 44,302,336 bytes, which is not an equal-method process peak comparison. No production backend was changed. This one-machine calculation does not establish any prediction-accuracy advantage. LOCAL EVIDENCE PATH: `runtime/checkpoints/child-v0-gpu-and-v4-benchmark/benchmark.json`.

## Tests, remaining questions and next scientific work

Focused temporal, known-answer, replay, feature, simulation, model, ensemble and observatory tests verify the implemented contracts. The final portable/local totals, failures and GitHub results are recorded in the [validation summary](evidence/child-validation-summary.json); component counts are not substituted for a completed whole-repository run.

Remaining limits are material: one reconstructed historical season; only 45 current final results at first inference; no independent historical fixture corroboration; incomplete cross-provider and player identity; unverified kickoff timezone; absent real odds; no scored prospective outcome; no demonstrated real research benefit; no clean-machine full laboratory bootstrap; no evidence yet of sustained multi-day acquisition; and no validated weather, lineup or injury contribution.

The next scientific evidence must come from continued lawful collection, preservation of frozen forecasts, later outcome scoring and a separately declared multi-season or prospective comparison. Additional architectures and features must not be counted as predictive progress until those measurements exist.
