"""Deterministic projections from validated CHILD state and bounded ARX probes."""
from datetime import timedelta
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path

from .contracts import (CognitiveStateSnapshot, WorldState, MachineState, ProjectState,
    ModelState, MemoryState, UncertaintyMap, UncertaintyState, ComponentState, Metric,
    StateLabel, EvidenceReference, SystemSelfModel, ContractError, content_hash, utc_time)
from .policy import default_capabilities
from ..localai.runtime import MODEL_PROFILES, RUNTIME_ID, SERVER_HASH

ROOT=Path(__file__).resolve().parents[3]

def build_snapshot(analysis,machine,*,prediction,memory_state=None,events=()):
    try:
        return _build_snapshot(analysis,machine,prediction=prediction,memory_state=memory_state,events=events)
    except ContractError: raise
    except (KeyError,TypeError,ValueError,AttributeError,StopIteration) as exc:
        raise ContractError('UNTRUSTED_CONTEXT') from exc

def _build_snapshot(analysis,machine,*,prediction,memory_state=None,events=()):
    """No SQL/filesystem capabilities reach an actor. Inputs come from controllers."""
    if analysis.get('project')!='DRAGONHYDRACHILD' or analysis.get('temporal_mode')!='STRICT_PIT':
        raise ContractError('UNTRUSTED_CONTEXT')
    evidence=analysis['evidence']
    if evidence.get('validation_verdict')!='ACCEPT' or evidence.get('temporal_mode')!='STRICT_PIT':
        raise ContractError('MEDUSA_REQUIRED')
    if prediction.get('kind')!='PREDICTION' or prediction.get('synthetic') is not False:
        raise ContractError('UNTRUSTED_CONTEXT')
    if not machine.observations:raise ContractError('MACHINE_PROBE_FAILED')
    at=machine.created_at
    observed=min((o.observed_at for o in machine.observations),key=utc_time)
    expires=min((utc_time(o.observed_at)+timedelta(seconds=o.freshness_ttl) for o in machine.observations)).isoformat()
    components=[]
    child_repository=None
    active_model=None
    for observation in sorted(machine.observations,key=lambda x:x.entity_id):
        data=observation.data
        if observation.kind=='repository' and data.get('name')=='child': child_repository=data
        if observation.kind=='process' and data.get('port')==8082:
            active_model={'QWEN_4B':'qwen3-4b','QWEN_30B':'qwen3-coder-30b'}.get(data.get('model_id'))
        metrics=tuple(Metric(name=key,value=float(value),unit=('BOOLEAN' if type(value) is bool else 'PROBE_NATIVE_UNIT'),
            provenance_refs=(observation.entity_id,)) for key,value in sorted(data.items()) if type(value) in (int,float,bool) and key!='uptime_seconds')
        labels=tuple(StateLabel(name=key,value=value) for key,value in sorted(data.items()) if type(value) is str)
        components.append(ComponentState(component_id=observation.entity_id,status=observation.status,
            metrics=metrics,labels=labels,references=(observation.state_hash,),reason_codes=observation.reason_codes))
    for event in events:
        components.append(ComponentState(component_id=event.event_id,status='OBSERVED_EVENT',
            labels=(StateLabel(name='event_type',value=event.event_type),StateLabel(name='entity_id',value=event.entity_id)),
            references=tuple(event.references),reason_codes=tuple(event.reason_codes)))
    if child_repository is None: raise ContractError('MACHINE_PROBE_FAILED')
    er=EvidenceReference(evidence_id=evidence['snapshot_id'],content_hash=evidence['content_hash'],
        observed_at=evidence['observed_at'],available_at=evidence['available_at'],source_id=evidence['source_id'],
        epistemic_state='OBSERVATION',medusa_accepted=True)
    unknown=[]
    dimensions={'lineup_continuity':'LINEUP','injury_burden':'INJURY','market_movement':'MARKET'}
    for name in analysis['uncertainty']['missing_external_features']:
        if name in dimensions: unknown.append(dimensions[name])
    unknown+=['TEMPORAL','IDENTITY','CALIBRATION','RESEARCH_VALUE']
    uncertainties=[UncertaintyState(uncertainty_id='uncertainty.'+name.lower(),dimension=name,
        last_updated=at,recommended_resolution='REQUEST_HYDRA_RESEARCH' if name in ('LINEUP','INJURY','MARKET','IDENTITY') else 'REQUEST_HUMAN_REVIEW',
        score=None,status='UNKNOWN',provenance_refs=(er.evidence_id,),reason_codes=('MISSING_VALIDATED_EVIDENCE',)) for name in sorted(set(unknown))]
    uncertainties.append(UncertaintyState(uncertainty_id='uncertainty.model_disagreement',dimension='MODEL_DISAGREEMENT',
        last_updated=at,recommended_resolution='REQUEST_MODEL_COMPARISON',
        score=analysis['uncertainty']['model_disagreement_nats']/math.log(3),status='OPEN',
        provenance_refs=(analysis['feature_snapshot']['snapshot_id'],),reason_codes=('NORMALIZED_JENSEN_SHANNON_DIVERGENCE',)))
    if machine.health.status!='HEALTHY':
        uncertainties.append(UncertaintyState(uncertainty_id='uncertainty.machine',dimension='MACHINE_STATE',last_updated=at,
            recommended_resolution='REQUEST_STATE_REFRESH',status='UNKNOWN',provenance_refs=(machine.state_hash,),
            reason_codes=machine.health.reason_codes or ('MACHINE_CAPABILITY_UNKNOWN',)))
    models=[ComponentState(component_id=key,status='PINNED_MODEL_EXPECTATION',references=(profile['sha256'],),
        labels=(StateLabel(name='runtime_id',value=RUNTIME_ID),)) for key,profile in MODEL_PROFILES.items()]
    for row in sorted(analysis['models'],key=lambda x:x['model_id']):
        if row['epistemic_state']!='PREDICTION': raise ContractError('UNTRUSTED_CONTEXT')
        values=[row['probabilities'][key] for key in ('HOME','DRAW','AWAY')]
        if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in values) or abs(sum(values)-1)>1e-6:
            raise ContractError('UNTRUSTED_CONTEXT')
        models.append(ComponentState(component_id=row['model_id'],status='PREDICTION',
            metrics=tuple(Metric(name=key,value=row['probabilities'][key],unit='PROBABILITY',provenance_refs=(prediction['prediction_id'],)) for key in ('HOME','DRAW','AWAY')),
            references=(row['feature_snapshot_id'],),reason_codes=('NOT_OBSERVATION',)))
    result=CognitiveStateSnapshot(snapshot_id='cognitive.pending',
        created_at=at,as_of_at=machine.as_of_at,temporal_mode='PRESENT',
        world_state=WorldState(as_of_at=machine.as_of_at,evidence=(er,),
            source_states=(ComponentState(component_id='hydra.MATCH',status='VALIDATED_CAPTURE',references=(er.evidence_id,)),
                           ComponentState(component_id='MEDUSA',status='ACCEPT',references=(er.evidence_id,))),
            prediction_refs=(prediction['prediction_id'],),feature_refs=(analysis['feature_snapshot']['snapshot_id'],),
            simulation_refs=(content_hash(analysis['simulation']),),reason_codes=('ORIGINAL_FORECAST_IMMUTABLE',)),
        machine_state=MachineState(machine_snapshot_hash=machine.state_hash,observed_at=observed,
            available_at=at,expires_at=expires,components=tuple(components),health='FAILED' if machine.health.failed_probes else machine.health.status,reason_codes=machine.health.reason_codes),
        project_state=ProjectState(project_id='DRAGONHYDRACHILD',branch=child_repository['branch'],head=child_repository['head'],
            working_tree='DIRTY' if child_repository['dirty'] else 'CLEAN',observed_at=observed,available_at=at,
            expires_at=expires,frozen_prediction_hash=prediction['hash']),
        model_state=ModelState(models=tuple(models),active_model=active_model,forecast_refs=(prediction['prediction_id'],),
            model_hashes=tuple(p['sha256'] for p in MODEL_PROFILES.values()),runtime_hashes=(SERVER_HASH,)),
        memory_state=memory_state or MemoryState(),uncertainties=UncertaintyMap(items=tuple(uncertainties)),
        capabilities=default_capabilities(),active_fixture=analysis['selected_fixture']['fixture_id'],
        active_prediction=prediction['prediction_id'],recent_events=tuple(e.event_id for e in events),
        chain_breaks=('REAL_ODDS_UNAVAILABLE','PROSPECTIVE_OUTCOME_UNOBSERVED','KICKOFF_TIMEZONE_UNVERIFIED',
            'PLAYER_IDENTITY_INCOMPLETE','RESEARCH_BENEFIT_UNMEASURED','QWEN_4B_PUBLISHER_PROVENANCE_UNVERIFIED'))
    return replace(result,snapshot_id='cognitive.'+result.state_hash[:32])

