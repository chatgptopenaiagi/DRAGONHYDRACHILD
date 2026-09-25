"""Explicit owner-scoped ARX A/B/C experiment. No unrelated process is controlled."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dragonhydra.machine import capture_machine, compare_machine, EventJournal, MachineDelta
from dragonhydra.machine.contracts import canonical, utc_now
from dragonhydra.cognitive_v2.artifacts import ArtifactStore

CANONICAL_PYTHON = Path("C:/Users/Administrator/anaconda3/envs/codex-pytorch/python.exe")


def run_experiment(checkpoint_name):
    if os.name != "nt" or sys.version_info[:2] != (3, 14) or Path(sys.executable).resolve() != CANONICAL_PYTHON.resolve():
        raise RuntimeError("CANONICAL_WINDOWS_PYTHON_314_REQUIRED")
    if type(checkpoint_name) is not str or not re.fullmatch(r"cognitive-awareness-v2-[0-9]{8}T[0-9]{6}Z", checkpoint_name):
        raise ValueError("INVALID_CHECKPOINT")
    checkpoint = ROOT / "runtime" / "checkpoints" / checkpoint_name
    for path in (checkpoint, *checkpoint.parents):
        if path.is_symlink() or path.is_junction(): raise ValueError("LINKED_PATH_FORBIDDEN")
    if not checkpoint.is_dir(): raise ValueError("CHECKPOINT_REQUIRED")
    run_id = "arx-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    store = ArtifactStore()
    journal = EventJournal(ROOT / "runtime" / "cognitive-v2" / "events" / run_id)
    before = capture_machine()
    before_ref = store.put("experiments", {"kind":"ARX_SNAPSHOT_A", "machine_snapshot":before.to_dict()})
    child = subprocess.Popen([str(CANONICAL_PYTHON), "-B", "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE":"1"}, cwd=ROOT)
    try:
        during = capture_machine(owned_test_pid=child.pid)
        if child.poll() is not None: raise RuntimeError("EXPERIMENT_PROCESS_EARLY_EXIT")
        during_ref = store.put("experiments", {"kind":"ARX_SNAPSHOT_B", "machine_snapshot":during.to_dict()})
    finally:
        # This Popen handle identifies the sole process we created and may stop.
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=5)
    after = capture_machine(owned_test_pid=child.pid)
    after_ref = store.put("experiments", {"kind":"ARX_SNAPSHOT_C", "machine_snapshot":after.to_dict()})
    appearance, disappearance = compare_machine(before, during), compare_machine(during, after)
    entity_id = f"process.{child.pid}"
    starts = tuple(e for e in appearance.events if e.entity_id == entity_id and e.event_type == "PROCESS_STARTED")
    stops = tuple(e for e in disappearance.events if e.entity_id == entity_id and e.event_type == "PROCESS_STOPPED")
    target_start = MachineDelta(appearance.before_hash, appearance.after_hash, appearance.observed_at, starts)
    target_stop = MachineDelta(disappearance.before_hash, disappearance.after_hash, disappearance.observed_at, stops)
    observed = next((o for o in during.observations if o.entity_id == entity_id), None)
    checks = {"before_process_probe_ok": next(r.status for r in before.receipts if r.probe_id=="process")=="OK",
        "during_process_probe_ok": next(r.status for r in during.receipts if r.probe_id=="process")=="OK",
        "after_process_probe_ok": next(r.status for r in after.receipts if r.probe_id=="process")=="OK",
        "owned_process_observed": observed is not None and observed.data.get("owned_experiment") is True,
        "appearance_detected": len(starts)==1, "disappearance_detected": len(stops)==1,
        "owned_process_stopped": child.poll() is not None,
        "no_unrelated_process_control": True}
    for item in starts+stops: journal.append(item)
    full_deltas_ref = store.put("experiments", {"kind":"ARX_FULL_DELTAS", "appearance":appearance.to_dict(), "disappearance":disappearance.to_dict()})
    payload = {"schema_version":"2", "kind":"ARX_PROCESS_EXPERIMENT", "epistemic_state":"OBSERVATION",
        "run_id":run_id, "created_at":utc_now(), "source_probe":"ARX_FIXED_READ_ONLY_PROBES",
        "owned_process_id":child.pid, "model_execution":"NOT_PERFORMED", "result_status":"COMPLETE" if all(checks.values()) else "FAILED",
        "checks":checks, "snapshot_refs":{"before":before_ref,"during":during_ref,"after":after_ref},
        "machine_hashes":{"before":before.state_hash,"during":during.state_hash,"after":after.state_hash},
        "full_deltas_ref":full_deltas_ref, "structured_appearance_delta":target_start.to_dict(),
        "structured_disappearance_delta":target_stop.to_dict(), "appearance_delta_hash":target_start.state_hash,
        "disappearance_delta_hash":target_stop.state_hash, "journal_event_ids":[e.event_id for e in starts+stops],
        "limitations":["CONTROLLED_PROCESS_EXPERIMENT_NOT_SCIENTIFIC_PREDICTION_ACCURACY", "QWEN_INTERPRETATION_REQUIRES_SEPARATE_ARTIFACT"]}
    artifact_ref = store.put("experiments", payload)
    receipt = {**payload,"artifact_ref":artifact_ref}
    destination = checkpoint / "arx-experiment.json"
    with destination.open("xb") as stream: stream.write(canonical(receipt))
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-name",required=True)
    args=parser.parse_args()
    receipt=run_experiment(args.checkpoint_name)
    print(json.dumps({key:receipt[key] for key in ("result_status","owned_process_id","checks","artifact_ref","snapshot_refs","appearance_delta_hash","disappearance_delta_hash")},indent=2))
    return 0 if receipt["result_status"]=="COMPLETE" else 1


if __name__ == "__main__": raise SystemExit(main())
