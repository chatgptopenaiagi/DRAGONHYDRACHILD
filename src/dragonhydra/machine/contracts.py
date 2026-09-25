"""ARX bounded observation contracts. Observations describe machines, never AI beliefs."""
from dataclasses import dataclass, fields
from datetime import datetime, timezone
import hashlib
import json
import math
import re


class MachineContractError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def timestamp(value):
    try:
        if type(value) is not str or len(value) > 40:
            raise ValueError()
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
            raise ValueError()
        return parsed
    except (ValueError, TypeError) as exc:
        raise MachineContractError("INVALID_CLOCK") from exc


def identifier(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value):
        raise MachineContractError("INVALID_IDENTIFIER")


def hash_value(value):
    if type(value) is not str or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise MachineContractError("INVALID_HASH")


def _strict(cls, value, extra=()):
    if type(value) is not dict or set(value) != {x.name for x in fields(cls)} | set(extra):
        raise MachineContractError("INVALID_SCHEMA")


FIELDS = {
    "os": {"name", "version", "build", "architecture", "boot_time", "uptime_seconds"},
    "cpu": {"name", "cores", "logical_processors", "load_percent"},
    "ram": {"total_bytes", "available_bytes"},
    "gpu": {"name", "driver", "memory_total_mib", "memory_used_mib", "utilization_percent", "cuda_version", "health"},
    "process": {"pid", "name", "start_time", "model_id", "port", "bind_address", "owned_experiment"},
    "service": {"name", "state", "start_mode", "pid"},
    "listener": {"address", "port", "pid", "exposure"},
    "tool": {"name", "version", "available", "runtime_id"},
    "repository": {"name", "head", "branch", "dirty", "staged_count", "unstaged_count", "untracked_count"},
    "task": {"name", "state", "last_result", "last_run", "next_run"},
    "distribution": {"name", "state", "version"},
    "conda_environment": {"name", "available"},
}
_SENSITIVE = re.compile(r"(?i)(password|passwd|api[_-]?key|access[_-]?token|bearer\s|sk-proj-|BEGIN .*PRIVATE KEY|chain.of.thought|hidden.reasoning)")
_STATUSES = {"OK", "UNKNOWN", "FAILED", "UNAVAILABLE"}
_NUMERIC = {"uptime_seconds", "cores", "logical_processors", "load_percent", "total_bytes", "available_bytes",
            "memory_total_mib", "memory_used_mib", "utilization_percent", "pid", "port", "staged_count",
            "unstaged_count", "untracked_count", "last_result"}


