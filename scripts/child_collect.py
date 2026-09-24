"""Bounded Task Scheduler entry point; no donor paths or private arguments."""
from pathlib import Path
from datetime import datetime, timezone
import json
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.dont_write_bytecode = True

if __name__ == '__main__':
    if sys.version_info[:2] != (3, 14):
        raise SystemExit('Python 3.14 required')
    from dragonhydra.child.acquisition import collect_once
    from dragonhydra.child.weather import collect_met_weather_once
    from dragonhydra.child.storage import ChildStore
    from dragonhydra.child.observatory import run_observatory
    from dragonhydra.web.provenance import exclusive_json
    receipt = {'run_id':uuid4().hex,'started_at':datetime.now(timezone.utc).isoformat(),'stages':{}}
    def stage(name, operation):
        try:
            value=operation()
            receipt['stages'][name]=value
            return value
        except Exception as error:
            receipt['stages'][name]={'status':'BLOCKED','reason':type(error).__name__}
            return receipt['stages'][name]
    fixture=stage('fixtures',collect_once)
    weather=stage('weather',collect_met_weather_once)
    if weather.get('status')=='CAPTURED':
        stage('weather_storage',lambda:ChildStore().persist_snapshot(weather['snapshot'],[]))
    stage('analysis_prediction_scoring_presentation',run_observatory)
    receipt['finished_at']=datetime.now(timezone.utc).isoformat()
    receipt['status']='PARTIAL' if any(row.get('status','COMPLETE') not in ('COMPLETE','CAPTURED','NOT_DUE') for row in receipt['stages'].values()) else 'COMPLETE'
    exclusive_json(ROOT/'runtime/child/job-runs'/(receipt['run_id']+'.json'),receipt)
    print(json.dumps({'run_id':receipt['run_id'],'status':receipt['status'],
        'stages':{key:value.get('status','COMPLETE') for key,value in receipt['stages'].items()}},indent=2))
    raise SystemExit(0 if receipt['status']=='COMPLETE' else 1)
