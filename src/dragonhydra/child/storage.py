"""Independent CHILD persistence. No donor credential or database can be selected.

SQL owns append-only intelligence; MariaDB owns replaceable presentation and jobs.
Drivers are inherited pinned wheels, but credentials and destinations are separate.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tomllib
from uuid import uuid4

from dragonhydra.config import PROJECT_ROOT, load_settings
from dragonhydra.integration.mariadb_probe import load_driver
from dragonhydra.storage.sqlserver import load_odbc, odbc_value
from dragonhydra.storage.sqlserver_config import load_sqlserver_settings

SQL_DATABASE = "DRAGONHYDRACHILD_LAB"
MARIA_DATABASE = "dragonhydrachild_ops"
TABLES = ("sources", "snapshots", "fixtures", "entities", "predictions", "evaluations")


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("An explicit offset-aware timestamp string is required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware")
    return result


def load_config(path=None):
    with (path or PROJECT_ROOT / "config/child-storage.toml").open("rb") as stream:
        cfg = tomllib.load(stream)
    sql, maria = cfg["sqlserver"], cfg["mariadb"]
    if (sql["database"] != SQL_DATABASE or sql["schema"] != "child"
            or maria["database"] != MARIA_DATABASE
            or sql["host"] != "127.0.0.1" or maria["host"] != "127.0.0.1"
            or sql["port"] != 1433 or maria["port"] != 3306
            or sql["odbc_driver"] != "ODBC Driver 18 for SQL Server"
            or sql["encrypt"] is not True or sql["trust_server_certificate"] is not True):
        raise ValueError("CHILD storage isolation invariant violated")
    if any(key in group for group in (sql, maria) for key in ("username", "password")):
        raise ValueError("Configuration must not contain credentials")
    return cfg


def sql_options(*, administrative=False):
    load_config()
    database = "master" if administrative else SQL_DATABASE
    return ("DRIVER={ODBC Driver 18 for SQL Server};SERVER=tcp:127.0.0.1,1433;"
            f"DATABASE={{{database}}};Encrypt=yes;TrustServerCertificate=yes;")


def drivers():
    # Existing settings are used solely to locate pinned copied wheels; no connection.
    return load_odbc(load_sqlserver_settings()), load_driver(load_settings())


def secret(engine, role):
    valid = {"sql": ("ingest", "read"), "maria": ("ops", "web")}
    if engine not in valid or role not in valid[engine]:
        raise ValueError("Unsupported CHILD runtime identity")
    raw = json.loads((PROJECT_ROOT / f"runtime/secrets/child-{engine}-{role}.local.json").read_text("utf-8"))
    if raw.get("username") != f"dragonhydrachild_{role}" or not isinstance(raw.get("password"), str) or len(raw["password"]) < 32:
        raise ValueError("CHILD identity mismatch or missing credential")
    return raw


@contextmanager
def sql_connection(role="ingest"):
    credential = secret("sql", role)
    odbc, _ = drivers()
    conn = None
    try:
        conn = odbc.connect(sql_options() + f'UID={odbc_value(credential["username"])};PWD={odbc_value(credential["password"])};', timeout=5, autocommit=False)
        conn.timeout = 10
        yield conn
    except odbc.Error:
        raise RuntimeError("CHILD_SQL_STORAGE_FAILURE") from None
    finally:
        if conn is not None:
            conn.close()


@contextmanager
def maria_connection(role="ops"):
    credential = secret("maria", role)
    _, driver = drivers()
    load_config()
    conn = None
    try:
        conn = driver.connect(host="127.0.0.1", port=3306, user=credential["username"], password=credential["password"], database=MARIA_DATABASE, charset="utf8mb4", connect_timeout=5, read_timeout=10, write_timeout=10, autocommit=False)
        yield conn
    except driver.MySQLError:
        raise RuntimeError("CHILD_MARIADB_STORAGE_FAILURE") from None
    finally:
        if conn is not None:
            conn.close()


def validate_snapshot(snapshot, *, clock=None):
    required = ("snapshot_id", "source_id", "source_url", "retrieved_at", "observed_at", "available_at", "content_hash", "raw_artifact_hash", "parser_version", "source_policy_version", "temporal_mode")
    if any(not isinstance(snapshot.get(key), str) or not snapshot[key].strip() for key in required):
        raise ValueError("Incomplete snapshot provenance")
    if snapshot["temporal_mode"] != "STRICT_PIT":
        raise ValueError("Live snapshots require STRICT_PIT")
    if not all(re.fullmatch(r"[0-9a-f]{64}", snapshot[key]) for key in ("content_hash", "raw_artifact_hash")):
        raise ValueError("SHA256 required")
    if snapshot["content_hash"] != snapshot["raw_artifact_hash"]:
        raise ValueError("Snapshot content and raw artifact must identify the same captured bytes")
    observed, retrieved = timestamp(snapshot["observed_at"]), timestamp(snapshot["retrieved_at"])
    if not observed <= retrieved <= timestamp(snapshot["available_at"]) <= timestamp(clock or now()):
        raise ValueError("Invalid live temporal order")
    from dragonhydra.web.contracts import public_url
    from .weather import MET_FORECAST_URL
    if snapshot["source_id"] == "met-norway" and snapshot["source_url"] == MET_FORECAST_URL:
        if snapshot.get("epistemic_state") != "HYPOTHESIS" or snapshot.get("capture_is_observation_of_forecast_not_weather") is not True:
            raise ValueError("MET forecast capture must preserve hypothesis labels")
    else:
        public_url(snapshot["source_url"])


class ChildStore:
    def append(self, connection, table, key, payload, source_id, available_at):
        if table not in TABLES or not isinstance(key, str) or not 1 <= len(key) <= 240:
            raise ValueError("Invalid bounded append operation")
        issued = now()
        if timestamp(available_at) > timestamp(issued):
            raise ValueError("Future data cannot be stored as available observation")
        body = canonical(payload).decode()
        fingerprint = hashlib.sha256(canonical([key, payload])).hexdigest()
        cur = connection.cursor()
        cur.execute(f"SELECT record_id FROM child.{table} WITH (UPDLOCK,HOLDLOCK) WHERE dedup_key=?", fingerprint)
        prior = cur.fetchone()
        if prior:
            return prior[0], False
        cur.execute(f"SELECT TOP(1) record_id,version FROM child.{table} WITH (UPDLOCK,HOLDLOCK) WHERE natural_key=? ORDER BY version DESC", key)
        prior = cur.fetchone()
        if prior and table in ("snapshots", "predictions"):
            raise ValueError("Immutable snapshot/prediction identity cannot acquire a different payload")
        record_id = uuid4().hex
        cur.execute(f"INSERT INTO child.{table}(record_id,natural_key,version,supersedes_id,source_id,available_at,created_at,dedup_key,payload) VALUES(?,?,?,?,?,?,?,?,?)", record_id, key, prior[1] + 1 if prior else 1, prior[0] if prior else None, source_id, available_at, issued, fingerprint, body)
        return record_id, True

    def persist_snapshot(self, snapshot, fixtures):
        validate_snapshot(snapshot)
        if not isinstance(fixtures, list) or len(fixtures) > 500:
            raise ValueError("Snapshot fixture batch is bounded to 500")
        available_at = now()
        inserted = 0
        with sql_connection() as conn:
            snap_id, fresh = self.append(conn, "snapshots", snapshot["snapshot_id"], snapshot, snapshot["source_id"], available_at)
            if not fresh:
                conn.commit()
                return {"snapshot_record_id": snap_id, "snapshot_inserted": False, "fixture_versions_inserted": 0, "database": SQL_DATABASE}
            source = {key: snapshot[key] for key in ("source_id", "source_url", "parser_version", "source_policy_version")}
            self.append(conn, "sources", snapshot["source_id"], source, snapshot["source_id"], available_at)
            for item in fixtures:
                if not isinstance(item, dict) or not item.get("fixture_id"):
                    raise ValueError("Canonical stable fixture_id required")
                if item.get("temporal_mode", "STRICT_PIT") != "STRICT_PIT":
                    raise ValueError("Reconstructed input cannot be relabelled as a live fixture observation")
                # Reconstructed event semantics cannot overwrite actual capture provenance.
                payload = dict(item, evidence_snapshot_id=snapshot["snapshot_id"], source_id=snapshot["source_id"], source_url=snapshot["source_url"], observed_at=snapshot["observed_at"], retrieved_at=snapshot["retrieved_at"], available_at=available_at, content_hash=snapshot["content_hash"], parser_version=snapshot["parser_version"], source_policy_version=snapshot["source_policy_version"], temporal_mode="STRICT_PIT")
                _, added = self.append(conn, "fixtures", str(item["fixture_id"]), payload, snapshot["source_id"], available_at)
                inserted += int(added)
            conn.commit()
        return {"snapshot_record_id": snap_id, "snapshot_inserted": fresh, "fixture_versions_inserted": inserted, "available_at": available_at, "database": SQL_DATABASE}

    def as_of(self, table, target_as_of, limit=500):
        timestamp(target_as_of)
        if table not in TABLES or type(limit) is not int or not 1 <= limit <= 2000:
            raise ValueError("Bounded as-of query required")
        with sql_connection("read") as conn:
            rows = conn.cursor().execute(f"""WITH versions AS (
              SELECT record_id,payload,available_at,created_at,version,natural_key,
              ROW_NUMBER() OVER(PARTITION BY natural_key ORDER BY version DESC) AS rn
              FROM child.{table} WHERE available_at<=? AND created_at<=?)
              SELECT TOP(?) record_id,payload,CONVERT(varchar(40),available_at,127),CONVERT(varchar(40),created_at,127),version FROM versions WHERE rn=1 ORDER BY natural_key""", target_as_of, target_as_of, limit).fetchall()
            return [{"record_id": r[0], "payload": json.loads(r[1]), "available_at": str(r[2]), "created_at": str(r[3]), "version": r[4]} for r in rows]

    def summary(self):
        with sql_connection("read") as conn:
            counts = {}
            cur = conn.cursor()
            for table in TABLES:
                row = cur.execute(f"SELECT COUNT(*),COUNT(DISTINCT natural_key) FROM child.{table}").fetchone()
                counts[table] = {"versions": row[0], "identities": row[1]}
            row = cur.execute("SELECT TOP(1) payload FROM child.snapshots ORDER BY created_at DESC").fetchone()
            latest = json.loads(row[0]) if row else None
        return {"project": "DRAGONHYDRACHILD", "database": SQL_DATABASE, "counts": counts, "latest_snapshot": latest, "built_at": now(), "sqlserver": "healthy", "temporal_mode": "STRICT_PIT", "observations_are_not_predictions": True}

    def analytical_export(self, table, target_as_of, destination):
        """Immutable bounded JSONL export; no new database or conflicting owner."""
        destination = Path(destination).resolve()
        root = (PROJECT_ROOT / "runtime/analytical").resolve()
        if not destination.is_relative_to(root) or destination.suffix != ".jsonl":
            raise ValueError("Analytical exports remain in CHILD runtime/analytical")
        records = self.as_of(table, target_as_of, 2000)
        body = b"".join(canonical(row) + b"\n" for row in records)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(body)
        manifest = {"format": "JSONL", "primary_owner": "SQL Server", "table": table, "target_as_of": target_as_of, "row_count": len(records), "sha256": hashlib.sha256(body).hexdigest(), "byte_count": len(body), "created_at": now()}
        with destination.with_suffix(".manifest.json").open("xb") as stream:
            stream.write(canonical(manifest) + b"\n")
        return manifest


class ChildPresentation:
    def cache(self, summary):
        body = canonical(dict(summary, mariadb="healthy")).decode()
        with maria_connection() as conn:
            conn.cursor().execute("INSERT INTO presentation_cache(cache_key,payload) VALUES(%s,%s) ON DUPLICATE KEY UPDATE payload=VALUES(payload),updated_at=CURRENT_TIMESTAMP", ("child-intelligence", body))
            conn.commit()
        return json.loads(body)

    def read_cache(self):
        with maria_connection("web") as conn:
            cur = conn.cursor()
            cur.execute("SELECT payload FROM presentation_cache WHERE cache_key=%s", ("child-intelligence",))
            row = cur.fetchone()
            return json.loads(row[0]) if row else None


def live_probe():
    """Read both child stores and prove runtime mutation denials with zero-row SQL."""
    odbc, maria = drivers()
    report = {"checked_at": now(), "sql_database": SQL_DATABASE, "maria_database": MARIA_DATABASE, "denials": {}, "identities": {}}
    for role in ("ingest", "read"):
        with sql_connection(role) as conn:
            cur = conn.cursor()
            identity = cur.execute("SELECT DB_NAME(),ORIGINAL_LOGIN(),IS_SRVROLEMEMBER('sysadmin'),IS_MEMBER('db_owner')").fetchone()
            report["identities"][f"sql_{role}"] = list(identity)
            if identity[0] != SQL_DATABASE or identity[1] != f"dragonhydrachild_{role}" or identity[2] != 0 or identity[3] != 0:
                raise RuntimeError("Child SQL identity is not bounded")
            report[f"sql_{role}_donor_database_access"] = cur.execute("SELECT HAS_DBACCESS(N'DRAGONHYDRA_LAB')").fetchone()[0]
            if report[f"sql_{role}_donor_database_access"] != 0:
                raise RuntimeError("Child runtime must not have donor database access")
            for operation in ("UPDATE", "DELETE"):
                query = "UPDATE child.fixtures SET natural_key=natural_key WHERE 1=0" if operation == "UPDATE" else "DELETE FROM child.fixtures WHERE 1=0"
                denied = False
                try:
                    cur.execute(query)
                except odbc.Error as exc:
                    denied = any("(229)" in str(arg) for arg in exc.args)
                    if not denied:
                        raise RuntimeError("Unexpected SQL permission probe error") from None
                finally:
                    conn.rollback()
                report["denials"][f"sql_{role}_{operation.lower()}"] = denied
            if role == "read":
                denied = False
                try:
                    cur.execute("INSERT INTO child.fixtures SELECT * FROM child.fixtures WHERE 1=0")
                except odbc.Error as exc:
                    denied = any("(229)" in str(arg) for arg in exc.args)
                    if not denied:
                        raise RuntimeError("Unexpected SQL insert probe error") from None
                finally:
                    conn.rollback()
                report["denials"]["sql_read_insert"] = denied
            report[f"sql_{role}_permissions"] = [list(row) for row in cur.execute("SELECT class,permission_name,state_desc FROM sys.database_permissions WHERE grantee_principal_id=USER_ID() ORDER BY class,permission_name").fetchall()]
    for role in ("ops", "web"):
        with maria_connection(role) as conn:
            cur = conn.cursor()
            cur.execute("SELECT DATABASE(),CURRENT_USER()")
            report["identities"][f"maria_{role}"] = list(cur.fetchone())
            cur.execute("SHOW GRANTS")
            report[f"maria_{role}_grants"] = [row[0].split(" TO ", 1)[0] for row in cur.fetchall()]
            query = "DELETE FROM presentation_cache WHERE 1=0" if role == "ops" else "UPDATE presentation_cache SET cache_key=cache_key WHERE 1=0"
            denied = False
            try:
                cur.execute(query)
            except maria.MySQLError as exc:
                denied = exc.args[0] == 1142
                if not denied:
                    raise RuntimeError("Unexpected MariaDB permission probe error") from None
            finally:
                conn.rollback()
            report["denials"][f"maria_{role}_write"] = denied
    report["passed"] = all(report["denials"].values())
    return report
