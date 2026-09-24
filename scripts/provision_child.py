"""Explicit one-time CHILD provisioning; refuses collisions and never resets state.

Uses authorized Windows integrated SQL administration and local MariaDB root.
All created names/files are CHILD-owned. Runtime code never uses admin identities.
"""
import json
import os
import platform
import secrets
import subprocess
import sys
from uuid import uuid4

from dragonhydra.config import PROJECT_ROOT
from dragonhydra.child.storage import TABLES, SQL_DATABASE, MARIA_DATABASE, canonical, drivers, now, sql_options, live_probe


def literal(value):
    return "N'" + value.replace("'", "''") + "'"


def prepare_private_directory(path, *, sql_service=False):
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)
        return
    account = subprocess.check_output(["whoami"], text=True).strip()
    grants = [f"{account}:(OI)(CI)F", "SYSTEM:(OI)(CI)F"]
    if sql_service:
        grants.append("NT SERVICE\\MSSQLSERVER:(OI)(CI)M")
    subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", *grants], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    if sys.version_info[:2] != (3, 14):
        raise RuntimeError("Python 3.14 required")
    if PROJECT_ROOT.name != "DRAGONHYDRACHILD":
        raise RuntimeError("Provisioning is restricted to the explicit CHILD root")
    secret_dir = PROJECT_ROOT / "runtime/secrets"
    data_dir = PROJECT_ROOT / "runtime/sqlserver-lab"
    secret_names = [f"child-{engine}-{role}.local.json" for engine, roles in (("sql", ("ingest", "read")), ("maria", ("ops", "web"))) for role in roles]
    if any((secret_dir / name).exists() for name in secret_names) or (data_dir.exists() and any(data_dir.iterdir())):
        raise RuntimeError("CHILD provisioning collision; never reset existing evidence")
    odbc, pymysql = drivers()
    sql = odbc.connect(sql_options(administrative=True) + "Trusted_Connection=yes;", timeout=5, autocommit=True)
    maria = pymysql.connect(host="127.0.0.1", user="root", password="", port=3306, connect_timeout=5, autocommit=True)
    try:
        cur = sql.cursor()
        row = cur.execute("SELECT DB_ID(N'DRAGONHYDRACHILD_LAB'),SUSER_ID(N'dragonhydrachild_ingest'),SUSER_ID(N'dragonhydrachild_read'),IS_SRVROLEMEMBER('sysadmin')").fetchone()
        if tuple(row[:3]) != (None, None, None) or row[3] != 1:
            raise RuntimeError("Database/login collision or missing administrator role")
        m = maria.cursor()
        m.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (MARIA_DATABASE,))
        if m.fetchone():
            raise RuntimeError("CHILD operational database collision")
        m.execute("SELECT User,Host FROM mysql.user WHERE User IN ('dragonhydrachild_ops','dragonhydrachild_web')")
        if m.fetchone():
            raise RuntimeError("CHILD MariaDB identity collision")
        prepare_private_directory(secret_dir)
        prepare_private_directory(data_dir, sql_service=True)
        credentials = {}
        for engine, roles in (("sql", ("ingest", "read")), ("maria", ("ops", "web"))):
            for role in roles:
                item = {"username": f"dragonhydrachild_{role}", "password": "Aa9!" + secrets.token_urlsafe(36), "created_at": now(), "scope": "CHILD LOCAL ONLY"}
                credentials[engine, role] = item
                with (secret_dir / f"child-{engine}-{role}.local.json").open("xb") as stream:
                    stream.write(canonical(item) + b"\n")
        cur.execute(f"CREATE DATABASE [{SQL_DATABASE}] ON PRIMARY (NAME=N'{SQL_DATABASE}_data',FILENAME={literal(str(data_dir / (SQL_DATABASE + '.mdf')))},SIZE=16MB,MAXSIZE=256MB,FILEGROWTH=8MB) LOG ON (NAME=N'{SQL_DATABASE}_log',FILENAME={literal(str(data_dir / (SQL_DATABASE + '_log.ldf')))},SIZE=8MB,MAXSIZE=256MB,FILEGROWTH=8MB)")
        cur.execute(f"USE [{SQL_DATABASE}]")
        cur.execute("EXEC sys.sp_addextendedproperty @name=N'CHILD_OWNER',@value=N'DRAGONHYDRACHILD independent experiment'")
        cur.execute("CREATE SCHEMA child AUTHORIZATION dbo")
        for table in TABLES:
            cur.execute(f"""CREATE TABLE child.{table}(
                record_id char(32) NOT NULL PRIMARY KEY,
                natural_key nvarchar(240) NOT NULL,
                version int NOT NULL CHECK(version>0),
                supersedes_id char(32) NULL REFERENCES child.{table}(record_id),
                source_id nvarchar(80) NOT NULL,
                available_at datetimeoffset NOT NULL,
                created_at datetimeoffset NOT NULL,
                dedup_key char(64) NOT NULL UNIQUE,
                payload nvarchar(max) NOT NULL CHECK(ISJSON(payload)=1),
                CONSTRAINT UQ_child_{table}_version UNIQUE(natural_key,version),
                CONSTRAINT CK_child_{table}_clock CHECK(available_at<=created_at))""")
        for role in ("ingest", "read"):
            item = credentials["sql", role]
            user = item["username"]
            cur.execute(f"CREATE LOGIN [{user}] WITH PASSWORD={literal(item['password'])},CHECK_POLICY=ON,CHECK_EXPIRATION=OFF,DEFAULT_DATABASE=[{SQL_DATABASE}]")
            cur.execute(f"CREATE USER [{user}] FOR LOGIN [{user}] WITH DEFAULT_SCHEMA=child")
            cur.execute(f"GRANT CONNECT TO [{user}]")
            for table in TABLES:
                cur.execute(f"GRANT SELECT{',INSERT' if role == 'ingest' else ''} ON OBJECT::child.{table} TO [{user}]")
                cur.execute(f"DENY UPDATE,DELETE ON OBJECT::child.{table} TO [{user}]")
        m.execute(f"CREATE DATABASE {MARIA_DATABASE} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        m.execute(f"CREATE TABLE {MARIA_DATABASE}.presentation_cache(cache_key varchar(80) PRIMARY KEY,payload longtext NOT NULL CHECK(JSON_VALID(payload)),updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        m.execute(f"CREATE TABLE {MARIA_DATABASE}.job_state(job_id varchar(80) PRIMARY KEY,status varchar(32) NOT NULL,payload longtext NOT NULL CHECK(JSON_VALID(payload)))")
        for role in ("ops", "web"):
            item = credentials["maria", role]
            user = item["username"]
            m.execute(f"CREATE USER '{user}'@'localhost' IDENTIFIED BY %s", (item["password"],))
            for table in (("presentation_cache", "job_state") if role == "ops" else ("presentation_cache",)):
                rights = "SELECT,INSERT,UPDATE" if role == "ops" else "SELECT"
                m.execute(f"GRANT {rights} ON {MARIA_DATABASE}.{table} TO '{user}'@'localhost'")
    finally:
        sql.close()
        maria.close()
    evidence = live_probe()
    evidence.update({"python": platform.python_version(), "tables": list(TABLES), "sql_database": SQL_DATABASE, "maria_database": MARIA_DATABASE, "runtime_admin": False, "services_restarted": False, "donor_database_mutations": False, "certificate_exception": "Encrypt=yes; loopback-only TrustServerCertificate=yes"})
    checkpoint = PROJECT_ROOT / "runtime/checkpoints" / ("child-v0-storage-" + now().replace(":", "").replace("-", "").replace("+0000", "Z") + "-" + uuid4().hex[:8])
    checkpoint.mkdir(parents=True, exist_ok=False)
    with (checkpoint / "storage-proof.json").open("xb") as stream:
        stream.write(canonical(evidence) + b"\n")
    print(json.dumps({"passed": evidence["passed"], "checkpoint": str(checkpoint), "databases": [SQL_DATABASE, MARIA_DATABASE], "runtime_admin": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "FAILED", "error_type": type(error).__name__, "action": "Inspect CHILD partial state; no automatic reset; no credential-bearing traceback."}))
        raise SystemExit(1) from None
