"""Explicit analysis cycles and a read-only status projection; no action executor."""
from datetime import datetime, timezone
from pathlib import Path

from .artifacts import ArtifactStore, PROJECT_RUNTIME, export_codex_request, load_codex_result
from .contracts import (CognitiveActorResult, CognitiveCycleReceipt, ContractError,
    CognitiveReconciliation, FAILURE_STATES, MemoryState, canonical_bytes, content_hash,
    ensure_fresh, snapshot_references, utc_time)
from .adapter import ACTORS, build_projection
from .memory import MemoryStore, EpisodeMemory
from .router import ModelRouter, RoutingInput
from .reconciliation import reconcile
from ..localai.runtime import MODEL_PROFILES, RUNTIME_ID, SERVER_HASH

def now(): return datetime.now(timezone.utc).isoformat()

def memory_state(store, at):
    items=store.active(at)
    groups={kind:tuple(i.memory_id for i in items if i.kind==kind) for kind in
        ('WORKING','EPISODE','DECISION','LEARNING','KNOWN_LIMITATION')}
    return MemoryState(memory_refs=tuple(i.memory_id for i in items),working_refs=groups['WORKING'],
        episode_refs=groups['EPISODE'],decision_refs=groups['DECISION'],learning_refs=groups['LEARNING'],
        limitation_refs=groups['KNOWN_LIMITATION'])

def route_snapshot(snapshot,task_kind,*,available_models):
    projection=build_projection(snapshot)
    values={metric.name:metric.value for c in snapshot.machine_state.components for metric in c.metrics}
    ram=values.get('available_bytes')
    vram=values.get('memory_total_mib')
    used=values.get('memory_used_mib')
    return ModelRouter().route(RoutingInput(task_kind=task_kind,context_bytes=len(canonical_bytes(projection.to_dict())),
        available_ram_mb=int(ram/(1024*1024)) if ram is not None else None,
        available_vram_mb=int(vram-used) if vram is not None and used is not None else None,
        cpu_load_percent=values.get('load_percent'),available_models=tuple(available_models)))

def run_cycle(snapshot,task_kind,*,adapters,store=None,codex_ref=None,clock=now,memory=None):
    """Adapters are explicit already-running backends. Routing cannot launch one."""
    store=store or ArtifactStore()
    stamp=clock()
    snapshot_ref=store.put('snapshots',snapshot.to_dict())
    request_ref=export_codex_request(store,snapshot,task_kind)
    failure=None
    routing=None
    try:
        ensure_fresh(snapshot,stamp)
        routing=route_snapshot(snapshot,task_kind,available_models=tuple(adapters))
        if routing.selected_model is None: raise ContractError('MODEL_UNAVAILABLE')
        result=adapters[routing.selected_model].analyze(snapshot,task_kind)
        if not isinstance(result,CognitiveActorResult) or result.state_hash!=snapshot.state_hash or result.task_kind!=task_kind:
            raise ContractError('QWEN_RESPONSE_INVALID')
        if result.actor_id != ACTORS[routing.selected_model]:
            raise ContractError('QWEN_RESPONSE_INVALID')
        if result.result_status in {'COMPLETE','PARTIAL'}:
            if result.model_id != routing.selected_model or result.model_hash != MODEL_PROFILES[routing.selected_model]['sha256']:
                raise ContractError('MODEL_HASH_MISMATCH')
            if result.runtime_id != RUNTIME_ID or result.runtime_hash != SERVER_HASH:
                raise ContractError('RUNTIME_HASH_MISMATCH')
        if result.result_status!='COMPLETE': failure=result.failure_state or 'QWEN_RESPONSE_INVALID'
    except (ContractError,ValueError,OSError,RuntimeError,TimeoutError) as exc:
        failure=getattr(exc,'reason_code',str(exc))
        if failure not in FAILURE_STATES:
            failure='RUNTIME_FAILURE' if isinstance(exc,(OSError,RuntimeError,TimeoutError)) else 'QWEN_RESPONSE_INVALID'
        identity=ACTORS.get(routing.selected_model,'SYSTEM') if routing else 'SYSTEM'
        result=CognitiveActorResult(actor_id=identity,state_hash=snapshot.state_hash,task_kind=task_kind,
            created_at=clock(),result_status='FAILED',failure_state=failure,reason_codes=(failure,))
    refs=[store.put('actor_results',result.to_dict())]
    comparison=None
    if codex_ref:
        try:
            codex=load_codex_result(store,codex_ref,snapshot)
            if codex.task_kind != task_kind:
                raise ContractError('UNSUPPORTED_TASK')
            comparison=reconcile(snapshot,result,codex,clock())
            refs.append(codex_ref)
            if codex.result_status != 'COMPLETE':
                failure = codex.failure_state or 'CODEX_RESPONSE_UNAVAILABLE'
        except (ContractError,ValueError,OSError) as exc:
            code=getattr(exc,'reason_code',str(exc))
            failure=code if code in FAILURE_STATES else 'CODEX_RESPONSE_UNAVAILABLE'
            codex=CognitiveActorResult(actor_id='CODEX',state_hash=snapshot.state_hash,
                task_kind=task_kind,created_at=clock(),result_status='FAILED',
                failure_state=failure,reason_codes=('CODEX_HANDOFF_REJECTED',failure))
            refs.append(store.put('actor_results',codex.to_dict()))
    reconciliation_ref=store.put('reconciliations',comparison.to_dict()) if comparison else None
    memory_hashes=()
    stamp=clock()
    cycle_id='cycle.'+content_hash({'state':snapshot.state_hash,'results':refs,'at':stamp})[:32]
    if memory is not None:
        item=EpisodeMemory(memory_id=cycle_id,created_at=stamp,source_refs=tuple(refs),input_hashes=(snapshot_ref,),
            reason_codes=('ANALYSIS_ONLY','NO_ACTION_EXECUTED'),epistemic_state='INTERPRETATION',confidence='UNKNOWN',
            summary='Completed bounded cognitive cycle.' if not failure else 'Bounded cognitive cycle failed closed.')
        try:
            memory_hashes=(memory.append(item,known_refs=set(refs)),)
        except (ContractError,ValueError,OSError):
            failure='AUDIT_FAILURE'
    receipt=CognitiveCycleReceipt(cycle_id=cycle_id,created_at=stamp,as_of_at=snapshot.as_of_at,
        state_hash=snapshot.state_hash,snapshot_hash=snapshot_ref,machine_snapshot_hash=snapshot.machine_state.machine_snapshot_hash,
        routing_hash=routing.routing_hash if routing else content_hash({'failure_state':failure}),
        actor_result_hashes=tuple(refs),result_status='FAILED' if failure else ('COMPLETE' if comparison else 'PARTIAL'),
        input_hash=content_hash({'snapshot':snapshot_ref,'task_kind':task_kind,'codex_request':request_ref}),
        output_hash=content_hash({'results':refs,'reconciliation':reconciliation_ref}),reconciliation_hash=reconciliation_ref,
        memory_hashes=memory_hashes,failure_state=failure,
        reason_codes=(failure,) if failure else ('NO_ACTION_EXECUTED',)+(('CODEX_RESPONSE_UNAVAILABLE',) if not comparison else ()))
    receipt_ref=store.put('receipts',receipt.to_dict())
    if routing: store.put('experiments',{'kind':'ROUTING_DECISION','cycle_id':cycle_id,'decision':routing.to_dict()})
    return {'receipt':receipt,'receipt_ref':receipt_ref,'result':result,'reconciliation':comparison,'codex_request_ref':request_ref}

