"""Strict advisory cognitive products. These types have no evidence-write authority."""

from dataclasses import dataclass, fields, MISSING
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import types
from typing import ClassVar, Literal, get_args, get_origin, get_type_hints

SCHEMA_VERSION = "2"
ACTORS = frozenset({"QWEN_4B", "QWEN_30B", "CODEX", "SYSTEM", "HUMAN", "HYDRA", "MEDUSA"})
TEMPORAL_MODES = frozenset({"STRICT_PIT", "RECONSTRUCTED_PIT", "PRESENT", "FUTURE", "SYNTHETIC"})
EPISTEMIC_STATES = frozenset({"STRICT_PIT", "RECONSTRUCTED_PIT", "HYPOTHESIS", "PREDICTION", "SIMULATION", "OBSERVATION", "SYNTHETIC", "INTERPRETATION", "CRITIQUE", "RESEARCH_PROPOSAL", "RECONCILIATION", "ANOMALY_REPORT"})
AI_STATES = frozenset({"HYPOTHESIS", "INTERPRETATION", "CRITIQUE", "RESEARCH_PROPOSAL", "RECONCILIATION", "ANOMALY_REPORT"})
CONFIDENCE = frozenset({"UNKNOWN", "LOW", "MEDIUM", "HIGH"})
ACTION_CLASSES = frozenset({"REQUEST_HUMAN_REVIEW", "REQUEST_HYDRA_RESEARCH", "REQUEST_CALCULATION", "REQUEST_STATE_REFRESH", "REQUEST_MODEL_COMPARISON", "REQUEST_MEMORY_LOOKUP", "NO_ACTION"})
ANALYSIS_CLASSES = frozenset({"ANALYZE_STATE", "COMPARE_MODELS", "RECONCILE"})
FAILURE_STATES = frozenset({"COGNITIVE_STATE_STALE", "MACHINE_STATE_STALE", "MACHINE_PROBE_FAILED", "MODEL_UNAVAILABLE", "MODEL_HASH_MISMATCH", "RUNTIME_HASH_MISMATCH", "QWEN_RESPONSE_INVALID", "CODEX_RESPONSE_UNAVAILABLE", "RECONCILIATION_INSUFFICIENT", "REQUEST_TOO_LARGE", "CAPABILITY_DENIED", "STATE_CHANGED_SINCE_PROPOSAL", "UNSUPPORTED_TASK", "UNTRUSTED_CONTEXT", "MEMORY_REFERENCE_MISSING", "HYDRA_REQUIRED", "MEDUSA_REQUIRED", "TIMEOUT", "RUNTIME_FAILURE", "INVALID_RESPONSE", "INVALID_REQUEST", "AUDIT_FAILURE", "REPLAY_REJECTED", "REQUEST_QUOTA_REACHED"})
_FORBIDDEN = re.compile(r"(?i)(chain.of.thought|hidden.reasoning|scratchpad|<think>|</think>|(?:password|passwd|api[_ -]?key|access[_ -]?token|bearer|secret)\s*[:=]|sk-proj-|-----BEGIN |[A-Za-z]:[\\/]|\\\\[^ ]+\\|file://|/(?:etc|home|root|Users)/|https?://[^ /]*@|ignore (?:all |previous |prior )?instructions|ignore previous|system prompt|powershell\s+-|cmd\.exe|<script)")


class ContractError(ValueError):
    def __init__(self, reason_code="UNTRUSTED_CONTEXT"):
        self.reason_code = reason_code
        super().__init__(reason_code)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def content_hash(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def utc_time(value):
    if type(value) is not str or len(value) > 40:
        raise ContractError()
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ContractError() from exc
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ContractError()
    return stamp


def _hash(value):
    if type(value) is not str or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ContractError()


def _text(value, maximum=500):
    if type(value) is not str or not value or len(value) > maximum or _FORBIDDEN.search(value) or any(ord(c) < 32 for c in value):
        raise ContractError()


def _identifier(value):
    _text(value, 128)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/+-]*", value) is None or ".." in value:
        raise ContractError()


