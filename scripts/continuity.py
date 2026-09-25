"""Conservative project continuity: observe and brief, never restore or execute actions."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dragonhydra.continuity import (CONTINUITY_ROOT,capture,load_public,observe,read_capsule,
    verify_capsule,compare_states,resume_briefing)

def main():
    if sys.version_info[:2]!=(3,14):raise SystemExit('Python 3.14 is required')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('capture','status','verify','resume-info','compare'))
    parser.add_argument('--capture-id',help='Existing capsule identifier, never a filesystem path')
    parser.add_argument('--repository-only',action='store_true',help='Skip fresh ARX probes; machine delta remains UNKNOWN')
    args=parser.parse_args()
    if args.command=='capture':
        if args.capture_id or args.repository_only:parser.error('capture always uses a new identifier and bounded observations')
        folder=capture();result=verify_capsule(CONTINUITY_ROOT,folder.name)
        result['capsule_location']=str(folder)
    elif args.command=='verify':result=verify_capsule(CONTINUITY_ROOT,args.capture_id)
    else:
        public=load_public();verification=verify_capsule(CONTINUITY_ROOT,args.capture_id)
        old=read_capsule(CONTINUITY_ROOT,args.capture_id) if verification['passed'] else None
        current=observe(machine=not args.repository_only,public=public)
        delta=compare_states(old,current) if old else {'changed':None,'changes':[],'status':'LOCAL_CAPSULE_UNAVAILABLE_OR_INVALID'}
        if args.repository_only:
            delta['changes']=[v for v in delta['changes'] if v['reason_code']!='MACHINE_CHANGED']
            delta['machine_comparison']='NOT_OBSERVED'
            delta['changed']=bool(delta['changes']) if old else None
        if args.command=='resume-info':result=resume_briefing(public,current=current,capsule=old,delta=delta)
        else:result={'project_id':'DRAGONHYDRACHILD','continuity_health':'VERIFIED' if old else 'PORTABLE_ONLY',
            'verification':verification,'captured_commit':old['repository'].get('git_commit') if old else None,
            'current_commit':current['repository']['git_commit'],'branch':current['repository']['branch'],
            'delta':delta,'next_action':public['resume-manifest'].get('next_action'),'automatic_restoration':'DISABLED'}
    print(json.dumps(result,indent=2,ensure_ascii=True))
    return 1 if args.command=='verify' and not result['passed'] else 0

if __name__=='__main__':raise SystemExit(main())
