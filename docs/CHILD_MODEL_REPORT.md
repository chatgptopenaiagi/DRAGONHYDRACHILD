# CHILD model and simulation report

The CHILD implements seven competing forecasting methods, two ensembles and a uniform benchmark. The implementation is experimental. Historical evaluation is an expanding chronological replay; reconstructed publication assumptions remain visible. No model is declared superior from one season, and no profitability inference is made.

## Methods

| Method | Actual implementation | Fixed controls / limits |
| --- | --- | --- |
| League empirical | Inherited Laplace-smoothed HOME/DRAW/AWAY frequencies | Pseudocount 1 per class |
| Venue empirical | Inherited home-team home and away-team away outcome frequencies, shrunk to league distribution | Prior strength 5 |
| Elo | Sequential team ratings; home offset and a league draw component | Initial 1500, K=20, home offset 65; draw treatment is a simple uncalibrated heuristic |
| Poisson | Venue attack/defence multiplicative scoring rates and independent Poisson score matrix | Five-match rate prior; target rates bounded 0.05–8 |
| Dixon–Coles correction | Poisson rates plus fitted low-score correction on 0–0, 0–1, 1–0 and 1–1 cells | Training-only penalized grid rho −0.15 to +0.15; every candidate must leave all training and target probabilities positive |
| Poisson GLM | Log-rate intercepts plus team attack and defence parameters; regularized likelihood gradients | Ridge 0.04, 70 batch iterations, step 0.08; no claim of optimizer convergence or reproduction of a statistical package |
| KNN classifier | Standardized historical feature distance, nearest outcomes and Laplace smoothing | 25 neighbors; scaling and missing-value means fitted on available training examples only |

The GLM and multiplicative rate estimator share a Poisson conditional distribution but use different estimation procedures. KNN is the distinct machine-learning baseline. Dixon–Coles here means the low-score correction with bounded fitted rho; it does **not** claim the full original time-weighted joint optimization procedure. There is no neural model in the production forecast path.

The [models implementation](../src/dragonhydra/child/models.py) uses the inherited typed probability and outcome contracts. Each result records model version, training window/count, feature snapshot, decision cursor, temporal mode, runtime, hardware, parameters and calibration state. Model failures propagate to the caller rather than silently producing a fabricated forecast.

