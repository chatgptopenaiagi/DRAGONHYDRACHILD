"""Deterministic advisory routing; this module never starts or stops a model."""
from dataclasses import asdict, dataclass
import math
import re

from dragonhydra.localai.contracts import content_hash

FAST_TASKS = frozenset({'CLASSIFY_STATE', 'SUMMARIZE_STATE', 'TRIAGE_CHANGES',
    'INTERPRET_HEALTH', 'CATEGORIZE_UNCERTAINTY', 'REVIEW_EVIDENCE', 'DETECT_ANOMALY',
    'ESTIMATE_COMPLEXITY'})
DEEP_TASKS = frozenset({'REVIEW_ARCHITECTURE', 'COMPARE_STATES', 'GENERATE_HYPOTHESES',
    'PLAN_RESEARCH', 'ANALYZE_DISAGREEMENT', 'DECOMPOSE_UNCERTAINTY',
    'RECONCILE_SOURCES', 'REVIEW_SOFTWARE'})
TASK_KINDS = FAST_TASKS | DEEP_TASKS
MODELS = ('qwen3-4b', 'qwen3-coder-30b')
MAX_CONTEXT_BYTES = 6500


@dataclass(frozen=True)
class RoutingInput:
    task_kind: str
    context_bytes: int
    complexity_class: str = 'LOW'
    urgency: str = 'NORMAL'
    required_latency_ms: int | None = None
    available_ram_mb: int | None = None
    available_vram_mb: int | None = None
    cpu_load_percent: float | None = None
    available_models: tuple[str, ...] = MODELS
    occupied_models: tuple[str, ...] = ()

    def __post_init__(self):
        if self.task_kind not in TASK_KINDS:
            raise ValueError('UNSUPPORTED_TASK')
        if type(self.context_bytes) is not int or not 0 < self.context_bytes <= MAX_CONTEXT_BYTES:
            raise ValueError('REQUEST_TOO_LARGE')
        if self.complexity_class not in {'LOW', 'MEDIUM', 'HIGH'} or self.urgency not in {'NORMAL', 'HIGH'}:
            raise ValueError('INVALID_ROUTING_INPUT')
        for name in ('required_latency_ms', 'available_ram_mb', 'available_vram_mb'):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError('INVALID_ROUTING_INPUT')
        value = self.cpu_load_percent
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100):
            raise ValueError('INVALID_ROUTING_INPUT')
        for name in ('available_models', 'occupied_models'):
            values = getattr(self, name)
            if type(values) not in (list, tuple) or any(v not in MODELS for v in values) or len(values) != len(set(values)):
                raise ValueError('INVALID_ROUTING_INPUT')
            object.__setattr__(self, name, tuple(sorted(values)))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise ValueError('INVALID_ROUTING_INPUT')
        return cls(**value)


@dataclass(frozen=True)
class RoutingDecision:
    selected_model: str | None
    reason_codes: tuple[str, ...]
    fallback_model: str | None
    routing_hash: str
    result_status: str

    def __post_init__(self):
        if self.selected_model not in (*MODELS, None) or self.fallback_model not in (*MODELS, None):
            raise ValueError('INVALID_ROUTING_DECISION')
        if self.selected_model is not None and self.selected_model == self.fallback_model:
            raise ValueError('INVALID_ROUTING_DECISION')
        if self.result_status not in {'SUCCESS', 'BLOCKED'} or (self.selected_model is None) != (self.result_status == 'BLOCKED'):
            raise ValueError('INVALID_ROUTING_DECISION')
        if type(self.routing_hash) is not str or re.fullmatch('[0-9a-f]{64}', self.routing_hash) is None:
            raise ValueError('INVALID_ROUTING_DECISION')
        if type(self.reason_codes) not in (list, tuple) or not 1 <= len(self.reason_codes) <= 20:
            raise ValueError('INVALID_ROUTING_DECISION')
        if any(type(value) is not str or re.fullmatch('[A-Z][A-Z_]{1,80}', value) is None for value in self.reason_codes):
            raise ValueError('INVALID_ROUTING_DECISION')
        object.__setattr__(self, 'reason_codes', tuple(self.reason_codes))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise ValueError('INVALID_ROUTING_DECISION')
        return cls(**value)


class ModelRouter:
    """Resource floors are conservative policy estimates, not latency guarantees.

    Unknown RAM prevents a new deep-model selection; an already available fast
    endpoint can still be proposed with an explicit resource uncertainty reason.
    No fallback is executed automatically and no unavailable output is invented.
    """

    def route(self, request: RoutingInput) -> RoutingDecision:
        if type(request) is not RoutingInput:
            raise ValueError('INVALID_ROUTING_INPUT')
        deep = request.task_kind in DEEP_TASKS or request.complexity_class == 'HIGH'
        reasons = ['DEEP_TASK' if deep else 'FAST_TASK']
        preferred = MODELS[1] if deep else MODELS[0]
        if deep and (request.urgency == 'HIGH' or (request.required_latency_ms is not None and request.required_latency_ms < 30000)):
            preferred = MODELS[0]
            reasons.append('LATENCY_BUDGET_PREFERS_FAST_MODEL')
        if request.cpu_load_percent is not None and request.cpu_load_percent >= 90:
            reasons.append('HIGH_MACHINE_LOAD')
        eligible = []
        for model in MODELS:
            if model not in request.available_models:
                reasons.append('FAST_MODEL_UNAVAILABLE' if model == MODELS[0] else 'DEEP_MODEL_UNAVAILABLE')
                continue
            if model in request.occupied_models:
                reasons.append('FAST_MODEL_OCCUPIED' if model == MODELS[0] else 'DEEP_MODEL_OCCUPIED')
                continue
            floor = 6144 if model == MODELS[0] else 28672
            if request.available_ram_mb is None and model == MODELS[1]:
                reasons.append('DEEP_MODEL_RAM_UNKNOWN')
                continue
            if request.available_ram_mb is not None and request.available_ram_mb < floor:
                reasons.append('FAST_MODEL_RAM_INSUFFICIENT' if model == MODELS[0] else 'DEEP_MODEL_RAM_INSUFFICIENT')
                continue
            if model == MODELS[1] and request.cpu_load_percent is not None and request.cpu_load_percent >= 90:
                continue
            eligible.append(model)
        selected = preferred if preferred in eligible else (eligible[0] if eligible else None)
        if selected and selected != preferred:
            reasons.append('EXPLICIT_RESOURCE_FALLBACK')
        if request.available_ram_mb is None:
            reasons.append('RAM_STATE_UNKNOWN')
        if selected and request.available_vram_mb is not None and request.available_vram_mb < 3072:
            reasons.append('CPU_FALLBACK_REQUIRES_ENGINEERING_LAUNCH')
        if selected is None:
            reasons.append('MODEL_UNAVAILABLE')
        fallback = next((model for model in eligible if model != selected), None)
        reason_codes = tuple(dict.fromkeys(reasons))
        digest = content_hash({'policy_version': '2.0', 'input': request.to_dict(),
            'selected_model': selected, 'fallback_model': fallback, 'reason_codes': reason_codes})
        return RoutingDecision(selected, reason_codes, fallback, digest,
            'SUCCESS' if selected else 'BLOCKED')
