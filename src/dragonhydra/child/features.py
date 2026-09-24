"""Small reproducible feature factory; observations and reconstructions stay distinct."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

from dragonhydra.science.evaluation import FixtureTarget, Outcome, ResultObservation
from dragonhydra.science.temporal import Availability, TemporalMode, TimedRevision, as_of, aware_utc


def digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class MatchEvidence:
    record_id: str
    fixture_id: str
    competition_id: str
    home_team_id: str
    away_team_id: str
    kickoff_at: datetime
    completed_at: datetime
    home_goals: int
    away_goals: int
    availability: Availability
    schedule_availability: Availability
    revision: int = 1
    supersedes_id: str | None = None

    def __post_init__(self):
        self.target()
        aware_utc(self.completed_at)
        if self.completed_at < self.kickoff_at:
            raise ValueError("completion cannot precede kickoff")
        if any(isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= 100
               for n in (self.home_goals, self.away_goals)):
            raise ValueError("goals must be bounded nonnegative integers")
        self.result()

    @property
    def outcome(self) -> Outcome:
        return Outcome.HOME if self.home_goals > self.away_goals else Outcome.AWAY if self.home_goals < self.away_goals else Outcome.DRAW

    def target(self) -> FixtureTarget:
        return FixtureTarget(self.fixture_id, self.competition_id, self.home_team_id,
                             self.away_team_id, self.kickoff_at, self.schedule_availability,
                             self.record_id + ":schedule")

    def result(self) -> ResultObservation:
        return ResultObservation(self.record_id, self.fixture_id, self.competition_id,
                                 self.home_team_id, self.away_team_id, self.completed_at,
                                 self.outcome, self.availability, self.revision, self.supersedes_id)

    def to_dict(self) -> dict:
        return {"record_id": self.record_id, "fixture_id": self.fixture_id,
                "competition_id": self.competition_id, "home_team_id": self.home_team_id,
                "away_team_id": self.away_team_id, "kickoff_at": self.kickoff_at.isoformat(),
                "completed_at": self.completed_at.isoformat(), "home_goals": self.home_goals,
                "away_goals": self.away_goals, "availability": self.availability.to_dict(),
                "schedule_availability": self.schedule_availability.to_dict(),
                "revision": self.revision, "supersedes_id": self.supersedes_id}


def eligible_history(records, target: FixtureTarget, at: datetime, mode: TemporalMode) -> tuple[MatchEvidence, ...]:
    """Resolve revisions before selecting completed, available, other-fixture evidence."""
    at = aware_utc(at)
    records = tuple(records)
    index = {row.record_id: row for row in records}
    selected = as_of((row.result().timed_revision() for row in records), at, mode)
    rows = [index[r.record_id] for r in selected]
    return tuple(sorted((r for r in rows if r.competition_id == target.competition_id
                         and r.fixture_id != target.fixture_id and r.completed_at < at),
                        key=lambda r: (r.completed_at, r.fixture_id)))


@dataclass(frozen=True, slots=True)
class FeatureValue:
    name: str
    value: float | None
    unit: str
    input_evidence_ids: tuple[str, ...]
    available_at: datetime | None
    confidence: float
    calculation_method: str
    missing_data_behavior: str = "NULL_WITH_MISSINGNESS_INDICATOR"
    version: str = "1.0.0"

    def __post_init__(self):
        if not self.name or not self.calculation_method or not self.version or not self.unit:
            raise ValueError("feature identity, unit and method required")
        if self.value is not None and (isinstance(self.value, bool) or not isinstance(self.value, (int, float)) or not isfinite(self.value)):
            raise ValueError("feature value must be finite numeric or explicitly missing")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0,1]")
        if self.available_at is not None: aware_utc(self.available_at)

    def to_dict(self) -> dict:
        return {"name": self.name, "value": self.value, "unit": self.unit,
                "input_evidence_ids": list(self.input_evidence_ids),
                "available_at": self.available_at.isoformat() if self.available_at else None,
                "confidence": self.confidence, "calculation_method": self.calculation_method,
                "missing_data_behavior": self.missing_data_behavior, "version": self.version}


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    fixture_id: str
    target_as_of_at: datetime
    temporal_mode: TemporalMode
    features: tuple[FeatureValue, ...]
    evidence: tuple[MatchEvidence, ...]
    schedule_record_id: str
    schedule_availability: Availability
    code_hash: str
    snapshot_id: str

    def __post_init__(self):
        aware_utc(self.target_as_of_at)
        if not self.schedule_availability.eligible(self.target_as_of_at, self.temporal_mode):
            raise ValueError("unavailable schedule in feature snapshot")
        if any(not r.availability.eligible(self.target_as_of_at, self.temporal_mode)
               or r.completed_at >= self.target_as_of_at or r.fixture_id == self.fixture_id for r in self.evidence):
            raise ValueError("unavailable result in feature snapshot")
        ids = {r.record_id for r in self.evidence}
        if len(ids) != len(self.evidence) or len({f.name for f in self.features}) != len(self.features):
            raise ValueError("duplicate feature or evidence identity")
        if any(not set(f.input_evidence_ids).issubset(ids)
               or (f.available_at is not None and f.available_at > self.target_as_of_at) for f in self.features):
            raise ValueError("feature lineage or availability violates snapshot")

    @property
    def values(self) -> dict[str, float | None]:
        return {f.name: f.value for f in self.features}

    def to_dict(self) -> dict:
        return {"schema_version": "1.0", "epistemic_state": "DERIVED_FEATURE",
                "fixture_id": self.fixture_id, "target_as_of_at": self.target_as_of_at.isoformat(),
                "temporal_mode": self.temporal_mode.value, "snapshot_id": self.snapshot_id,
                "code_hash": self.code_hash, "features": [f.to_dict() for f in self.features],
                "evidence": [r.to_dict() for r in self.evidence],
                "schedule_record_id": self.schedule_record_id,
                "schedule_availability": self.schedule_availability.to_dict()}


def build_features(target: FixtureTarget, records, target_as_of: datetime,
                   mode: TemporalMode = TemporalMode.STRICT_PIT) -> FeatureSnapshot:
    at, mode = aware_utc(target_as_of), TemporalMode(mode)
    if at > target.kickoff_at:
        raise ValueError("pre-match feature cursor cannot follow kickoff")
    if not target.schedule_availability.eligible(at, mode):
        raise ValueError("fixture schedule unavailable at decision horizon")
    history = eligible_history(records, target, at, mode)
    features = []

    def add(name, value, rows, unit, method):
        refs = tuple(sorted(row.record_id for row in rows))
        latest = max((row.availability.available_at for row in rows), default=None)
        confidence = min((row.availability.confidence for row in rows), default=0.0)
        features.append(FeatureValue(name, value, unit, refs, latest, confidence, method))

    def team_features(team, prefix, home_venue):
        matches = [r for r in history if team in (r.home_team_id, r.away_team_id)]
        recent = matches[-5:]
        venue = [r for r in matches if (r.home_team_id == team) == home_venue]
        def goals(r):
            return (r.home_goals, r.away_goals) if r.home_team_id == team else (r.away_goals, r.home_goals)
        points = [3.0 if a > b else 1.0 if a == b else 0.0 for a, b in map(goals, recent)]
        add(prefix + "_form", sum(points) / len(points) if points else None, recent, "points/match", "mean last five completed available results")
        for suffix, selected, component in (("goals_for", matches, 0), ("goals_against", matches, 1), ("venue_goals_for", venue, 0), ("venue_goals_against", venue, 1)):
            add(prefix + "_" + suffix, sum(goals(r)[component] for r in selected) / len(selected) if selected else None,
                selected, "goals/match", "arithmetic mean over available history")
        last = matches[-1:]
        add(prefix + "_rest_days", (target.kickoff_at - last[0].completed_at).total_seconds() / 86400 if last else None,
            last, "days", "scheduled kickoff minus latest available completion")
        recent14 = [r for r in matches if r.completed_at >= at - timedelta(days=14)]
        add(prefix + "_congestion_14d", float(len(recent14)), recent14, "matches", "completed matches within prior 14 days")
        add(prefix + "_history_missing", float(not matches), matches, "indicator", "one when no available team history")
    team_features(target.home_team_id, "home", True)
    team_features(target.away_team_id, "away", False)
    for name in ("lineup_continuity", "injury_burden", "market_movement"):
        add(name, None, [], "UNKNOWN", "no approved input supplied; never impute external facts")
        add(name + "_missing", 1.0, [], "indicator", "external evidence absent")
    code_hash = sha256(Path(__file__).read_bytes()).hexdigest()
    body = {"fixture": target.fixture_id, "cursor": at.isoformat(), "mode": mode.value,
            "features": [f.to_dict() for f in features], "evidence": [r.to_dict() for r in history],
            "schedule_id": target.schedule_record_id, "schedule": target.schedule_availability.to_dict(), "code_hash": code_hash}
    return FeatureSnapshot(target.fixture_id, at, mode, tuple(features), history,
                           target.schedule_record_id, target.schedule_availability, code_hash, digest(body))


def analytical_export(snapshot: FeatureSnapshot) -> dict:
    """Versioned JSON analytical export; does not introduce a second state owner."""
    return {"schema": "dragonhydra.child.feature-export/1", "owner": "DERIVED_FEATURE",
            "source_owner": "SQL_SERVER_STRUCTURED_INTELLIGENCE", "snapshot": snapshot.to_dict()}