Mathematical references: the [original Dixon–Coles paper](https://rss.onlinelibrary.wiley.com/doi/10.1111/1467-9876.00065), [statsmodels GLM family documentation](https://www.statsmodels.org/stable/glm.html), and [scikit-learn nearest-neighbor classifier documentation](https://scikit-learn.org/stable/modules/generated/sklearn.neighbors.KNeighborsClassifier). The packages are methodological references, not added runtime dependencies.

## Feature factory and analytical export

[Features](../src/dragonhydra/child/features.py) retain name/version, value/unit, evidence IDs, calculation method, code SHA-256, availability, decision cursor, missing-data behavior and confidence. Snapshot hashes include input evidence and its full temporal assumptions. Sixteen outputs cover each team's recent form, overall and venue goal rates, rest, 14-day congestion and history missingness. Six more outputs explicitly represent absent lineup, injury and market inputs as null plus missing indicators. These missing fields are not claims of collected data.

The historical records use canonical fixture and team identities. Result revisions are resolved as of the decision time; the forecast fixture's own result is excluded. First supplied schedule determines replay horizons. This does not reconstruct unavailable historical schedule-revision archives.

A typed JSON analytical export is implemented. It labels derived features and retains SQL Server's structured-intelligence ownership. DuckDB and Parquet are not activated without a measured workload justification.

## Simulation and Tribunal

[Simulation](../src/dragonhydra/child/simulation.py) provides independent and corrected exact score matrices, goal marginals, HOME/DRAW/AWAY, over 2.5 goals, explicit truncated tail mass, weighted conditional scenarios and seeded Monte Carlo. HOME/DRAW/AWAY and over/under outputs are conditional on the retained matrix; they are never silently called the full infinite support. Default support 0–20 makes the tail small at usual rates, while still reporting it.

Monte Carlo optionally propagates a declared mean-preserving lognormal rate hypothesis. Its Wilson intervals describe sampling error in the simulation, not full epistemic uncertainty. Scenario weights and rate perturbations are hypotheses; neither injuries nor lineups are invented.

The [Tribunal](../src/dragonhydra/child/tribunal.py) reports equal-weight and exponential-negative-prior-mean-log-loss ensembles. Adaptive weights begin only after every participant has at least 30 genuinely earlier, outcome-available evaluation scores. It exposes class ranges and Jensen–Shannon disagreement. It does not fit a stacking model on the current test outcomes. Outputs remain marked uncalibrated because no independent calibration fit has been established.

## Evaluation and limitations

[Walk-forward evaluation](../src/dragonhydra/child/evaluation.py) rebuilds features and fits methods at each declared horizon using only eligible results. Same-time matches cannot learn one another's result. Test outcomes are scored after prediction; the Tribunal independently filters scores by outcome availability. The report distinguishes actual computation time from historical simulated issuance time.

Metrics are natural-log loss, RPS (HOME/DRAW/AWAY ordered cumulative errors divided by two), unscaled multiclass Brier (sum of three squared errors), per-class Brier terms, five-bin classwise calibration data/ECE and secondary accuracy. Date-block bootstrap intervals accompany paired log-loss differences against the league baseline. Four hundred seeded resamples describe this sample's sensitivity; they do not establish multi-season robustness or correct all serial dependence.

The KNN ablation removes form, rest and congestion jointly. It measures that particular bundle, not each feature's independent causal value. No source ablation is claimed from a single inherited provider. Final measured historical metrics belong in the CHILD scientific report and curated evidence generated by the integration run.

The [science tests](../tests/test_child_science.py) cover temporal canaries, revision replay, strict/reconstructed separation, unavailable schedules, forged future snapshots, missingness, deterministic feature hashes and exports, model contract compatibility, training-frame guards, GLM direction, KNN priors, score-matrix mass/tails, Dixon–Coles bounds, conditional scenarios, Monte Carlo agreement, scoring known answers, chronological ties, Tribunal score availability and replay determinism.

## Complexity ownership

| Component | Why it exists | Dependencies | Measurement / failure | Removal path |
| --- | --- | --- | --- | --- |
| Feature factory | Recreate declared knowledge at a decision cursor | Inherited temporal/evidence contracts | Snapshot hashes, leakage tests; missing/ambiguous evidence stays absent | Retain serialized snapshot schema; replace calculator version |
| Seven methods | Compare competing falsifiable hypotheses | Standard library, shared snapshots/probabilities | Walk-forward proper scores, runtime; bad fit stays visible | Remove method registry entry; keep historical forecasts |
| Simulation | Express distributions and conditional assumptions | Typed goal rates | Matrix mass, Monte Carlo agreement, explicit tail | Retain distribution contract, remove optional simulation method |
| Tribunal | Preserve disagreement and compare simple ensemble policies | Available historical evaluation scores | Proper scores versus equal weight; insufficient samples preserve equal weights | Keep individual forecasts and equal-weight baseline |
| Evaluation | Make complexity earn predictive value | Immutable snapshots and scoring labels | Reproducible replay, date-block sensitivity | Version protocol; never mutate old evaluation records |

## Measured retained-source experiment

The CHILD run on 2026-09-24 used the preserved OpenFootball 2023/24 raw SHA-256 `03e13eafbf78dfe00d7e89dd3bf6643986eb6e8fd86c7664aeb8c5bc0bed88d0`. Of 380 fixtures, 321 passed the minimum 50 available training-result gate. The horizon is **DAY_START_UTC_PROXY**, every historical input is **RECONSTRUCTED_PIT**, and genuine historical STRICT_PIT record count is zero. Actual CHILD derived ingestion is 2026-09-24T20:44:11.221548+00:00; original capture clocks remain separate. CPU computation took 25.454 seconds on Python 3.14.7.

| Method | Log loss | RPS | Brier |
| --- | ---: | ---: | ---: |
| League empirical | 1.058500 | 0.234043 | 0.639600 |
| Venue empirical | 1.021001 | 0.214819 | 0.606150 |
| Elo | 0.989816 | 0.208012 | 0.587538 |
| Poisson | 0.981222 | 0.205419 | 0.582089 |
| Dixon–Coles correction | 0.979420 | 0.205252 | 0.581084 |
| Poisson GLM | 0.973495 | 0.203170 | 0.577028 |
| KNN | 1.030123 | 0.219457 | 0.613707 |
| KNN without form/rest/congestion | 0.995200 | 0.206458 | 0.588491 |
| Equal-weight ensemble | 0.991230 | 0.208641 | 0.588592 |
| Prior-loss-weighted ensemble | 0.990813 | 0.208496 | 0.588304 |
| Uniform | 1.098612 | 0.241433 | 0.666667 |

These are descriptive results for this one reconstructed season. The KNN date-block interval for log-loss difference against league baseline spans zero (−0.0663 to +0.0123). Its form/rest/congestion bundle worsened observed log loss compared with the ablation; adding features did not automatically help. The ensembles did not produce the lowest sample loss. The GLM had the lowest sample loss but classwise five-bin ECE of approximately 0.0805 / 0.0138 / 0.0600; lowest loss is not a claim of perfect calibration or future superiority. No multi-season or prospective generalization claim follows.

The [curated science summary](evidence/child-science-summary.json) contains all comparison metrics, Brier components, calibration summaries and date-block intervals. LOCAL EVIDENCE PATH: `runtime/checkpoints/child-v3-v6-science-20260924T204411Z-7664718c` retains full predictions, feature example, simulation example, identity registry, input metadata and a manifest. Run the [CHILD research runner](../src/dragonhydra/child/research_run.py) to create a new immutable research run; no network or database mutation occurs.

A separate [frozen-input replay](evidence/child-science-replay.json) reproduced every metric and the exact prediction hash `17429689fa0ec638e53e1d8ad805a68ec6b6717bc1f85ac1481a258c224b60a3` across all 321 evaluated fixtures in 26.693 seconds. Replay preserves the saved evidence clocks and records a new computation clock. A fresh derived-input construction receives a new ingestion timestamp and consequently a different evidence identity; it is intentionally distinct from replaying frozen inputs.

Maturity: EXPERIMENTAL. Mathematical/unit gates can be COMPLETE while prospective, multi-season and real-market validation remain PARTIAL or BLOCKED in the overall version matrix.