@dataclass(frozen=True, slots=True)
class MachineObservation:
    probe_id: str
    entity_id: str
    kind: str
    observed_at: str
    available_at: str
    created_at: str
    as_of_at: str
    freshness_ttl: int
    level: int
    status: str
    attributes: tuple
    reason_codes: tuple = ()

    def __post_init__(self):
        identifier(self.probe_id); identifier(self.entity_id)
        if self.kind not in FIELDS or self.status not in _STATUSES:
            raise MachineContractError("INVALID_OBSERVATION")
        clocks = [timestamp(getattr(self, x)) for x in ("observed_at", "available_at", "created_at", "as_of_at")]
        if clocks[0] > clocks[1] or clocks[1] > clocks[2] or clocks[0] > clocks[3]:
            raise MachineContractError("INVALID_CLOCK_ORDER")
        if type(self.level) is not int or not 0 <= self.level <= 2:
            raise MachineContractError("INSPECTION_LEVEL_DENIED")
        if type(self.freshness_ttl) is not int or not 1 <= self.freshness_ttl <= 86400:
            raise MachineContractError("INVALID_TTL")
        if type(self.attributes) not in (tuple, list) or len(self.attributes) > 20:
            raise MachineContractError("INVALID_ATTRIBUTES")
        seen = set()
        pairs = []
        for pair in self.attributes:
            if type(pair) not in (tuple, list) or len(pair) != 2:
                raise MachineContractError("INVALID_ATTRIBUTES")
            key, value = pair
            if key not in FIELDS[self.kind] or key in seen:
                raise MachineContractError("UNTRUSTED_CONTEXT")
            seen.add(key)
            if type(value) not in (str, int, float, bool, type(None)):
                raise MachineContractError("INVALID_ATTRIBUTE_VALUE")
            if type(value) is str:
                if len(value) > 180 or _SENSITIVE.search(value) or any(ord(c) < 32 for c in value) or "\\" in value or ":/" in value:
                    raise MachineContractError("UNTRUSTED_CONTEXT")
            if type(value) is float and not math.isfinite(value):
                raise MachineContractError("INVALID_ATTRIBUTE_VALUE")
            if key in _NUMERIC and value is not None:
                if type(value) not in (int, float) or value < 0:
                    raise MachineContractError("INVALID_ATTRIBUTE_VALUE")
                if key not in {"load_percent", "utilization_percent"} and (type(value) is not int or value > 2**63-1):
                    raise MachineContractError("INVALID_ATTRIBUTE_VALUE")
                if key in {"load_percent", "utilization_percent"} and value > 100:
                    raise MachineContractError("INVALID_ATTRIBUTE_VALUE")
                if key == "port" and not 1 <= value <= 65535:
                    raise MachineContractError("INVALID_ATTRIBUTE_VALUE")
                if key == "pid" and value > 2147483647:
                    raise MachineContractError("INVALID_ATTRIBUTE_VALUE")
            if key in {"dirty", "available", "owned_experiment"} and type(value) is not bool:
                raise MachineContractError("INVALID_ATTRIBUTE_VALUE")
            if key == "model_id" and value not in {None, "QWEN_4B", "QWEN_30B"}:
                raise MachineContractError("UNTRUSTED_CONTEXT")
            if key in {"address", "bind_address"} and value not in {None, "127.0.0.1", "localhost", "::1", "::", "0.0.0.0"}:
                raise MachineContractError("UNTRUSTED_CONTEXT")
            if key == "exposure" and value not in {"LOOPBACK", "ALL_INTERFACES"}:
                raise MachineContractError("UNTRUSTED_CONTEXT")
            if key == "state" and value not in {"Running", "Stopped", "Paused", "Start Pending", "Stop Pending", "Continue Pending", "Pause Pending", "Unknown", "Ready", "Disabled", "Queued", "Installing"}:
                raise MachineContractError("UNTRUSTED_CONTEXT")
            if key == "health" and value not in {"AVAILABLE", "UNAVAILABLE", "UNKNOWN"}:
                raise MachineContractError("UNTRUSTED_CONTEXT")
            if key in {"start_time", "boot_time", "last_run", "next_run"} and value is not None:
                timestamp(value)
            pairs.append((key, value))
        if self.status == "OK" and not pairs:
            raise MachineContractError("EMPTY_OBSERVATION")
        if type(self.reason_codes) not in (tuple, list) or len(self.reason_codes) > 12:
            raise MachineContractError("INVALID_REASONS")
        for code in self.reason_codes:
            identifier(code)
        object.__setattr__(self, "attributes", tuple(sorted(pairs)))
        object.__setattr__(self, "reason_codes", tuple(sorted(set(self.reason_codes))))

    @property
    def data(self):
        return dict(self.attributes)

    @property
    def state_hash(self):
        value = {"entity_id": self.entity_id, "kind": self.kind, "status": self.status,
                 "attributes": dict(self.attributes), "reason_codes": self.reason_codes}
        # Capture time and uptime do not represent semantic identity changes.
        value["attributes"].pop("uptime_seconds", None)
        return digest(value)

    def is_fresh(self, now):
        age = (timestamp(now) - timestamp(self.observed_at)).total_seconds()
        return self.status == "OK" and 0 <= age <= self.freshness_ttl

    def to_dict(self):
        return {field.name: ([list(v) for v in self.attributes] if field.name == "attributes" else
                list(self.reason_codes) if field.name == "reason_codes" else getattr(self, field.name)) for field in fields(self)}

    @classmethod
    def from_dict(cls, value):
        _strict(cls, value)
        return cls(**value)


@dataclass(frozen=True, slots=True)
class MachineProbeReceipt:
    probe_id: str
    observed_at: str
    available_at: str
    status: str
    observation_count: int
    latency_ms: int
    failure_state: str | None
    output_hash: str

    def __post_init__(self):
        identifier(self.probe_id); timestamp(self.observed_at); timestamp(self.available_at); hash_value(self.output_hash)
        if timestamp(self.available_at) < timestamp(self.observed_at):
            raise MachineContractError("INVALID_CLOCK_ORDER")
        if self.status not in _STATUSES or type(self.observation_count) is not int or not 0 <= self.observation_count <= 1024:
            raise MachineContractError("INVALID_RECEIPT")
        if type(self.latency_ms) is not int or not 0 <= self.latency_ms <= 300000:
            raise MachineContractError("INVALID_RECEIPT")
        if (self.status == "OK") != (self.failure_state is None):
            raise MachineContractError("INVALID_FAILURE_STATE")
        if self.failure_state is not None:
            identifier(self.failure_state)

    def to_dict(self):
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @property
    def state_hash(self): return digest(self.to_dict())

    @classmethod
    def from_dict(cls, value):
        _strict(cls, value); return cls(**value)


