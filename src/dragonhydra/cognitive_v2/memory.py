"""Five explicit memory layers in a bounded append-only hash chain.

The store never imports arbitrary files into memory or expires evidence by deletion.
Capacity stops writes; archival/rotation is an explicit engineering operation.
"""

from dataclasses import dataclass, replace
from contextlib import contextmanager
import json
from pathlib import Path
import re
from typing import ClassVar

from .contracts import (Contract, ContractError, LearningFeedback, canonical_bytes,
                        content_hash, utc_time)

KINDS = frozenset({"WORKING", "EPISODE", "DECISION", "LEARNING", "KNOWN_LIMITATION"})
MEMORY_ROOT = Path(__file__).resolve().parents[3] / "runtime" / "cognitive-v2"


def _confined_root(root):
    root = Path(root).absolute()
    boundary = MEMORY_ROOT.absolute()
    if root != boundary and boundary not in root.parents:
        raise ContractError("UNTRUSTED_CONTEXT")
    for path in (root, *root.parents):
        if path.exists() and (path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())):
            raise ContractError("UNTRUSTED_CONTEXT")
    if root.resolve() != root:
        raise ContractError("UNTRUSTED_CONTEXT")
    return root


@dataclass(frozen=True, kw_only=True)
class MemoryItem(Contract):
    memory_id: str
    kind: str
    created_at: str
    source_refs: tuple[str, ...]
    input_hashes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    epistemic_state: str
    confidence: str
    summary: str
    expires_at: str | None = None
    supersedes: str | None = None
    feedback_hash: str | None = None
    CHOICES: ClassVar[dict] = {"kind": KINDS}

    def __post_init__(self):
        super().__post_init__()
        if not self.source_refs or not self.input_hashes or not self.reason_codes:
            raise ContractError("MEMORY_REFERENCE_MISSING")
        if self.kind == "WORKING" and self.expires_at is None:
            raise ContractError()
        if self.kind == "LEARNING" and (self.feedback_hash is None or self.epistemic_state != "RECONCILIATION"):
            raise ContractError("MEMORY_REFERENCE_MISSING")


@dataclass(frozen=True, kw_only=True)
class WorkingMemory(MemoryItem):
    kind: str = "WORKING"
    CHOICES: ClassVar[dict] = {"kind": {"WORKING"}}


@dataclass(frozen=True, kw_only=True)
class EpisodeMemory(MemoryItem):
    kind: str = "EPISODE"
    CHOICES: ClassVar[dict] = {"kind": {"EPISODE"}}


@dataclass(frozen=True, kw_only=True)
class DecisionMemory(MemoryItem):
    kind: str = "DECISION"
    CHOICES: ClassVar[dict] = {"kind": {"DECISION"}}


@dataclass(frozen=True, kw_only=True)
class LearningMemory(MemoryItem):
    kind: str = "LEARNING"
    CHOICES: ClassVar[dict] = {"kind": {"LEARNING"}}


@dataclass(frozen=True, kw_only=True)
class KnownLimitationMemory(MemoryItem):
    kind: str = "KNOWN_LIMITATION"
    CHOICES: ClassVar[dict] = {"kind": {"KNOWN_LIMITATION"}}


def learning_memory(feedback, memory_id, confidence="UNKNOWN"):
    if not isinstance(feedback, LearningFeedback):
        raise ContractError()
    return LearningMemory(memory_id=memory_id, created_at=feedback.created_at,
                          source_refs=feedback.source_refs,
                          input_hashes=(feedback.expected_hash, feedback.observation_hash),
                          reason_codes=feedback.reason_codes or ("OBSERVED_DIFFERENCE",),
                          epistemic_state="RECONCILIATION", confidence=confidence,
                          summary=feedback.difference_summary, feedback_hash=feedback.digest())


