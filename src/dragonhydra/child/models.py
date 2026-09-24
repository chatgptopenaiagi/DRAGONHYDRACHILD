"""Seven compact falsifiable forecasting methods sharing feature/evidence contracts.

All hyperparameters are declared constants, not selected on this replay's test set.
The GLM is a ridge-regularized Poisson log-linear likelihood fit by fixed-step
batch gradient descent. KNN is a separate instance-based classification method.
"""
from dataclasses import dataclass
from datetime import datetime
from math import exp, log, fsum, sqrt
from time import perf_counter

from dragonhydra.science.evaluation import Baseline, FixtureTarget, Probabilities, baseline_probabilities
from dragonhydra.science.temporal import TemporalMode
from .features import FeatureSnapshot, MatchEvidence
from .simulation import score_matrix, tau


ML_FEATURES = ("home_form", "away_form", "home_goals_for", "away_goals_for",
               "home_goals_against", "away_goals_against", "home_rest_days", "away_rest_days",
               "home_congestion_14d", "away_congestion_14d", "home_history_missing", "away_history_missing")


@dataclass(frozen=True, slots=True)
class ModelForecast:
    model_id: str
    probabilities: Probabilities
    feature_snapshot_id: str
    prediction_at: datetime
    temporal_mode: TemporalMode
    training_start: datetime | None
    training_end: datetime | None
    training_count: int
    runtime_seconds: float
    parameters: tuple[tuple[str, object], ...] = ()
    model_version: str = "1.0.0"
    hardware: str = "CPU"
    calibration_state: str = "UNCALIBRATED"
    failure_state: str | None = None

    def to_dict(self) -> dict:
        return {"engine_id": self.model_id, "model_id": self.model_id, "model_version": self.model_version,
                "epistemic_state": "PREDICTION", "probabilities": self.probabilities.to_dict(),
                "feature_snapshot_id": self.feature_snapshot_id, "prediction_at": self.prediction_at.isoformat(),
                "temporal_mode": self.temporal_mode.value,
                "training_window": {"start": self.training_start.isoformat() if self.training_start else None,
                                    "end": self.training_end.isoformat() if self.training_end else None},
                "training_count": self.training_count, "runtime_seconds": self.runtime_seconds,
                "parameters": dict(self.parameters), "hardware": self.hardware,
                "calibration_state": self.calibration_state, "failure_state": self.failure_state}


def goal_rates(history: tuple[MatchEvidence, ...], target: FixtureTarget, prior: float = 5.0) -> tuple[float, float]:
    """Smoothed venue attack/defence rates; no same-match or future results."""
    home_mean = (sum(r.home_goals for r in history) + 1.5 * prior) / (len(history) + prior)
    away_mean = (sum(r.away_goals for r in history) + 1.2 * prior) / (len(history) + prior)
    h = [r for r in history if r.home_team_id == target.home_team_id]
    a = [r for r in history if r.away_team_id == target.away_team_id]
    home_attack = (sum(r.home_goals for r in h) + home_mean * prior) / (len(h) + prior)
    away_defence = (sum(r.home_goals for r in a) + home_mean * prior) / (len(a) + prior)
    away_attack = (sum(r.away_goals for r in a) + away_mean * prior) / (len(a) + prior)
    home_defence = (sum(r.away_goals for r in h) + away_mean * prior) / (len(h) + prior)
    return max(.05, min(8., home_attack * away_defence / home_mean)), max(.05, min(8., away_attack * home_defence / away_mean))


def elo_probabilities(history, target, draw_rate):
    ratings = {}
    for row in history:
        h, a = ratings.get(row.home_team_id, 1500.), ratings.get(row.away_team_id, 1500.)
        expected = 1 / (1 + 10 ** ((a - h - 65) / 400))
        actual = 1 if row.home_goals > row.away_goals else 0 if row.home_goals < row.away_goals else .5
        change = 20 * (actual - expected)
        ratings[row.home_team_id], ratings[row.away_team_id] = h + change, a - change
    chance = 1 / (1 + 10 ** ((ratings.get(target.away_team_id, 1500.) - ratings.get(target.home_team_id, 1500.) - 65) / 400))
    return Probabilities((1-draw_rate)*chance, draw_rate, (1-draw_rate)*(1-chance))


def fit_rho(history, target_rates):
    """Bounded grid likelihood fit of DC correction on training low-score cells."""
    pairs = [(row, goal_rates(history, row.target())) for row in history]
    valid = []
    for step in range(-15, 16):
        rho = step / 100
        all_rates = [target_rates] + [rates for _, rates in pairs]
        if any(tau(i, j, h, a, rho) <= .001 for h, a in all_rates for i in (0, 1) for j in (0, 1)):
            continue
        loss = -fsum(log(tau(r.home_goals, r.away_goals, h, a, rho)) for r, (h, a) in pairs)
        # Weak fixed regularization prevents unbounded excitement about a few cells.
        loss += 10 * rho * rho
        valid.append((loss, abs(rho), rho))
    return min(valid)[2] if valid else 0.0


