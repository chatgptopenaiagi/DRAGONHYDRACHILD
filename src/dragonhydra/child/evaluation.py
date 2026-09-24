"""Chronological replay, permanent baselines and explicitly labelled uncertainty."""
from datetime import datetime, timezone
from math import fsum
from random import Random

from dragonhydra.science.evaluation import Probabilities, Outcome, score_prediction
from dragonhydra.science.temporal import TemporalMode, DecisionHorizon
from .features import MatchEvidence, build_features, digest
from .models import predict_models
from .tribunal import PastScore, compare


def probabilities_from_dict(value):
    return Probabilities(value["HOME"], value["DRAW"], value["AWAY"])


def summarize(pairs: list[tuple[Probabilities, Outcome]], bins=5) -> dict:
    if not isinstance(bins, int) or isinstance(bins, bool) or not 1 <= bins <= 100:
        raise ValueError("calibration bins must be 1..100")
    scores = [score_prediction(p, y) for p, y in pairs]
    n = len(scores)
    calibration = []
    ece = []
    for index, label in enumerate((Outcome.HOME, Outcome.DRAW, Outcome.AWAY)):
        error = 0.
        for bucket in range(bins):
            members = [(p.values[index], float(y == label)) for p, y in pairs
                       if min(bins-1, int(p.values[index]*bins)) == bucket]
            mean = fsum(p for p, _ in members)/len(members) if members else None
            frequency = fsum(y for _, y in members)/len(members) if members else None
            if members: error += len(members) * abs(mean-frequency) / n
            calibration.append({"class": label.value, "bucket": bucket, "count": len(members),
                                "mean_probability": mean, "observed_frequency": frequency})
        ece.append(error if n else None)
    infinite = any(s.log_loss_infinite for s in scores)
    return {"matches": n, "log_loss": fsum(s.log_loss for s in scores)/n if n and not infinite else None,
            "log_loss_infinite": infinite, "rps": fsum(s.rps for s in scores)/n if n else None,
            "brier": fsum(s.brier for s in scores)/n if n else None,
            "brier_per_class": [fsum(s.brier_components[i] for s in scores)/n if n else None for i in range(3)],
            "accuracy_secondary": sum(s.correct for s in scores)/n if n else None,
            "classwise_ece_5bins": ece, "calibration": calibration}


def _paired_intervals(rows, benchmark="LEAGUE_EMPIRICAL", draws=400):
    """Date-block bootstrap describes this sample; league/season generalization unproven."""
    groups = {}
    for row in rows:
        groups.setdefault(row["prediction_issued_at"][:10], []).append(row)
    blocks = list(groups.values())
    if not blocks: return {}
    models = list(rows[0]["scores"])
    result = {}
    for model in models:
        rng, samples = Random(0), []
        for _ in range(draws):
            selected = [r for _ in blocks for r in rng.choice(blocks)]
            differences = [r["scores"][model]["log_loss"]-r["scores"][benchmark]["log_loss"] for r in selected]
            samples.append(fsum(differences)/len(differences))
        samples.sort()
        result[model] = {"benchmark": benchmark, "mean_log_loss_difference":
                         fsum(r["scores"][model]["log_loss"]-r["scores"][benchmark]["log_loss"] for r in rows)/len(rows),
                         "date_block_bootstrap_95pct": [samples[int(draws*.025)], samples[int(draws*.975)-1]],
                         "resamples": draws, "seed": 0,
                         "limitation": "within-season dependent sample; not robust multi-season inference"}
    return result