def performance_metrics(store):
    """Operational counts only. Null means no measured denominator/outcome."""
    receipts=[];results=[];comparisons=[]
    for kind,target,cls in (('receipts',receipts,CognitiveCycleReceipt),('actor_results',results,CognitiveActorResult)):
        for path in sorted((store.root/kind).glob('*.json')):
            target.append(cls.from_dict(store.get(kind,path.stem)))
    for path in sorted((store.root/'reconciliations').glob('*.json')):
        comparisons.append(CognitiveReconciliation.from_dict(store.get('reconciliations',path.stem)).to_dict())
    receipts.sort(key=lambda value:(utc_time(value.created_at),value.cycle_id))
    results.sort(key=lambda value:(utc_time(value.created_at),value.digest()))
    comparisons.sort(key=lambda value:(utc_time(value['created_at']),value['reconciliation_id']))
    qwen=[r for r in results if r.actor_id in ('QWEN_4B','QWEN_30B')]
    routes=[]
    from .router import RoutingDecision
    for path in sorted((store.root/'experiments').glob('*.json')):
        value=store.get('experiments',path.stem)
        if value.get('kind')=='ROUTING_DECISION':
            routes.append(RoutingDecision.from_dict(value['decision']))
    count=len(qwen)
    def rate(n,d):return n/d if d else None
    latency={actor:[r.latency_ms for r in qwen if r.actor_id==actor and r.latency_ms is not None] for actor in ('QWEN_4B','QWEN_30B')}
    return {'cycle_count':len(receipts),'cognitive_cycle_failures':sum(r.result_status=='FAILED' for r in receipts),
        'routing_frequency':{actor:sum(ACTORS.get(r.selected_model)==actor for r in routes) for actor in latency},
        'latency_ms':{actor:{'count':len(v),'mean':sum(v)/len(v) if v else None,'last':v[-1] if v else None} for actor,v in latency.items()},
        'agreement_rate':rate(sum(r['status']=='AGREEMENT' for r in comparisons),len(comparisons)),
        'disagreement_rate':rate(sum(bool(r['disagreements']) for r in comparisons),len(comparisons)),
        'invalid_response_rate':rate(sum(r.failure_state=='QWEN_RESPONSE_INVALID' for r in qwen),count),
        'abstention_rate':rate(sum(any(c.position=='ABSTAIN' for c in r.conclusions) for r in qwen),count),
        'hypotheses_generated':sum(len(r.hypotheses) for r in results),'hypotheses_later_supported':None,
        'hypotheses_later_rejected':None,'research_needs_generated':sum(len(r.research_needs) for r in results),
        'research_needs_fulfilled':None,'uncertainties_reduced':None,
        'gateway_errors':None,'qwen_operation_failures':sum(r.failure_state is not None for r in qwen),
        'predictive_accuracy_gain':None,'actor_metric_population':'STORED_UNIQUE_ACTOR_RESULTS'}

