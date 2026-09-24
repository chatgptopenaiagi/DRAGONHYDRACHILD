"""Thirteen logical capabilities share acquisition infrastructure; no agents/processes."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from math import isfinite

from dragonhydra.science.temporal import aware_utc


class Maturity(StrEnum):
    CONCEPT = "CONCEPT"
    EXPERIMENTAL = "EXPERIMENTAL"
    VALIDATED = "VALIDATED"
    STABLE = "STABLE"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class OperationalStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    READY = "READY"
    ACTIVE = "ACTIVE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    TERMS_BLOCKED = "TERMS_BLOCKED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"


HEAD_NAMES = ("MATCH", "PLAYER", "TEAM", "INJURY", "LINEUP", "COACH", "WEATHER",
              "TRAVEL", "TACTICAL", "NEWS", "ODDS", "MARKET", "HISTORICAL")


@dataclass(frozen=True, slots=True)
class HeadStatus:
    head: str
    scope: str
    data_classes: tuple[str, ...]
    allowed_sources: tuple[str, ...]
    contract_version: str
    maturity: Maturity
    operational_status: OperationalStatus
    max_requests_per_minute: int = 1
    failure_policy: str = "RECORD_AND_STOP_NO_EVASION"
    reliability_score: float | None = None
    last_observation_at: datetime | None = None
    last_failure: str | None = None
    test_evidence: tuple[str, ...] = ()

    def __post_init__(self):
        if self.head not in HEAD_NAMES or not self.scope.strip() or not self.contract_version.strip():
            raise ValueError("Logical head identity, scope and contract are required")
        if not isinstance(self.maturity, Maturity) or not isinstance(self.operational_status, OperationalStatus):
            raise ValueError("Maturity and operational status are separate typed dimensions")
        if not isinstance(self.data_classes, tuple) or not self.data_classes or not isinstance(self.allowed_sources, tuple):
            raise ValueError("Head data classes and sources must be immutable")
        if type(self.max_requests_per_minute) is not int or not 1 <= self.max_requests_per_minute <= 60:
            raise ValueError("Head rate policy must remain bounded")
        if self.reliability_score is not None and (not isfinite(self.reliability_score) or not 0 <= self.reliability_score <= 1):
            raise ValueError("Reliability must be measured in [0,1] or unknown")
        if self.last_observation_at is not None:
            aware_utc(self.last_observation_at)
        if self.operational_status in (OperationalStatus.ACTIVE, OperationalStatus.READY) and not self.allowed_sources:
            raise ValueError("An active capability requires an explicit source allowlist")
        if self.maturity in (Maturity.VALIDATED, Maturity.STABLE) and not self.test_evidence:
            raise ValueError("Validated maturity requires test evidence")

    def to_dict(self):
        return {"head": self.head, "scope": self.scope, "data_classes": list(self.data_classes),
                "allowed_sources": list(self.allowed_sources), "contract_version": self.contract_version,
                "maturity": self.maturity.value, "operational_status": self.operational_status.value,
                "max_requests_per_minute": self.max_requests_per_minute, "failure_policy": self.failure_policy,
                "reliability_score": self.reliability_score,
                "last_observation_at": self.last_observation_at.isoformat() if self.last_observation_at else None,
                "last_failure": self.last_failure, "test_evidence": list(self.test_evidence),
                "execution_model": "LOGICAL_CAPABILITY_SHARED_FETCHER"}


def default_heads() -> tuple[HeadStatus, ...]:
    return tuple(HeadStatus(name, f"One approved competition: {name.lower()} evidence", (name.lower(),), (),
                            "1", Maturity.CONCEPT,
                            OperationalStatus.SOURCE_UNAVAILABLE if name == "PLAYER" else OperationalStatus.NOT_STARTED,
                            last_failure="PLAYER_IDENTITY_DEFERRED_NO_APPROVED_SOURCE" if name == "PLAYER" else None)
                 for name in HEAD_NAMES)


def update_head(heads: tuple[HeadStatus, ...], head: str, **changes) -> tuple[HeadStatus, ...]:
    if len(heads) != 13 or {item.head for item in heads} != set(HEAD_NAMES):
        raise ValueError("Registry must contain exactly the thirteen logical capabilities")
    if head not in HEAD_NAMES:
        raise ValueError("Unknown logical head")
    return tuple(replace(item, **changes) if item.head == head else item for item in heads)
