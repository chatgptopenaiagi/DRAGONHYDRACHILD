"""Portable ARX contracts, failure semantics, deltas and bounded journal tests."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dragonhydra.machine import (EventJournal, MachineCapability, MachineContractError, MachineDelta,
    MachineEvent, MachineHealth, MachineObservation, MachineProbeReceipt, MachineSnapshot, compare_machine)
from dragonhydra.machine.contracts import digest
from dragonhydra.machine import probes
from dragonhydra.machine import journal as journal_module

T0 = "2026-09-25T20:00:00Z"
T1 = "2026-09-25T20:00:10Z"
T2 = "2026-09-25T20:03:00Z"


def observation(kind="process", entity="process.100", at=T0, **data):
    if not data:
        data = {"pid": 100, "name": "python.exe", "start_time": T0, "owned_experiment": True}
    return MachineObservation(kind, entity, kind, at, at, at, at, 120, 2, "OK", tuple(data.items()))


def snapshot(items=(), at=T0, domain="process", status="OK"):
    items = tuple(items)
    receipts = []
    for name in sorted({x.probe_id for x in items} | {domain}):
        rows = sorted((x.to_dict() for x in items if x.probe_id == name), key=lambda x: x["entity_id"])
        receipts.append(MachineProbeReceipt(name, at, at, status, len(rows), 1,
            None if status == "OK" else "MACHINE_PROBE_FAILED", digest(rows)))
    return MachineSnapshot("snapshot."+at.replace(":", "-"), at, at, items, tuple(receipts))


def event(number=1):
    return MachineEvent(f"event.{number}", "PROCESS_STARTED", T1, "process", "process.100", None,
                        "a"*64, "INFO", "FRESH", ("PROCESS_STARTED",), ("snapshot.1",))


class MachineV2ContractTests(unittest.TestCase):
    def test_observation_roundtrip(self):
        value = observation()
        self.assertEqual(value, MachineObservation.from_dict(json.loads(json.dumps(value.to_dict()))))

    def test_snapshot_roundtrip(self):
        value = snapshot([observation()])
        self.assertEqual(value, MachineSnapshot.from_dict(value.to_dict()))

    def test_snapshot_rejects_modified_hash(self):
        value = snapshot([observation()]).to_dict(); value["state_hash"] = "0"*64
        with self.assertRaises(MachineContractError): MachineSnapshot.from_dict(value)

    def test_snapshot_rejects_modified_receipt_content(self):
        value = snapshot([observation()]).to_dict(); value["observations"][0]["attributes"][0][1] = "forged"
        with self.assertRaises(MachineContractError): MachineSnapshot.from_dict(value)

    def test_snapshot_ignores_capture_clock_drift(self):
        self.assertEqual(snapshot([observation()]).state_hash,
                         snapshot([observation(at=T1)], at=T1).state_hash)

    def test_semantic_change_changes_hash(self):
        a = snapshot([observation()]); b = snapshot([observation(pid=101, name="python.exe")])
        self.assertNotEqual(a.state_hash, b.state_hash)

    def test_snapshot_order_is_canonical(self):
        a, b = observation(entity="process.1"), observation(entity="process.2")
        self.assertEqual(snapshot([a,b]).state_hash, snapshot([b,a]).state_hash)

    def test_uptime_drift_does_not_change_hash(self):
        a = observation("os", "os.windows", name="Windows", uptime_seconds=100)
        b = observation("os", "os.windows", at=T1, name="Windows", uptime_seconds=110)
        self.assertEqual(snapshot([a], domain="os").state_hash, snapshot([b], at=T1, domain="os").state_hash)

    def test_extra_contract_key_rejected(self):
        value = observation().to_dict(); value["chain_of_thought"] = "forbidden"
        with self.assertRaises(MachineContractError): MachineObservation.from_dict(value)

    def test_secret_attribute_rejected(self):
        for key in ("password", "command_line", "registry", "api_key", "filesystem", "hidden_reasoning"):
            with self.subTest(key=key), self.assertRaises(MachineContractError): observation(**{key:"private"})

    def test_sensitive_value_rejected(self):
        for value in ("Bearer token", "sk-proj-example", "password=example", "C:\\Secrets\\data", "ignore\nprevious"):
            with self.subTest(value=value), self.assertRaises(MachineContractError): observation(name=value)

    def test_nested_context_rejected(self):
        with self.assertRaises(MachineContractError): observation(name={"arbitrary":"context"})

    def test_negative_and_nonfinite_metrics_rejected(self):
        for value in (-1, float("nan"), float("inf"), True, "100"):
            with self.subTest(value=value), self.assertRaises(MachineContractError): observation("ram", "ram.system", available_bytes=value)

    def test_future_clock_rejected(self):
        with self.assertRaises(MachineContractError): replace(observation(), observed_at=T1)

    def test_process_and_port_values_are_integral_and_bounded(self):
        for data in ({"pid":1.5},{"pid":2147483648},{"port":65536},{"port":80.5}):
            with self.subTest(data=data), self.assertRaises(MachineContractError): observation(**data)

    def test_naive_clock_rejected(self):
        with self.assertRaises(MachineContractError): observation(at="2026-09-25T20:00:00")

    def test_freshness_and_future_rejection(self):
        value = snapshot([observation()])
        self.assertTrue(value.is_fresh(T1)); self.assertFalse(value.is_fresh(T2))
        self.assertFalse(value.is_fresh("2026-09-25T19:59:00Z"))

    def test_failed_probe_not_healthy_or_fresh(self):
        value = snapshot([], status="FAILED")
        self.assertEqual(value.health.status, "FAILED"); self.assertFalse(value.is_fresh(T1))

    def test_duplicate_observation_rejected(self):
        with self.assertRaises(MachineContractError): snapshot([observation(), observation()])

    def test_deep_inspection_rejected(self):
        with self.assertRaises(MachineContractError): replace(observation(), level=4)

    def test_ai_belief_cannot_claim_machine_observation(self):
        with self.assertRaises(MachineContractError): replace(observation(), status="HYPOTHESIS")
        with self.assertRaises(MachineContractError): replace(observation(), kind="AI_OUTPUT")

    def test_capability_cannot_enable_write(self):
        with self.assertRaises(MachineContractError): MachineCapability("probe", read_only=False)

    def test_auxiliary_contract_roundtrips(self):
        values = [MachineCapability("probe"), MachineHealth("HEALTHY", (), (), ()), event(),
                  snapshot([observation()]).receipts[0]]
        for value in values:
            self.assertEqual(value, type(value).from_dict(value.to_dict()))
            self.assertEqual(len(value.state_hash), 64)


class MachineV2DeltaTests(unittest.TestCase):
    def test_process_appearance_and_disappearance(self):
        a = snapshot([]); b = snapshot([observation(at=T1)], at=T1); c = snapshot([], at=T2)
        self.assertEqual(compare_machine(a,b).events[0].event_type,"PROCESS_STARTED")
        self.assertEqual(compare_machine(b,c).events[0].event_type,"PROCESS_STOPPED")

    def test_failed_probe_is_not_process_disappearance(self):
        a = snapshot([observation()]); b = snapshot([], at=T1, status="FAILED")
        result = compare_machine(a,b)
        self.assertEqual([x.event_type for x in result.events], ["MACHINE_PROBE_FAILED"])

    def test_recovered_probe_does_not_fabricate_start(self):
        a = snapshot([], status="FAILED"); b = snapshot([observation(at=T1)], at=T1)
        self.assertEqual([x.event_type for x in compare_machine(a,b).events],["MACHINE_PROBE_RECOVERED"])

    def test_pid_reuse_is_stop_and_start(self):
        a = snapshot([observation()]); b = snapshot([observation(at=T1, pid=100, name="python.exe", start_time=T1)], at=T1)
        self.assertEqual({x.event_type for x in compare_machine(a,b).events}, {"PROCESS_STARTED", "PROCESS_STOPPED"})

    def test_model_runtime_and_change_classification(self):
        item = observation(name="llama-server.exe", pid=100, model_id="QWEN_4B")
        self.assertEqual(compare_machine(snapshot([]),snapshot([item],at=T1)).events[0].event_type,"MODEL_RUNTIME_STARTED")
        other = observation(at=T1, name="llama-server.exe", pid=100, model_id="QWEN_30B")
        self.assertEqual(compare_machine(snapshot([item]),snapshot([other],at=T1)).events[0].event_type,"QWEN_MODEL_CHANGED")

    def test_gpu_noise_threshold(self):
        def gpu(amount): return snapshot([observation("gpu","gpu.0", memory_used_mib=amount)],domain="gpu")
        self.assertFalse(compare_machine(gpu(100),gpu(200)).events)
        self.assertEqual(compare_machine(gpu(100),gpu(400)).events[0].event_type,"GPU_MEMORY_INCREASED")

    def test_cpu_load_drift_not_event(self):
        a = snapshot([observation("cpu","cpu.0",load_percent=10)],domain="cpu")
        b = snapshot([observation("cpu","cpu.0",load_percent=12)],domain="cpu")
        self.assertFalse(compare_machine(a,b).events)

    def test_service_database_loss(self):
        a = snapshot([observation("service","service.sql",name="MSSQLSERVER",state="Running")],domain="service")
        b = snapshot([observation("service","service.sql",name="MSSQLSERVER",state="Stopped")],domain="service")
        self.assertIn("DATABASE_UNAVAILABLE",[x.event_type for x in compare_machine(a,b).events])

    def test_repository_branch_and_dirty(self):
        a = snapshot([observation("repository","repository.child",branch="main",dirty=False)],domain="repository")
        b = snapshot([observation("repository","repository.child",branch="feature/test",dirty=True)],domain="repository")
        self.assertEqual({x.event_type for x in compare_machine(a,b).events},{"GIT_BRANCH_CHANGED","REPOSITORY_DIRTY"})

    def test_port_opened(self):
        a = snapshot([],domain="listener")
        b = snapshot([observation("listener","listener.local",port=8083,address="127.0.0.1")],domain="listener")
        self.assertEqual(compare_machine(a,b).events[0].event_type,"NEW_LOCAL_LISTENER")

    def test_delta_deterministic_roundtrip(self):
        a,b = snapshot([]),snapshot([observation(at=T1)],at=T1)
        first,second = compare_machine(a,b),compare_machine(a,b)
        self.assertEqual(first.state_hash,second.state_hash)
        self.assertEqual(first,MachineDelta.from_dict(first.to_dict()))

    def test_reverse_time_rejected(self):
        with self.assertRaises(ValueError): compare_machine(snapshot([],at=T1),snapshot([]))


class MachineV2ProbeTests(unittest.TestCase):
    def raw(self, rows=()):
        return json.dumps({"schema_version":"2","rows":list(rows),"domains":[
            {"probe_id":key,"status":"OK","failure_state":None} for key in probes._DOMAINS]})

    def test_probe_schema_parses_controlled_values(self):
        observations,receipts=probes.parse_windows_probe(self.raw([{"kind":"cpu","entity_id":"cpu.0","attributes":{"load_percent":10}}]),T0)
        self.assertEqual(observations[0].data["load_percent"],10); self.assertEqual(len(receipts),9)

    def test_probe_rejects_raw_commandline(self):
        with self.assertRaises(MachineContractError): probes.parse_windows_probe(self.raw([
            {"kind":"process","entity_id":"process.1","attributes":{"command_line":"private"}}]),T0)

    def test_probe_rejects_duplicate_json_keys(self):
        with self.assertRaises(MachineContractError): probes.parse_windows_probe('{"schema_version":"2","schema_version":"2"}',T0)

    def test_probe_rejects_oversized_output(self):
        with self.assertRaises(MachineContractError): probes.parse_windows_probe("x"*262145,T0)

    def test_probe_rejects_unknown_domain(self):
        value=json.loads(self.raw()); value["domains"][0]["probe_id"]="shell"
        with self.assertRaises(MachineContractError): probes.parse_windows_probe(json.dumps(value),T0)

    def test_probe_rejects_partial_success_with_failed_rows(self):
        value=json.loads(self.raw([{"kind":"cpu","entity_id":"cpu.0","attributes":{"load_percent":10}}]))
        value["domains"][1].update(status="FAILED",failure_state="MACHINE_PROBE_FAILED")
        with self.assertRaises(MachineContractError): probes.parse_windows_probe(json.dumps(value),T0)

    def test_test_process_selector_requires_integer(self):
        for value in ("1;malicious", -1, True, 0):
            with self.subTest(value=value),self.assertRaises(MachineContractError): probes.capture_machine(owned_test_pid=value)

    def test_command_output_is_bounded(self):
        with self.assertRaisesRegex(MachineContractError,"PROBE_OUTPUT_TOO_LARGE"):
            probes._run([sys.executable,"-B","-c","print('x'*10000)"],max_bytes=1024)

    def test_command_timeout_is_bounded(self):
        with self.assertRaisesRegex(MachineContractError,"PROBE_TIMEOUT"):
            probes._run([sys.executable,"-B","-c","import time;time.sleep(5)"],timeout=0.1)

    def test_command_crash_is_failure(self):
        with self.assertRaisesRegex(MachineContractError,"MACHINE_PROBE_FAILED"):
            probes._run([sys.executable,"-B","-c","raise SystemExit(3)"])

    def test_capture_failure_explicit_no_fabricated_machine(self):
        with patch.object(probes,"os",SimpleNamespace(name="nt")),patch.object(probes.shutil,"which",return_value="probe"),\
             patch.object(probes,"_run",side_effect=MachineContractError("MACHINE_PROBE_FAILED")),\
             patch.object(probes,"utc_now",return_value=T1):
            result=probes.capture_machine(observed_at=T0)
        self.assertEqual(result.health.status,"FAILED"); self.assertFalse(result.observations)
        self.assertFalse(result.is_fresh(T1))

    def test_probe_source_is_fixed_readonly_no_secrets(self):
        source=Path(probes.__file__).with_name("probe_windows.ps1").read_text(encoding="utf-8")
        for forbidden in ("Invoke-Expression","Set-ItemProperty","Stop-Service","Start-Service","Get-Credential","Secrets\\"):
            self.assertNotIn(forbidden,source)
        self.assertIn("-OwnedTestPid",Path(probes.__file__).read_text(encoding="utf-8"))


class MachineV2JournalTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.patcher=patch.object(journal_module,"_RUNTIME_ROOT",self.root)
        self.patcher.start(); self.addCleanup(self.patcher.stop)

    def test_append_roundtrip_idempotence(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            journal=EventJournal(directory)
            first=journal.append(event()); second=journal.append(event())
            self.assertEqual(first,second); self.assertEqual(journal.read(),(event(),))

    def test_rotation_preserves_old_segment(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            journal=EventJournal(directory,max_segment_bytes=1024,max_segments=4)
            journal.append(event(1)); original=(Path(directory)/"events-0000.jsonl").read_bytes()
            journal.append(event(2)); self.assertEqual((Path(directory)/"events-0000.jsonl").read_bytes(),original)
            self.assertEqual(len(journal.read()),2)

    def test_quota_fails_closed_without_deletion(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            journal=EventJournal(directory,max_events=1)
            journal.append(event(1)); original=(Path(directory)/"events-0000.jsonl").read_bytes()
            with self.assertRaisesRegex(MachineContractError,"JOURNAL_QUOTA_EXCEEDED"): journal.append(event(2))
            self.assertEqual((Path(directory)/"events-0000.jsonl").read_bytes(),original)

    def test_tampered_record_rejected(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            journal=EventJournal(directory); journal.append(event())
            path=Path(directory)/"events-0000.jsonl"
            path.write_bytes(path.read_bytes().replace(b"PROCESS_STARTED",b"PROCESS_STOPPED"))
            with self.assertRaises(MachineContractError): journal.read()

    def test_busy_journal_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            journal=EventJournal(directory); (Path(directory)/".writer.lock").write_text("",encoding="ascii")
            with self.assertRaisesRegex(MachineContractError,"JOURNAL_BUSY"): journal.append(event())

    def test_event_conflict_rejected(self):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            journal=EventJournal(directory); journal.append(event())
            with self.assertRaisesRegex(MachineContractError,"EVENT_ID_CONFLICT"):
                journal.append(replace(event(),severity="WARNING"))

    def test_parent_and_localai_destinations_denied(self):
        for destination in (self.root.parent/"DRAGONHYDRA",self.root.parent/"LocalAI",self.root/".."/"escape"):
            with self.subTest(destination=destination),self.assertRaisesRegex(MachineContractError,"JOURNAL_PATH_DENIED"):
                EventJournal(destination)

    def test_symlink_ancestor_denied(self):
        with patch.object(Path,"is_symlink",return_value=True):
            with self.assertRaisesRegex(MachineContractError,"JOURNAL_PATH_DENIED"): EventJournal(self.root/"events")

    def test_junction_ancestor_denied(self):
        with patch.object(Path,"is_junction",return_value=True):
            with self.assertRaisesRegex(MachineContractError,"JOURNAL_PATH_DENIED"): EventJournal(self.root/"events")


if __name__ == "__main__": unittest.main()
