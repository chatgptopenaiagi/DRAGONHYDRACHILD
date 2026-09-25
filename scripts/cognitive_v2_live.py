"""Explicit engineering comparison of pinned backends on an identical frozen input."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dragonhydra.cognitive_v2.artifacts import ArtifactStore
from dragonhydra.cognitive_v2.contracts import CognitiveStateSnapshot,canonical_bytes,content_hash
from dragonhydra.cognitive_v2.adapter import (QwenCognitiveEngine,CognitiveAnalysisRequest,CognitiveProjection,ProjectionFact,build_projection)
from dragonhydra.localai.runtime import LlamaRuntime,MODEL_PROFILES
from dragonhydra.localai.windows_process import sample_metrics

def gpu():
    try:
        p=subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5,check=True)
        v=[int(x.strip()) for x in p.stdout.strip().split(',')]
        return {'memory_used_mib':v[0],'utilization_percent':v[1]}
    except (OSError,ValueError,subprocess.SubprocessError):return {'status':'UNKNOWN'}

def main():
    if sys.version_info[:2]!=(3,14):raise SystemExit('Python 3.14 required')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',required=True,choices=tuple(MODEL_PROFILES))
    parser.add_argument('--snapshot',required=True)
    parser.add_argument('--arx-experiment',help='Optional immutable artifact hash, only structured delta is passed')
    args=parser.parse_args()
    store=ArtifactStore();snapshot=CognitiveStateSnapshot.from_dict(store.get('snapshots',args.snapshot))
    session='v2-live-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    runtime=LlamaRuntime(args.model,ROOT/'runtime/localai'/session)
    engine=QwenCognitiveEngine(runtime,ROOT/'runtime/localai'/session/'cognitive')
    results=[]
    try:
        runtime.start(timeout=180)
        before=sample_metrics(runtime.process.pid);gpu_before=gpu();start=time.monotonic()
        projection=build_projection(snapshot)
        request=CognitiveAnalysisRequest.create(projection,'TRIAGE_CHANGES',args.model,replay_mode=True)
        result=engine.analyze_request(request)
        elapsed=time.monotonic()-start;after=sample_metrics(runtime.process.pid);gpu_after=gpu()
        result_ref=store.put('actor_results',result.to_dict())
        comparison={'kind':'FROZEN_MODEL_COMPARISON','model_id':args.model,'model_identity':runtime.identity,
            'state_hash':snapshot.state_hash,'snapshot_ref':args.snapshot,'projection':projection.to_dict(),
            'projection_hash':projection.projection_hash,'request':request.to_dict(),'result_ref':result_ref,
            'result':result.to_dict(),'startup_seconds':runtime.startup_seconds,'elapsed_seconds':elapsed,
            'process_before':before,'process_after':after,'gpu_before':gpu_before,'gpu_after':gpu_after,
            'parameters':{'temperature':0,'seed':42,'max_tokens':512,'context_size':4096},
            'limitations':['NO_UNIVERSAL_WINNER','STRUCTURED_NON_EVIDENCE','FROZEN_REPLAY_NOT_ACTION_AUTHORITY']}
        ref=store.put('experiments',comparison);results.append({'comparison_ref':ref,'result_ref':result_ref,'result_status':result.result_status,'failure_state':result.failure_state})
        print(json.dumps(results[-1]),flush=True)
        if args.arx_experiment:
            experiment=store.get('experiments',args.arx_experiment)
            if experiment.get('kind')!='ARX_PROCESS_EXPERIMENT':raise ValueError('UNTRUSTED_CONTEXT')
            facts=[]
            for delta in ('structured_appearance_delta','structured_disappearance_delta'):
                for event in experiment[delta]['events']:
                    facts.extend((ProjectionFact(event['event_id'],'PROCESS','event_type',event['event_type']),
                        ProjectionFact(event['event_id'],'PROCESS','entity_id',event['entity_id'])))
            at=experiment['created_at']
            projection=CognitiveProjection(state_hash=content_hash({'appearance':experiment['structured_appearance_delta'],
                'disappearance':experiment['structured_disappearance_delta']}),as_of_at=at,temporal_mode='PRESENT',
                machine_expires_at=at,project_expires_at=at,facts=tuple(facts))
            request=CognitiveAnalysisRequest.create(projection,'TRIAGE_CHANGES',args.model,replay_mode=True)
            result=engine.analyze_request(request)
            result_ref=store.put('actor_results',result.to_dict())
            observed={fact.value for fact in facts if fact.key=='event_type'}
            claims=[c for c in result.conclusions if c.subject=='PROCESS']
            checked={'complete':result.result_status=='COMPLETE','both_changes_identified':observed <= {c.position for c in claims},
                'all_process_claims_supported':bool(claims) and all(c.position in observed and 'UNSUPPORTED_BY_PROJECTION' not in c.reason_codes for c in claims),
                'references_valid':all(set(c.evidence_refs)<=set(projection.references) for c in result.conclusions)}
            payload={'kind':'ARX_QWEN_INTERPRETATION','source_experiment_ref':args.arx_experiment,'projection':projection.to_dict(),
                'request':request.to_dict(),'result_ref':result_ref,'result':result.to_dict(),'checks':checked,
                'without_observation_baseline':'ABSTAIN_NO_MACHINE_FACTS','epistemic_state':'INTERPRETATION'}
            ref=store.put('experiments',payload);results.append({'arx_qwen_ref':ref,'checks':checked,'result_status':result.result_status,'failure_state':result.failure_state})
            print(json.dumps(results[-1]),flush=True)
    finally:runtime.stop()
    receipt={'kind':'LIVE_MODEL_SESSION','created_at':datetime.now(timezone.utc).isoformat(),'model_id':args.model,
        'snapshot_ref':args.snapshot,'session':session,'results':results,'backend_stopped':runtime.process is None or runtime.process.poll() is not None}
    ref=store.put('experiments',receipt)
    print(json.dumps({'session_receipt':ref,'backend_stopped':receipt['backend_stopped']}),flush=True)

if __name__=='__main__':main()
