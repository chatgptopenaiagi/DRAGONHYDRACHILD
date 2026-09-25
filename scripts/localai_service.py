"""Start the explicitly selected preserved model and CHILD's bounded gateway.

Engineering command only; no service installation or automatic reboot startup.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import json
import os

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dragonhydra.localai.runtime import LlamaRuntime,MODEL_PROFILES,create_token,local_runtime_dir
from dragonhydra.localai.gateway import AnalysisEngine,BoundedHTTPServer

def main():
    if sys.version_info[:2]!=(3,14): raise SystemExit('Python 3.14 is mandatory')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',choices=sorted(MODEL_PROFILES),default='qwen3-4b')
    parser.add_argument('--cpu-only',action='store_true')
    parser.add_argument('--stop',action='store_true',help='Request orderly stop of this CHILD gateway only')
    args=parser.parse_args()
    root=local_runtime_dir(ROOT/'runtime/localai')
    if args.stop:
        active=json.loads((root/'active.json').read_text(encoding='utf-8'))
        name=active['session']
        if Path(name).name!=name or not name.startswith('service-'): raise SystemExit('Invalid session')
        with (root/(name+'.stop')).open('x',encoding='ascii') as stream: stream.write('OWNER_ENGINEERING_STOP')
        print('Stop requested for '+name)
        return
    session=root/('service-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    runtime=LlamaRuntime(args.model,session,cpu_only=args.cpu_only)
    token=create_token(root/'gateway.key')
    engine=AnalysisEngine(runtime,session)
    server=BoundedHTTPServer(('127.0.0.1',8083),engine,token)
    server.timeout=1
    try:
        runtime.start()
        (root/'active.json').write_text(json.dumps({'session':session.name,'pid':os.getpid(),'backend_pid':runtime.process.pid,
            'model_id':args.model,'started_at':datetime.now(timezone.utc).isoformat()},indent=2),encoding='utf-8')
        engine.publish_status()
        print('READY: authenticated 127.0.0.1:8083; '+args.model,flush=True)
        last=time.monotonic()
        while runtime.healthy():
            if (root/(session.name+'.stop')).exists(): break
            if engine.metrics['request_count']>=256 or sum(p.stat().st_size for p in session.rglob('*') if p.is_file())>64*1024*1024:
                engine.metrics['last_failure']='SESSION_QUOTA_REACHED'
                break
            server.handle_request()
            if time.monotonic()-last>=5:
                engine.publish_status(); last=time.monotonic()
    except KeyboardInterrupt: pass
    finally:
        server.server_close()
        runtime.stop()
        engine.publish_status(stopped=True)

if __name__=='__main__': main()