class MemoryStore:
    def __init__(self, root, *, max_records=2048, max_bytes=16 * 1024 * 1024):
        if not 1 <= max_records <= 10000 or not 1024 <= max_bytes <= 64 * 1024 * 1024:
            raise ContractError()
        self.root = _confined_root(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_records = max_records
        self.max_bytes = max_bytes

    def records(self):
        for path in (self.root, *self.root.parents):
            if path.exists() and (path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())):
                raise ContractError("UNTRUSTED_CONTEXT")
        paths = sorted(self.root.glob("*.json"))
        if len(paths) > self.max_records or sum(path.stat().st_size for path in paths) > self.max_bytes:
            raise ContractError("REQUEST_TOO_LARGE")
        records, previous, ids = [], "0" * 64, set()
        for index, path in enumerate(paths):
            if not path.is_file() or path.is_symlink() or re.fullmatch(r"[0-9]{8}_[0-9a-f]{64}\.json", path.name) is None or path.stat().st_size > 32768:
                raise ContractError("UNTRUSTED_CONTEXT")
            try:
                def unique_pairs(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ContractError("UNTRUSTED_CONTEXT")
                        result[key] = value
                    return result
                record = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
            except (ValueError, UnicodeError, OSError) as exc:
                raise ContractError("UNTRUSTED_CONTEXT") from exc
            if type(record) is not dict or set(record) != {"sequence", "previous_hash", "item", "record_hash"}:
                raise ContractError()
            item = MemoryItem.from_dict(record["item"])
            payload = {key: record[key] for key in ("sequence", "previous_hash", "item")}
            digest = content_hash(payload)
            if record["sequence"] != index or record["previous_hash"] != previous or record["record_hash"] != digest or path.name != f"{index:08d}_{digest}.json" or item.memory_id in ids:
                raise ContractError("UNTRUSTED_CONTEXT")
            records.append(record)
            ids.add(item.memory_id)
            previous = digest
        return tuple(records)

    @contextmanager
    def _writer_lock(self):
        # Single writer across threads/processes. A crash leaves a fail-closed lock
        # for explicit engineering inspection, never an automatically stolen lease.
        path = self.root / ".memory-writer.lock"
        try:
            stream = path.open("xb")
        except FileExistsError as exc:
            raise ContractError("AUDIT_FAILURE") from exc
        try:
            with stream:
                stream.write(b"MEMORY_WRITER_ACTIVE")
                stream.flush()
                yield
        finally:
            path.unlink(missing_ok=True)

    def append(self, item, *, known_refs, feedback=None):
        # Recheck confinement before creating the owner-controlled lock artifact.
        for path in (self.root, *self.root.parents):
            if path.exists() and (path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())):
                raise ContractError("UNTRUSTED_CONTEXT")
        with self._writer_lock():
            return self._append(item, known_refs=known_refs, feedback=feedback)

    def _append(self, item, *, known_refs, feedback=None):
        if not isinstance(item, MemoryItem):
            raise ContractError()
        if not set(item.source_refs) <= set(known_refs):
            raise ContractError("MEMORY_REFERENCE_MISSING")
        records = self.records()
        if len(records) >= self.max_records:
            raise ContractError("REQUEST_TOO_LARGE")
        existing = {record["item"]["memory_id"]: record for record in records}
        if item.memory_id in existing:
            raise ContractError("UNTRUSTED_CONTEXT")
        if item.supersedes and (item.supersedes not in existing or existing[item.supersedes]["item"]["kind"] != item.kind):
            raise ContractError("MEMORY_REFERENCE_MISSING")
        if item.supersedes and utc_time(item.created_at) < utc_time(existing[item.supersedes]["item"]["created_at"]):
            raise ContractError("UNTRUSTED_CONTEXT")
        if item.kind == "LEARNING" and (not isinstance(feedback, LearningFeedback) or item.feedback_hash != feedback.digest() or set(item.source_refs) != set(feedback.source_refs)):
            raise ContractError("MEMORY_REFERENCE_MISSING")
        record = {"sequence": len(records), "previous_hash": records[-1]["record_hash"] if records else "0" * 64, "item": item.to_dict()}
        record["record_hash"] = content_hash(record)
        raw = canonical_bytes(record)
        if len(raw) > 32768 or sum(path.stat().st_size for path in self.root.glob("*.json")) + len(raw) > self.max_bytes:
            raise ContractError("REQUEST_TOO_LARGE")
        path = self.root / f"{len(records):08d}_{record['record_hash']}.json"
        # Exclusive create: no historical record can be overwritten.
        with path.open("xb") as stream:
            stream.write(raw)
        return record["record_hash"]

    def lookup(self, memory_id, *, now):
        items = [MemoryItem.from_dict(record["item"]) for record in self.records()]
        matches = [item for item in items if item.memory_id == memory_id]
        if not matches:
            raise ContractError("MEMORY_REFERENCE_MISSING")
        item = matches[0]
        if any(other.supersedes == memory_id for other in items) or (item.expires_at and utc_time(now) >= utc_time(item.expires_at)) or utc_time(now) < utc_time(item.created_at):
            raise ContractError("MEMORY_REFERENCE_MISSING")
        return item

    def active(self, now):
        result = []
        for record in self.records():
            try:
                result.append(self.lookup(record["item"]["memory_id"], now=now))
            except ContractError as exc:
                if exc.reason_code != "MEMORY_REFERENCE_MISSING":
                    raise
        return tuple(result)