def controlled_child_inputs():
    """Fixed project-owned stores, bounded reads, no caller-selected path."""
    folder=ROOT/'runtime/child/analysis'
    for path in (folder,ROOT/'runtime/child/predictions',*folder.parents):
        if path.is_symlink() or path.is_junction():raise ContractError('UNTRUSTED_CONTEXT')
    paths=[p for p in folder.iterdir() if p.is_file() and len(p.name)==64]
    if not paths: raise ContractError('UNTRUSTED_CONTEXT')
    path=max(paths,key=lambda p:p.stat().st_mtime_ns)
    if path.is_symlink() or path.stat().st_size>1024*1024: raise ContractError('UNTRUSTED_CONTEXT')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=path.name: raise ContractError('UNTRUSTED_CONTEXT')
    from ..child.ledger import PredictionLedger
    events=PredictionLedger(ROOT/'runtime/child/predictions').verify()
    prediction=next(row for row in events if row['kind']=='PREDICTION' and not row['synthetic'])
    return json.loads(raw),prediction

def self_model(snapshot,*,last_reconciliation_at=None):
    enabled=tuple(c.action_class for c in snapshot.capabilities.capabilities if c.enabled)
    disabled=tuple(c.action_class for c in snapshot.capabilities.capabilities if not c.enabled)
    return SystemSelfModel(version='cognitive-v2/1',created_at=snapshot.created_at,
        components=(ComponentState(component_id='ARX',status='OBSERVE_ONLY'),ComponentState(component_id='COGNITIVE_CORE',status='ANALYSIS_ONLY'),
            ComponentState(component_id='HYDRA',status='EXISTING_ACQUISITION_PATH'),ComponentState(component_id='MEDUSA',status='VALIDATION_REQUIRED')),
        available_models=tuple(MODEL_PROFILES),active_model=snapshot.model_state.active_model,
        available_data_sources=tuple(e.source_id for e in snapshot.world_state.evidence),active_hydra_heads=('MATCH',),
        active_math_engines=tuple(m.component_id for m in snapshot.model_state.models if m.status=='PREDICTION'),
        known_databases=('CHILD_SQL_SERVER','CHILD_MARIADB'),available_actions=enabled,disabled_actions=disabled,
        machine_capabilities=('READ_ONLY_LEVEL_0','READ_ONLY_LEVEL_1','READ_ONLY_LEVEL_2'),known_blockers=snapshot.chain_breaks,
        known_scientific_limits=('NO_PREDICTIVE_ACCURACY_GAIN_ESTABLISHED','FUTURE_IS_NOT_OBSERVATION'),
        current_feature_branch=snapshot.project_state.branch,last_validated_state_hash=snapshot.state_hash,
        last_reconciliation_at=last_reconciliation_at)
