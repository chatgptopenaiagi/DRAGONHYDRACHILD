"""CHILD-only local integration. No inherited donor account or database is used.

Requires two genuine OpenFootball captures already ingested, the CHILD databases,
and the separately deployed localhost dashboard. These are explicit local-tier
prerequisites, not portable CI skips. No source acquisition occurs in these tests.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
from pathlib import Path
import unittest
from uuid import uuid4

from dragonhydra.child.storage import (
    ChildStore, PROJECT_ROOT, SQL_DATABASE, MARIA_DATABASE, canonical,
    maria_connection, now, sql_connection, timestamp,
)


class ChildRuntimeLiveTests(unittest.TestCase):
    def test_real_fixture_capture_t0_t1_replay_preserves_old_records_and_raw_hash(self):
        with sql_connection("read") as conn:
            cur = conn.cursor()
            captures = cur.execute("""SELECT JSON_VALUE(payload,'$.evidence_snapshot_id'),
                COUNT(*),CONVERT(varchar(40),MAX(created_at),127)
                FROM child.fixtures WHERE source_id=?
                GROUP BY JSON_VALUE(payload,'$.evidence_snapshot_id')
                ORDER BY MAX(created_at)""", "openfootball").fetchall()
            self.assertGreaterEqual(len(captures), 2, "Two real fixture captures must exist before this local replay gate")
            first, second = captures[0], captures[1]
            frozen = cur.execute("SELECT record_id,payload FROM child.fixtures WHERE JSON_VALUE(payload,'$.evidence_snapshot_id')=? ORDER BY record_id", first[0]).fetchall()
            frozen_hash = hashlib.sha256(canonical([list(row) for row in frozen])).hexdigest()
            snapshot = cur.execute("SELECT payload FROM child.snapshots WHERE natural_key=?", first[0]).fetchone()
            first_snapshot = json.loads(snapshot[0])
        t0 = (timestamp(first[2]) + timedelta(microseconds=1)).isoformat()
        t1 = (timestamp(second[2]) + timedelta(microseconds=1)).isoformat()
        self.assertLess(timestamp(t0), timestamp(t1))
        store = ChildStore()
        old = {row["payload"]["fixture_id"]: row for row in store.as_of("fixtures", t0, 2000) if row["payload"].get("source_id") == "openfootball"}
        new = {row["payload"]["fixture_id"]: row for row in store.as_of("fixtures", t1, 2000) if row["payload"].get("source_id") == "openfootball"}
        self.assertEqual(len(old), first[1])
        self.assertEqual(len(new), second[1])
        self.assertEqual(set(old), set(new), "Schedule revisions must retain fixture identity")
        for fixture_id, row in old.items():
            self.assertEqual(row["payload"]["evidence_snapshot_id"], first[0])
            self.assertEqual(new[fixture_id]["payload"]["evidence_snapshot_id"], second[0])
            self.assertGreater(new[fixture_id]["version"], row["version"])
            self.assertLessEqual(timestamp(row["available_at"]), timestamp(t0))
            self.assertLessEqual(timestamp(row["created_at"]), timestamp(t0))
        with sql_connection("read") as conn:
            after = conn.cursor().execute("SELECT record_id,payload FROM child.fixtures WHERE JSON_VALUE(payload,'$.evidence_snapshot_id')=? ORDER BY record_id", first[0]).fetchall()
        self.assertEqual(hashlib.sha256(canonical([list(row) for row in after])).hexdigest(), frozen_hash)
        raw_path = PROJECT_ROOT / "runtime/raw" / first_snapshot["raw_artifact_hash"]
        self.assertEqual(hashlib.sha256(raw_path.read_bytes()).hexdigest(), first_snapshot["content_hash"])
        self.assertEqual(first_snapshot["temporal_mode"], "STRICT_PIT")

    def test_simultaneous_child_connections_preserve_disjoint_runtime_permissions(self):
        # Unlike the separate native denied-write tests, hold both engines open and
        # inspect actual permitted operations, database ownership and transaction use.
        with sql_connection("read") as sql, maria_connection("web") as maria:
            sql_cur = sql.cursor()
            row = sql_cur.execute("""SELECT DB_NAME(),HAS_PERMS_BY_NAME('child.fixtures','OBJECT','SELECT'),
                HAS_PERMS_BY_NAME('child.fixtures','OBJECT','INSERT'),
                HAS_PERMS_BY_NAME('child.fixtures','OBJECT','ALTER'),
                HAS_PERMS_BY_NAME(NULL,'DATABASE','CREATE TABLE'),HAS_DBACCESS('DRAGONHYDRA_LAB')""").fetchone()
            self.assertEqual(tuple(row), (SQL_DATABASE, 1, 0, 0, 0, 0))
            count_before = sql_cur.execute("SELECT COUNT(*) FROM child.snapshots").fetchone()[0]
            maria_cur = maria.cursor()
            maria_cur.execute("START TRANSACTION READ ONLY")
            maria_cur.execute("SELECT DATABASE(),CURRENT_USER()")
            self.assertEqual(tuple(maria_cur.fetchone()), (MARIA_DATABASE, "dragonhydrachild_web@localhost"))
            maria_cur.execute("SELECT TABLE_SCHEMA,TABLE_NAME,PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.TABLE_PRIVILEGES")
            grants = set(maria_cur.fetchall())
            self.assertEqual(grants, {(MARIA_DATABASE, "presentation_cache", "SELECT", "NO")})
            maria_cur.execute("SELECT COUNT(*) FROM presentation_cache")
            self.assertGreater(maria_cur.fetchone()[0], 0)
            self.assertEqual(sql_cur.execute("SELECT COUNT(*) FROM child.snapshots").fetchone()[0], count_before)
            sql.rollback()
            maria.rollback()

    def test_analytical_export_replays_sql_and_cannot_overwrite_previous_bytes(self):
        store, target = ChildStore(), now()
        destination = PROJECT_ROOT / "runtime/analytical/tests" / ("fixtures-" + uuid4().hex + ".jsonl")
        expected = store.as_of("fixtures", target, 2000)
        self.assertGreater(len(expected), 0)
        manifest = store.analytical_export("fixtures", target, destination)
        original = destination.read_bytes()
        exported = [json.loads(line) for line in original.splitlines()]
        self.assertEqual(exported, expected)
        self.assertEqual(manifest["primary_owner"], "SQL Server")
        self.assertEqual(manifest["row_count"], len(expected))
        self.assertEqual(manifest["sha256"], hashlib.sha256(original).hexdigest())
        with self.assertRaises(FileExistsError):
            store.analytical_export("fixtures", target, destination)
        self.assertEqual(destination.read_bytes(), original)
        self.assertEqual(store.as_of("fixtures", target, 2000), expected)

    def test_dashboard_http_json_cache_parity_and_secret_exclusion(self):
        base = "/joomla-codex-lab/dragonhydrachild/"
        bodies = []
        for suffix, expected_type in (("", "text/html"), ("?format=json", "application/json")):
            conn = http.client.HTTPConnection("127.0.0.1", 80, timeout=10)
            try:
                conn.request("GET", base + suffix)
                response = conn.getresponse()
                self.assertEqual(response.status, 200, "CHILD dashboard must return HTTP 200")
                self.assertIn(expected_type, response.getheader("Content-Type", ""))
                self.assertIn("no-store", response.getheader("Cache-Control", ""))
                self.assertEqual({value.strip() for value in response.getheader("X-Content-Type-Options", "").split(",")}, {"nosniff"})
                body = response.read(2_000_001)
                self.assertLessEqual(len(body), 2_000_000)
                bodies.append(body)
            finally:
                conn.close()
        payload = json.loads(bodies[1])
        self.assertEqual(payload["project"], "DRAGONHYDRACHILD")
        self.assertEqual(payload["sqlserver"], "healthy")
        self.assertEqual(payload["mariadb"], "healthy")
        with maria_connection("web") as conn:
            cur = conn.cursor()
            cur.execute("SELECT payload FROM presentation_cache WHERE cache_key=%s", ("child-intelligence",))
            cached = json.loads(cur.fetchone()[0])
        self.assertEqual(payload, cached)
        # Deliberately avoid assertNotIn(secret, body): failure output could disclose it.
        for path in (PROJECT_ROOT / "runtime/secrets").glob("child-*.local.json"):
            value = json.loads(path.read_text("utf-8"))
            for field in ("password", "token", "api_key", "secret"):
                candidate = value.get(field)
                if isinstance(candidate, str) and candidate and any(candidate.encode() in body for body in bodies):
                    self.fail("Dashboard exposed protected local secret material; value suppressed")
        prohibited = {"password", "api_key", "access_token", "authorization", "cookie", "connection_string"}
        def inspect(value):
            if isinstance(value, dict):
                self.assertFalse(prohibited.intersection(str(key).lower() for key in value), "Credential-bearing field in presentation JSON")
                for item in value.values():
                    inspect(item)
            elif isinstance(value, list):
                for item in value:
                    inspect(item)
        inspect(payload)


if __name__ == "__main__":
    unittest.main()
