"""Bounded, non-evidence LocalAI protocol. No source prose or executable actions.

Only controlled summary fields cross this boundary. Conclusions remain advisory;
they cannot construct accepted HYDRA/MEDUSA evidence or mutate a forecast.
"""

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from uuid import UUID, uuid4


SCHEMA_VERSION = "1"
MAX_SNAPSHOT_BYTES = 6000
MAX_REQUEST_BYTES = 8192
MAX_RESPONSE_BYTES = 16384
TASK_KINDS = frozenset({"ANALYZE_UNCERTAINTY", "CRITIQUE_STATE", "SUGGEST_RESEARCH"})
DIMENSIONS = frozenset({"LINEUP", "INJURY", "MARKET", "WEATHER", "IDENTITY", "TIMING",
                        "MODEL_DISAGREEMENT", "SOURCE_RELIABILITY", "HISTORY", "OUTCOME", "GENERAL"})
MISSING_EVIDENCE = frozenset({"LINEUP", "INJURY", "ODDS", "WEATHER", "IDENTITY", "KICKOFF_TIME",
                             "HISTORY", "OUTCOME", "SOURCE_VALIDATION"})
OUTPUT_STATES = frozenset({"HYPOTHESIS", "INTERPRETATION", "CRITIQUE", "RESEARCH_PROPOSAL", "ANOMALY_REPORT"})
REASON_CODES = frozenset({"MISSING_EVIDENCE", "HIGH_UNCERTAINTY", "MODEL_DISAGREEMENT", "SOURCE_FAILURE",
                         "TEMPORAL_GAP", "INSUFFICIENT_EVIDENCE", "RESEARCH_RECOMMENDED", "NO_ACTION_REQUIRED"})
FAILURE_STATES = frozenset({"LOCALAI_UNAVAILABLE", "MODEL_UNAVAILABLE", "MODEL_HASH_MISMATCH",
                           "REQUEST_TOO_LARGE", "INVALID_RESPONSE", "TIMEOUT", "RUNTIME_FAILURE",
                           "UNSUPPORTED_TASK", "INVALID_REQUEST", "AUDIT_FAILURE"})


