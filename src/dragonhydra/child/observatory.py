"""Connect genuine CHILD evidence to models, frozen forecasts and presentation.

Source-local match dates are not invented UTC kickoffs. Forecast issuance uses
an explicitly labelled earliest global-timezone date bound. Outcome scoring
waits for a later actually captured explicit final score.
"""
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path

from ..config import PROJECT_ROOT
from ..science.evaluation import FixtureTarget, Outcome, Probabilities
from ..science.prospective import RawEvidenceStore
from ..science.temporal import Availability, TemporalMode
from ..web.provenance import encode, exclusive_json
from .acquisition import source_metrics, fault_injection_report
from .features import MatchEvidence
from .ledger import LedgerProposal, PredictionLedger
from .registry import Maturity, OperationalStatus, default_heads, update_head
from .research_run import predict_current
from .simulation import score_matrix, monte_carlo, scenario_mixture
from .storage import ChildStore, ChildPresentation, sql_connection
from .uncertainty import ResearchNeed, ResearchScenario, ResearchAnswer, entropy, rank_research, run_controlled_research


def _now():
    return datetime.now(timezone.utc)


def _hash(value):
    return hashlib.sha256(encode(value)).hexdigest()


def latest_fixture_capture(root=PROJECT_ROOT):
    records = [json.loads(path.read_text(encoding='utf-8')) for path in (root/'runtime/child/snapshots').glob('*.json')]
    if not records:
        raise ValueError('SOURCE_UNAVAILABLE: no genuine CHILD fixture capture')
    return max(records, key=lambda row: row['snapshot']['retrieved_at'])


def strict_inputs(capture: dict, *, constructed_at: datetime):
    snapshot = capture['snapshot']
    if snapshot.get('temporal_mode') != 'STRICT_PIT' or snapshot.get('synthetic', False) is not False:
        raise ValueError('Strict inputs require genuine STRICT_PIT capture')
    observed = datetime.fromisoformat(snapshot['observed_at'])
    retrieved = datetime.fromisoformat(snapshot['retrieved_at'])
    available = datetime.fromisoformat(snapshot['available_at'])
    if not observed <= retrieved <= available <= constructed_at:
        raise ValueError('Cannot construct inputs before genuine source capture')
    availability = Availability(TemporalMode.STRICT_PIT, constructed_at, observed, retrieved, constructed_at,
        'GENUINE_CHILD_CAPTURE_CURRENT_KNOWLEDGE', '1.0',
        'Capture availability is genuine. Match calendar dates are source values; UTC day proxies are not verified kickoff/final-whistle times.',
        0.8, snapshot['source_url'])
    results = []
    for row in capture['fixtures']:
        if row.get('temporal_mode') != 'STRICT_PIT' or row.get('synthetic') is not False:
            raise ValueError('Reconstructed or synthetic fixture cannot enter genuine strict inputs')
        if (row.get('snapshot_id') != snapshot['snapshot_id']
                or row.get('content_hash') != snapshot['content_hash']
                or datetime.fromisoformat(row['available_at']) > constructed_at):
            raise ValueError('Fixture provenance or availability does not match the capture')
        day = datetime.combine(date.fromisoformat(row['match_date']), time(), timezone.utc)
        if row['status'] != 'REPORTED_FINAL' or day + timedelta(days=1) >= constructed_at:
            continue
        results.append(MatchEvidence(snapshot['snapshot_id']+':result:'+row['fixture_id'],row['fixture_id'],
            row['competition_id'],row['home_team_id'],row['away_team_id'],day,day+timedelta(days=1),
            row['home_score'],row['away_score'],availability,availability))
    return tuple(results), availability


def select_target(capture: dict, availability: Availability, *, at: datetime):
    candidates = []
    for row in capture['fixtures']:
        # A source calendar date could correspond to UTC+14. This lower bound
        # is conservative across civil timezones, explicitly not actual kickoff.
        lower = datetime.combine(date.fromisoformat(row['match_date']), time(), timezone.utc)-timedelta(hours=14)
        if row['status'] != 'REPORTED_FINAL' and lower > at + timedelta(hours=1):
            candidates.append((lower,row['fixture_id'],row))
    if not candidates:
        raise ValueError('INSUFFICIENT_EVIDENCE: no defensible future schedule bound')
    lower,_,row = min(candidates)
    target = FixtureTarget(row['fixture_id'],row['competition_id'],row['home_team_id'],row['away_team_id'],
                           lower,availability,capture['snapshot']['snapshot_id']+':schedule:'+row['fixture_id'])
    return target, {**row,'earliest_global_date_bound':lower.isoformat(),
                    'schedule_time_semantics':'DATE_EARLIEST_GLOBAL_BOUND','actual_utc_kickoff_verified':False}