@dataclass(frozen=True, slots=True)
class MachineHealth:
    status: str
    failed_probes: tuple
    unavailable_probes: tuple
    reason_codes: tuple

    def __post_init__(self):
        if self.status not in {"HEALTHY", "PARTIAL", "FAILED"}: raise MachineContractError("INVALID_HEALTH")
        for name in ("failed_probes", "unavailable_probes", "reason_codes"):
            values = getattr(self, name)
            if type(values) not in (list, tuple) or len(values) > 32: raise MachineContractError("INVALID_HEALTH")
            for value in values: identifier(value)
            object.__setattr__(self, name, tuple(values))

    @property
    def state_hash(self): return digest(self.to_dict())

    def to_dict(self):
        return {"status": self.status, "failed_probes": list(self.failed_probes),
                "unavailable_probes": list(self.unavailable_probes), "reason_codes": list(self.reason_codes)}

    @classmethod
    def from_dict(cls, value):
        _strict(cls, value)
        if value["status"] not in {"HEALTHY", "PARTIAL", "FAILED"}:
            raise MachineContractError("INVALID_HEALTH")
        for key in ("failed_probes", "unavailable_probes", "reason_codes"):
            if type(value[key]) not in (list, tuple) or len(value[key]) > 32:
                raise MachineContractError("INVALID_HEALTH")
            for item in value[key]: identifier(item)
        return cls(value["status"], tuple(value["failed_probes"]), tuple(value["unavailable_probes"]), tuple(value["reason_codes"]))


@dataclass(frozen=True, slots=True)
class MachineCapability:
    capability_id: str
    enabled: bool = True
    read_only: bool = True
    maximum_level: int = 2
    timeout_seconds: int = 15

    def __post_init__(self):
        identifier(self.capability_id)
        if type(self.enabled) is not bool or self.read_only is not True or type(self.maximum_level) is not int or not 0 <= self.maximum_level <= 2:
            raise MachineContractError("CAPABILITY_DENIED")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 30:
            raise MachineContractError("CAPABILITY_DENIED")

    def to_dict(self): return {x.name: getattr(self, x.name) for x in fields(self)}

    @property
    def state_hash(self): return digest(self.to_dict())

    @classmethod
    def from_dict(cls, value):
        _strict(cls, value); return cls(**value)