class ContractError(ValueError):
    """Protocol rejection with a safe, non-secret reason code."""

    def __init__(self, reason_code="INVALID_REQUEST"):
        self.reason_code = reason_code
        super().__init__(reason_code)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def content_hash(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def strict_json(raw, *, max_bytes=MAX_RESPONSE_BYTES):
    """Reject duplicate keys, non-JSON numeric constants and oversized input."""
    if not isinstance(raw, (str, bytes)):
        raise ContractError("INVALID_RESPONSE")
    if len(raw.encode("utf-8") if isinstance(raw, str) else raw) > max_bytes:
        raise ContractError("REQUEST_TOO_LARGE")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ContractError("INVALID_RESPONSE")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ContractError("INVALID_RESPONSE")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError("INVALID_RESPONSE") from exc


def _keys(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise ContractError()


def _choice(value, choices):
    if type(value) is not str or value not in choices:
        raise ContractError()


def _identifier(value):
    if (type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value)
            or re.search(r"(?i)(password|passwd|secret|bearer|api.?key|access.?token|sk-proj)", value)):
        raise ContractError()


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ContractError()


def _time(value):
    if type(value) is not str or len(value) > 40:
        raise ContractError()
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ContractError() from exc
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ContractError()
    return stamp


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _score(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ContractError()


def _sequence(value, maximum, *, minimum=0):
    if type(value) not in (list, tuple) or not minimum <= len(value) <= maximum:
        raise ContractError()


class _Contract:
    def to_dict(self):
        # A JSON round-trip converts immutable tuples to portable JSON arrays.
        return json.loads(canonical_bytes(asdict(self)))

    @classmethod
    def from_dict(cls, value):
        _keys(value, (field.name for field in fields(cls)))
        return cls(**value)


@dataclass(frozen=True, slots=True)
class EvidenceSummary(_Contract):
    evidence_id: str
    source_id: str
    content_hash: str
    provenance_ids: tuple[str, ...]
    epistemic_state: str
    available_at: str

    def __post_init__(self):
        _identifier(self.evidence_id)
        _identifier(self.source_id)
        _hash(self.content_hash)
        _sequence(self.provenance_ids, 8, minimum=1)
        for value in self.provenance_ids:
            _identifier(value)
        object.__setattr__(self, "provenance_ids", tuple(self.provenance_ids))
        _choice(self.epistemic_state, {"OBSERVATION", "RECONSTRUCTED_PIT", "SYNTHETIC"})
        _time(self.available_at)


@dataclass(frozen=True, slots=True)
class UncertaintySummary(_Contract):
    dimension: str
    score: float

    def __post_init__(self):
        _choice(self.dimension, DIMENSIONS)
        _score(self.score)


@dataclass(frozen=True, slots=True)
class ForecastSummary(_Contract):
    model_id: str
    probabilities: tuple[float, float, float]
    epistemic_state: str = "PREDICTION"

    def __post_init__(self):
        _identifier(self.model_id)
        _sequence(self.probabilities, 3, minimum=3)
        for value in self.probabilities:
            _score(value)
        if abs(sum(self.probabilities) - 1) > 1e-9:
            raise ContractError()
        object.__setattr__(self, "probabilities", tuple(self.probabilities))
        _choice(self.epistemic_state, {"PREDICTION"})


@dataclass(frozen=True, slots=True)
class Snapshot(_Contract):
    schema_version: str
    as_of_at: str
    temporal_mode: str
    fixture_id: str
    evidence: tuple[EvidenceSummary, ...]
    uncertainty: tuple[UncertaintySummary, ...]
    forecasts: tuple[ForecastSummary, ...]
    missing_evidence: tuple[str, ...]

    def __post_init__(self):
        _choice(self.schema_version, {SCHEMA_VERSION})
        cursor = _time(self.as_of_at)
        _choice(self.temporal_mode, {"STRICT_PIT", "RECONSTRUCTED_PIT", "SYNTHETIC"})
        _identifier(self.fixture_id)
        for name, cls, maximum in (("evidence", EvidenceSummary, 16),
                                   ("uncertainty", UncertaintySummary, 11),
                                   ("forecasts", ForecastSummary, 8)):
            values = getattr(self, name)
            _sequence(values, maximum)
            normalized = tuple(item if type(item) is cls else cls.from_dict(item) for item in values)
            object.__setattr__(self, name, normalized)
        _sequence(self.missing_evidence, len(MISSING_EVIDENCE))
        for item in self.missing_evidence:
            _choice(item, MISSING_EVIDENCE)
        object.__setattr__(self, "missing_evidence", tuple(self.missing_evidence))
        for values in ((e.evidence_id for e in self.evidence), (u.dimension for u in self.uncertainty),
                       (f.model_id for f in self.forecasts), self.missing_evidence):
            items = list(values)
            if len(items) != len(set(items)):
                raise ContractError()
        for evidence in self.evidence:
            if _time(evidence.available_at) > cursor:
                raise ContractError()
            expected = {"STRICT_PIT": "OBSERVATION", "RECONSTRUCTED_PIT": "RECONSTRUCTED_PIT",
                        "SYNTHETIC": "SYNTHETIC"}[self.temporal_mode]
            if evidence.epistemic_state != expected:
                raise ContractError()
        if len(canonical_bytes(self.to_dict())) > MAX_SNAPSHOT_BYTES:
            raise ContractError("REQUEST_TOO_LARGE")

    @property
    def state_hash(self):
        return content_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class AnalysisRequest(_Contract):
    schema_version: str
    request_id: str
    created_at: str
    model_id: str
    model_hash: str
    runtime_id: str
    task_kind: str
    snapshot: Snapshot
    input_hash: str

    def __post_init__(self):
        _choice(self.schema_version, {SCHEMA_VERSION})
        try:
            if type(self.request_id) is not str or str(UUID(self.request_id)) != self.request_id:
                raise ValueError()
        except (ValueError, AttributeError) as exc:
            raise ContractError() from exc
        _time(self.created_at)
        _identifier(self.model_id)
        _identifier(self.runtime_id)
        _hash(self.model_hash)
        if type(self.task_kind) is not str or self.task_kind not in TASK_KINDS:
            raise ContractError("UNSUPPORTED_TASK")
        if type(self.snapshot) is not Snapshot:
            object.__setattr__(self, "snapshot", Snapshot.from_dict(self.snapshot))
        if _time(self.snapshot.as_of_at) > _time(self.created_at):
            raise ContractError()
        _hash(self.input_hash)
        if self.input_hash != self.expected_input_hash():
            raise ContractError()
        if len(canonical_bytes(self.to_dict())) > MAX_REQUEST_BYTES:
            raise ContractError("REQUEST_TOO_LARGE")

    def expected_input_hash(self):
        return content_hash({"snapshot": self.snapshot.to_dict(), "task_kind": self.task_kind})

    @classmethod
    def create(cls, snapshot, task_kind, model_id, model_hash, runtime_id, *, request_id=None, created_at=None):
        if type(snapshot) is not Snapshot:
            raise ContractError()
        return cls(SCHEMA_VERSION, request_id or str(uuid4()), created_at or utc_now(), model_id,
                   model_hash, runtime_id, task_kind, snapshot,
                   content_hash({"snapshot": snapshot.to_dict(), "task_kind": task_kind}))


@dataclass(frozen=True, slots=True)
class Conclusion(_Contract):
    epistemic_state: str
    dimension: str
    priority: str
    reason_code: str

    def __post_init__(self):
        _choice(self.epistemic_state, OUTPUT_STATES)
        _choice(self.dimension, DIMENSIONS)
        _choice(self.priority, {"LOW", "MEDIUM", "HIGH"})
        _choice(self.reason_code, REASON_CODES)


MODEL_OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["conclusions"],
    "properties": {"conclusions": {"type": "array", "minItems": 1, "maxItems": 4, "items": {
        "type": "object", "additionalProperties": False,
        "required": ["epistemic_state", "dimension", "priority", "reason_code"], "properties": {
            "epistemic_state": {"type": "string", "enum": sorted(OUTPUT_STATES)},
            "dimension": {"type": "string", "enum": sorted(DIMENSIONS)},
            "priority": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
            "reason_code": {"type": "string", "enum": sorted(REASON_CODES)},
        }}}}}


def parse_model_output(raw):
    try:
        payload = strict_json(raw)
        _keys(payload, {"conclusions"})
        _sequence(payload["conclusions"], 4, minimum=1)
        return tuple(Conclusion.from_dict(item) for item in payload["conclusions"])
    except (ContractError, TypeError, KeyError) as exc:
        raise ContractError("INVALID_RESPONSE") from exc


@dataclass(frozen=True, slots=True)
class AnalysisResponse(_Contract):
    schema_version: str
    request_id: str
    created_at: str
    model_id: str
    model_hash: str
    runtime_id: str
    input_hash: str
    output_hash: str
    task_kind: str
    result_status: str
    failure_state: str | None
    latency_ms: float
    reason_codes: tuple[str, ...]
    conclusions: tuple[Conclusion, ...]

    def __post_init__(self):
        _choice(self.schema_version, {SCHEMA_VERSION})
        try:
            if type(self.request_id) is not str or str(UUID(self.request_id)) != self.request_id:
                raise ValueError()
        except (ValueError, AttributeError) as exc:
            raise ContractError() from exc
        _time(self.created_at)
        _identifier(self.model_id)
        _identifier(self.runtime_id)
        for value in (self.model_hash, self.input_hash, self.output_hash):
            _hash(value)
        _choice(self.task_kind, TASK_KINDS)
        _choice(self.result_status, {"SUCCESS", "FAILURE"})
        if type(self.latency_ms) not in (float, int) or not math.isfinite(self.latency_ms) or not 0 <= self.latency_ms <= 3600000:
            raise ContractError()
        _sequence(self.reason_codes, 4, minimum=1)
        _sequence(self.conclusions, 4)
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "conclusions", tuple(c if type(c) is Conclusion else Conclusion.from_dict(c) for c in self.conclusions))
        if self.result_status == "SUCCESS":
            if self.failure_state is not None or not self.conclusions or self.reason_codes != ("MODEL_ANALYSIS",):
                raise ContractError()
        else:
            _choice(self.failure_state, FAILURE_STATES)
            if self.conclusions or self.reason_codes != (self.failure_state,):
                raise ContractError()
        if self.output_hash != self.expected_output_hash():
            raise ContractError("INVALID_RESPONSE")
        if len(canonical_bytes(self.to_dict())) > MAX_RESPONSE_BYTES:
            raise ContractError("INVALID_RESPONSE")

    def expected_output_hash(self):
        data = self.to_dict()
        data.pop("output_hash")
        return content_hash(data)

    @classmethod
    def _build(cls, request, conclusions, latency_ms, failure_state):
        data = {"schema_version": SCHEMA_VERSION, "request_id": request.request_id,
                "created_at": utc_now(), "model_id": request.model_id, "model_hash": request.model_hash,
                "runtime_id": request.runtime_id, "input_hash": request.input_hash,
                "task_kind": request.task_kind, "result_status": "FAILURE" if failure_state else "SUCCESS",
                "failure_state": failure_state, "latency_ms": latency_ms,
                "reason_codes": [failure_state] if failure_state else ["MODEL_ANALYSIS"],
                "conclusions": [c.to_dict() if type(c) is Conclusion else c for c in conclusions]}
        data["output_hash"] = content_hash(data)
        return cls.from_dict(data)

    @classmethod
    def success(cls, request, conclusions, latency_ms):
        return cls._build(request, conclusions, latency_ms, None)

    @classmethod
    def failure(cls, request, failure_state, latency_ms=0):
        return cls._build(request, (), latency_ms, failure_state)

    def validate_for(self, request):
        for name in ("request_id", "model_id", "model_hash", "runtime_id", "input_hash", "task_kind"):
            if getattr(self, name) != getattr(request, name):
                raise ContractError("MODEL_HASH_MISMATCH" if name in {"model_id", "model_hash", "runtime_id"} else "INVALID_RESPONSE")
        return self