def controlled_research(fixture_id: str, deadline: datetime):
    now = _now()
    baseline = Probabilities(.4,.3,.3)
    scenarios = (ResearchScenario('available',.5,Probabilities(.6,.25,.15)),
                 ResearchScenario('unavailable',.5,Probabilities(.2,.35,.45)))
    need = ResearchNeed('controlled-lineup-availability',fixture_id,'synthetic-player',
        'Can the controlled availability state resolve this information gap?', 'player_available',
        ('synthetic-validated-source',),'controlled-policy/1',deadline,0.0,1.0,scenarios)
    before = now - timedelta(seconds=1)
    availability = Availability(TemporalMode.STRICT_PIT,before,before,before,before,
        'SYNTHETIC_CONTROL_CLOCK','1','Controlled experiment; no real player or injury claim',1.0,'synthetic-validated-source')
    answer = ResearchAnswer('synthetic-answer','synthetic-validated-source','player_available',True,
                            availability,_hash({'synthetic':True,'player_available':True}),True)
    states = {'synthetic-validated-source':'APPROVED'}
    ranking = rank_research((need,),baseline,states,now=now,cost_budget=0)
    result = run_controlled_research(need,baseline,states,now=now,
        known_fields=frozenset({'fixture'}),required_fields=frozenset({'fixture','player_available'}),
        fetcher=lambda request,source:answer,validator=lambda evidence:evidence.synthetic and evidence.content_hash==answer.content_hash,
        recalculator=lambda evidence:scenarios[0].conditional_forecast,cost_budget=0)
    return {'label':'SYNTHETIC_CONTROLLED_RESEARCH_LOOP','ranking':ranking,'result':result,
            'active_real_gaps':['verified kickoff timezone','confirmed lineup','lawful real odds'],
            'real_world_accuracy_gain':'UNMEASURED; no outcome for this controlled information intervention'}


def append_available_outcomes(capture: dict, ledger: PredictionLedger, availability: Availability):
    events = ledger.verify()
    scored = {row['prediction_id'] for row in events if row['kind']=='OUTCOME'}
    latest = {row['fixture_id']:row for row in capture['fixtures']}
    outcomes=[]
    for event in events:
        if event['kind']!='PREDICTION' or event['prediction_id'] in scored or event['synthetic']:
            continue
        row=latest.get(event['fixture_id'])
        if (not row or row['status']!='REPORTED_FINAL'
                or date.fromisoformat(row['match_date']) >= availability.observed_at.date()
                or availability.observed_at <= datetime.fromisoformat(event['kickoff_at'])):
            continue
        # The capture proves a final-score report exists by this instant. It
        # does not recover the actual final-whistle timestamp.
        outcome=Outcome.HOME if row['home_score']>row['away_score'] else Outcome.AWAY if row['home_score']<row['away_score'] else Outcome.DRAW
        proof=Availability(TemporalMode.STRICT_PIT,availability.available_at,availability.observed_at,
            availability.retrieved_at,availability.ingested_at,'FINAL_SCORE_OBSERVED_BY_CAPTURE','1',
            'event_completed_at is an observed-by upper bound, not the exact final whistle; explicit source ft score.',.8,availability.source)
        outcomes.append(ledger.append_outcome(event['prediction_id'],outcome,event_completed_at=proof.observed_at,
            availability=proof,evidence_hash=capture['snapshot']['content_hash'],synthetic=False))
    return outcomes


