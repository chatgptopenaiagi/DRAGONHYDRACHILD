"""Allowlisted proposal review. There is deliberately no action executor."""

from .contracts import (ACTION_CLASSES, ANALYSIS_CLASSES, ActionDecision, CapabilityDescriptor,
                        CapabilityState, ContractError, ensure_fresh, utc_time)


DISABLED_MUTATIONS = frozenset({"RUN_ARBITRARY_COMMAND", "DELETE_FILE", "EDIT_REGISTRY",
                               "KILL_PROCESS", "INSTALL_SOFTWARE", "CHANGE_SERVICE",
                               "ALTER_FIREWALL", "PRIVILEGED_SQL"})


def default_capabilities(actor=None):
    actors = (actor,) if actor is not None else ("CODEX", "QWEN_4B", "QWEN_30B")
    result = []
    for identity in actors:
        prefix = "" if identity == "CODEX" else identity.lower() + "."
        for action in sorted(ACTION_CLASSES | ANALYSIS_CLASSES | DISABLED_MUTATIONS):
            result.append(CapabilityDescriptor(
                capability_id=prefix + action.lower(), actor=identity, action_class=action,
                enabled=action not in DISABLED_MUTATIONS,
                risk_class="HIGH" if action in DISABLED_MUTATIONS else "LOW",
                requires_human=action == "REQUEST_HUMAN_REVIEW" or action in DISABLED_MUTATIONS,
                requires_hydra=action == "REQUEST_HYDRA_RESEARCH",
                requires_medusa=action == "REQUEST_HYDRA_RESEARCH",
                reason_codes=("DISABLED_MACHINE_MUTATION",) if action in DISABLED_MUTATIONS else
                             (("BOUNDED_ANALYSIS",) if action in ANALYSIS_CLASSES else ("PROPOSAL_ONLY",))))
    return CapabilityState(capabilities=tuple(result))


def evaluate_proposal(proposal, snapshot, now, *, recent_count=0):
    """An accepted proposal is never permission for arbitrary machine execution."""
    def decision(status, *codes):
        return ActionDecision(proposal_id=proposal.proposal_id, created_at=now,
                              state_hash=snapshot.state_hash, status=status,
                              reason_codes=codes)
    if proposal.state_hash != snapshot.state_hash:
        return decision("DENIED", "STATE_CHANGED_SINCE_PROPOSAL")
    if utc_time(now) < utc_time(proposal.created_at) or utc_time(now) >= utc_time(proposal.expires_at):
        return decision("DENIED", "COGNITIVE_STATE_STALE")
    registry = {item.capability_id: item for item in snapshot.capabilities.capabilities}
    capability = registry.get(proposal.capability_id)
    if capability is None or not capability.enabled or capability.action_class != proposal.action_class or capability.actor != proposal.actor_id:
        return decision("DENIED", "CAPABILITY_DENIED")
    if type(recent_count) is not int or recent_count < 0 or recent_count >= capability.max_frequency:
        return decision("DENIED", "CAPABILITY_DENIED", "FREQUENCY_LIMIT")
    if capability.requires_fresh_state:
        try:
            ensure_fresh(snapshot, now)
        except ContractError as exc:
            return decision("DENIED", exc.reason_code)
    allowed_hashes = {snapshot.state_hash, snapshot.machine_state.machine_snapshot_hash}
    if any(value not in allowed_hashes for value in proposal.precondition_hashes):
        return decision("DENIED", "STATE_CHANGED_SINCE_PROPOSAL")
    if capability.requires_hydra or capability.requires_medusa:
        return decision("REQUIRES_REVIEW", "HYDRA_REQUIRED", "MEDUSA_REQUIRED", "PROPOSAL_ONLY")
    if capability.requires_human:
        return decision("REQUIRES_REVIEW", "HUMAN_REQUIRED", "PROPOSAL_ONLY")
    return decision("PROPOSAL_ACCEPTED", "PROPOSAL_ONLY", "NO_EXECUTION_AUTHORITY")