@dataclass(frozen=True, slots=True)
class MachineSnapshot:
    snapshot_id: str
    created_at: str
    as_of_at: str
    observations: tuple
    receipts: tuple
    schema_version: str = "2"

    def __post_init__(self):
        identifier(self.snapshot_id); timestamp(self.created_at); timestamp(self.as_of_at)
        if self.schema_version != "2" or timestamp(self.as_of_at) > timestamp(self.created_at):
            raise MachineContractError("INVALID_SNAPSHOT")
        if type(self.observations) not in (list, tuple) or len(self.observations) > 1024 or type(self.receipts) not in (list, tuple) or not 1 <= len(self.receipts) <= 32:
            raise MachineContractError("REQUEST_TOO_LARGE")
        observations = tuple(x if isinstance(x, MachineObservation) else MachineObservation.from_dict(x) for x in self.observations)
        receipts = tuple(x if isinstance(x, MachineProbeReceipt) else MachineProbeReceipt.from_dict(x) for x in self.receipts)
        if len({x.entity_id for x in observations}) != len(observations) or len({x.probe_id for x in receipts}) != len(receipts):
            raise MachineContractError("DUPLICATE_ENTITY")
        by_probe = {x.probe_id: x for x in receipts}
        for observation in observations:
            if observation.probe_id not in by_probe or timestamp(observation.as_of_at) > timestamp(self.as_of_at):
                raise MachineContractError("MISSING_PROVENANCE")
        for receipt in receipts:
            members = [x.to_dict() for x in observations if x.probe_id == receipt.probe_id]
            if len(members) != receipt.observation_count or digest(sorted(members, key=lambda x: x["entity_id"])) != receipt.output_hash:
                raise MachineContractError("PROBE_HASH_MISMATCH")
        object.__setattr__(self, "observations", tuple(sorted(observations, key=lambda x: x.entity_id)))
        object.__setattr__(self, "receipts", tuple(sorted(receipts, key=lambda x: x.probe_id)))
        if len(canonical(self.to_dict())) > 524288:
            raise MachineContractError("REQUEST_TOO_LARGE")

    @property
    def state_hash(self):
        return digest({"schema_version": self.schema_version, "observations": [(x.entity_id, x.state_hash) for x in self.observations],
                       "probes": [(x.probe_id, x.status, x.failure_state) for x in self.receipts]})

    @property
    def health(self):
        failed = tuple(x.probe_id for x in self.receipts if x.status in {"FAILED", "UNKNOWN"})
        unavailable = tuple(x.probe_id for x in self.receipts if x.status == "UNAVAILABLE")
        status = "HEALTHY" if not failed and not unavailable else "FAILED" if not self.observations else "PARTIAL"
        return MachineHealth(status, failed, unavailable, ("MACHINE_PROBE_FAILED",) if failed else ("OPTIONAL_COMPONENT_UNAVAILABLE",) if unavailable else ())

    def is_fresh(self, now, ttl=120):
        if type(ttl) is not int or not 1 <= ttl <= 86400:
            raise MachineContractError("INVALID_TTL")
        age = (timestamp(now) - timestamp(self.as_of_at)).total_seconds()
        return (0 <= age <= ttl and bool(self.observations) and not self.health.failed_probes
                and all(x.is_fresh(now) for x in self.observations if x.status == "OK"))

    def to_dict(self):
        return {"schema_version": self.schema_version, "snapshot_id": self.snapshot_id, "created_at": self.created_at,
                "as_of_at": self.as_of_at, "observations": [x.to_dict() for x in self.observations],
                "receipts": [x.to_dict() for x in self.receipts], "state_hash": self.state_hash}

    @classmethod
    def from_dict(cls, value):
        _strict(cls, value, ("state_hash",))
        instance = cls(**{k: v for k, v in value.items() if k != "state_hash"})
        if value["state_hash"] != instance.state_hash: raise MachineContractError("STATE_HASH_MISMATCH")
        return instance


@dataclass(frozen=True, slots=True)
class MachineEvent:
    event_id: str
    event_type: str
    observed_at: str
    source_probe: str
    entity_id: str
    before_hash: str | None
    after_hash: str | None
    severity: str
    freshness: str
    reason_codes: tuple
    references: tuple

    def __post_init__(self):
        for value in (self.event_id, self.event_type, self.source_probe, self.entity_id): identifier(value)
        timestamp(self.observed_at)
        for value in (self.before_hash, self.after_hash):
            if value is not None: hash_value(value)
        if self.severity not in {"INFO", "WARNING", "ERROR"} or self.freshness not in {"FRESH", "STALE", "UNKNOWN"}:
            raise MachineContractError("INVALID_EVENT")
        for name in ("reason_codes", "references"):
            values = getattr(self, name)
            if type(values) not in (tuple, list) or len(values) > 12: raise MachineContractError("INVALID_EVENT")
            for value in values: identifier(value)
            object.__setattr__(self, name, tuple(values))

    def to_dict(self):
        return {x.name: list(getattr(self, x.name)) if x.name in {"reason_codes", "references"} else getattr(self, x.name) for x in fields(self)}

    @property
    def state_hash(self): return digest(self.to_dict())

    @classmethod
    def from_dict(cls, value):
        _strict(cls, value); return cls(**value)


@dataclass(frozen=True, slots=True)
class MachineDelta:
    before_hash: str
    after_hash: str
    observed_at: str
    events: tuple
    reason_codes: tuple = ()

    def __post_init__(self):
        hash_value(self.before_hash); hash_value(self.after_hash); timestamp(self.observed_at)
        if type(self.events) not in (tuple, list) or len(self.events) > 2048: raise MachineContractError("REQUEST_TOO_LARGE")
        object.__setattr__(self, "events", tuple(x if isinstance(x, MachineEvent) else MachineEvent.from_dict(x) for x in self.events))
        if type(self.reason_codes) not in (tuple, list) or len(self.reason_codes) > 32: raise MachineContractError("INVALID_REASONS")
        for value in self.reason_codes: identifier(value)
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))

    @property
    def state_hash(self): return digest(self.to_dict())

    def to_dict(self):
        return {"before_hash": self.before_hash, "after_hash": self.after_hash, "observed_at": self.observed_at,
                "events": [x.to_dict() for x in self.events], "reason_codes": list(self.reason_codes)}

    @classmethod
    def from_dict(cls, value):
        _strict(cls, value); return cls(**value)
