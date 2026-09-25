"""Engineering-only explicit cognitive capture and analysis. No machine actions."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dragonhydra.machine import capture_machine
from dragonhydra.cognitive_v2.artifacts import ArtifactStore,export_codex_request
from dragonhydra.cognitive_v2.contracts import CognitiveStateSnapshot
from dragonhydra.cognitive_v2.snapshot import build_snapshot,controlled_child_inputs,self_model
from dragonhydra.cognitive_v2.cycle import memory_state,run_cycle,cockpit,publish_cockpit,now
from dragonhydra.cognitive_v2.memory import MemoryStore
from dragonhydra.cognitive_v2.adapter import QwenCognitiveAdapter
from dragonhydra.cognitive_v2.router import TASK_KINDS

def main():
    if sys.version_info[:2]!=(3,14):raise SystemExit('Python 3.14 required')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('capture','cycle','export-codex'))
    parser.add_argument('--snapshot',help='Existing content hash; never an arbitrary path')
    parser.add_argument('--codex-result',help='Typed actor artifact content hash')
    parser.add_argument('--task',choices=sorted(TASK_KINDS),default='SUMMARIZE_STATE')
    args=parser.parse_args()
    store=ArtifactStore();memory=MemoryStore(ROOT/'runtime/cognitive-v2/memory')
    if args.snapshot:
        snapshot=CognitiveStateSnapshot.from_dict(store.get('snapshots',args.snapshot))
    else:
        analysis,prediction=controlled_child_inputs();machine=capture_machine()
        store.put('experiments',{'kind':'MACHINE_CAPTURE','snapshot':machine.to_dict()})
        snapshot=build_snapshot(analysis,machine,prediction=prediction,memory_state=memory_state(memory,now()))
    ref=store.put('snapshots',snapshot.to_dict())
    store.put('experiments',{'kind':'SYSTEM_SELF_MODEL','self_model':self_model(snapshot).to_dict()})
    result=None;auth='UNKNOWN'
    output={'snapshot_ref':ref,'state_hash':snapshot.state_hash}
    if args.operation=='export-codex':
        output['codex_request_ref']=export_codex_request(store,snapshot,args.task)
    if args.operation=='cycle':
        adapters={}
        try:
            active=json.loads((ROOT/'runtime/localai/active.json').read_text(encoding='utf-8'))
            client=QwenCognitiveAdapter('http://127.0.0.1:8083',model_id=active['model_id'],
                token=(ROOT/'runtime/localai/gateway.key').read_text(encoding='ascii').strip(),
                audit_dir=ROOT/'runtime/localai/cognitive-client')
            health=client.health()
            if health.get('result_status')=='SUCCESS' or health.get('status')=='READY':
                adapters[active['model_id']]=client;auth='AUTHENTICATED'
        except (OSError,ValueError,KeyError):pass
        result=run_cycle(snapshot,args.task,adapters=adapters,store=store,codex_ref=args.codex_result,memory=memory)
        output.update({'receipt_ref':result['receipt_ref'],'result_status':result['receipt'].result_status,
            'failure_state':result['receipt'].failure_state,'codex_request_ref':result['codex_request_ref']})
    publish_cockpit(cockpit(snapshot,store=store,last_cycle=result,gateway_status=auth,memory=memory))
    print(json.dumps(output,indent=2))

if __name__=='__main__':main()
