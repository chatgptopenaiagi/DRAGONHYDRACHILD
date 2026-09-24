"""CHILD-only retained-byte historical experiment; no acquisition or database writes."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import subprocess
from time import perf_counter
from uuid import uuid4

from dragonhydra.config import PROJECT_ROOT
from dragonhydra.science.demo import CaptureMetadata, build_historical_inputs, parse_historical_rows
from dragonhydra.science.temporal import TemporalMode
from .evaluation import walk_forward
from .features import MatchEvidence, build_features, analytical_export
from .models import predict_models
from .simulation import score_matrix, scenario_mixture, monte_carlo
from .tribunal import compare


RAW_HASH = "03e13eafbf78dfe00d7e89dd3bf6643986eb6e8fd86c7664aeb8c5bc0bed88d0"
CAPTURE_PATH = "runtime/checkpoints/scientific-spine-a-20260924T192859Z-c463e0ca/historical-demo/capture-metadata.json"


def _within_child(path: Path) -> Path:
    path = path.resolve()
    if PROJECT_ROOT.name.upper() != "DRAGONHYDRACHILD" or not path.is_relative_to(PROJECT_ROOT.resolve()):
        raise ValueError("This experiment is bounded to the independent CHILD checkout")
    return path


def _load(raw_file=None, capture_file=None, computed_at=None, *, replay_capture=False):
    computed = computed_at or datetime.now(timezone.utc)
    metadata_path = _within_child(Path(capture_file) if capture_file else PROJECT_ROOT / CAPTURE_PATH)
    original_capture = CaptureMetadata.from_dict(json.loads(metadata_path.read_text(encoding="utf-8")))
    capture = original_capture if replay_capture else replace(original_capture, ingested_at=computed,
                      capture_basis=original_capture.capture_basis + "; CHILD_DERIVED_INPUT_CONSTRUCTED_NOW_FROM_COPIED_HASH_VERIFIED_BYTES")
    if raw_file:
        candidates = [_within_child(Path(raw_file))]
    else:
        candidates = sorted((PROJECT_ROOT / "runtime/handoff/browser_downloads").glob("*.json"))
    raw, retained_path = None, None
    for candidate in candidates:
        candidate = _within_child(candidate)
        if candidate.is_symlink() or not 0 < candidate.stat().st_size <= 2000000: continue
        body = candidate.read_bytes()
        if sha256(body).hexdigest() == RAW_HASH:
            raw, retained_path = body, candidate
            break
    if raw is None or capture.content_hash != RAW_HASH:
        raise ValueError("Required hash-verified retained OpenFootball bytes are unavailable")
    inputs = build_historical_inputs(raw, capture, computed_at=computed)
    parsed = parse_historical_rows(raw)
    if not len(parsed) == len(inputs.fixtures) == len(inputs.results):
        raise ValueError("Historical source and inherited identity builder length mismatch")
    records = []
    for row, fixture, result in zip(parsed, inputs.fixtures, inputs.results):
        if (fixture.fixture_id != result.fixture_id or fixture.kickoff_at.date().isoformat() != row["date"]
                or result.outcome.value != ("HOME" if row["home_score"] > row["away_score"] else "AWAY" if row["home_score"] < row["away_score"] else "DRAW")):
            raise ValueError("Goal-row alignment with inherited canonical identities failed")
        records.append(MatchEvidence(result.record_id, fixture.fixture_id, fixture.competition_id,
                       fixture.home_team_id, fixture.away_team_id, fixture.kickoff_at, result.event_completed_at,
                       row["home_score"], row["away_score"], result.availability, fixture.schedule_availability))
    return tuple(records), capture, original_capture, inputs, retained_path


def load_historical_records(*, raw_file=None, capture_file=None, computed_at=None) -> tuple[MatchEvidence, ...]:
    return _load(raw_file, capture_file, computed_at)[0]


def replay_checkpoint(checkpoint: Path) -> dict:
    """Recompute frozen inputs, preserving their recorded clocks, never recapture them."""
    checkpoint = _within_child(checkpoint)
    if not checkpoint.is_relative_to((PROJECT_ROOT/"runtime/checkpoints").resolve()):
        raise ValueError("Replay requires a CHILD forensic checkpoint")
    old = json.loads((checkpoint/"summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((checkpoint/"manifest.json").read_text(encoding="utf-8"))
    for name in ("capture-metadata.json", "summary.json"):
        if sha256((checkpoint/name).read_bytes()).hexdigest() != manifest["files"][name]["sha256"]:
            raise ValueError("Saved checkpoint hash mismatch")
    computed = datetime.now(timezone.utc)
    records, _, _, inputs, _ = _load(capture_file=checkpoint/"capture-metadata.json",
                                    computed_at=computed, replay_capture=True)
    started = perf_counter()
    report = walk_forward(records, horizon=inputs.protocol.decision_horizon, computed_at=computed)
    compact = {name: {key: value for key, value in metrics.items() if key != "calibration"}
               for name, metrics in report["metrics"].items()}
    return {"schema_version": "child-frozen-replay/1", "computed_at": computed.isoformat(),
            "source_checkpoint": str(checkpoint.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "replay_hash_equal": report["replay_hash"] == old["replay_hash"],
            "all_metrics_equal": compact == old["metrics"], "replay_hash": report["replay_hash"],
            "cpu_runtime_seconds": perf_counter()-started, "evaluation_matches": report["evaluation_matches"],
            "timestamp_semantics": "ORIGINAL_RECORDED_CAPTURE_REPLAYED; COMPUTATION_CLOCK_IS_NEW"}


def predict_current(target, records, *, at=None, mode=TemporalMode.STRICT_PIT):
    """Current inference requires genuine caller-supplied availability contracts.

    Does not relabel reconstructed inputs. KNN has no historically genuine
    training feature frames in this route, so its uniform fallback is explicit.
    """
    cursor = at or datetime.now(timezone.utc)
    snapshot = build_features(target, records, cursor, mode)
    forecasts = predict_models(snapshot, target)
    return {"feature_snapshot": snapshot.to_dict(), "forecasts": [f.to_dict() for f in forecasts],
            "tribunal": compare(forecasts, cursor), "computed_at": datetime.now(timezone.utc).isoformat(),
            "ml_training_frame_status": "NO_GENUINE_HISTORICAL_FEATURE_FRAMES; KNN_RETURNS_UNIFORM_PRIOR",
            "limitations": ["UNCALIBRATED_CURRENT_EXPERIMENT", "NO_REAL_MARKET_INPUT", "NO_PROFITABILITY_CLAIM"]}


def _write_new(path, payload):
    content = (json.dumps(payload, sort_keys=True, indent=2, allow_nan=False)+"\n").encode("utf-8")
    with path.open("xb") as stream: stream.write(content)
    return {"sha256": sha256(content).hexdigest(), "byte_count": len(content)}


def run_research(output=None) -> dict:
    computed = datetime.now(timezone.utc)
    checkpoint = _within_child(Path(output) if output else PROJECT_ROOT / "runtime/checkpoints" /
                              ("child-v3-v6-science-"+computed.strftime("%Y%m%dT%H%M%SZ")+"-"+uuid4().hex[:8]))
    if not checkpoint.is_relative_to((PROJECT_ROOT / "runtime/checkpoints").resolve()):
        raise ValueError("Research output must be a new local checkpoint")
    checkpoint.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    records, capture, donor_capture, inputs, raw_path = _load(computed_at=computed)
    report = walk_forward(records, mode=TemporalMode.RECONSTRUCTED_PIT, min_training=50,
                          horizon=inputs.protocol.decision_horizon, computed_at=computed)
    elapsed = perf_counter()-started
    example_row = records[-1]
    example = build_features(example_row.target(), records, example_row.kickoff_at, TemporalMode.RECONSTRUCTED_PIT)
    forecasts = report["predictions"][-1]["forecasts"]
    poisson = next(f["parameters"] for f in forecasts if f["model_id"] == "POISSON")
    dc = next(f["parameters"] for f in forecasts if f["model_id"] == "DIXON_COLES")
    rates = poisson["home_rate"], poisson["away_rate"]
    simulation = {"fixture_id": example.fixture_id, "temporal_mode": "RECONSTRUCTED_PIT",
                  "feature_snapshot_id": example.snapshot_id, "independent": score_matrix(*rates).to_dict(),
                  "dixon_coles": score_matrix(*rates, rho=dc["rho"]).to_dict(),
                  "scenario_mixture": scenario_mixture(((.5, score_matrix(rates[0]*.85, rates[1]*1.15)),
                                                        (.5, score_matrix(rates[0]*1.15, rates[1]*.85)))),
                  "monte_carlo": monte_carlo(*rates, samples=20000, seed=20260924, log_rate_sd=.1),
                  "scenario_note": "CONTROLLED_RATE_HYPOTHESES; NOT_OBSERVED_LINEUPS_OR_INJURIES"}
    summary = {"schema_version": "child-science-summary/1", "computed_at": computed.isoformat(),
               "status": "PARTIAL", "source_hash": RAW_HASH, "source_url": capture.source_url,
               "original_observed_at": capture.observed_at.isoformat(), "original_retrieved_at": capture.retrieved_at.isoformat(),
               "child_derived_ingested_at": capture.ingested_at.isoformat(), "temporal_mode": "RECONSTRUCTED_PIT",
               "decision_horizon": "DAY_START_UTC_PROXY", "historical_strict_pit_records": 0,
               "input_matches": len(records), "evaluation_matches": report["evaluation_matches"],
               "feature_outputs": 22, "historical_metrics_and_indicators": 16, "missing_external_fields_and_indicators": 6,
               "model_count": 7, "model_ids": [f["model_id"] for f in forecasts if not f["model_id"].startswith("KNN_ABLATION")],
               "metrics": {name: {key: value for key, value in metrics.items() if key != "calibration"} for name, metrics in report["metrics"].items()},
               "paired_log_loss": report["paired_log_loss"], "replay_hash": report["replay_hash"],
               "cpu_runtime_seconds": elapsed, "environment": {"python": platform.python_version(), "platform": platform.platform()},
               "packages_added": [], "raw_source_changes": "NONE_RETAINED_BYTES_ONLY",
               "inference_status": report["inference_status"], "limitations": report["limitations"],
               "checkpoint": str(checkpoint.relative_to(PROJECT_ROOT)).replace("\\", "/")}
    hashes = {}
    payloads = {"report": report, "summary": summary, "feature-example": analytical_export(example),
                "simulation-example": simulation, "capture-metadata": capture.to_dict(),
                "donor-capture-metadata": donor_capture.to_dict(), "registry": inputs.registry.to_dict()}
    for name, payload in payloads.items(): hashes[name+".json"] = _write_new(checkpoint/(name+".json"), payload)
    code_files = tuple(Path(__file__).parent/name for name in ("features.py", "models.py", "simulation.py", "tribunal.py", "evaluation.py", "research_run.py"))
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    _write_new(checkpoint/"manifest.json", {"files": hashes, "source_hash": RAW_HASH,
               "source_local_path": str(raw_path.relative_to(PROJECT_ROOT)),
               "git_head_at_run": git.stdout.strip() if git.returncode == 0 else None,
               "code_files": {str(p.relative_to(PROJECT_ROOT)): sha256(p.read_bytes()).hexdigest() for p in code_files},
               "created_at": computed.isoformat(), "immutable": True,
               "secrets_included": False, "tests_reference": "tests/test_child_science.py"})
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(run_research(args.output), indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
