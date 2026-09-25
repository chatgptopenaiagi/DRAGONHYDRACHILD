"""Fixed engineering-owned read-only probes, not a model-accessible shell API."""
import csv
from dataclasses import replace
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

from .contracts import (MachineContractError, MachineObservation, MachineProbeReceipt,
                        MachineSnapshot, canonical, digest, utc_now)

_ROOT = Path(__file__).resolve().parents[3]
_MAX_BYTES = 262144
_DOMAINS = ("os", "cpu", "ram", "process", "service", "listener", "tool", "task", "conda_environment")


def _run(argv, *, timeout=15, max_bytes=_MAX_BYTES, encoding="utf-8"):
    """Bound both output streams during reading; never evaluate command strings."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, creationflags=flags,
                               env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "GIT_OPTIONAL_LOCKS": "0"})
    output = [bytearray(), bytearray()]
    exceeded = threading.Event()
    def read(stream, destination):
        while True:
            data = stream.read(4096)
            if not data: break
            if len(destination) + len(data) > max_bytes:
                exceeded.set(); process.kill(); break
            destination.extend(data)
    threads = [threading.Thread(target=read, args=(pipe, output[index]), daemon=True)
               for index, pipe in enumerate((process.stdout, process.stderr))]
    for thread in threads: thread.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill(); process.wait(timeout=3)
        raise MachineContractError("PROBE_TIMEOUT") from exc
    finally:
        for thread in threads: thread.join(timeout=3)
        process.stdout.close(); process.stderr.close()
    if exceeded.is_set(): raise MachineContractError("PROBE_OUTPUT_TOO_LARGE")
    if process.returncode: raise MachineContractError("MACHINE_PROBE_FAILED")
    try: return bytes(output[0]).decode(encoding).rstrip().lstrip("\ufeff")
    except UnicodeError as exc: raise MachineContractError("INVALID_PROBE_ENCODING") from exc


def _observation(kind, entity_id, attributes, at, *, probe_id=None, status="OK", reasons=()):
    return MachineObservation(probe_id or kind, entity_id, kind, at, at, at, at,
                              120, 2, status, tuple(attributes.items()), tuple(reasons))


def _receipt(probe_id, at, observations, status="OK", failure=None, elapsed=0):
    members = sorted((x.to_dict() for x in observations if x.probe_id == probe_id), key=lambda x: x["entity_id"])
    return MachineProbeReceipt(probe_id, at, at, status, len(members), elapsed, failure, digest(members))


def parse_windows_probe(raw, at):
    """Strict revalidation prevents arbitrary command output becoming AI context."""
    if type(raw) is not str or len(raw.encode("utf-8")) > _MAX_BYTES:
        raise MachineContractError("PROBE_OUTPUT_TOO_LARGE")
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result: raise MachineContractError("INVALID_PROBE_SCHEMA")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(MachineContractError("INVALID_PROBE_SCHEMA")))
        if type(value) is not dict or set(value) != {"schema_version", "rows", "domains"} or value["schema_version"] != "2":
            raise MachineContractError("INVALID_PROBE_SCHEMA")
        if type(value["rows"]) is not list or len(value["rows"]) > 768 or type(value["domains"]) is not list or len(value["domains"]) != len(_DOMAINS):
            raise MachineContractError("INVALID_PROBE_SCHEMA")
        domains = {}
        for domain in value["domains"]:
            if type(domain) is not dict or set(domain) != {"probe_id", "status", "failure_state"}:
                raise MachineContractError("INVALID_PROBE_SCHEMA")
            if domain["probe_id"] not in _DOMAINS or domain["probe_id"] in domains or domain["status"] not in {"OK", "FAILED"}:
                raise MachineContractError("INVALID_PROBE_SCHEMA")
            if (domain["status"] == "OK") != (domain["failure_state"] is None):
                raise MachineContractError("INVALID_PROBE_SCHEMA")
            domains[domain["probe_id"]] = domain
        observations = []
        for row in value["rows"]:
            if type(row) is not dict or set(row) != {"kind", "entity_id", "attributes"} or row["kind"] not in domains:
                raise MachineContractError("INVALID_PROBE_SCHEMA")
            if domains[row["kind"]]["status"] != "OK" or type(row["attributes"]) is not dict:
                raise MachineContractError("INVALID_PROBE_SCHEMA")
            observations.append(_observation(row["kind"], row["entity_id"], row["attributes"], at))
        receipts = [_receipt(key, at, observations, domain["status"], domain["failure_state"]) for key, domain in domains.items()]
        return observations, receipts
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise MachineContractError("INVALID_PROBE_SCHEMA") from exc


def _gpu(at):
    binary = shutil.which("nvidia-smi")
    if not binary: raise FileNotFoundError("GPU_PROBE_UNAVAILABLE")
    raw = _run([binary, "--query-gpu=index,name,driver_version,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"], max_bytes=8192)
    rows = []
    for cells in csv.reader(io.StringIO(raw)):
        if len(cells) != 6 or len(rows) >= 8: raise MachineContractError("INVALID_PROBE_SCHEMA")
        index, name, driver, total, used, utilization = [x.strip() for x in cells]
        if not index.isdigit(): raise MachineContractError("INVALID_PROBE_SCHEMA")
        rows.append(_observation("gpu", "gpu."+index, {"name": name, "driver": driver,
                    "memory_total_mib": int(total), "memory_used_mib": int(used),
                    "utilization_percent": int(utilization), "cuda_version": None, "health": "AVAILABLE"}, at))
    if not rows: raise MachineContractError("EMPTY_GPU_PROBE")
    # This reports driver-visible CUDA, not a claim that a toolkit is installed.
    try:
        summary = _run([binary], max_bytes=16384)
        match = re.search(r"CUDA Version:\s*([0-9]+\.[0-9]+)", summary)
        cuda = match.group(1) if match else None
        rows = [_observation("gpu", x.entity_id, {**x.data, "cuda_version": cuda}, at) for x in rows]
    except (OSError, MachineContractError): pass
    return rows


def _repositories(at):
    binary = shutil.which("git")
    if not binary: raise FileNotFoundError("GIT_UNAVAILABLE")
    result = []
    for label, path in (("child", _ROOT), ("parent", _ROOT.parent / "DRAGONHYDRA")):
        if not path.is_dir(): raise MachineContractError("REPOSITORY_UNAVAILABLE")
        base = [binary, "--no-optional-locks", "-C", str(path)]
        head = _run(base+["rev-parse", "HEAD"], max_bytes=256)
        branch = _run(base+["branch", "--show-current"], max_bytes=256) or "DETACHED"
        if not re.fullmatch("[0-9a-f]{40,64}", head) or not re.fullmatch(r"[A-Za-z0-9_./-]{1,128}", branch):
            raise MachineContractError("INVALID_REPOSITORY_STATE")
        raw = _run(base+["status", "--porcelain=v1", "--untracked-files=normal"], max_bytes=65536)
        statuses = [line[:2] for line in raw.splitlines() if line]
        result.append(_observation("repository", "repository."+label, {"name": label, "head": head, "branch": branch,
            "dirty": bool(statuses), "staged_count": sum(x[0] not in (" ", "?") for x in statuses),
            "unstaged_count": sum(x[1] not in (" ", "?") for x in statuses), "untracked_count": sum(x == "??" for x in statuses)}, at))
    return result


def _wsl(at):
    binary = shutil.which("wsl")
    if not binary: raise FileNotFoundError("WSL_UNAVAILABLE")
    raw = _run([binary, "--list", "--verbose"], timeout=8, max_bytes=8192, encoding="utf-16-le")
    result = []
    for line in raw.splitlines()[1:]:
        match = re.fullmatch(r"\s*\*?\s*([A-Za-z0-9_.-]{1,64})\s+(Running|Stopped|Installing)\s+([12])\s*", line)
        if match:
            name, state, version = match.groups()
            result.append(_observation("distribution", "wsl."+name, {"name": name, "state": state, "version": int(version)}, at))
        elif line.strip(): raise MachineContractError("WSL_STATE_UNKNOWN")
    return result


def capture_machine(*, observed_at=None, owned_test_pid=None):
    """Capture fixed levels 0–2. A test PID adds metadata for one owned process only."""
    if owned_test_pid is not None and (type(owned_test_pid) is not int or not 1 <= owned_test_pid <= 2147483647):
        raise MachineContractError("CAPABILITY_DENIED")
    at = observed_at or utc_now()
    observations, receipts = [], []
    if os.name == "nt":
        try:
            binary = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
            if not binary: raise FileNotFoundError()
            raw = _run([binary, "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                        str(Path(__file__).with_name("probe_windows.ps1")), "-OwnedTestPid", str(owned_test_pid or 0)], timeout=30)
            observations, receipts = parse_windows_probe(raw, at)
        except (OSError, MachineContractError):
            receipts = [_receipt(domain, at, [], "FAILED", "MACHINE_PROBE_FAILED") for domain in _DOMAINS]
    else:
        receipts = [_receipt(domain, at, [], "UNAVAILABLE", "WINDOWS_PROBE_UNAVAILABLE") for domain in _DOMAINS]
    for probe_id, operation in (("gpu", _gpu), ("repository", _repositories), ("distribution", _wsl)):
        started = time.monotonic()
        try:
            rows = operation(at)
            observations.extend(rows)
            receipts.append(_receipt(probe_id, at, rows, elapsed=int((time.monotonic()-started)*1000)))
        except FileNotFoundError:
            receipts.append(_receipt(probe_id, at, [], "UNAVAILABLE", "OPTIONAL_COMPONENT_UNAVAILABLE", int((time.monotonic()-started)*1000)))
        except (OSError, MachineContractError, ValueError):
            receipts.append(_receipt(probe_id, at, [], "FAILED", "MACHINE_PROBE_FAILED", int((time.monotonic()-started)*1000)))
    completed = utc_now()
    observations = [replace(x, available_at=completed, created_at=completed, as_of_at=completed) for x in observations]
    receipts = [replace(x, available_at=completed,
                        output_hash=digest(sorted([o.to_dict() for o in observations if o.probe_id == x.probe_id], key=lambda o: o["entity_id"]))) for x in receipts]
    return MachineSnapshot("machine."+digest({"at": at, "observations": [x.state_hash for x in observations]})[:32], completed, completed, observations, receipts)