def walk_forward(records, *, mode=TemporalMode.RECONSTRUCTED_PIT, min_training=50,
                 horizon=None, computed_at=None, include_predictions=True) -> dict:
    """Fit every model afresh using only results available before that target.

    Results are labelled historical replay. Latest supplied result revisions are
    scoring labels only; as-of training independently resolves prior revisions.
    First supplied fixture schedule is the reconstruction horizon; historical
    schedule-revision recovery is not invented by this harness.
    """
    mode = TemporalMode(mode)
    horizon = horizon or DecisionHorizon.named("KICKOFF")
    computed_at = computed_at or datetime.now(timezone.utc)
    if not isinstance(min_training, int) or isinstance(min_training, bool) or min_training < 1:
        raise ValueError("positive integer training floor required")
    if computed_at.tzinfo is None or computed_at.utcoffset() is None:
        raise ValueError("actual computation timestamp must be timezone aware")
    records = tuple(records)
    first, latest = {}, {}
    for r in sorted(records, key=lambda r: (r.fixture_id, r.revision)):
        first.setdefault(r.fixture_id, r)
        latest[r.fixture_id] = r
    frames, skipped = {}, []
    for row in first.values():
        at = horizon.target(row.kickoff_at)
        if not row.schedule_availability.eligible(at, mode):
            skipped.append({"fixture_id": row.fixture_id, "reason": "SCHEDULE_UNAVAILABLE_AT_HORIZON"})
            continue
        frames[row.fixture_id] = build_features(row.target(), records, at, mode)
    rows, prior_scores, all_pairs = [], [], {}
    for row in sorted(first.values(), key=lambda r: (horizon.target(r.kickoff_at), r.fixture_id)):
        if row.fixture_id not in frames: continue
        snapshot = frames[row.fixture_id]
        at = snapshot.target_as_of_at
        if len(snapshot.evidence) < min_training:
            skipped.append({"fixture_id": row.fixture_id, "reason": "INSUFFICIENT_TRAINING_HISTORY"})
            continue
        # Training labels are the as-of selected versions, never current final rows.
        training_frames = tuple((frames[r.fixture_id], r) for r in snapshot.evidence if r.fixture_id in frames)
        forecasts = predict_models(snapshot, row.target(), training_frames=training_frames, include_ablation=True)
        base_forecasts = tuple(f for f in forecasts if not f.model_id.startswith("KNN_ABLATION"))
        tribunal = compare(base_forecasts, at, prior_scores)
        outputs = {f.model_id: f.probabilities for f in forecasts}
        outputs["ENSEMBLE_EQUAL"] = probabilities_from_dict(tribunal["equal_weight"])
        outputs["ENSEMBLE_PAST_LOSS"] = probabilities_from_dict(tribunal["weighted"])
        outputs["UNIFORM"] = Probabilities(1/3, 1/3, 1/3)
        actual = latest[row.fixture_id]
        score_output = {}
        for name, probs in outputs.items():
            scored = score_prediction(probs, actual.outcome)
            score_output[name] = {"log_loss": scored.log_loss, "rps": scored.rps, "brier": scored.brier}
            all_pairs.setdefault(name, []).append((probs, actual.outcome))
            if actual.availability.available_at is not None and scored.log_loss is not None:
                prior_scores.append(PastScore(name, row.fixture_id, at, actual.availability.available_at, scored.log_loss))
        item = {"fixture_id": row.fixture_id, "prediction_issued_at": at.isoformat(),
                "issuance_kind": "HISTORICAL_REPLAY", "decision_horizon": horizon.to_dict(),
                "temporal_mode": mode.value, "feature_snapshot_id": snapshot.snapshot_id,
                "evidence_snapshot_id": digest([r.to_dict() for r in snapshot.evidence]),
                "training_record_ids": [r.record_id for r in snapshot.evidence],
                "schedule_availability": row.schedule_availability.to_dict(),
                "outcome_record_id": actual.record_id, "outcome": actual.outcome.value,
                "outputs": {k: p.to_dict() for k, p in outputs.items()},
                "forecasts": [f.to_dict() for f in forecasts], "tribunal": tribunal, "scores": score_output}
        immutable = {k: v for k, v in item.items() if k not in ("forecasts", "scores", "outcome", "outcome_record_id")}
        item["prediction_id"] = digest(immutable)
        rows.append(item)
    metrics = {name: summarize(pairs) for name, pairs in all_pairs.items()}
    return {"schema_version": "dragonhydra.child.walk-forward/1", "computed_at": computed_at.isoformat(),
            "temporal_mode": mode.value, "issuance_kind": "HISTORICAL_REPLAY",
            "inference_status": ["DEMONSTRATION_ONLY", "INSUFFICIENT_SAMPLE_FOR_STRONG_INFERENCE"],
            "protocol": {"min_training": min_training, "decision_horizon": horizon.to_dict(),
                         "window": "EXPANDING", "tie_handling": "OUTCOMES_UNAVAILABLE_UNTIL_COMPLETION_PLUS_POLICY_DELAY",
                         "hyperparameters": "FIXED_BEFORE_EVALUATION", "calibration_bins": 5,
                         "scoring_label": "LATEST_SUPPLIED_RESULT_REVISION", "schedule_policy": "FIRST_SUPPLIED_SCHEDULE"},
            "input_fixture_count": len(first), "evaluation_matches": len(rows), "feature_count": 22,
            "model_count": 7, "metrics": metrics, "paired_log_loss": _paired_intervals(rows),
            "ablation": {"model": "KNN", "comparison": "KNN_ABLATION_NO_FORM_REST",
                         "meaning": "joint removal of form/rest/congestion; no individual causal feature claim"},
            "predictions": rows if include_predictions else [], "skipped": skipped,
            "evidence_registry": {r.record_id: {"availability": r.availability.to_dict(),
                                   "schedule_availability": r.schedule_availability.to_dict()} for r in records},
            "replay_hash": digest([r["prediction_id"] for r in rows]),
            "limitations": ["ONE_SEASON_DEMONSTRATION", "NO_REAL_ODDS_BENCHMARK_IN_THIS_HARNESS",
                            "NO_PROFITABILITY_INFERENCE", "NO_TRUE_HISTORICAL_CAPTURE_RECOVERY",
                            "NO_COMPLETE_HISTORICAL_SCHEDULE_REVISION_RECOVERY",
                            "FEATURE_AND_HYPERPARAMETER_SELECTION_NOT_EXTERNALLY_VALIDATED"]}
