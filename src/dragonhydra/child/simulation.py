"""Exact truncated score distributions, conditional scenarios and seeded Monte Carlo."""
from dataclasses import dataclass
from math import exp, isfinite, sqrt, fsum
from random import Random

from dragonhydra.science.evaluation import Probabilities


def _rate(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 < value <= 10:
        raise ValueError("goal rate must be positive, finite and <= 10")


def tau(home: int, away: int, home_rate: float, away_rate: float, rho: float) -> float:
    if (home, away) == (0, 0): return 1 - home_rate * away_rate * rho
    if (home, away) == (0, 1): return 1 + home_rate * rho
    if (home, away) == (1, 0): return 1 + away_rate * rho
    if (home, away) == (1, 1): return 1 - rho
    return 1.0


@dataclass(frozen=True, slots=True)
class ScoreDistribution:
    matrix: tuple[tuple[float, ...], ...]
    tail_mass: float
    home_rate: float
    away_rate: float
    rho: float
    kind: str = "SIMULATION"

    @property
    def captured_mass(self):
        return fsum(fsum(row) for row in self.matrix)

    @property
    def probabilities(self) -> Probabilities:
        """H/D/A conditional on retained matrix; tail mass is separately explicit."""
        total = self.captured_mass
        h = fsum(p for i, row in enumerate(self.matrix) for j, p in enumerate(row) if i > j)
        d = fsum(row[i] for i, row in enumerate(self.matrix))
        return Probabilities(h / total, d / total, (total - h - d) / total)

    def to_dict(self):
        over = fsum(p for i, row in enumerate(self.matrix) for j, p in enumerate(row) if i + j > 2)
        return {"epistemic_state": self.kind, "matrix": self.matrix, "tail_mass": self.tail_mass,
                "home_rate": self.home_rate, "away_rate": self.away_rate, "rho": self.rho,
                "home_goals": [fsum(row) for row in self.matrix],
                "away_goals": [fsum(row[j] for row in self.matrix) for j in range(len(self.matrix))],
                "probabilities": self.probabilities.to_dict(), "over_2_5_conditional": over / self.captured_mass,
                "normalization": "HDA_AND_TOTALS_CONDITIONAL_ON_RETAINED_MATRIX"}


def score_matrix(home_rate: float, away_rate: float, *, rho: float = 0.0, max_goals: int = 20) -> ScoreDistribution:
    _rate(home_rate); _rate(away_rate)
    if not isinstance(max_goals, int) or isinstance(max_goals, bool) or not 2 <= max_goals <= 100:
        raise ValueError("max_goals must be 2..100")
    if not isfinite(rho) or any(tau(i, j, home_rate, away_rate, rho) <= 0 for i in (0, 1) for j in (0, 1)):
        raise ValueError("rho makes a low-score probability nonpositive")
    def pmf(rate):
        result = [exp(-rate)]
        for i in range(1, max_goals + 1): result.append(result[-1] * rate / i)
        return result
    h, a = pmf(home_rate), pmf(away_rate)
    matrix = tuple(tuple(x * y * tau(i, j, home_rate, away_rate, rho) for j, y in enumerate(a)) for i, x in enumerate(h))
    return ScoreDistribution(matrix, max(0.0, 1.0 - fsum(fsum(row) for row in matrix)), home_rate, away_rate, rho)


def scenario_mixture(scenarios: tuple[tuple[float, ScoreDistribution], ...]) -> dict:
    if not scenarios or any(not isfinite(w) or w < 0 for w, _ in scenarios) or abs(fsum(w for w, _ in scenarios) - 1) > 1e-12:
        raise ValueError("scenario weights must be nonnegative and sum to one")
    probs = Probabilities(*(fsum(w * d.probabilities.values[i] for w, d in scenarios) for i in range(3)))
    return {"epistemic_state": "HYPOTHESIS", "probabilities": probs.to_dict(),
            "scenario_count": len(scenarios), "weighted_tail_mass": fsum(w * d.tail_mass for w, d in scenarios),
            "assumption": "user-supplied conditional scenario probabilities, not observed states"}


def monte_carlo(home_rate: float, away_rate: float, *, samples: int = 10000, seed: int = 0,
                log_rate_sd: float = 0.0) -> dict:
    _rate(home_rate); _rate(away_rate)
    if not isinstance(samples, int) or isinstance(samples, bool) or not 100 <= samples <= 1000000:
        raise ValueError("sample budget must be 100..1000000")
    if not isfinite(log_rate_sd) or not 0 <= log_rate_sd <= 0.5:
        raise ValueError("log-rate scenario spread must be 0..0.5")
    rng, counts = Random(seed), [0, 0, 0]
    def poisson(rate):
        threshold, product, count = exp(-rate), 1.0, 0
        while product > threshold:
            product *= rng.random(); count += 1
        return count - 1
    for _ in range(samples):
        # Mean-preserving lognormal perturbation is an explicit hypothesis.
        h = poisson(home_rate * exp(rng.gauss(-log_rate_sd ** 2 / 2, log_rate_sd)))
        a = poisson(away_rate * exp(rng.gauss(-log_rate_sd ** 2 / 2, log_rate_sd)))
        counts[0 if h > a else 1 if h == a else 2] += 1
    probs = tuple(n / samples for n in counts)
    intervals = []
    for p in probs:
        z, n = 1.96, samples
        centre = (p + z*z/(2*n))/(1+z*z/n)
        half = z*sqrt(p*(1-p)/n + z*z/(4*n*n))/(1+z*z/n)
        intervals.append([max(0, centre-half), min(1, centre+half)])
    return {"epistemic_state": "SIMULATION", "probabilities": Probabilities(*probs).to_dict(),
            "samples": samples, "seed": seed, "log_rate_sd": log_rate_sd,
            "monte_carlo_95pct_intervals": intervals,
            "interval_meaning": "simulation sampling error only; not predictive epistemic confidence"}
