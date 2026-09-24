"""Local append-only prospective prediction ledger with a verifiable hash chain.

Issuance uses the real process clock. Historical replay predictions cannot be
imported through this API. Hash chaining detects mutation against a retained
head hash; it is neither trusted timestamping nor remote cryptographic attestation.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from dragonhydra.science.evaluation import Outcome, Probabilities, score_prediction
from dragonhydra.science.temporal import Availability, TemporalMode, aware_utc


_CHILD_ROOT = Path(__file__).resolve().parents[3]
_GENESIS = "0" * 64


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(value: dict) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _digest(value: str, name: str):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{name} must be a SHA-256 digest")


@dataclass(frozen=True, slots=True)
class LedgerProposal:
    fixture_id: str
    kickoff_at: datetime
    probabilities: Probabilities
    model_id: str
    model_version: str
    feature_snapshot_id: str
    evidence_snapshot_id: str
    source_ids: tuple[str, ...]
    code_hash: str
    input_availability: tuple[Availability, ...]
    synthetic: bool = False
    schedule_time_semantics: str = "VERIFIED_KICKOFF"
    analysis_artifact_hash: str | None = None

    def __post_init__(self):
        for name in ("fixture_id", "model_id", "model_version"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        aware_utc(self.kickoff_at)
        if not isinstance(self.probabilities, Probabilities):
            raise ValueError("Normalized prediction probabilities are required")
        for name in ("feature_snapshot_id", "evidence_snapshot_id", "code_hash"):
            _digest(getattr(self, name), name)
        if not isinstance(self.source_ids, tuple) or not self.source_ids or any(not source.strip() for source in self.source_ids):
            raise ValueError("Explicit immutable source references are required")
        if not isinstance(self.input_availability, tuple) or not self.input_availability:
            raise ValueError("Prospective issuance requires input availability proofs")
        if any(not isinstance(item, Availability) or item.availability_mode is not TemporalMode.STRICT_PIT
               or item.source not in self.source_ids for item in self.input_availability):
            raise ValueError("Every input must be STRICT_PIT with a declared source")
        if type(self.synthetic) is not bool:
            raise ValueError("Synthetic status must be explicit")
        if self.schedule_time_semantics not in ("VERIFIED_KICKOFF", "DATE_EARLIEST_GLOBAL_BOUND"):
            raise ValueError("Schedule timestamp semantics must be explicitly supported")
        if self.analysis_artifact_hash is not None:
            _digest(self.analysis_artifact_hash, "analysis_artifact_hash")
        elif not self.synthetic:
            raise ValueError("A real prediction requires an immutable full analysis artifact hash")


class PredictionLedger:
    """Single-writer append with exclusive lock, fsync, exclusive file creation.

    A crash can leave an incomplete event/lock. Validation then fails closed;
    recovery requires preserving and reviewing that evidence, not silent repair.
    """

    def __init__(self, directory: Path):
        requested = Path(directory).resolve()
        if not requested.is_relative_to((_CHILD_ROOT / "runtime").resolve()):
            raise ValueError("Prediction ledger must remain in ignored CHILD runtime")
        requested.mkdir(parents=True, exist_ok=True)
        self.directory = requested

    def verify(self, *, expected_head: str | None = None) -> tuple[dict, ...]:
        paths = sorted(self.directory.glob("*.json"))
        events = []
        previous = _GENESIS
        last_time = None
        predictions, outcome_ids = {}, set()
        for index, path in enumerate(paths, 1):
            if path.name != f"{index:08d}.json":
                raise ValueError("Ledger sequence is missing, duplicated or contains foreign files")
            if path.is_symlink():
                raise ValueError("Ledger events must be local immutable files")
            event = json.loads(path.read_text(encoding="utf-8"))
            claimed = event.get("hash")
            body = {key: value for key, value in event.items() if key != "hash"}
            if event.get("sequence") != index or event.get("previous_hash") != previous or _hash(body) != claimed:
                raise ValueError("Ledger hash chain does not verify")
            recorded = aware_utc(datetime.fromisoformat(event["recorded_at"]))
            if last_time is not None and recorded < last_time:
                raise ValueError("Ledger clock moved backwards")
            if event["kind"] == "PREDICTION":
                if event["prediction_id"] in predictions:
                    raise ValueError("Duplicate prediction identity")
                if event["prediction_issued_at"] != event["recorded_at"]:
                    raise ValueError("Prospective issue time must be the actual append clock")
                if recorded >= datetime.fromisoformat(event["kickoff_at"]):
                    raise ValueError("Prospective prediction was not issued before kickoff")
                if event["temporal_mode"] != TemporalMode.STRICT_PIT.value:
                    raise ValueError("A replay cannot appear in the prospective ledger")
                LedgerProposal(event["fixture_id"], datetime.fromisoformat(event["kickoff_at"]),
                               Probabilities(*event["probabilities"]), event["model_id"], event["model_version"],
                               event["feature_snapshot_id"], event["evidence_snapshot_id"], tuple(event["source_ids"]),
                               event["code_hash"], tuple(Availability.from_dict(item) for item in event["input_availability"]),
                               event["synthetic"], event["schedule_time_semantics"], event["analysis_artifact_hash"])
                expected_horizon = ("ACTUAL_PRE_KICKOFF_TIMESTAMP" if event["schedule_time_semantics"] == "VERIFIED_KICKOFF"
                                    else "ACTUAL_PRE_SCHEDULE_LOWER_BOUND_TIMESTAMP")
                if event["decision_horizon"] != expected_horizon:
                    raise ValueError("Decision horizon misrepresents schedule timestamp semantics")
                for item in event["input_availability"]:
                    availability = Availability.from_dict(item)
                    if not availability.eligible(recorded, TemporalMode.STRICT_PIT) or availability.ingested_at > recorded:
                        raise ValueError("Prediction contains unavailable evidence")
                predictions[event["prediction_id"]] = event
            elif event["kind"] == "OUTCOME":
                if event["prediction_id"] not in predictions or event["prediction_id"] in outcome_ids:
                    raise ValueError("Outcome must reference one preceding unscored prediction")
                prediction = predictions[event["prediction_id"]]
                outcome = Outcome(event["outcome"])
                availability = Availability.from_dict(event["availability"])
                completed = aware_utc(datetime.fromisoformat(event["event_completed_at"]))
                kickoff = aware_utc(datetime.fromisoformat(prediction["kickoff_at"]))
                if (not kickoff < completed <= availability.observed_at <= recorded
                        or not availability.eligible(recorded, TemporalMode.STRICT_PIT)
                        or availability.ingested_at > recorded or event["synthetic"] != prediction["synthetic"]):
                    raise ValueError("Outcome chronology or evidence class does not verify")
                _digest(event["evidence_hash"], "evidence_hash")
                scored = score_prediction(Probabilities(*prediction["probabilities"]), outcome)
                expected_scores = {"LOG_LOSS": scored.log_loss, "log_loss_infinite": scored.log_loss_infinite,
                                   "RPS": scored.rps, "MULTICLASS_BRIER": scored.brier}
                if event["scores"] != expected_scores:
                    raise ValueError("Stored outcome scores do not recompute")
                outcome_ids.add(event["prediction_id"])
            else:
                raise ValueError("Unknown ledger event")
            events.append(event)
            previous, last_time = claimed, recorded
        if expected_head is not None and previous != expected_head:
            raise ValueError("Ledger differs from the externally retained head hash")
        return tuple(events)

    def _append(self, build):
        lock = self.directory / ".append.lock"
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.close(descriptor)
            events = self.verify()
            now = _utc_now()
            if events and now < datetime.fromisoformat(events[-1]["recorded_at"]):
                raise ValueError("Actual clock precedes ledger head")
            body = {"schema_version": "1", "sequence": len(events) + 1,
                    "previous_hash": events[-1]["hash"] if events else _GENESIS,
                    "recorded_at": now.isoformat(), **build(events, now)}
            event = {**body, "hash": _hash(body)}
            target = self.directory / f"{len(events) + 1:08d}.json"
            with target.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(event, stream, sort_keys=True, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            return event
        finally:
            lock.unlink()

    def append_prediction(self, proposal: LedgerProposal) -> dict:
        if not isinstance(proposal, LedgerProposal):
            raise ValueError("Prospective issuance requires a typed proposal, not a historical prediction")

        def build(events, now):
            if now >= proposal.kickoff_at:
                raise ValueError("Past kickoff: prospective issuance cannot be backfilled")
            if any(not item.eligible(now, TemporalMode.STRICT_PIT) or item.ingested_at > now
                   for item in proposal.input_availability):
                raise ValueError("Prediction inputs must genuinely be available at actual issuance")
            return {"kind": "PREDICTION", "prediction_id": str(uuid4()),
                    "fixture_id": proposal.fixture_id, "kickoff_at": proposal.kickoff_at.isoformat(),
                    "prediction_issued_at": now.isoformat(),
                    "decision_horizon": ("ACTUAL_PRE_KICKOFF_TIMESTAMP" if proposal.schedule_time_semantics == "VERIFIED_KICKOFF"
                                         else "ACTUAL_PRE_SCHEDULE_LOWER_BOUND_TIMESTAMP"),
                    "schedule_time_semantics": proposal.schedule_time_semantics,
                    "analysis_artifact_hash": proposal.analysis_artifact_hash,
                    "seconds_before_kickoff": (proposal.kickoff_at - now).total_seconds(),
                    "probabilities": list(proposal.probabilities.values), "model_id": proposal.model_id,
                    "model_version": proposal.model_version, "feature_snapshot_id": proposal.feature_snapshot_id,
                    "evidence_snapshot_id": proposal.evidence_snapshot_id, "source_ids": list(proposal.source_ids),
                    "code_hash": proposal.code_hash, "temporal_mode": TemporalMode.STRICT_PIT.value,
                    "input_availability": [item.to_dict() for item in proposal.input_availability],
                    "synthetic": proposal.synthetic}
        return self._append(build)

    def append_outcome(self, prediction_id: str, outcome: Outcome, *, event_completed_at: datetime,
                       availability: Availability, evidence_hash: str, synthetic: bool) -> dict:
        _digest(evidence_hash, "evidence_hash")
        completed = aware_utc(event_completed_at)
        if not isinstance(outcome, Outcome) or not isinstance(availability, Availability):
            raise ValueError("Outcome and availability must be typed")
        if type(synthetic) is not bool:
            raise ValueError("Outcome synthetic label must be explicit")

        def build(events, now):
            prediction = next((event for event in events if event["kind"] == "PREDICTION"
                               and event["prediction_id"] == prediction_id), None)
            if prediction is None or any(event["kind"] == "OUTCOME" and event["prediction_id"] == prediction_id for event in events):
                raise ValueError("Outcome needs an existing unscored prediction")
            kickoff = datetime.fromisoformat(prediction["kickoff_at"])
            if not kickoff < completed <= availability.observed_at <= now:
                raise ValueError("Outcome completion/observation must follow kickoff and precede actual scoring")
            if not availability.eligible(now, TemporalMode.STRICT_PIT) or availability.ingested_at > now:
                raise ValueError("Outcome needs genuinely available strict evidence")
            if synthetic != prediction["synthetic"]:
                raise ValueError("Synthetic and real prediction/outcome classes cannot be mixed")
            score = score_prediction(Probabilities(*prediction["probabilities"]), outcome)
            return {"kind": "OUTCOME", "prediction_id": prediction_id, "outcome": outcome.value,
                    "event_completed_at": completed.isoformat(), "availability": availability.to_dict(),
                    "evidence_hash": evidence_hash, "synthetic": synthetic,
                    "scores": {"LOG_LOSS": score.log_loss, "log_loss_infinite": score.log_loss_infinite,
                               "RPS": score.rps, "MULTICLASS_BRIER": score.brier}}
        return self._append(build)
