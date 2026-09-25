"""Deterministic projection of a controlled CHILD analysis, not arbitrary files.

The producer must already have validated acquisition through HYDRA/MEDUSA. This
projection preserves that provenance and never promotes model claims to facts.
"""
import math
from .contracts import Snapshot, ContractError

def from_child_analysis(analysis):
    try:
        if analysis['project']!='DRAGONHYDRACHILD' or analysis['temporal_mode']!='STRICT_PIT':
            raise ContractError()
        evidence=analysis['evidence']
        if evidence['validation_verdict']!='ACCEPT' or evidence['temporal_mode']!='STRICT_PIT':
            raise ContractError()
        fixture=analysis['selected_fixture']
        if type(fixture['actual_utc_kickoff_verified']) is not bool or fixture['score_state'] not in ('NOT_REPORTED','REPORTED_FINAL'):
            raise ContractError()
        missing=[]
        mapping={'lineup_continuity':'LINEUP','injury_burden':'INJURY','market_movement':'ODDS'}
        for feature in analysis['uncertainty']['missing_external_features']:
            if feature in mapping: missing.append(mapping[feature])
        if not analysis['selected_fixture']['actual_utc_kickoff_verified']: missing.append('KICKOFF_TIME')
        if analysis['selected_fixture']['score_state']=='NOT_REPORTED': missing.append('OUTCOME')
        if analysis['market']['status']=='BLOCKED': missing.append('ODDS')
        forecasts=[]
        for model in sorted(analysis['models'],key=lambda row:row['model_id']):
            if model['epistemic_state']!='PREDICTION' or model['failure_state'] is not None:
                raise ContractError()
            forecasts.append({'model_id':model['model_id'],'probabilities':[
                model['probabilities'][key] for key in ('HOME','DRAW','AWAY')],'epistemic_state':'PREDICTION'})
        return Snapshot.from_dict({'schema_version':'1','as_of_at':analysis['computed_at'],
            'temporal_mode':'STRICT_PIT','fixture_id':analysis['selected_fixture']['fixture_id'],
            'evidence':[{'evidence_id':evidence['snapshot_id'],'source_id':evidence['source_id'],
                'content_hash':evidence['content_hash'],'provenance_ids':[evidence['snapshot_id']],
                'epistemic_state':'OBSERVATION','available_at':evidence['available_at']}],
            'uncertainty':[{'dimension':'GENERAL','score':analysis['uncertainty']['predictive_entropy_nats']/math.log(3)},
                {'dimension':'MODEL_DISAGREEMENT','score':analysis['uncertainty']['model_disagreement_nats']/math.log(3)}],
            'forecasts':forecasts,'missing_evidence':sorted(set(missing))})
    except (KeyError,TypeError,ValueError) as exc:
        raise ContractError('INVALID_REQUEST') from exc
