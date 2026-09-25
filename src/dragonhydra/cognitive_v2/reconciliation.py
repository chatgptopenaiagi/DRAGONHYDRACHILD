"""Compare explicit positions on the same frozen state without inventing a winner."""

from .contracts import (CognitiveReconciliation, ContractError, PositionComparison,
                        content_hash, snapshot_references)


def reconcile(snapshot, left, right, created_at, reconciliation_id=None):
    if left.state_hash != snapshot.state_hash or right.state_hash != snapshot.state_hash:
        raise ContractError("STATE_CHANGED_SINCE_PROPOSAL")
    refs = snapshot_references(snapshot)
    unsupported, missing, assumptions, confidence = [], [], [], []
    agreements, disagreements = [], []
    for result in (left, right):
        for claim in result.conclusions:
            unknown = sorted(set(claim.evidence_refs) - refs)
            if not claim.evidence_refs or unknown or "UNSUPPORTED_BY_PROJECTION" in claim.reason_codes:
                unsupported.append(result.actor_id + ":" + claim.claim_id)
                missing.extend(unknown or [claim.subject])
    comparable = left.actor_id != right.actor_id and left.task_kind == right.task_kind
    if comparable:
        for a in left.conclusions:
            for b in right.conclusions:
                if a.subject != b.subject:
                    continue
                matches = a.position == b.position
                item = PositionComparison(subject=a.subject, left_actor=left.actor_id,
                                          right_actor=right.actor_id, left_claim=a,
                                          right_claim=b, status="AGREEMENT" if matches else "DISAGREEMENT",
                                          reason_codes=("EXPLICIT_POSITION_COMPARISON", "NO_TRUTH_VERDICT"))
                (agreements if matches else disagreements).append(item)
                if set(a.assumptions) != set(b.assumptions):
                    assumptions.append(a.subject)
                if a.confidence != b.confidence:
                    confidence.append(a.subject)
    if not comparable:
        status = "NOT_COMPARABLE"
    elif unsupported or not (agreements or disagreements) or any(r.result_status != "COMPLETE" for r in (left, right)):
        status = "INSUFFICIENT_EVIDENCE"
    elif agreements and disagreements:
        status = "PARTIAL_AGREEMENT"
    elif disagreements:
        status = "DISAGREEMENT"
    else:
        status = "AGREEMENT"
    key = content_hash([snapshot.state_hash, left.digest(), right.digest()])
    measurements = sorted(set(item.subject for item in disagreements) | set(missing))
    return CognitiveReconciliation(
        reconciliation_id=reconciliation_id or "reconcile-" + key[:24], created_at=created_at,
        state_hash=snapshot.state_hash, left_result_hash=left.digest(), right_result_hash=right.digest(),
        status=status, agreements=tuple(agreements), disagreements=tuple(disagreements),
        unsupported_claims=tuple(sorted(set(unsupported))), different_assumptions=tuple(sorted(set(assumptions))),
        missing_evidence=tuple(sorted(set(missing))), confidence_conflicts=tuple(sorted(set(confidence))),
        recommended_measurement=tuple(measurements),
        research_needs=tuple(sorted({n.need_id: n for n in (*left.research_needs, *right.research_needs)}.values(), key=lambda n: n.need_id)),
        reason_codes=("CLAIMS_PRESERVED", "WORLD_VALIDATION_REQUIRED"))
