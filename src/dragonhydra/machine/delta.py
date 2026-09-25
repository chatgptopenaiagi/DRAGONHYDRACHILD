"""Deterministic change detection. Failed probes never imply vanished entities."""
from .contracts import MachineDelta, MachineEvent, digest, timestamp


def compare_machine(before, after, *, gpu_threshold_mib=256, ram_threshold_bytes=1073741824):
    if type(gpu_threshold_mib) is not int or not 1 <= gpu_threshold_mib <= 65536:
        raise ValueError("INVALID_THRESHOLD")
    if type(ram_threshold_bytes) is not int or ram_threshold_bytes < 1:
        raise ValueError("INVALID_THRESHOLD")
    if timestamp(after.as_of_at) < timestamp(before.as_of_at): raise ValueError("INVALID_CLOCK_ORDER")
    old = {x.entity_id: x for x in before.observations}
    new = {x.entity_id: x for x in after.observations}
    old_probes = {x.probe_id: x for x in before.receipts}
    new_probes = {x.probe_id: x for x in after.receipts}
    events = []
    reasons = []

    def emit(entity_id, probe, code, previous=None, current=None, severity="INFO"):
        previous_hash = previous.state_hash if previous else None
        current_hash = current.state_hash if current else None
        identity = {"before": before.state_hash, "after": after.state_hash, "entity": entity_id,
                    "code": code, "previous": previous_hash, "current": current_hash}
        freshness = "FRESH" if current is not None and current.is_fresh(after.as_of_at) else "FRESH" if current is None and previous is not None else "UNKNOWN"
        events.append(MachineEvent("event."+digest(identity)[:32], code, after.as_of_at, probe, entity_id,
                                  previous_hash, current_hash, severity, freshness, (code,),
                                  (before.snapshot_id, after.snapshot_id)))

    for probe in sorted(set(old_probes) | set(new_probes)):
        a, b = old_probes.get(probe), new_probes.get(probe)
        if b is None or b.status != "OK":
            reasons.append("MACHINE_PROBE_FAILED")
            if a is not None and a.status == "OK": emit("probe."+probe, probe, "MACHINE_PROBE_FAILED", severity="WARNING")
        elif a is not None and a.status != "OK":
            emit("probe."+probe, probe, "MACHINE_PROBE_RECOVERED")

    for entity in sorted(set(old) | set(new)):
        a, b = old.get(entity), new.get(entity)
        item = b or a
        # Both domains must be observed successfully before appearance/disappearance claims.
        if not all(probes.get(item.probe_id) and probes[item.probe_id].status == "OK" for probes in (old_probes, new_probes)):
            continue
        if a is None or b is None:
            opening = a is None
            if item.kind == "process":
                runtime = item.data.get("name") in {"llama-server.exe", "ollama.exe", "ollama_llama_server.exe"}
                code = ("MODEL_RUNTIME_" if runtime else "PROCESS_") + ("STARTED" if opening else "STOPPED")
            elif item.kind == "listener": code = "NEW_LOCAL_LISTENER" if opening else "LOCAL_LISTENER_CLOSED"
            else: code = "COMPONENT_APPEARED" if opening else "COMPONENT_DISAPPEARED"
            emit(entity, item.probe_id, code, a, b)
            continue
        if a.state_hash == b.state_hash: continue
        av, bv = a.data, b.data
        if item.kind == "process":
            if av.get("start_time") != bv.get("start_time"):
                runtime = bv.get("name") in {"llama-server.exe", "ollama.exe", "ollama_llama_server.exe"}
                prefix = "MODEL_RUNTIME_" if runtime else "PROCESS_"
                emit(entity, item.probe_id, prefix+"STOPPED", a, None)
                emit(entity, item.probe_id, prefix+"STARTED", None, b)
            elif av.get("model_id") != bv.get("model_id"):
                emit(entity, item.probe_id, "QWEN_MODEL_CHANGED", a, b)
            elif av != bv: emit(entity, item.probe_id, "RUNTIME_CHANGED", a, b)
        elif item.kind == "gpu":
            used_a, used_b = av.get("memory_used_mib"), bv.get("memory_used_mib")
            if type(used_a) in (int, float) and type(used_b) in (int, float) and abs(used_b-used_a) >= gpu_threshold_mib:
                emit(entity, item.probe_id, "GPU_MEMORY_INCREASED" if used_b > used_a else "GPU_MEMORY_DECREASED", a, b)
            if any(av.get(k) != bv.get(k) for k in ("name", "driver", "health", "cuda_version")):
                emit(entity, item.probe_id, "GPU_HEALTH_CHANGED", a, b, "WARNING")
        elif item.kind == "cpu":
            # Load oscillation is retained in observations, not emitted as event noise.
            if any(av.get(k) != bv.get(k) for k in ("name", "cores", "logical_processors")):
                emit(entity, item.probe_id, "CPU_CONFIGURATION_CHANGED", a, b)
        elif item.kind == "ram":
            if abs((bv.get("available_bytes") or 0)-(av.get("available_bytes") or 0)) >= ram_threshold_bytes:
                emit(entity, item.probe_id, "RAM_AVAILABILITY_CHANGED", a, b)
        elif item.kind == "repository":
            if av.get("branch") != bv.get("branch"): emit(entity, item.probe_id, "GIT_BRANCH_CHANGED", a, b)
            if av.get("head") != bv.get("head"): emit(entity, item.probe_id, "GIT_HEAD_CHANGED", a, b)
            if any(av.get(k) != bv.get(k) for k in ("dirty", "staged_count", "unstaged_count", "untracked_count")):
                emit(entity, item.probe_id, "REPOSITORY_DIRTY" if bv.get("dirty") else "REPOSITORY_CLEAN", a, b)
        elif item.kind == "service":
            emit(entity, item.probe_id, "SERVICE_STATE_CHANGED", a, b)
            if bv.get("state") != "Running" and bv.get("name", "").lower().startswith(("mssql", "mysql", "mariadb")):
                emit(entity, item.probe_id, "DATABASE_UNAVAILABLE", a, b, "WARNING")
            if bv.get("name", "").lower().startswith("apache"): emit(entity, item.probe_id, "XAMPP_STATE_CHANGED", a, b)
        elif item.kind == "task": emit(entity, item.probe_id, "SCHEDULED_TASK_CHANGED", a, b)
        elif item.kind == "tool": emit(entity, item.probe_id, "RUNTIME_CHANGED", a, b)
        else: emit(entity, item.probe_id, "COMPONENT_STATE_CHANGED", a, b)
    return MachineDelta(before.state_hash, after.state_hash, after.as_of_at,
                        tuple(sorted(events, key=lambda x: (x.entity_id, x.event_type, x.event_id))), tuple(sorted(set(reasons))))
