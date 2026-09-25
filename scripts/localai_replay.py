"""Explicit local tier: frozen CHILD input, no-AI baseline, 4B and 30B replay.

Starts only the preserved llama-server through the restricted launcher; stops
each owned process. No external requests, forecasts, databases or old services.
"""
from datetime import datetime,timezone
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dragonhydra.localai import LocalAIClient,Snapshot
from dragonhydra.localai.contracts import AnalysisRequest,canonical_bytes,content_hash
from dragonhydra.localai.runtime import LlamaRuntime,create_token,local_json
from dragonhydra.localai.gateway import AnalysisEngine,BoundedHTTPServer

def run():
    if sys.version_info[:2]!=(3,14) or os.name!='nt': raise SystemExit('Requires local Windows Python 3.14')
    from dragonhydra.localai.windows_process import sample_metrics,process_security
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    checkpoint=ROOT/'runtime/checkpoints'/('localai-replay-'+stamp)
    checkpoint.mkdir(parents=True)
    snapshot=Snapshot.from_dict(json.loads((ROOT/'docs/evidence/localai_replay_input.json').read_text()))
    (checkpoint/'input.json').write_bytes(canonical_bytes(snapshot.to_dict()))
    task='ANALYZE_UNCERTAINTY'
    baseline={'actor':'DETERMINISTIC_NO_AI_BASELINE','status':'ABSTAIN','conclusions':[],
        'state_hash':snapshot.state_hash,'input_hash':content_hash({'snapshot':snapshot.to_dict(),'task_kind':task}),
        'missing_evidence':list(snapshot.missing_evidence),'accuracy_gain':'UNMEASURED'}
    results={'baseline':baseline,'models':[],'negative_checks':[],'successful':False}
    checks=results['negative_checks']
    def check(name,truth):
        checks.append({'name':name,'passed':bool(truth)})
        if not truth: raise AssertionError(name)
    try:
        for model in ('qwen3-4b','qwen3-coder-30b'):
            print('Starting restricted '+model,flush=True)
            work=ROOT/'runtime/localai'/('replay-'+stamp+'-'+model)
            runtime=LlamaRuntime(model,work)
            gateway=None; thread=None; stop=threading.Event(); samples=[]
            def monitor():
                while not stop.is_set():
                    try:
                        sample=sample_metrics(runtime.process.pid)
                        sample['elapsed_seconds']=round(time.monotonic()-started,3)
                        gpu=subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu,utilization.memory','--format=csv,noheader,nounits'],
                            capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=4)
                        sample['gpu_csv']=gpu.stdout.strip()
                        samples.append(sample)
                    except (OSError,subprocess.SubprocessError): pass
                    stop.wait(1)
            try:
                runtime.start()
                token=create_token(work/'gateway.key')
                engine=AnalysisEngine(runtime,work,timeout_seconds=120)
                gateway=BoundedHTTPServer(('127.0.0.1',8083),engine,token)
                thread=threading.Thread(target=gateway.serve_forever,daemon=True); thread.start()
                client=LocalAIClient('http://127.0.0.1:8083',model_id=model,
                    model_hash=runtime.identity['model_hash'],runtime_id=runtime.identity['runtime_id'],
                    token=token,audit_dir=work/'client-receipts',timeout_seconds=140)
                check(model+' health',client.health()['status']=='READY')
                check(model+' identity',client.model()['model_id']==model)
                security=process_security(runtime.process.pid)
                started=time.monotonic()
                watcher=threading.Thread(target=monitor,daemon=True); watcher.start()
                response=client.analyze(snapshot,task)
                stop.set(); watcher.join(timeout=6)
                check(model+' validated analysis',response.result_status=='SUCCESS')
                check(model+' identical input',response.input_hash==baseline['input_hash'])
                results['models'].append({'identity':runtime.identity,'startup_seconds':runtime.startup_seconds,
                    'security':security,'response':response.to_dict(),'resources':samples,
                    'receipt':json.loads((work/'receipts'/(response.request_id+'.json')).read_text())})
                print(model+' '+response.result_status+' '+str(round(response.latency_ms))+'ms '+str([c.dimension for c in response.conclusions]),flush=True)
                if model=='qwen3-4b':
                    def raw(method,path,body=None,headers=None):
                        conn=http.client.HTTPConnection('127.0.0.1',8083,timeout=10)
                        try:
                            conn.request(method,path,body=body,headers=headers or {})
                            r=conn.getresponse(); return r.status,r.read(20000)
                        finally:conn.close()
                    auth={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
                    check('unauthenticated rejected',raw('GET','/health')[0]==403)
                    check('browser origin rejected',raw('GET','/health',headers={**auth,'Origin':'https://untrusted.invalid'})[0]==403)
                    check('shell route absent',raw('POST','/execute',b'{}',auth)[0]==404)
                    check('oversized body rejected',raw('POST','/analyze',b' '*8193,auth)[0]==413)
                    check('invalid schema rejected',raw('POST','/analyze',b'{"command":"ignored"}',auth)[0]==400)
                    request=AnalysisRequest.create(snapshot,task,model,'0'*64,runtime.identity['runtime_id'])
                    status,body=raw('POST','/analyze',canonical_bytes(request.to_dict()),auth)
                    check('model hash mismatch',status==200 and json.loads(body)['failure_state']=='MODEL_HASH_MISMATCH')
                    caps=json.loads(raw('GET','/capabilities',headers=auth)[1])
                    check('no action capabilities',caps['action_capabilities']==[])
                    # Deliberately crash only the process started by this test.
                    runtime.process.kill(); runtime.process.wait(timeout=10)
                    failed=client.analyze(snapshot,task)
                    check('backend crash fails closed',failed.failure_state=='LOCALAI_UNAVAILABLE' and not failed.conclusions)
            finally:
                stop.set()
                if gateway: gateway.shutdown(); gateway.server_close()
                if thread: thread.join(timeout=5)
                runtime.stop()
                if gateway: engine.publish_status(stopped=True)
                check(model+' process exited',runtime.process is not None and runtime.process.poll() is not None)
        # GPU-unavailable path safely simulated by explicit CPU-only selection.
        cpu=LlamaRuntime('qwen3-4b',ROOT/'runtime/localai'/('cpu-check-'+stamp),cpu_only=True)
        try:
            cpu.start()
            response=local_json(cpu.url+'/v1/chat/completions',token=cpu.token,timeout=60,payload={
                'model':'qwen3-4b','messages':[{'role':'user','content':'Return only the integer result of 7 + 5. /no_think'}],
                'max_tokens':8,'temperature':0,'seed':42})
            check('CPU-only inference',response['choices'][0]['message']['content'].strip()=='12')
            results['cpu_only']={'identity':cpu.identity,'security':process_security(cpu.process.pid),
                'metrics':sample_metrics(cpu.process.pid),'timings':response.get('timings'),'output':'12'}
        finally: cpu.stop()
        results['successful']=all(row['passed'] for row in checks)
    finally:
        (checkpoint/'replay.json').write_text(json.dumps(results,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print('CHECKPOINT '+str(checkpoint),flush=True)
    return 0 if results['successful'] else 1

if __name__=='__main__': raise SystemExit(run())