def _decode(annotation, value):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (types.UnionType,):
        for option in args:
            try:
                return _decode(option, value)
            except ContractError:
                pass
        raise ContractError()
    if annotation is type(None):
        if value is not None:
            raise ContractError()
        return None
    if origin is Literal:
        if value not in args:
            raise ContractError()
        return value
    if origin is tuple:
        if type(value) not in (tuple, list) or len(value) > 128:
            raise ContractError("REQUEST_TOO_LARGE")
        if len(args) != 2 or args[1] is not Ellipsis:
            raise ContractError()
        return tuple(_decode(args[0], item) for item in value)
    if isinstance(annotation, type) and issubclass(annotation, Contract):
        if isinstance(value, annotation):
            return value
        return annotation.from_dict(value)
    if annotation is float:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ContractError()
        return float(value)
    if annotation in (str, int, bool):
        if type(value) is not annotation:
            raise ContractError()
        if annotation is str:
            _text(value)
        elif annotation is int and abs(value) > 10**18:
            raise ContractError()
        return value
    raise ContractError()


def _encode(value):
    if isinstance(value, Contract):
        return value.to_dict()
    if type(value) is tuple:
        return [_encode(item) for item in value]
    return value


@dataclass(frozen=True, kw_only=True)
class Contract:
    schema_version: str = SCHEMA_VERSION
    CHOICES: ClassVar[dict] = {}

    def __post_init__(self):
        hints = get_type_hints(type(self))
        for field in fields(self):
            value = getattr(self, field.name)
            decoded = _decode(hints[field.name], value)
            object.__setattr__(self, field.name, decoded)
            if value is None:
                continue
            if field.name.endswith("_at"):
                utc_time(value)
            if field.name.endswith("_hash"):
                _hash(value)
            if field.name.endswith("_hashes"):
                for item in value:
                    _hash(item)
            if field.name.endswith("_id") or field.name in {"actor", "actor_id", "created_by", "task_kind"}:
                _identifier(value)
            if field.name.endswith("_refs") or field.name in {"references", "reason_codes"}:
                for item in value:
                    _identifier(item)
            if field.name in self.CHOICES and value not in self.CHOICES[field.name]:
                raise ContractError()
        if self.schema_version != SCHEMA_VERSION:
            raise ContractError()
        if hasattr(self, "confidence") and self.confidence not in CONFIDENCE:
            raise ContractError()
        if hasattr(self, "epistemic_state") and self.epistemic_state not in EPISTEMIC_STATES:
            raise ContractError()
        for key in ("actor", "actor_id", "created_by"):
            if hasattr(self, key) and getattr(self, key) not in ACTORS:
                raise ContractError()
        if hasattr(self, "observed_at") and hasattr(self, "available_at") and utc_time(self.available_at) < utc_time(self.observed_at):
            raise ContractError()
        if hasattr(self, "expires_at") and self.expires_at is not None and hasattr(self, "created_at") and utc_time(self.expires_at) <= utc_time(self.created_at):
            raise ContractError()
        if len(canonical_bytes(self.to_dict())) > 262144:
            raise ContractError("REQUEST_TOO_LARGE")

    def to_dict(self):
        return {field.name: _encode(getattr(self, field.name)) for field in fields(self)}

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict:
            raise ContractError()
        expected = {f.name for f in fields(cls)}
        required = {f.name for f in fields(cls) if f.default is MISSING and f.default_factory is MISSING}
        if not required <= set(value) or set(value) - expected:
            raise ContractError()
        hints = get_type_hints(cls)
        return cls(**{key: _decode(hints[key], val) for key, val in value.items()})

    def digest(self):
        return content_hash(self.to_dict())


@dataclass(frozen=True, kw_only=True)
class Metric(Contract):
    name: str
    value: float | None
    unit: str
    provenance_refs: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class StateLabel(Contract):
    name: str
    value: str

    def __post_init__(self):
        super().__post_init__()
        _identifier(self.name)
        _text(self.value, 160)


