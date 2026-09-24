"""Portable ownership, provenance, append/version and immutable-export checks."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from dragonhydra.child import storage


class Cursor:
    def __init__(self, responses=()):
        self.responses = iter(responses)
        self.calls = []

    def execute(self, sql, *params):
        self.calls.append((sql, params))
        return self

    def fetchone(self):
        return next(self.responses, None)


class Connection:
    def __init__(self, cursor=None):
        self.cur = cursor or Cursor()
        self.committed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True


class ChildStorageTests(unittest.TestCase):
    def snapshot(self):
        return {"snapshot_id": "capture-1", "source_id": "openfootball", "source_url": "https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/en.1.json", "retrieved_at": "2026-01-01T12:00:00+00:00", "observed_at": "2026-01-01T12:00:00+00:00", "available_at": "2026-01-01T12:00:00+00:00", "content_hash": "a" * 64, "raw_artifact_hash": "a" * 64, "parser_version": "openfootball/1", "source_policy_version": "child/1", "temporal_mode": "STRICT_PIT"}

    def test_destinations_cannot_select_donor(self):
        self.assertIn("DATABASE={DRAGONHYDRACHILD_LAB}", storage.sql_options())
        cfg = storage.load_config()
        self.assertEqual(cfg["mariadb"]["database"], "dragonhydrachild_ops")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.toml"
            path.write_text((storage.PROJECT_ROOT / "config/child-storage.toml").read_text().replace("DRAGONHYDRACHILD_LAB", "DRAGONHYDRA_LAB"))
            with self.assertRaises(ValueError):
                storage.load_config(path)

    def test_runtime_roles_are_closed(self):
        for engine, role in (("sql", "admin"), ("maria", "root"), ("parent", "read")):
            with self.assertRaises(ValueError):
                storage.secret(engine, role)

    def test_snapshot_future_naive_and_reconstructed_rejected(self):
        for updates in ({"retrieved_at": "2999-01-01T00:00:00+00:00"}, {"available_at": "2999-01-01T00:00:00+00:00"}, {"available_at": "2025-01-01T00:00:00+00:00"}, {"observed_at": "2026-01-02T00:00:00+00:00"}, {"retrieved_at": "2026-01-01T12:00:00"}, {"temporal_mode": "RECONSTRUCTED_PIT"}, {"raw_artifact_hash": "missing"}, {"source_url": "https://127.0.0.1/private"}, {"source_policy_version": ""}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                storage.validate_snapshot(dict(self.snapshot(), **updates), clock="2026-01-03T00:00:00+00:00")
        storage.validate_snapshot(self.snapshot(), clock="2026-01-03T00:00:00+00:00")

    def test_only_exact_met_query_allowed_and_forecast_label_required(self):
        from dragonhydra.child.weather import MET_FORECAST_URL
        snapshot = dict(self.snapshot(), source_id="met-norway", source_url=MET_FORECAST_URL, epistemic_state="HYPOTHESIS", capture_is_observation_of_forecast_not_weather=True)
        storage.validate_snapshot(snapshot)
        for changed in ({"epistemic_state": "OBSERVATION"}, {"source_url": MET_FORECAST_URL + "&altitude=1"}, {"source_id": "pretender"}, {"raw_artifact_hash": "b" * 64}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                storage.validate_snapshot(dict(snapshot, **changed))

    def test_new_revision_retains_predecessor_and_parameterizes_payload(self):
        cursor = Cursor([None, ("old-id", 2)])
        conn = Connection(cursor)
        record_id, inserted = storage.ChildStore().append(conn, "fixtures", "same-fixture", {"name": "x'; DROP TABLE ignored; --"}, "test", "2026-01-01T00:00:00+00:00")
        self.assertTrue(inserted)
        sql, params = cursor.calls[-1]
        self.assertIn("INSERT INTO child.fixtures", sql)
        self.assertNotIn("DROP", sql)
        self.assertEqual(params[2:4], (3, "old-id"))
        self.assertEqual(params[0], record_id)
        self.assertIn("UPDLOCK,HOLDLOCK", cursor.calls[0][0])

    def test_dedup_never_rewrites_record(self):
        cursor = Cursor([("existing",)])
        result = storage.ChildStore().append(Connection(cursor), "snapshots", "capture", {"a": 1}, "test", "2026-01-01T00:00:00+00:00")
        self.assertEqual(result, ("existing", False))
        self.assertEqual(len(cursor.calls), 1)

    def test_snapshot_or_prediction_id_cannot_be_reused_for_different_payload(self):
        for table in ("snapshots", "predictions"):
            with self.subTest(table=table), self.assertRaises(ValueError):
                storage.ChildStore().append(Connection(Cursor([None, ("old", 1)])), table, "immutable-id", {"changed": True}, "test", "2026-01-01T00:00:00+00:00")

    def test_unknown_table_and_future_available_are_rejected(self):
        for table, stamp in (("snapshots; DELETE", "2026-01-01T00:00:00+00:00"), ("snapshots", "2999-01-01T00:00:00+00:00")):
            with self.assertRaises(ValueError):
                storage.ChildStore().append(Connection(), table, "key", {}, "test", stamp)

    def test_duplicate_snapshot_does_not_create_new_fixture_versions(self):
        conn = Connection()
        @contextmanager
        def context():
            yield conn
        with patch.object(storage, "sql_connection", context), patch.object(storage.ChildStore, "append", return_value=("id", False)) as appender:
            report = storage.ChildStore().persist_snapshot(self.snapshot(), [{"fixture_id": "fixture"}])
        self.assertEqual(report["fixture_versions_inserted"], 0)
        self.assertEqual(appender.call_count, 1)

    def test_snapshot_enrichment_cannot_backdate_capture_and_does_not_mutate_input(self):
        conn = Connection()
        @contextmanager
        def context():
            yield conn
        fixture = {"fixture_id": "stable", "available_at": "2019-01-01T00:00:00+00:00"}
        original = deepcopy(fixture)
        with patch.object(storage, "sql_connection", context), patch.object(storage.ChildStore, "append", return_value=("id", True)) as appender:
            storage.ChildStore().persist_snapshot(self.snapshot(), [fixture])
        payload = appender.call_args.args[3]
        self.assertEqual(payload["temporal_mode"], "STRICT_PIT")
        self.assertGreater(storage.timestamp(payload["available_at"]), storage.timestamp(self.snapshot()["retrieved_at"]))
        self.assertEqual(fixture, original)
        self.assertTrue(conn.committed)

    def test_reconstructed_fixture_cannot_become_strict_observation(self):
        conn = Connection()
        @contextmanager
        def context():
            yield conn
        with patch.object(storage, "sql_connection", context), patch.object(storage.ChildStore, "append", return_value=("id", True)), self.assertRaises(ValueError):
            storage.ChildStore().persist_snapshot(self.snapshot(), [{"fixture_id": "stable", "temporal_mode": "RECONSTRUCTED_PIT"}])
        self.assertFalse(conn.committed)

    def test_export_is_immutable_hashed_and_root_bounded(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(storage, "PROJECT_ROOT", Path(directory)), patch.object(storage.ChildStore, "as_of", return_value=[{"record_id": "one", "payload": {"x": 1}}]):
            path = Path(directory) / "runtime/analytical/test.jsonl"
            store = storage.ChildStore()
            manifest = store.analytical_export("fixtures", "2026-01-01T00:00:00+00:00", path)
            self.assertEqual(manifest["row_count"], 1)
            self.assertEqual(manifest["sha256"], storage.hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError):
                store.analytical_export("fixtures", "2026-01-01T00:00:00+00:00", path)
            with self.assertRaises(ValueError):
                store.analytical_export("fixtures", "2026-01-01T00:00:00+00:00", Path(directory) / "outside.jsonl")

    def test_nonfinite_values_cannot_enter_json_storage(self):
        with self.assertRaises(ValueError):
            storage.canonical({"value": float("nan")})


class ChildStorageLiveTests(unittest.TestCase):
    """Local tier only: uses exclusively bounded CHILD identities and child data."""

    def test_live_isolation_and_native_denials(self):
        proof = storage.live_probe()
        self.assertTrue(proof["passed"])
        self.assertEqual(proof["sql_read_donor_database_access"], 0)
        self.assertEqual(proof["sql_ingest_donor_database_access"], 0)
        self.assertEqual(len(proof["denials"]), 7)

    def test_live_revision_asof_and_future_leakage_canary(self):
        key = "controlled-temporal-canary-" + uuid4().hex
        store = storage.ChildStore()
        with storage.sql_connection() as conn:
            first_id, fresh = store.append(conn, "entities", key, {"canonical_id": key, "revision": 1, "synthetic": True, "purpose": "CHILD isolation temporal test"}, "child-controlled-probe", storage.now())
            conn.commit()
        self.assertTrue(fresh)
        t0 = storage.now()
        with storage.sql_connection() as conn:
            second_id, fresh = store.append(conn, "entities", key, {"canonical_id": key, "revision": 2, "synthetic": True, "purpose": "CHILD isolation temporal test"}, "child-controlled-probe", storage.now())
            conn.commit()
        self.assertTrue(fresh)
        old = {r["payload"].get("canonical_id"): r for r in store.as_of("entities", t0, 2000)}[key]
        new = {r["payload"].get("canonical_id"): r for r in store.as_of("entities", storage.now(), 2000)}[key]
        self.assertEqual(old["record_id"], first_id)
        self.assertEqual(old["version"], 1)
        self.assertEqual(new["record_id"], second_id)
        self.assertEqual(new["version"], 2)
        self.assertLessEqual(storage.timestamp(old["available_at"]), storage.timestamp(t0))
        self.assertLessEqual(storage.timestamp(old["created_at"]), storage.timestamp(t0))

    def test_live_mariadb_operational_cache_roundtrip(self):
        key = "controlled-probe-" + uuid4().hex
        payload = {"synthetic": True, "purpose": "CHILD presentation-cache bounded identity proof", "value": 314}
        with storage.maria_connection("ops") as conn:
            conn.cursor().execute("INSERT INTO presentation_cache(cache_key,payload) VALUES(%s,%s)", (key, storage.canonical(payload).decode()))
            conn.commit()
        with storage.maria_connection("web") as conn:
            cur = conn.cursor()
            cur.execute("SELECT payload FROM presentation_cache WHERE cache_key=%s", (key,))
            self.assertEqual(json.loads(cur.fetchone()[0]), payload)


if __name__ == "__main__":
    unittest.main()
