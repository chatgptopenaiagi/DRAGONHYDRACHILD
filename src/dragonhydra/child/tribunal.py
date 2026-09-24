"""Mathematical ensembles with explicit disagreement; no synthetic AI debate."""
from dataclasses import dataclass
from datetime import datetime
from math import fsum, exp, log, isfinite

from dragonhydra.science.evaluation import Probabilities
from dragonhydra.science.temporal import aware_utc
from .models import ModelForecast


@dataclass(frozen=True, slots=True)
class PastScore:
    model_id: str
    fixture_id: str
    prediction_at: datetime
    outcome_available_at: datetime
    log_loss: float

    def __post_init__(self):
        if aware_utc(self.prediction_at) >= aware_utc(self.outcome_available_at):
            raise ValueError("score must follow forecast")
        if not isfinite(self.log_loss) or self.log_loss < 0:
            raise ValueError("past log loss must be finite and nonnegative")


def entropy(probabilities: Probabilities) -> float:
    return -fsum(p*log(p) for p in probabilities.values if p)


def compare(forecasts: tuple[ModelForecast, ...], at: datetime, scores=(), *, minimum_scores=30) -> dict:
    at = aware_utc(at)
    if not isinstance(minimum_scores, int) or isinstance(minimum_scores, bool) or minimum_scores < 1:
        raise ValueError("a positive integer past-score floor is required")
    if not forecasts or len({f.model_id for f in forecasts}) != len(forecasts):
        raise ValueError("unique model forecasts required")
    if len({(f.feature_snapshot_id, f.prediction_at, f.temporal_mode) for f in forecasts}) != 1:
        raise ValueError("models must share feature snapshot, cursor and temporal mode")
    if any(f.prediction_at != at for f in forecasts):
        raise ValueError("tribunal cursor must match forecast cursor")
    prior = [s for s in scores if s.outcome_available_at <= at and s.prediction_at < at]
    losses = {f.model_id: [s.log_loss for s in prior if s.model_id == f.model_id] for f in forecasts}
    weights = {f.model_id: 1/len(forecasts) for f in forecasts}
    weighting = "EQUAL_WEIGHT_INSUFFICIENT_PRIOR_SCORES"
    if all(len(values) >= minimum_scores for values in losses.values()):
        raw = {key: exp(-fsum(vals)/len(vals)) for key, vals in losses.items()}
        weights = {key: value/fsum(raw.values()) for key, value in raw.items()}
        weighting = "EXP_NEGATIVE_PRIOR_MEAN_LOG_LOSS"
    equal = Probabilities(*(fsum(f.probabilities.values[i] for f in forecasts)/len(forecasts) for i in range(3)))
    weighted = Probabilities(*(fsum(weights[f.model_id]*f.probabilities.values[i] for f in forecasts) for i in range(3)))
    disagreement = entropy(equal) - fsum(entropy(f.probabilities) for f in forecasts)/len(forecasts)
    return {"equal_weight": equal.to_dict(), "weighted": weighted.to_dict(), "weights": weights,
            "weighting_method": weighting, "prior_score_counts": {k: len(v) for k, v in losses.items()},
            "jensen_shannon_disagreement_nats": max(0., disagreement),
            "class_probability_ranges": [max(f.probabilities.values[i] for f in forecasts)-min(f.probabilities.values[i] for f in forecasts) for i in range(3)],
            "calibration_status": "UNCALIBRATED_NO_HELD_OUT_CALIBRATION_FIT",
            "epistemic_state": "PREDICTION", "temporal_mode": forecasts[0].temporal_mode.value,
            "caveat": "loss weights are a tested adaptive ensemble, not evidence of superiority"}