def run_observatory(*, issue_prediction=True) -> dict:
    capture=latest_fixture_capture()
    constructed=_now()
    if constructed - datetime.fromisoformat(capture['snapshot']['retrieved_at']) > timedelta(days=2):
        raise ValueError('STALE_DATA: refuse new current forecasts from capture older than two days')
    records,availability=strict_inputs(capture,constructed_at=constructed)
    ledger=PredictionLedger(PROJECT_ROOT/'runtime/child/predictions')
    outcomes=append_available_outcomes(capture,ledger,availability)
    store=ChildStore()
    # Outcome scoring continues even when a season has no future fixture.
    if outcomes:
        with sql_connection('ingest') as conn:
            for outcome in outcomes:
                store.append(conn,'evaluations',outcome['prediction_id'],outcome,'openfootball',outcome['recorded_at'])
            conn.commit()
    cursor=_now()
    try:
        target,selected=select_target(capture,availability,at=cursor)
    except ValueError as error:
        if not str(error).startswith('INSUFFICIENT_EVIDENCE:'):
            raise
        summary=store.summary()
        summary['analysis']={'status':'INSUFFICIENT_EVIDENCE','reason':'NO_DEFENSIBLE_FUTURE_FIXTURE',
                             'newly_scored_outcomes':len(outcomes)}
        ChildPresentation().cache(summary)
        return summary['analysis']
    current=predict_current(target,records,at=cursor,mode=TemporalMode.STRICT_PIT)
    forecasts=current['forecasts']; tribunal=current['tribunal']
    probabilities=Probabilities(*(tribunal['weighted'][key] for key in ('HOME','DRAW','AWAY')))
    poisson=next(row['parameters'] for row in forecasts if row['model_id']=='POISSON')
    correction=next(row['parameters'] for row in forecasts if row['model_id']=='DIXON_COLES')
    rates=poisson['home_rate'],poisson['away_rate']
    simulation={'exact_poisson':score_matrix(*rates).to_dict(),
        'dixon_coles':score_matrix(*rates,rho=correction['rho']).to_dict(),
        'monte_carlo':monte_carlo(*rates,samples=20000,seed=314,log_rate_sd=.1),
        'conditional_scenarios':scenario_mixture(((.5,score_matrix(rates[0]*.85,rates[1]*1.15)),
                                                 (.5,score_matrix(rates[0]*1.15,rates[1]*.85))))}
    research=controlled_research(target.fixture_id,target.kickoff_at)
    feature_values={row['name']:row['value'] for row in current['feature_snapshot']['features']}
    uncertainty={'predictive_entropy_nats':entropy(probabilities),
        'model_disagreement_nats':tribunal['jensen_shannon_disagreement_nats'],
        'aleatoric_component':'Outcome randomness is represented by distributions; not separately identifiable from these data.',
        'epistemic_component':'Model disagreement and explicit conditional scenarios are proxies, not a complete decomposition.',
        'evidence_confidence':.8,'training_matches':len(records),
        'missing_external_features':[key for key,value in feature_values.items() if value is None],
        'calibration':'UNCALIBRATED_CURRENT_EXPERIMENT'}
    analysis={'project':'DRAGONHYDRACHILD','selected_fixture':selected,'computed_at':current['computed_at'],
        'evidence':capture['snapshot'],'temporal_mode':'STRICT_PIT','features':current['feature_snapshot']['features'],
        'feature_snapshot':current['feature_snapshot'],'models':forecasts,'tribunal':tribunal,
        'ensemble':{'probabilities':probabilities.to_dict(),'method':tribunal['weighting_method']},
        'simulation':simulation,'uncertainty':uncertainty,'research':research,
        'market':{'status':'BLOCKED','real_source_count':0,'reasons':['AUTH_REQUIRED: The Odds API','TERMS_BLOCKED: Football-Data'],
                  'model_market_difference':None,'synthetic_odds_are_not_real':True},
        'explanation':{'observed_factors':{key:value for key,value in feature_values.items() if key in ('home_form','away_form','home_goals_for','away_goals_for','home_rest_days','away_rest_days')},
            'positive_factors':'Direction depends on model; reported goal/form factors are evidence, not causal attributions.',
            'negative_factors':['short current-season history','lineup/injury/market evidence absent','kickoff timezone unverified'],
            'model_disagreement':tribunal['class_probability_ranges'],'primary_uncertainty':'missing current team information and uncalibrated models'},
        'ml_training_frame_status':current['ml_training_frame_status'],
        'chain_breaks':['No real market snapshot/benchmark','No real-world lineup research benefit validated',
            'Future selected-match outcome has not occurred/been observed','Verified kickoff timezone and cross-provider identities remain incomplete']}
    code_files=sorted((PROJECT_ROOT/'src/dragonhydra/child').glob('*.py'))
    code_hash=_hash({path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in code_files})
    artifact_hash=RawEvidenceStore(PROJECT_ROOT/'runtime/child/analysis').put(encode(analysis))
    existing=next((event for event in ledger.verify() if event['kind']=='PREDICTION' and event['fixture_id']==target.fixture_id),None)
    event=existing
    if issue_prediction and event is None:
        proposal=LedgerProposal(target.fixture_id,target.kickoff_at,probabilities,'CHILD_EQUAL_WEIGHT_ENSEMBLE','1.0',
            current['feature_snapshot']['snapshot_id'],_hash({'source_snapshot':capture['snapshot'],
            'input_record_ids':[row.record_id for row in records]}),(availability.source,),code_hash,(availability,),False,
            schedule_time_semantics='DATE_EARLIEST_GLOBAL_BOUND',analysis_artifact_hash=artifact_hash)
        event=ledger.append_prediction(proposal)
    if event:
        with sql_connection('ingest') as conn:
            store.append(conn,'predictions',event['prediction_id'],event,'child-models',event['prediction_issued_at'])
            conn.commit()
        already_scored=any(row['kind']=='OUTCOME' and row['prediction_id']==event['prediction_id'] for row in ledger.verify())
        analysis['prospective_prediction']={'status':'SCORED' if already_scored else 'FROZEN_AWAITING_OUTCOME','prediction_id':event['prediction_id'],
            'issued_at':event['prediction_issued_at'],'hash':event['hash'],'analysis_artifact_hash':event['analysis_artifact_hash'],
            'schedule_time_semantics':event['schedule_time_semantics'],'newly_scored_outcomes':len(outcomes),
            'frozen_probabilities':event['probabilities'],
            'current_analysis_is_new_calculation':'Frozen original remains in its referenced immutable artifact.'}
    else:
        analysis['prospective_prediction']={'status':'NOT_REQUESTED'}
    heads=default_heads()
    for name in ('MATCH','TEAM','HISTORICAL'):
        heads=update_head(heads,name,maturity=Maturity.VALIDATED,operational_status=OperationalStatus.ACTIVE,
            allowed_sources=('openfootball',),last_observation_at=availability.observed_at,
            test_evidence=('test_child_acquisition.ChildAcquisitionTests','test_child_storage.ChildStorageLiveTests'))
    weather_paths=list((PROJECT_ROOT/'runtime/prospective/met-norway-london').glob('*.json'))
    if weather_paths:
        weather=max((json.loads(path.read_text(encoding='utf-8')) for path in weather_paths),key=lambda row:row['attempted_at'])
        if weather.get('status')=='CAPTURED':
            snapshot=weather['snapshot']
            analysis['weather']={key:value for key,value in snapshot.items() if key!='rows'}
            analysis['weather']['sample_forecasts']=snapshot['rows'][:3]
            heads=update_head(heads,'WEATHER',maturity=Maturity.EXPERIMENTAL,operational_status=OperationalStatus.ACTIVE,
                allowed_sources=('met-norway',),last_observation_at=datetime.fromisoformat(snapshot['observed_at']))
    for name in ('ODDS','MARKET'):
        heads=update_head(heads,name,operational_status=OperationalStatus.SOURCE_UNAVAILABLE,last_failure='AUTH_REQUIRED_OR_TERMS_BLOCKED')
    analysis['heads']=[head.to_dict() for head in heads]
    analysis['sources']=[source_metrics(),{'source_id':'met-norway','scope':'London proxy forecast; no tested predictive effect',
                                         'status':'CAPTURED' if 'weather' in analysis else 'BLOCKED'},
                        {'source_id':'open-meteo','status':'ROBOTS_BLOCKED','forecast_requested':False}]
    scientific=json.loads((PROJECT_ROOT/'docs/evidence/child-science-summary.json').read_text(encoding='utf-8'))
    analysis['historical_evaluation']={'evaluation_matches':scientific['evaluation_matches'],
        'temporal_mode':'RECONSTRUCTED_PIT','model_results':[{'model':key,**value} for key,value in scientific['metrics'].items()],
        'calibration_summary':'Class-wise 5-bin ECE and sample sizes in table; estimates on one reconstructed season.'}
    gpu=PROJECT_ROOT/'runtime/checkpoints/child-v0-gpu-and-v4-benchmark/benchmark.json'
    if gpu.exists():
        analysis['gpu']=json.loads(gpu.read_text(encoding='utf-8'))
    analysis['scheduler']={'task':'DRAGONHYDRACHILD-Prospective','cadence':'daily while owner signed in',
                           'stop':'.\\scripts\\Manage-ChildScheduler.ps1 -Action Disable'}
    summary=store.summary()
    summary['analysis']=analysis
    ChildPresentation().cache(summary)
    return {'selected_fixture':selected,'prospective_prediction':analysis['prospective_prediction'],
            'current_training_matches':len(records),'feature_count':len(current['feature_snapshot']['features']),
            'model_count':len(forecasts),'ensemble':analysis['ensemble'],'uncertainty':uncertainty,
            'research':research,'analysis_artifact_hash':artifact_hash,'code_hash':code_hash,
            'source_snapshot_id':capture['snapshot']['snapshot_id'],'computed_at':current['computed_at']}


if __name__=='__main__':
    print(json.dumps(run_observatory(),indent=2,allow_nan=False))