def glm_rates(history, target, *, epochs=70, ridge=.04, step=.08):
    """Regularized team attack/defence Poisson GLM, independent goal conditionals."""
    teams = sorted({team for r in history for team in (r.home_team_id, r.away_team_id)})
    attack, defence = dict.fromkeys(teams, 0.), dict.fromkeys(teams, 0.)
    bh = log((sum(r.home_goals for r in history)+7.5)/(len(history)+5))
    ba = log((sum(r.away_goals for r in history)+6)/(len(history)+5))
    n = max(1, len(history))
    for _ in range(epochs):
        ga, gd = dict.fromkeys(teams, 0.), dict.fromkeys(teams, 0.)
        gh, gw = 0., 0.
        for r in history:
            eh = exp(max(-4, min(2.5, bh + attack[r.home_team_id] + defence[r.away_team_id]))) - r.home_goals
            ea = exp(max(-4, min(2.5, ba + attack[r.away_team_id] + defence[r.home_team_id]))) - r.away_goals
            gh += eh; gw += ea
            ga[r.home_team_id] += eh; gd[r.away_team_id] += eh
            ga[r.away_team_id] += ea; gd[r.home_team_id] += ea
        bh -= step * gh/n; ba -= step * gw/n
        for team in teams:
            attack[team] -= step * (ga[team]/n + ridge*attack[team])
            defence[team] -= step * (gd[team]/n + ridge*defence[team])
    home = exp(max(-3, min(2, bh + attack.get(target.home_team_id, 0) + defence.get(target.away_team_id, 0))))
    away = exp(max(-3, min(2, ba + attack.get(target.away_team_id, 0) + defence.get(target.home_team_id, 0))))
    return home, away


def knn_probabilities(snapshot, frames, *, omit=(), neighbors=25):
    """Train-only standardized Euclidean KNN, Laplace-smoothed class counts."""
    names = [name for name in ML_FEATURES if name not in omit]
    if not names: raise ValueError("ablation must retain at least one feature")
    means, scales = {}, {}
    for name in names:
        vals = [s.values[name] for s, _ in frames if s.values[name] is not None]
        means[name] = fsum(vals)/len(vals) if vals else 0.
        scales[name] = max(1e-6, sqrt(fsum((v-means[name])**2 for v in vals)/len(vals))) if vals else 1.
    target = snapshot.values
    def distance(item):
        snap, row = item
        vals = snap.values
        sq = fsum((((vals[name] if vals[name] is not None else means[name]) -
                    (target[name] if target[name] is not None else means[name])) / scales[name])**2 for name in names)
        return sq, row.fixture_id
    selected = sorted(frames, key=distance)[:neighbors]
    counts = [1., 1., 1.]
    for _, row in selected: counts[0 if row.home_goals > row.away_goals else 1 if row.home_goals == row.away_goals else 2] += 1
    return Probabilities(*(c/fsum(counts) for c in counts))


def predict_models(snapshot: FeatureSnapshot, target: FixtureTarget, *, training_frames=(), include_ablation=False) -> tuple[ModelForecast, ...]:
    if snapshot.fixture_id != target.fixture_id:
        raise ValueError("feature snapshot belongs to another fixture")
    history = snapshot.evidence
    if any(not r.availability.eligible(snapshot.target_as_of_at, snapshot.temporal_mode)
           or r.completed_at >= snapshot.target_as_of_at or r.fixture_id == target.fixture_id for r in history):
        raise ValueError("unavailable training evidence")
    ids = {r.record_id for r in history}
    if any(row.record_id not in ids or snap.fixture_id != row.fixture_id
           or snap.temporal_mode is not snapshot.temporal_mode
           or snap.target_as_of_at > row.kickoff_at for snap, row in training_frames):
        raise ValueError("ML training frame violates temporal or fixture identity")
    results = tuple(r.result() for r in history)
    start = min((r.completed_at for r in history), default=None)
    end = max((r.completed_at for r in history), default=None)
    forecasts = []
    def run(name, fn):
        started = perf_counter()
        probabilities, params = fn()
        forecasts.append(ModelForecast(name, probabilities, snapshot.snapshot_id, snapshot.target_as_of_at,
                         snapshot.temporal_mode, start, end, len(history), perf_counter()-started, tuple(params.items())))
    league = baseline_probabilities(Baseline.LEAGUE_EMPIRICAL, results, target)
    run("LEAGUE_EMPIRICAL", lambda: (league, {"smoothing": 1.0}))
    run("VENUE_EMPIRICAL", lambda: (baseline_probabilities(Baseline.HOME_AWAY_EMPIRICAL, results, target), {"prior_strength": 5.0}))
    run("ELO", lambda: (elo_probabilities(history, target, league.draw), {"k": 20, "home_advantage": 65, "initial_rating": 1500}))
    rates = goal_rates(history, target)
    run("POISSON", lambda: (score_matrix(*rates).probabilities, {"home_rate": rates[0], "away_rate": rates[1], "prior": 5.0}))
    def dc():
        rho = fit_rho(history, rates)
        return score_matrix(*rates, rho=rho).probabilities, {"home_rate": rates[0], "away_rate": rates[1], "rho": rho, "rho_fit": "TRAINING_GRID_PENALIZED"}
    run("DIXON_COLES", dc)
    def glm():
        h, a = glm_rates(history, target)
        return score_matrix(h, a).probabilities, {"home_rate": h, "away_rate": a, "ridge": .04, "epochs": 70, "step": .08}
    run("POISSON_GLM", glm)
    run("KNN", lambda: (knn_probabilities(snapshot, training_frames), {"neighbors": 25, "training_frames": len(training_frames), "feature_names": ML_FEATURES}))
    if include_ablation:
        omit = ("home_form", "away_form", "home_rest_days", "away_rest_days", "home_congestion_14d", "away_congestion_14d")
        run("KNN_ABLATION_NO_FORM_REST", lambda: (knn_probabilities(snapshot, training_frames, omit=omit), {"omitted": omit, "neighbors": 25}))
    return tuple(forecasts)
