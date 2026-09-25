"""Reconcile explicit same-state actor artifacts; never select a truth winner."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dragonhydra.cognitive_v2.artifacts import ArtifactStore
from dragonhydra.cognitive_v2.contracts import (CognitiveStateSnapshot,CognitiveActorResult,CognitiveCycleReceipt,
    Conclusion,content_hash,snapshot_references)
from dragonhydra.cognitive_v2.reconciliation import reconcile

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',required=True)
    parser.add_argument('--qwen4',required=True)
    parser.add_argument('--qwen30',required=True)
    parser.add_argument('--codex',required=True)
    args=parser.parse_args()
    store=ArtifactStore();at=datetime.now(timezone.utc).isoformat()
    state=CognitiveStateSnapshot.from_dict(store.get('snapshots',args.snapshot))
    values=[CognitiveActorResult.from_dict(store.get('actor_results',ref)) for ref in (args.qwen4,args.qwen30,args.codex)]
    if [v.actor_id for v in values]!=['QWEN_4B','QWEN_30B','CODEX'] or any(v.state_hash!=state.state_hash or v.task_kind!='TRIAGE_CHANGES' for v in values):
        raise ValueError('UNTRUSTED_CONTEXT')
    baseline=CognitiveActorResult(actor_id='SYSTEM',state_hash=state.state_hash,task_kind='TRIAGE_CHANGES',created_at=at,
        result_status='ABSTAINED',conclusions=(Conclusion(claim_id='baseline.no-delta',subject='MACHINE_HEALTH',position='ABSTAIN',
            summary='A single snapshot does not establish a temporal change.',evidence_refs=(state.machine_state.machine_snapshot_hash,),
            reason_codes=('NO_COMPARISON_SNAPSHOT',)),),references=(state.state_hash,),reason_codes=('DETERMINISTIC_BASELINE','NO_MODEL_EXECUTION'))
    baseline_ref=store.put('actor_results',baseline.to_dict())
    comparisons=[reconcile(state,values[0],values[1],at),reconcile(state,values[0],values[2],at),reconcile(state,values[1],values[2],at)]
    refs=[store.put('reconciliations',v.to_dict()) for v in comparisons]
    known=snapshot_references(state)
    metrics=[{'actor_id':v.actor_id,'latency_ms':v.latency_ms,'conclusions':len(v.conclusions),
        'reference_checks_passed':sum(bool(c.evidence_refs) and set(c.evidence_refs)<=known for c in v.conclusions),
        'claims_without_valid_references':sum(not c.evidence_refs or not set(c.evidence_refs)<=known for c in v.conclusions),
        'abstentions':sum(c.position=='ABSTAIN' for c in v.conclusions),
        'uncertainty_refs':len(v.uncertainties),'hypotheses':len(v.hypotheses),'research_needs':len(v.research_needs)} for v in [baseline,*values]]
    receipt=CognitiveCycleReceipt(cycle_id='cycle.comparison.'+content_hash(refs)[:24],created_at=at,as_of_at=state.as_of_at,
        state_hash=state.state_hash,snapshot_hash=args.snapshot,machine_snapshot_hash=state.machine_state.machine_snapshot_hash,
        routing_hash=content_hash({'mode':'EXPLICIT_ENGINEERING_COMPARISON','models':['qwen3-4b','qwen3-coder-30b']}),
        actor_result_hashes=(baseline_ref,args.qwen4,args.qwen30,args.codex),result_status='COMPLETE',input_hash=content_hash(args.snapshot),
        output_hash=content_hash(refs),reconciliation_hash=refs[-1],reason_codes=('FROZEN_REPLAY','NO_ACTION_EXECUTED','NO_TRUTH_WINNER'))
    cycle_ref=store.put('receipts',receipt.to_dict())
    summary={'kind':'DUAL_QWEN_CODEX_COMPARISON','created_at':at,'snapshot_ref':args.snapshot,'state_hash':state.state_hash,
        'actor_refs':[baseline_ref,args.qwen4,args.qwen30,args.codex],'reconciliation_refs':refs,'cycle_ref':cycle_ref,'metrics':metrics,
        'reconciliation_statuses':[v.status for v in comparisons],
        'limitations':['REFERENCE_EXISTENCE_IS_NOT_CLAIM_TRUTH','CODEX_FULL_STATE_AND_PROJECTION_QWEN_BOUNDED_PROJECTION',
            'LATENCY_NOT_COMPARABLE_TO_CODEX_INTERACTIVE_REVIEW','NO_UNIVERSAL_WINNER','NO_PREDICTIVE_ACCURACY_MEASUREMENT']}
    ref=store.put('experiments',summary)
    print(json.dumps(dict(summary,artifact_ref=ref),indent=2))

if __name__=='__main__':main()
