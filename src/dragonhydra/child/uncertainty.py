"""Bounded research requests and a controlled, measurable validation/recalculation loop."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import fsum, isclose, isfinite, log
import re
from typing import Callable

from dragonhydra.science.evaluation import Probabilities
from dragonhydra.science.temporal import Availability, TemporalMode, aware_utc


def entropy(probabilities: Probabilities) -> float:
    return -fsum(value * log(value) for value in probabilities.values if value)


class ResearchState(StrEnum):
    VALIDATED_RECALCULATED = "VALIDATED_RECALCULATED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    TERMS_BLOCKED = "TERMS_BLOCKED"
    DEADLINE_EXPIRED = "DEADLINE_EXPIRED"
    QUARANTINE = "QUARANTINE"
    REJECT = "REJECT"
    MODEL_FAILURE = "MODEL_FAILURE"


@dataclass(frozen=True, slots=True)
class ResearchScenario:
    label: str
    probability: float
    conditional_forecast: Probabilities

    def __post_init__(self):
        if not self.label.strip() or not isfinite(self.probability) or not 0 <= self.probability <= 1:
            raise ValueError("Scenario label and finite probability are required")
        if not isinstance(self.conditional_forecast, Probabilities):
            raise ValueError("Conditional forecast must be normalized")


@dataclass(frozen=True, slots=True)
class ResearchNeed:
    need_id: str
    fixture_id: str
    entity_id: str
    question: str
    missing_field: str
    allowed_sources: tuple[str, ...]
    source_policy_version: str
    deadline: datetime
    expected_cost: float
    expected_seconds: float
    scenarios: tuple[ResearchScenario, ...]

    def __post_init__(self):
        for name in ("need_id", "fixture_id", "entity_id", "question", "missing_field", "source_policy_version"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        aware_utc(self.deadline)
        if not isinstance(self.allowed_sources, tuple) or not self.allowed_sources or len(set(self.allowed_sources)) != len(self.allowed_sources):
            raise ValueError("An explicit bounded source allowlist is required")
        if any(not item.strip() for item in self.allowed_sources):
            raise ValueError("Source identities must be nonempty")
        for value in (self.expected_cost, self.expected_seconds):
            if isinstance(value, bool) or not isfinite(value) or value < 0:
                raise ValueError("Research cost and latency estimates must be finite and nonnegative")
        if not isinstance(self.scenarios, tuple) or not self.scenarios or any(not isinstance(item, ResearchScenario) for item in self.scenarios):
            raise ValueError("Explicit hypothetical information scenarios are required")
        if not isclose(fsum(item.probability for item in self.scenarios), 1.0, abs_tol=1e-12):
            raise ValueError("Scenario probabilities must sum to one")


def rank_research(needs: tuple[ResearchNeed, ...], baseline: Probabilities,
                  source_states: dict[str, str], *, now: datetime, cost_budget: float) -> tuple[dict, ...]:
    """Estimate conditional entropy gain; this is a sensitivity heuristic, not causal VOI proof."""
    current = aware_utc(now)
    if not isfinite(cost_budget) or cost_budget < 0:
        raise ValueError("Finite nonnegative research budget is required")
    if len({need.need_id for need in needs}) != len(needs):
        raise ValueError("Research request identities must be unique")
    ranked = []
    for need in needs:
        sources = [source for source in need.allowed_sources if source_states.get(source) == "APPROVED"]
        feasible = bool(sources) and current < need.deadline and need.expected_cost <= cost_budget
        remaining = (need.deadline - current).total_seconds()
        feasible = feasible and need.expected_seconds < remaining
        expected_entropy = fsum(item.probability * entropy(item.conditional_forecast) for item in need.scenarios)
        gain = entropy(baseline) - expected_entropy
        sensitivity = max(fsum(abs(before - after) for before, after in zip(baseline.values, item.conditional_forecast.values)) / 2
                          for item in need.scenarios)
        ranked.append({"need_id": need.need_id, "feasible": feasible,
                       "approved_sources": sources, "estimated_entropy_gain": gain,
                       "maximum_probability_total_variation": sensitivity,
                       "priority_score": max(0.0, gain) / (1 + need.expected_cost + need.expected_seconds / 60) if feasible else 0.0,
                       "estimated_cost": need.expected_cost, "deadline": need.deadline.isoformat(),
                       "estimate_kind": "DECLARED_SCENARIO_SENSITIVITY_NOT_VALIDATED_CAUSAL_VOI"})
    return tuple(sorted(ranked, key=lambda item: (-item["priority_score"], item["need_id"])))


@dataclass(frozen=True, slots=True)
class ResearchAnswer:
    evidence_id: str
    source_id: str
    field: str
    value: str | float | bool
    availability: Availability
    content_hash: str
    synthetic: bool

    def __post_init__(self):
        if not self.evidence_id.strip() or not self.source_id.strip() or not self.field.strip():
            raise ValueError("Answer needs identity, source and field")
        if not isinstance(self.availability, Availability) or re.fullmatch(r"[0-9a-f]{64}", self.content_hash) is None:
            raise ValueError("Answer requires availability and raw content hash")
        if self.availability.source != self.source_id:
            raise ValueError("Answer source must agree with its availability provenance")
        if not isinstance(self.value, (str, int, float, bool)) or isinstance(self.value, float) and not isfinite(self.value):
            raise ValueError("Answer value must be a finite scalar")
        if type(self.synthetic) is not bool:
            raise ValueError("Synthetic label must be explicit")


def run_controlled_research(
    need: ResearchNeed, baseline: Probabilities, source_states: dict[str, str], *,
    now: datetime, known_fields: frozenset[str], required_fields: frozenset[str],
    fetcher: Callable[[ResearchNeed, str], ResearchAnswer | None],
    validator: Callable[[ResearchAnswer], bool],
    recalculator: Callable[[ResearchAnswer], Probabilities], cost_budget: float,
) -> dict:
    """One approved source, one fetch, one validation, one recalculation; no daemon.

    Callbacks are explicit adapters. The synthetic contract experiment is not a
    demonstrated real-world research benefit. Negative entropy changes are retained.
    """
    current = aware_utc(now)
    if not required_fields or not known_fields <= required_fields or need.missing_field not in required_fields:
        raise ValueError("Completeness denominator and missing field must be explicit")
    if need.missing_field in known_fields:
        raise ValueError("Research should target an actual missing field")
    base = {"need_id": need.need_id, "fixture_id": need.fixture_id,
            "entropy_before": entropy(baseline), "entropy_after": None, "entropy_reduction": None,
            "completeness_before": len(known_fields) / len(required_fields),
            "completeness_after": len(known_fields) / len(required_fields),
            "source_policy_version": need.source_policy_version, "evidence_id": None,
            "real_world_benefit_proven": False}
    if current >= need.deadline:
        return {**base, "state": ResearchState.DEADLINE_EXPIRED.value}
    approved = [source for source in need.allowed_sources if source_states.get(source) == "APPROVED"]
    if not approved:
        return {**base, "state": ResearchState.TERMS_BLOCKED.value}
    ranked = rank_research((need,), baseline, source_states, now=current, cost_budget=cost_budget)[0]
    if not ranked["feasible"]:
        return {**base, "state": ResearchState.SOURCE_UNAVAILABLE.value, "reason": "BUDGET_OR_LATENCY_BOUND"}
    source = approved[0]
    try:
        answer = fetcher(need, source)
    except Exception as error:
        return {**base, "state": ResearchState.SOURCE_UNAVAILABLE.value,
                "reason": "FETCH_FAILED", "exception_type": type(error).__name__}
    if answer is None:
        return {**base, "state": ResearchState.SOURCE_UNAVAILABLE.value}
    if not isinstance(answer, ResearchAnswer):
        return {**base, "state": ResearchState.REJECT.value, "reason": "INVALID_ANSWER_CONTRACT"}
    if (answer.source_id != source or answer.field != need.missing_field
            or not answer.availability.eligible(current, TemporalMode.STRICT_PIT)
            or answer.availability.ingested_at > current):
        return {**base, "state": ResearchState.REJECT.value, "reason": "SOURCE_FIELD_OR_TIME_MISMATCH"}
    try:
        valid = validator(answer)
    except Exception as error:
        return {**base, "state": ResearchState.QUARANTINE.value,
                "reason": "VALIDATOR_FAILED", "exception_type": type(error).__name__}
    if valid is not True:
        return {**base, "state": ResearchState.QUARANTINE.value, "evidence_id": answer.evidence_id}
    try:
        after = recalculator(answer)
    except Exception as error:
        return {**base, "state": ResearchState.MODEL_FAILURE.value,
                "reason": "RECALCULATION_FAILED", "exception_type": type(error).__name__}
    if not isinstance(after, Probabilities):
        raise ValueError("Recalculation must return normalized probabilities")
    return {**base, "state": ResearchState.VALIDATED_RECALCULATED.value,
            "entropy_after": entropy(after), "entropy_reduction": entropy(baseline) - entropy(after),
            "completeness_after": len(known_fields | {need.missing_field}) / len(required_fields),
            "evidence_id": answer.evidence_id, "source_id": answer.source_id,
            "availability": answer.availability.to_dict(), "content_hash": answer.content_hash,
            "probabilities_after": after.to_dict(), "synthetic": answer.synthetic,
            "interpretation": "CONTROLLED_EXPERIMENT_REQUIRES_PROSPECTIVE_OUTCOME_VALIDATION"}
