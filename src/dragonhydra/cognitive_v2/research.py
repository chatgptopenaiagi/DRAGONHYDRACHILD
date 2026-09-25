"""Falsifiable hypothesis lifecycle and explicitly estimated research priorities."""

from dataclasses import replace
from .contracts import ContractError, Hypothesis, ResearchNeed

_TRANSITIONS = {
    "PROPOSED": {"UNDER_TEST", "UNRESOLVED", "SUPERSEDED"},
    "UNDER_TEST": {"SUPPORTED", "WEAKENED", "REJECTED", "UNRESOLVED", "SUPERSEDED"},
    "UNRESOLVED": {"UNDER_TEST", "SUPERSEDED"},
    "SUPPORTED": {"UNDER_TEST", "WEAKENED", "REJECTED", "SUPERSEDED"},
    "WEAKENED": {"UNDER_TEST", "SUPPORTED", "REJECTED", "SUPERSEDED"},
    "REJECTED": {"SUPERSEDED"},
    "SUPERSEDED": set(),
}


def transition_hypothesis(hypothesis, status, *, observation_refs=(), known_observation_refs=()):
    """Return a new version; callers preserve the original immutable hypothesis."""
    if status not in _TRANSITIONS[hypothesis.status]:
        raise ContractError()
    refs = tuple(observation_refs)
    if status in {"SUPPORTED", "WEAKENED", "REJECTED"}:
        if not refs or not set(refs) <= set(known_observation_refs):
            raise ContractError("MEDUSA_REQUIRED")
    if status == "SUPPORTED":
        return replace(hypothesis, status=status,
                       supporting_refs=tuple(sorted(set(hypothesis.supporting_refs + refs))),
                       reason_codes=("LATER_OBSERVATION_SUPPORT",))
    if status in {"WEAKENED", "REJECTED"}:
        return replace(hypothesis, status=status,
                       contradicting_refs=tuple(sorted(set(hypothesis.contradicting_refs + refs))),
                       reason_codes=("LATER_OBSERVATION_CONTRADICTION",))
    return replace(hypothesis, status=status, reason_codes=("HYPOTHESIS_LIFECYCLE",))


def information_priority(need):
    value = need.value
    fields = (value.expected_uncertainty_reduction, value.observation_cost, value.decision_relevance)
    if any(item is None for item in fields):
        return None
    # Dimensionless heuristic, not predictive gain. A unit cost offset prevents infinity.
    return value.expected_uncertainty_reduction * value.decision_relevance / (1 + value.observation_cost)


def rank_research(needs):
    if len(needs) > 128 or any(not isinstance(item, ResearchNeed) for item in needs):
        raise ContractError("REQUEST_TOO_LARGE")
    return tuple(sorted(needs, key=lambda n: (information_priority(n) is None,
                                             -(information_priority(n) or 0), n.need_id)))