@dataclass(frozen=True, kw_only=True)
class ComponentState(Contract):
    component_id: str
    status: str
    metrics: tuple[Metric, ...] = ()
    labels: tuple[StateLabel, ...] = ()
    references: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class EvidenceReference(Contract):
    evidence_id: str
    content_hash: str
    observed_at: str
    available_at: str
    source_id: str
    epistemic_state: str
    medusa_accepted: bool
    CHOICES: ClassVar[dict] = {"epistemic_state": {"OBSERVATION", "STRICT_PIT", "RECONSTRUCTED_PIT", "SYNTHETIC"}}


@dataclass(frozen=True, kw_only=True)
class WorldState(Contract):
    as_of_at: str
    evidence: tuple[EvidenceReference, ...] = ()
    source_states: tuple[ComponentState, ...] = ()
    prediction_refs: tuple[str, ...] = ()
    feature_refs: tuple[str, ...] = ()
    simulation_refs: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self):
        super().__post_init__()
        for item in self.evidence:
            if utc_time(item.available_at) > utc_time(self.as_of_at) or utc_time(item.observed_at) > utc_time(self.as_of_at):
                raise ContractError("UNTRUSTED_CONTEXT")


@dataclass(frozen=True, kw_only=True)
class MachineState(Contract):
    machine_snapshot_hash: str
    observed_at: str
    available_at: str
    expires_at: str
    components: tuple[ComponentState, ...] = ()
    health: str = "UNKNOWN"
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self):
        super().__post_init__()
        if utc_time(self.expires_at) <= utc_time(self.available_at):
            raise ContractError()


@dataclass(frozen=True, kw_only=True)
class ProjectState(Contract):
    project_id: str
    branch: str
    head: str
    working_tree: str
    observed_at: str
    available_at: str
    expires_at: str
    frozen_prediction_hash: str | None = None
    reason_codes: tuple[str, ...] = ()
    CHOICES: ClassVar[dict] = {"working_tree": {"CLEAN", "DIRTY", "UNKNOWN"}}

    def __post_init__(self):
        super().__post_init__()
        if utc_time(self.expires_at) <= utc_time(self.available_at):
            raise ContractError()


@dataclass(frozen=True, kw_only=True)
class ModelState(Contract):
    models: tuple[ComponentState, ...] = ()
    active_model: str | None = None
    forecast_refs: tuple[str, ...] = ()
    disagreement_refs: tuple[str, ...] = ()
    model_hashes: tuple[str, ...] = ()
    runtime_hashes: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class MemoryState(Contract):
    memory_refs: tuple[str, ...] = ()
    working_refs: tuple[str, ...] = ()
    episode_refs: tuple[str, ...] = ()
    decision_refs: tuple[str, ...] = ()
    learning_refs: tuple[str, ...] = ()
    limitation_refs: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class UncertaintyState(Contract):
    uncertainty_id: str
    dimension: str
    last_updated: str
    recommended_resolution: str
    score: float | None = None
    status: str = "UNKNOWN"
    provenance_refs: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    CHOICES: ClassVar[dict] = {"status": {"UNKNOWN", "OPEN", "RESOLVED", "BLOCKED"}}

    def __post_init__(self):
        super().__post_init__()
        utc_time(self.last_updated)
        if self.score is not None and (not 0 <= self.score <= 1 or not self.provenance_refs):
            raise ContractError()


@dataclass(frozen=True, kw_only=True)
class UncertaintyMap(Contract):
    items: tuple[UncertaintyState, ...] = ()

    def __post_init__(self):
        super().__post_init__()
        if len({item.uncertainty_id for item in self.items}) != len(self.items):
            raise ContractError()


@dataclass(frozen=True, kw_only=True)
class CapabilityDescriptor(Contract):
    capability_id: str
    actor: str
    action_class: str
    enabled: bool
    risk_class: str = "LOW"
    requires_fresh_state: bool = True
    requires_human: bool = False
    requires_medusa: bool = False
    requires_hydra: bool = False
    reversible: bool = True
    max_frequency: int = 1
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self):
        super().__post_init__()
        if self.enabled and self.action_class not in ACTION_CLASSES | ANALYSIS_CLASSES:
            raise ContractError("CAPABILITY_DENIED")
        if not 1 <= self.max_frequency <= 60:
            raise ContractError()
        if self.action_class == "REQUEST_HYDRA_RESEARCH" and not (self.requires_hydra and self.requires_medusa):
            raise ContractError("HYDRA_REQUIRED")


