"""Epistemic labels are part of the contract, not presentation decoration."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from dragonhydra.science.temporal import Availability, TemporalMode, aware_utc


class EpistemicType(StrEnum):
    OBSERVATION = "OBSERVATION"
    RECONSTRUCTION = "RECONSTRUCTION"
    DERIVED_FEATURE = "DERIVED_FEATURE"
    PREDICTION = "PREDICTION"
    SIMULATION = "SIMULATION"
    MARKET_OBSERVATION = "MARKET_OBSERVATION"
    HYPOTHESIS = "HYPOTHESIS"


@dataclass(frozen=True, slots=True)
class ContinuumRecord:
    record_id: str
    fixture_id: str
    epistemic_type: EpistemicType
    event_at: datetime
    availability: Availability
    evidence_ids: tuple[str, ...]
    description: str
    synthetic: bool = False

    def __post_init__(self):
        if not self.record_id.strip() or not self.fixture_id.strip() or not self.description.strip():
            raise ValueError("Continuum identity and description are required")
        if not isinstance(self.epistemic_type, EpistemicType) or not isinstance(self.availability, Availability):
            raise ValueError("Typed epistemic and availability contracts are required")
        aware_utc(self.event_at)
        if not isinstance(self.evidence_ids, tuple) or not self.evidence_ids or any(not value.strip() for value in self.evidence_ids):
            raise ValueError("Every continuum record needs immutable evidence references")
        if self.epistemic_type in (EpistemicType.OBSERVATION, EpistemicType.MARKET_OBSERVATION):
            if self.availability.availability_mode is not TemporalMode.STRICT_PIT:
                raise ValueError("Reconstructed availability cannot be labeled genuine observation")
        if self.epistemic_type is EpistemicType.RECONSTRUCTION and self.availability.availability_mode is not TemporalMode.RECONSTRUCTED_PIT:
            raise ValueError("Reconstruction requires reconstructed temporal metadata")

    def require_observed_fact(self) -> "ContinuumRecord":
        if self.synthetic or self.epistemic_type not in (EpistemicType.OBSERVATION, EpistemicType.MARKET_OBSERVATION):
            raise ValueError("Projection, reconstruction and synthetic material are not observed facts")
        return self

    def to_dict(self) -> dict:
        return {"record_id": self.record_id, "fixture_id": self.fixture_id,
                "epistemic_type": self.epistemic_type.value, "event_at": self.event_at.isoformat(),
                "availability": self.availability.to_dict(), "evidence_ids": list(self.evidence_ids),
                "description": self.description, "synthetic": self.synthetic}


def cursor(records: tuple[ContinuumRecord, ...], target_as_of: datetime, mode: TemporalMode,
           *, fixture_id: str | None = None, observed_facts_only: bool = False) -> tuple[ContinuumRecord, ...]:
    """Return what was available at a knowledge cursor, retaining epistemic labels.

    A known future schedule is permissible: event_at need not precede the cursor.
    Predictions/hypotheses remain separate and cannot pass the observed-fact gate.
    """
    target = aware_utc(target_as_of)
    if len({record.record_id for record in records}) != len(records):
        raise ValueError("Continuum record IDs must be unique")
    selected = []
    for record in records:
        if fixture_id is not None and record.fixture_id != fixture_id:
            continue
        if not record.availability.eligible(target, mode):
            continue
        if observed_facts_only:
            try:
                record.require_observed_fact()
            except ValueError:
                continue
        selected.append(record)
    return tuple(sorted(selected, key=lambda item: (item.availability.available_at, item.record_id)))