def cockpit(snapshot,*,store,last_cycle=None,events=(),gateway_status='UNKNOWN',memory=None,clock=now):
    if gateway_status not in {'UNKNOWN','AUTHENTICATED','AUTHENTICATED_LOOPBACK','UNAVAILABLE','FAILED','HEALTHY'}:
        raise ContractError('UNTRUSTED_CONTEXT')
    stamp=clock()
    components=snapshot.machine_state.components
    machine={c.component_id:{'status':c.status,'labels':{v.name:v.value for v in c.labels},
        'metrics':{v.name:v.value for v in c.metrics}} for c in components
        if c.component_id.split('.')[0] in {'os','cpu','ram','gpu','service','tool','process','listener'}}
    # Bounded summary rather than every process or arbitrary model text.
    machine=dict(list(machine.items())[:48])
    active=memory.active(stamp) if memory else ()
    ordered=sorted(active,key=lambda item:utc_time(item.created_at))
    recent_memory={kind:next(({'memory_id':item.memory_id,'summary':item.summary,'created_at':item.created_at}
        for item in reversed(ordered) if item.kind==kind),None) for kind in ('EPISODE','DECISION','LEARNING')}
    recs=[store.get('reconciliations',p.stem) for p in (store.root/'reconciliations').glob('*.json')]
    latest_rec=max(recs,key=lambda r:utc_time(r['created_at'])) if recs else None
    try:
        ensure_fresh(snapshot,stamp)
        freshness='FRESH'
    except ContractError as exc:
        freshness=exc.reason_code
    return {'schema_version':'2','status':'PARTIAL','created_at':stamp,'observed_at':snapshot.machine_state.observed_at,
        'state_hash':snapshot.state_hash,'cognitive':{'qwen_4b':'PROCESS_OBSERVED' if snapshot.model_state.active_model=='qwen3-4b' else 'PINNED_MODEL_EXPECTATION',
            'qwen_30b':'PROCESS_OBSERVED' if snapshot.model_state.active_model=='qwen3-coder-30b' else 'PINNED_MODEL_EXPECTATION',
            'codex_artifact_status':'EXPLICIT_HANDOFF','last_cycle':last_cycle['receipt_ref'] if last_cycle else None,
            'last_reconciliation':content_hash(latest_rec) if latest_rec else None,
            'agreement_state':latest_rec['status'] if latest_rec else 'INSUFFICIENT_EVIDENCE',
            'last_action':'NO_ACTION','last_action_result':'PROPOSALS_ONLY_NO_EXECUTION'},
        'machine':machine,'world':{'active_fixture':snapshot.active_fixture,'active_prediction':snapshot.active_prediction,
            'evidence_count':len(snapshot.world_state.evidence),'hydra':'ACQUISITION_PATH_PRESERVED','medusa':'VALIDATION_REQUIRED',
            'prediction_status':'FROZEN_FUTURE_PREDICTION','uncertainty_count':len(snapshot.uncertainties.items)},
        'deltas':[{'event_type':e.event_type,'reason_codes':list(e.reason_codes),'severity':e.severity} for e in events[-12:]],
        'memory':{'active_items':len(active),'kinds':{kind:sum(i.kind==kind for i in active) for kind in
            ('WORKING','EPISODE','DECISION','LEARNING','KNOWN_LIMITATION')},'recent':recent_memory,'known_blockers':list(snapshot.chain_breaks)},
        'security':{'gateway_authentication':gateway_status,'action_authority':'PROPOSALS_ONLY','machine_mutation':'DISABLED',
            'restricted_process':'EXPECTED_TOKEN_AND_JOB_BOUNDARY','freshness_policy':'REQUIRE_CURRENT_STATE',
            'freshness_status':freshness,'machine_snapshot_age_seconds':max(0,(utc_time(stamp)-utc_time(snapshot.machine_state.observed_at)).total_seconds()),
            'owner_manual_ports':[11434,11435],'listener_classification':'OBSERVATION_DOES_NOT_IMPLY_HOSTILITY'},
        'metrics':performance_metrics(store),'reason_codes':['READ_ONLY','NO_PREDICTIVE_ACCURACY_CLAIM']}

def publish_cockpit(value):
    from .artifacts import _safe_root, _inspect
    _inspect(value)
    root=_safe_root(PROJECT_RUNTIME);root.mkdir(parents=True,exist_ok=True)
    raw=canonical_bytes(value)
    if len(raw)>65536:raise ValueError('REQUEST_TOO_LARGE')
    target=root/'cockpit.json'
    if target.is_symlink():raise ValueError('UNTRUSTED_CONTEXT')
    temporary=root/'cockpit.new'
    with temporary.open('xb') as stream:stream.write(raw)
    temporary.replace(target)