@dataclass(frozen=True, kw_only=True)
class CapabilityState(Contract):
    capabilities: tuple[CapabilityDescriptor, ...] = ()

    def __post_init__(self):
        super().__post_init__()
        if len({item.capability_id for item in self.capabilities}) != len(self.capabilities):
            raise ContractError()


@dataclass(frozen=True, kw_only=True)
class CognitiveStateSnapshot(Contract):
    snapshot_id: str
    created_at: str
    as_of_at: str
    temporal_mode: str
    world_state: WorldState
    machine_state: MachineState
    project_state: ProjectState
    model_state: ModelState
    memory_state: MemoryState
    uncertainties: UncertaintyMap
    capabilities: CapabilityState
    active_fixture: str | None = None
    active_prediction: str | None = None
    recent_events: tuple[str, ...] = ()
    chain_breaks: tuple[str, ...] = ()
    CHOICES: ClassVar[dict] = {"temporal_mode": TEMPORAL_MODES}

    def __post_init__(self):
        super().__post_init__()
        if self.world_state.as_of_at != self.as_of_at:
            raise ContractError()
        if self.temporal_mode == "FUTURE" and self.world_state.evidence:
            raise ContractError()
        if utc_time(self.created_at) < utc_time(self.as_of_at):
            raise ContractError()
        if any(utc_time(item.available_at) > utc_time(self.created_at) for item in (self.machine_state, self.project_state)):
            raise ContractError()
        if len({item.evidence_id for item in self.world_state.evidence}) != len(self.world_state.evidence):
            raise ContractError()

    @property
    def state_hash(self):
        data = Contract.to_dict(self)
        data.pop("snapshot_id")
        data.pop("created_at")
        for section in ("machine_state", "project_state"):
            for key in ("observed_at", "available_at", "expires_at"):
                data[section].pop(key, None)
        return content_hash(data)

    def assert_fresh(self, now):
        return ensure_fresh(self, now)

    def to_dict(self):
        return dict(Contract.to_dict(self), state_hash=self.state_hash)

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict:
            raise ContractError()
        value = dict(value)
        expected_hash = value.pop("state_hash", None)
        result = super().from_dict(value)
        if expected_hash is not None and result.state_hash != expected_hash:
            raise ContractError("STATE_CHANGED_SINCE_PROPOSAL")
        return result


CognitiveState = CognitiveStateSnapshot


@dataclass(frozen=True, kw_only=True)
class Conclusion(Contract):
    claim_id: str
    subject: str
    position: str
    summary: str
    evidence_refs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    confidence: str = "UNKNOWN"
    epistemic_state: str = "INTERPRETATION"
    reason_codes: tuple[str, ...] = ()
    CHOICES: ClassVar[dict] = {"epistemic_state": AI_STATES}


@dataclass(frozen=True, kw_only=True)
class Hypothesis(Contract):
    hypothesis_id: str
    statement_summary: str
    created_by: str
    created_at: str
    state_hash: str
    falsification_condition: str
    required_observation: str
    supporting_refs: tuple[str, ...] = ()
    contradicting_refs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    confidence: str = "UNKNOWN"
    status: str = "PROPOSED"
    epistemic_state: str = "HYPOTHESIS"
    reason_codes: tuple[str, ...] = ()
    CHOICES: ClassVar[dict] = {"status": {"PROPOSED", "UNDER_TEST", "SUPPORTED", "WEAKENED", "REJECTED", "SUPERSEDED", "UNRESOLVED"}, "epistemic_state": {"HYPOTHESIS"}}

    def __post_init__(self):
        super().__post_init__()
        if self.status == "SUPPORTED" and not self.supporting_refs:
            raise ContractError("MEDUSA_REQUIRED")
        if self.status in {"WEAKENED", "REJECTED"} and not self.contradicting_refs:
            raise ContractError("MEDUSA_REQUIRED")


