"""Portable preservation checks using synthetic, small, local fixtures only."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from dragonhydra import continuity


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name) / "continuity"
        self.policy = patch.object(continuity, "CONTINUITY_ROOT", self.base)
        self.policy.start()
        self.addCleanup(self.policy.stop)

    def payloads(self):
        return {
            "repository": {"branch": "feature/example", "git_commit": "a" * 40,
                           "git_tree": "b" * 40, "working_tree_clean": True},
            "machine": {"os": {"name": "Windows", "build": "26100"}},
            "resume": {"next_action": "Review bounded evidence", "maturity": "PARTIAL_EXPERIMENTAL"},
            "important-files": {"items": []},
        }

    def capsule(self):
        return continuity.create_capsule(self.base, self.payloads())

    def test_canonical_serialization_ignores_mapping_order(self):
        self.assertEqual(continuity.canonical({"b": 2, "a": 1}),
                         continuity.canonical({"a": 1, "b": 2}))

    def test_digest_changes_with_semantic_content(self):
        self.assertEqual(len(continuity.digest({"a": 1})), 64)
        self.assertNotEqual(continuity.digest({"a": 1}), continuity.digest({"a": 2}))

    def test_nonfinite_number_is_not_canonical_json(self):
        with self.assertRaises((ValueError, TypeError)):
            continuity.canonical({"value": float("nan")})

    def test_secret_keys_are_filtered_recursively(self):
        marker = "synthetic-sensitive-value"
        sanitized = continuity.sanitize({"nested": {"password": marker,
                                      "authorization": marker, "safe": "READY"}})
        encoded = json.dumps(sanitized)
        self.assertNotIn(marker, encoded)
        self.assertIn("READY", encoded)

    def test_token_pattern_is_filtered_without_real_credential(self):
        marker = "ghp_" + "X" * 36
        self.assertNotIn(marker, json.dumps(continuity.sanitize({"text": marker})))

    def test_capsule_creation_produces_manifest_and_latest_pointer(self):
        capsule = self.capsule()
        self.assertTrue(capsule.is_dir())
        self.assertTrue((capsule / "manifest.json").is_file())
        self.assertTrue((self.base / "latest.json").is_file())
        self.assertTrue(continuity.verify_capsule(self.base)["passed"])

    def test_read_capsule_preserves_useful_state(self):
        self.capsule()
        values = continuity.read_capsule(self.base)
        self.assertEqual(values["repository"]["git_commit"], "a" * 40)
        self.assertEqual(values["resume"]["next_action"], "Review bounded evidence")

    def test_payload_envelope_is_explicit_and_consistent(self):
        capsule = self.capsule()
        for name in ("repository", "machine", "resume", "important-files"):
            value = json.loads((capsule / (name + ".json")).read_text(encoding="utf-8"))
            self.assertEqual(value["project_id"], "DRAGONHYDRACHILD")
            self.assertEqual(value["capture_id"], capsule.name)
            self.assertIn("created_at", value)
            self.assertTrue(value["schema_name"].startswith("dragonhydra.continuity."))
            continuity.validate_document(value)

    def test_unknown_schema_version_is_rejected(self):
        capsule = self.capsule()
        value = json.loads((capsule / "repository.json").read_text(encoding="utf-8"))
        value["schema_version"] = 999
        with self.assertRaises((ValueError, TypeError)):
            continuity.validate_document(value)

    def test_wrong_project_identity_is_rejected(self):
        capsule = self.capsule()
        value = json.loads((capsule / "repository.json").read_text(encoding="utf-8"))
        value["project_id"] = "ANOTHER_PROJECT"
        with self.assertRaises((ValueError, TypeError)):
            continuity.validate_document(value)

    def test_schema_name_mismatch_is_rejected(self):
        capsule = self.capsule()
        value = json.loads((capsule / "repository.json").read_text(encoding="utf-8"))
        with self.assertRaises((ValueError, TypeError)):
            continuity.validate_document(value, "dragonhydra.continuity.machine")

    def test_tampered_payload_fails_integrity(self):
        capsule = self.capsule()
        path = capsule / "repository.json"
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        self.assertFalse(continuity.verify_capsule(self.base)["passed"])

    def test_missing_payload_fails_integrity(self):
        capsule = self.capsule()
        (capsule / "machine.json").unlink()
        self.assertFalse(continuity.verify_capsule(self.base)["passed"])

    def test_unlisted_payload_fails_integrity(self):
        capsule = self.capsule()
        (capsule / "unexpected.txt").write_text("synthetic", encoding="utf-8")
        self.assertFalse(continuity.verify_capsule(self.base)["passed"])

    def test_read_rejects_unverified_payload(self):
        capsule = self.capsule()
        (capsule / "machine.json").write_text("{}", encoding="utf-8")
        with self.assertRaises((ValueError, TypeError, OSError)):
            continuity.read_capsule(self.base)

    def test_capsule_cannot_be_overwritten(self):
        capsule = self.capsule()
        original = (capsule / "manifest.json").read_bytes()
        with self.assertRaises((ValueError, FileExistsError)):
            continuity.create_capsule(self.base, self.payloads(), capture_id=capsule.name)
        self.assertEqual((capsule / "manifest.json").read_bytes(), original)

    def test_capture_id_path_traversal_is_rejected(self):
        with self.assertRaises((ValueError, OSError)):
            continuity.create_capsule(self.base, self.payloads(), capture_id="../escape")

    def test_capsule_root_cannot_escape_local_policy(self):
        outside = Path(self.directory.name) / "outside"
        with self.assertRaises((ValueError, OSError)):
            continuity.create_capsule(outside, self.payloads())
        self.assertFalse(outside.exists())

    def test_linked_ancestor_is_rejected_before_writing(self):
        linked_parent = self.base.parent
        with patch.object(Path, "is_junction", lambda path: path == linked_parent):
            with self.assertRaises((ValueError, OSError)):
                self.capsule()
        self.assertFalse(self.base.exists())

    def test_latest_pointer_hash_tampering_fails_integrity(self):
        self.capsule()
        path = self.base / "latest.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["data"]["capsule_manifest_hash"] = "0" * 64
        path.write_bytes(continuity.canonical(value))
        self.assertFalse(continuity.verify_capsule(self.base)["passed"])

    def test_latest_pointer_traversal_is_rejected(self):
        self.capsule()
        path = self.base / "latest.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["capture_id"] = "../another-directory"
        path.write_bytes(continuity.canonical(value))
        self.assertFalse(continuity.verify_capsule(self.base)["passed"])

    def test_duplicate_json_keys_fail_integrity(self):
        capsule = self.capsule()
        path = capsule / "manifest.json"
        raw = path.read_text(encoding="utf-8")
        path.write_text('{"project_id":"DRAGONHYDRACHILD",' + raw[1:], encoding="utf-8")
        result = continuity.verify_capsule(self.base)
        self.assertFalse(result["passed"])
        self.assertIn("DUPLICATE_JSON_KEY", result["errors"])

    def test_oversized_payload_is_rejected_before_writing(self):
        payloads = self.payloads()
        payloads["resume"]["synthetic_details"] = "X" * (continuity.MAX_FILE + 1)
        with self.assertRaises((ValueError, OSError)):
            continuity.create_capsule(self.base, payloads)
        self.assertFalse(self.base.exists())

    def test_invalid_git_hash_cannot_form_verified_capsule(self):
        payloads = self.payloads()
        payloads["repository"]["git_commit"] = "not-a-commit"
        with self.assertRaises((ValueError, OSError)):
            continuity.create_capsule(self.base, payloads)
        self.assertFalse((self.base / "latest.json").exists())

    def test_captured_secret_is_omitted_and_capsule_verifies(self):
        payloads = self.payloads()
        marker = "synthetic-sensitive-value"
        payloads["resume"]["password"] = marker
        capsule = continuity.create_capsule(self.base, payloads)
        self.assertTrue(continuity.verify_capsule(self.base)["passed"])
        for path in capsule.iterdir():
            self.assertNotIn(marker, path.read_text(encoding="utf-8"))

    def test_identical_states_have_no_meaningful_delta(self):
        before = self.payloads()
        self.assertFalse(continuity.compare_states(before, deepcopy(before))["changed"])

    def test_repository_change_is_reported(self):
        before = self.payloads()
        after = deepcopy(before)
        after["repository"]["git_commit"] = "c" * 40
        result = continuity.compare_states(before, after)
        self.assertTrue(result["changed"])
        self.assertTrue(result["changes"])
        self.assertIn("reason_code", result["changes"][0])

    def test_timestamp_only_change_is_not_semantic_delta(self):
        before = self.payloads()
        after = deepcopy(before)
        before["machine"]["created_at"] = "2026-09-25T00:00:00Z"
        after["machine"]["created_at"] = "2026-09-26T00:00:00Z"
        self.assertFalse(continuity.compare_states(before, after)["changed"])

    def test_model_runtime_port_and_process_changes_are_meaningful(self):
        before = self.payloads()
        before["models"] = [{"model_id": "model-a", "size": 16}]
        before["runtime"] = {"recorded_status": {"runtime_id": "runtime-a"}}
        before["machine"]["observations"] = [
            {"kind": "listener", "entity_id": "listener.8082", "attributes": {"port": 8082, "pid": 10}},
            {"kind": "process", "entity_id": "process.10", "attributes": {"pid": 10, "name": "fixture.exe"}}]
        for section, replacement in (
            ("models", [{"model_id": "model-b", "size": 16}]),
            ("runtime", {"recorded_status": {"runtime_id": "runtime-b"}}),
            ("machine", {"observations": []}),
            ("machine", {"observations": [{"kind": "process", "entity_id": "process.11", "attributes": {"pid": 11}}]}),
        ):
            with self.subTest(section=section, replacement=replacement):
                after = deepcopy(before)
                after[section] = replacement
                self.assertTrue(continuity.compare_states(before, after)["changed"])

    def test_important_file_missing_and_hash_change_are_reported(self):
        before = self.payloads()
        before["important-files"] = {"files": [{"path": "docs/example.md", "exists": True, "sha256": "a" * 64}]}
        for file_state in ([], [{"path": "docs/example.md", "exists": True, "sha256": "b" * 64}]):
            with self.subTest(file_state=file_state):
                after = deepcopy(before)
                after["important-files"] = {"files": file_state}
                self.assertTrue(continuity.compare_states(before, after)["changed"])

    def test_git_metadata_capture_is_read_only(self):
        repository = Path(self.directory.name) / "repository"
        repository.mkdir()
        def git(*args):
            return subprocess.run(["git", "-C", str(repository), *args], check=True,
                                  capture_output=True, text=True).stdout.strip()
        git("init", "-b", "feature/fixture")
        (repository / "fixture.txt").write_text("synthetic fixture\n", encoding="utf-8")
        git("add", "fixture.txt")
        git("-c", "user.name=Continuity Test", "-c", "user.email=fixture@example.invalid",
            "commit", "-m", "fixture")
        before = git("status", "--porcelain=v1")
        result = continuity.repository_state(repository)
        self.assertIn(git("rev-parse", "HEAD"), json.dumps(result))
        self.assertIn("feature/fixture", json.dumps(result))
        self.assertEqual(git("status", "--porcelain=v1"), before)

    def test_briefing_is_compact_and_preserves_next_action(self):
        public = {"project_id": "DRAGONHYDRACHILD", "maturity": "PARTIAL_EXPERIMENTAL",
                  "next_action": "Review bounded evidence", "authoritative_files": ["docs/continuity/CURRENT_STATE.md"]}
        result = continuity.resume_briefing(public)
        encoded = json.dumps(result)
        self.assertIn("Review bounded evidence", encoded)
        self.assertIn("DRAGONHYDRACHILD", encoded)
        self.assertLess(len(encoded), 20000)

    def test_briefing_does_not_blindly_copy_private_context(self):
        public = {"project_id": "DRAGONHYDRACHILD", "next_action": "Review bounded evidence"}
        marker = "private-synthetic-content"
        current = {"repository": {"branch": "feature/example", "git_commit": "a" * 40},
                   "private_detail": marker, "machine": {"private_detail": marker},
                   "runtime": {"private_detail": marker}}
        encoded = json.dumps(continuity.resume_briefing(public, current=current))
        self.assertNotIn(marker, encoded)
        self.assertIn("NEXT_ACTION", encoded)

    def test_public_only_resume_still_has_useful_reconstruction(self):
        public = {"current-state": {"project_id": "DRAGONHYDRACHILD", "git_commit": "a" * 40,
                  "branch": "feature/example", "completed": ["Cognitive V2 foundation"]},
                  "resume-manifest": {"next_action": "Review bounded evidence", "do_not_repeat": ["Model inference"]}}
        result = continuity.resume_briefing(public)
        self.assertFalse(result["LOCAL_CAPSULE_AVAILABLE"])
        self.assertEqual(result["COMMIT"], "a" * 40)
        self.assertEqual(result["NEXT_ACTION"], "Review bounded evidence")
        self.assertEqual(result["AUTOMATIC_RESTORATION"], "DISABLED")

    def test_invalid_required_payload_type_fails_before_creation(self):
        values=self.payloads();values['repository']=[]
        with self.assertRaises(ValueError):continuity.create_capsule(self.base,values)
        self.assertFalse((self.base/'capsules').exists())

    def test_briefing_machine_summary_is_an_explicit_projection(self):
        result=continuity.resume_briefing({'project_id':'DRAGONHYDRACHILD'},current={
            'machine':{'summary':{'os':'synthetic OS','private_detail':'do-not-copy'}}})
        self.assertEqual(result['MACHINE_CONTEXT']['summary'],{'os':'synthetic OS'})


if __name__ == "__main__":
    unittest.main()
