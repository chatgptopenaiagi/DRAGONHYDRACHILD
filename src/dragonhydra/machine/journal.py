"""Bounded hash-chained journal. Rotation preserves segments; quota exhaustion closes writes."""
import os
from pathlib import Path
import stat

from .contracts import MachineContractError, MachineEvent, canonical, digest
import json

_RUNTIME_ROOT = Path(__file__).resolve().parents[3] / "runtime" / "cognitive-v2"


def _validate_root(root):
    path = Path(root).absolute()
    expected = _RUNTIME_ROOT.absolute()
    if not path.is_relative_to(expected): raise MachineContractError("JOURNAL_PATH_DENIED")
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink() or (hasattr(ancestor, "is_junction") and ancestor.is_junction()):
            raise MachineContractError("JOURNAL_PATH_DENIED")
        try:
            if getattr(ancestor.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise MachineContractError("JOURNAL_PATH_DENIED")
        except FileNotFoundError: pass
    if not path.resolve().is_relative_to(expected.resolve()): raise MachineContractError("JOURNAL_PATH_DENIED")
    return path


class EventJournal:
    def __init__(self, root, *, max_segment_bytes=65536, max_segments=16, max_events=2048):
        self.root = _validate_root(root)
        if type(max_segment_bytes) is not int or not 1024 <= max_segment_bytes <= 1048576 or type(max_segments) is not int or not 1 <= max_segments <= 128 or type(max_events) is not int or not 1 <= max_events <= 16384:
            raise MachineContractError("INVALID_JOURNAL_LIMIT")
        self.root.mkdir(parents=True, exist_ok=True)
        _validate_root(self.root)
        self.max_segment_bytes, self.max_segments, self.max_events = max_segment_bytes, max_segments, max_events

    def _records(self):
        _validate_root(self.root)
        paths = sorted(self.root.glob("events-????.jsonl"))
        if len(paths) > self.max_segments: raise MachineContractError("JOURNAL_QUOTA_EXCEEDED")
        records = []
        previous = "0"*64
        seen = set()
        for index, path in enumerate(paths):
            if path.name != f"events-{index:04}.jsonl" or path.is_symlink() or path.stat().st_size > self.max_segment_bytes:
                raise MachineContractError("INVALID_JOURNAL")
            raw = path.read_bytes()
            if raw and not raw.endswith(b"\n"): raise MachineContractError("INVALID_JOURNAL")
            for line in raw.splitlines():
                try:
                    record = json.loads(line)
                    if set(record) != {"sequence", "previous_hash", "event", "record_hash"}: raise ValueError()
                    event = MachineEvent.from_dict(record["event"])
                    body = {key: value for key, value in record.items() if key != "record_hash"}
                    if record["sequence"] != len(records) or record["previous_hash"] != previous or record["record_hash"] != digest(body) or event.event_id in seen:
                        raise ValueError()
                    seen.add(event.event_id); records.append(record); previous = record["record_hash"]
                    if len(records) > self.max_events: raise MachineContractError("JOURNAL_QUOTA_EXCEEDED")
                except (ValueError, TypeError, KeyError) as exc:
                    raise MachineContractError("INVALID_JOURNAL") from exc
        return records

    def read(self):
        return tuple(MachineEvent.from_dict(x["event"]) for x in self._records())

    def append(self, event):
        if not isinstance(event, MachineEvent): raise MachineContractError("INVALID_EVENT")
        _validate_root(self.root)
        lock = self.root / ".writer.lock"
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc: raise MachineContractError("JOURNAL_BUSY") from exc
        try:
            os.close(descriptor)
            records = self._records()
            for item in records:
                if item["event"]["event_id"] == event.event_id:
                    if item["event"] != event.to_dict(): raise MachineContractError("EVENT_ID_CONFLICT")
                    return item["record_hash"]
            if len(records) >= self.max_events: raise MachineContractError("JOURNAL_QUOTA_EXCEEDED")
            body = {"sequence": len(records), "previous_hash": records[-1]["record_hash"] if records else "0"*64, "event": event.to_dict()}
            record_hash = digest(body)
            encoded = canonical({**body, "record_hash": record_hash})+b"\n"
            if len(encoded) > self.max_segment_bytes: raise MachineContractError("EVENT_TOO_LARGE")
            paths = sorted(self.root.glob("events-????.jsonl"))
            index = max(len(paths)-1, 0)
            if paths and paths[-1].stat().st_size+len(encoded) > self.max_segment_bytes: index += 1
            if index >= self.max_segments: raise MachineContractError("JOURNAL_QUOTA_EXCEEDED")
            destination = self.root / f"events-{index:04}.jsonl"
            if destination.is_symlink(): raise MachineContractError("JOURNAL_PATH_DENIED")
            with destination.open("ab") as stream:
                stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
            return record_hash
        finally:
            lock.unlink()