@dataclass(frozen=True, kw_only=True)
class ExpectedInformationValue(Contract):
    expected_uncertainty_reduction: float | None = None
    observation_cost: float | None = None
    latency_seconds: float | None = None
    decision_relevance: float | None = None
    basis_refs: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ("UNKNOWN_INFORMATION_VALUE",)
    measured: bool = False

    def __post_init__(self):
        super().__post_init__()
        for name in ("expected_uncertainty_reduction", "decision_relevance"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 1:
                raise ContractError()
        if any(value is not None and value < 0 for value in (self.observation_cost, self.latency_seconds)):
            raise ContractError()
        values = (self.expected_uncertainty_reduction, self.observation_cost, self.latency_seconds, self.decision_relevance)
        if any(value is not None for value in values) and not self.basis_refs:
            raise ContractError()
        if self.measured and (not self.basis_refs or self.expected_uncertainty_reduction is None):
            raise ContractError()


@dataclass(frozen=True, kw_only=True)
class ResearchNeed(Contract):
    need_id: str
    created_by: str
    created_at: str
    state_hash: str
    uncertainty_id: str
    required_observation: str
    requested_hydra_head: str
    provenance_refs: tuple[str, ...]
    fulfillment_refs: tuple[str, ...] = ()
    value: ExpectedInformationValue = ExpectedInformationValue()
    status: str = "PROPOSED"
    requires_hydra: bool = True
    requires_medusa: bool = True
    epistemic_state: str = "RESEARCH_PROPOSAL"
    reason_codes: tuple[str, ...] = ()
    CHOICES: ClassVar[dict] = {"status": {"PROPOSED", "REQUESTED", "FULFILLED", "BLOCKED", "UNRESOLVED"}, "epistemic_state": {"RESEARCH_PROPOSAL"}}

    def __post_init__(self):
        super().__post_init__()
        if not self.requires_hydra:
            raise ContractError("HYDRA_REQUIRED")
        if not self.requires_medusa:
            raise ContractError("MEDUSA_REQUIRED")
        if not self.provenance_refs:
            raise ContractError("MEMORY_REFERENCE_MISSING")
        if self.status == "FULFILLED" and not self.fulfillment_refs:
            raise ContractError("MEDUSA_REQUIRED")


@dataclass(frozen=True, kw_only=True)
class ActionProposal(Contract):
    proposal_id: str
    actor_id: str
    created_at: str
    expires_at: str
    state_hash: str
    capability_id: str
    action_class: str
    references: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    precondition_hashes: tuple[str, ...] = ()
    epistemic_state: str = "RESEARCH_PROPOSAL"
    CHOICES: ClassVar[dict] = {"action_class": ACTION_CLASSES, "epistemic_state": AI_STATES}


@dataclass(frozen=True, kw_only=True)
class ActionDecision(Contract):
    proposal_id: str
    created_at: str
    state_hash: str
    status: str
    reason_codes: tuple[str, ...]
    executes_action: bool = False
    CHOICES: ClassVar[dict] = {"status": {"PROPOSAL_ACCEPTED", "DENIED", "REQUIRES_REVIEW"}}

    def __post_init__(self):
        super().__post_init__()
        if self.executes_action:
            raise ContractError("CAPABILITY_DENIED")


@dataclass(frozen=True, kw_only=True)
class CognitiveActorResult(Contract):
    actor_id: str
    state_hash: str
    task_kind: str
    created_at: str
    conclusions: tuple[Conclusion, ...] = ()
    uncertainties: tuple[str, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = ()
    research_needs: tuple[ResearchNeed, ...] = ()
    proposals: tuple[ActionProposal, ...] = ()
    references: tuple[str, ...] = ()
    result_status: str = "COMPLETE"
    failure_state: str | None = None
    model_id: str | None = None
    model_hash: str | None = None
    runtime_id: str | None = None
    runtime_hash: str | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    latency_ms: float | None = None
    reason_codes: tuple[str, ...] = ()
    CHOICES: ClassVar[dict] = {"result_status": {"COMPLETE", "PARTIAL", "BLOCKED", "FAILED", "ABSTAINED"}, "failure_state": FAILURE_STATES}

    def __post_init__(self):
        super().__post_init__()
        if self.actor_id.startswith("QWEN") and self.result_status in {"COMPLETE", "PARTIAL"} and not all((self.model_id, self.model_hash, self.runtime_id, self.runtime_hash, self.input_hash, self.output_hash)):
            raise ContractError("QWEN_RESPONSE_INVALID")
        if self.result_status in {"FAILED", "BLOCKED"} and (not self.failure_state or self.conclusions or self.hypotheses or self.research_needs or self.proposals):
            raise ContractError("QWEN_RESPONSE_INVALID")
        if self.result_status == "COMPLETE" and self.failure_state:
            raise ContractError()
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ContractError()
        for item in (*self.hypotheses, *self.research_needs, *self.proposals):
            if item.state_hash != self.state_hash:
                raise ContractError("STATE_CHANGED_SINCE_PROPOSAL")
            identity = getattr(item, "created_by", getattr(item, "actor_id", None))
            if identity != self.actor_id:
                raise ContractError()
        if len({item.claim_id for item in self.conclusions}) != len(self.conclusions):
            raise ContractError()
        if self.actor_id in {"CODEX", "QWEN_4B", "QWEN_30B"}:
            if any(item.status not in {"PROPOSED", "UNRESOLVED"} for item in self.hypotheses):
                raise ContractError("MEDUSA_REQUIRED")
            if any(item.status not in {"PROPOSED", "BLOCKED", "UNRESOLVED"} for item in self.research_needs):
                raise ContractError("MEDUSA_REQUIRED")


@dataclass(frozen=True, kw_only=True)
class PositionComparison(Contract):
    subject: str
    left_actor: str
    right_actor: str
    left_claim: Conclusion
    right_claim: Conclusion
    status: str
    reason_codes: tuple[str, ...] = ()
    CHOICES: ClassVar[dict] = {"status": {"AGREEMENT", "DISAGREEMENT", "INSUFFICIENT_EVIDENCE"}}


@dataclass(frozen=True, kw_only=True)
class CognitiveReconciliation(Contract):
    reconciliation_id: str
    created_at: str
    state_hash: str
    left_result_hash: str
    right_result_hash: str
    status: str
    agreements: tuple[PositionComparison, ...] = ()
    disagreements: tuple[PositionComparison, ...] = ()
    unsupported_claims: tuple[str, ...] = ()
    different_assumptions: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    confidence_conflicts: tuple[str, ...] = ()
    recommended_measurement: tuple[str, ...] = ()
    research_needs: tuple[ResearchNeed, ...] = ()
    reason_codes: tuple[str, ...] = ()
    epistemic_state: str = "RECONCILIATION"
    CHOICES: ClassVar[dict] = {"status": {"AGREEMENT", "PARTIAL_AGREEMENT", "DISAGREEMENT", "INSUFFICIENT_EVIDENCE", "NOT_COMPARABLE"}, "epistemic_state": {"RECONCILIATION"}}


@dataclass(frozen=True, kw_only=True)
class LearningFeedback(Contract):
    feedback_id: str
    created_at: str
    expected_at: str
    observed_at: str
    available_at: str
    expected_hash: str
    observation_hash: str
    expected_summary: str
    observed_summary: str
    difference_summary: str
    contributor: str
    source_refs: tuple[str, ...]
    observation_kind: str
    validated_by: str
    next_test: str
    failed_assumptions: tuple[str, ...] = ()
    helpful_feature_refs: tuple[str, ...] = ()
    missing_evidence_refs: tuple[str, ...] = ()
    accuracy_gain: float | None = None
    outcome_ref: str | None = None
    prior_score: float | None = None
    later_score: float | None = None
    score_method: str | None = None
    reason_codes: tuple[str, ...] = ()
    epistemic_state: str = "RECONCILIATION"
    CHOICES: ClassVar[dict] = {"observation_kind": {"WORLD", "MACHINE", "OUTCOME"}, "validated_by": {"MEDUSA", "ARX"}, "epistemic_state": {"RECONCILIATION"}}

    def __post_init__(self):
        super().__post_init__()
        if not self.source_refs or utc_time(self.observed_at) <= utc_time(self.expected_at) or utc_time(self.created_at) < utc_time(self.available_at):
            raise ContractError()
        if self.observation_kind in {"WORLD", "OUTCOME"} and self.validated_by != "MEDUSA":
            raise ContractError("MEDUSA_REQUIRED")
        if self.observation_kind == "MACHINE" and self.validated_by != "ARX":
            raise ContractError()
        if self.accuracy_gain is not None:
            if (self.observation_kind != "OUTCOME" or not self.outcome_ref or self.outcome_ref not in self.source_refs or self.prior_score is None or self.later_score is None or self.score_method not in {"BRIER_LOWER_BETTER", "LOG_LOSS_LOWER_BETTER"}):
                raise ContractError("MEDUSA_REQUIRED")
            if self.prior_score < 0 or self.later_score < 0 or abs(self.accuracy_gain - (self.prior_score - self.later_score)) > 1e-9:
                raise ContractError()


@dataclass(frozen=True, kw_only=True)
class SystemSelfModel(Contract):
    version: str
    created_at: str
    components: tuple[ComponentState, ...]
    available_models: tuple[str, ...]
    active_model: str | None
    available_data_sources: tuple[str, ...]
    active_hydra_heads: tuple[str, ...]
    active_math_engines: tuple[str, ...]
    known_databases: tuple[str, ...]
    available_actions: tuple[str, ...]
    disabled_actions: tuple[str, ...]
    machine_capabilities: tuple[str, ...]
    known_blockers: tuple[str, ...]
    known_scientific_limits: tuple[str, ...]
    current_feature_branch: str
    last_validated_state_hash: str
    last_reconciliation_at: str | None = None


@dataclass(frozen=True, kw_only=True)
class CognitiveCycleReceipt(Contract):
    cycle_id: str
    created_at: str
    as_of_at: str
    state_hash: str
    snapshot_hash: str
    machine_snapshot_hash: str
    routing_hash: str
    actor_result_hashes: tuple[str, ...]
    result_status: str
    input_hash: str
    output_hash: str
    reconciliation_hash: str | None = None
    memory_hashes: tuple[str, ...] = ()
    failure_state: str | None = None
    reason_codes: tuple[str, ...] = ()
    CHOICES: ClassVar[dict] = {"result_status": {"COMPLETE", "PARTIAL", "BLOCKED", "FAILED"}, "failure_state": FAILURE_STATES}


def ensure_fresh(snapshot, now):
    """Freshness is explicit and never refreshed by loading an old artifact."""
    stamp = utc_time(now)
    if stamp < utc_time(snapshot.created_at) or stamp < utc_time(snapshot.as_of_at):
        raise ContractError("COGNITIVE_STATE_STALE")
    if snapshot.machine_state.health in {"FAILED", "UNAVAILABLE"}:
        raise ContractError("MACHINE_PROBE_FAILED")
    if stamp >= utc_time(snapshot.machine_state.expires_at) or utc_time(snapshot.machine_state.available_at) > stamp:
        raise ContractError("MACHINE_STATE_STALE")
    if stamp >= utc_time(snapshot.project_state.expires_at) or utc_time(snapshot.project_state.available_at) > stamp:
        raise ContractError("COGNITIVE_STATE_STALE")
    return True


def snapshot_references(snapshot):
    refs = {snapshot.snapshot_id, snapshot.state_hash, snapshot.machine_state.machine_snapshot_hash}
    refs.update(e.evidence_id for e in snapshot.world_state.evidence)
    refs.update(e.content_hash for e in snapshot.world_state.evidence)
    refs.update(snapshot.world_state.prediction_refs)
    refs.update(snapshot.world_state.feature_refs)
    refs.update(snapshot.world_state.simulation_refs)
    refs.update(snapshot.recent_events)
    refs.update(snapshot.memory_state.memory_refs)
    refs.update(u.uncertainty_id for u in snapshot.uncertainties.items)
    for component in (*snapshot.machine_state.components, *snapshot.world_state.source_states, *snapshot.model_state.models):
        refs.add(component.component_id)
        refs.update(component.references)
    return frozenset(refs)
