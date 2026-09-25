"""Small, read-only continuity capture. This is an awareness aid, not a backup/restorer."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
CONTINUITY_ROOT = ROOT / 'runtime/continuity'
PROJECT = 'DRAGONHYDRACHILD'
VERSION = '1'
KINDS = ('repository','machine','runtime','environment','tools','models','tests','experiments',
         'decisions','limitations','important-files','resume')
REQUIRED = {'repository','machine','resume','important-files'}
MAX_FILE = 262144
MAX_CAPSULE = 2 * 1024 * 1024
SENSITIVE_KEYS = re.compile(r'(?i)^(password|passwd|secret|secrets|token|tokens|access_token|refresh_token|api_key|gateway_key|authorization|cookie|cookies|private_key|commandline|command_line|raw_commandline|environment_variables|chain_of_thought|reasoning_content)$')
SENSITIVE_VALUE = re.compile(r'(?i)(?:-----BEGIN [A-Z ]*PRIVATE KEY|\bBearer\s+\S+|\bgh[pousr]_[A-Za-z0-9]{12,}|\bgithub_pat_[A-Za-z0-9_]{12,}|\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}|(?:password|passwd|api[_ -]?key|access[_ -]?token)\s*[=:]\s*\S+|https?://[^\s/]+@|[?&](?:token|key|password)=)')

def utc_now(): return datetime.now(timezone.utc).isoformat()
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf-8')
def digest(value): return hashlib.sha256(canonical(value)).hexdigest()

def sanitize(value):
    """Defense in depth; capture producers already project explicit safe fields."""
    if isinstance(value,dict):
        return {str(k):'OMITTED' if SENSITIVE_KEYS.fullmatch(str(k)) else sanitize(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [sanitize(v) for v in value]
    if isinstance(value,str): return 'OMITTED' if SENSITIVE_VALUE.search(value) else value
    if value is None or type(value) in (bool,int,float):
        canonical(value)
        return value
    raise ValueError('UNSUPPORTED_MANIFEST_VALUE')

def _json(raw):
    if len(raw)>MAX_FILE: raise ValueError('FILE_TOO_LARGE')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('DUPLICATE_JSON_KEY')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('NONFINITE_JSON')))

def _clock(value):
    if type(value) is not str or len(value)>40:raise ValueError('INVALID_TIMESTAMP')
    stamp=datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds()!=0:raise ValueError('UTC_REQUIRED')

def validate_document(value,schema_name=None):
    if type(value) is not dict:raise ValueError('INVALID_SCHEMA')
    for key in ('schema_name','schema_version','created_at','project_id','capture_id'):
        if key not in value:raise ValueError('MISSING_SCHEMA_FIELD')
    if value['schema_version']!=VERSION or value['project_id']!=PROJECT:raise ValueError('UNSUPPORTED_SCHEMA')
    if type(value['schema_name']) is not str or not re.fullmatch(r'dragonhydra\.continuity\.[a-z-]+',value['schema_name']):raise ValueError('INVALID_SCHEMA_NAME')
    if schema_name and value['schema_name']!=schema_name:raise ValueError('WRONG_SCHEMA_NAME')
    _clock(value['created_at'])
    if value['capture_id'] is not None:_capture_id(value['capture_id'])
    if sanitize(value)!=value:raise ValueError('SECRET_MATERIAL_REJECTED')
    canonical(value)
    return True

def _capture_id(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}',value) is None:raise ValueError('INVALID_CAPTURE_ID')
    return value

def _plain(path):
    path=Path(path).absolute()
    if '..' in path.parts:raise ValueError('PATH_TRAVERSAL')
    for item in (path,*path.parents):
        if item.is_symlink() or item.is_junction():raise ValueError('LINKED_PATH_FORBIDDEN')
    return path

def _safe_base(base):
    path=_plain(base)
    allowed=_plain(CONTINUITY_ROOT)
    if path!=allowed and allowed not in path.parents:raise ValueError('CHILD_CONTINUITY_REQUIRED')
    return path

def _envelope(kind,data,capture_id,created_at):
    return {'schema_name':'dragonhydra.continuity.'+kind,'schema_version':VERSION,'project_id':PROJECT,
        'capture_id':capture_id,'created_at':created_at,'data':sanitize(data)}

def _read(path):
    path=_plain(path)
    if not path.is_file() or path.stat().st_size>MAX_FILE:raise ValueError('MISSING_OR_OVERSIZED_FILE')
    return _json(path.read_bytes())

def _atomic_pointer(base,payload):
    destination=_plain(base/'latest.json')
    temporary=base/('latest-'+uuid.uuid4().hex+'.tmp')
    with temporary.open('xb') as stream:stream.write(canonical(payload))
    temporary.replace(destination)

def create_capsule(base,payloads,*,capture_id=None,created_at=None):
    base=_safe_base(base)
    if type(payloads) is not dict or not REQUIRED<=set(payloads) or set(payloads)-set(KINDS):raise ValueError('INVALID_CAPSULE_PAYLOADS')
    if any(type(payloads[key]) is not dict for key in REQUIRED):raise ValueError('INVALID_CAPSULE_PAYLOADS')
    stamp=created_at or utc_now();_clock(stamp)
    payloads={kind:sanitize(payloads.get(kind,{})) for kind in KINDS}
    head=payloads['repository'].get('git_commit','unknown')
    capture_id=_capture_id(capture_id or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+str(head)[:8]+'_'+uuid.uuid4().hex[:8])
    folder=_plain(base/'capsules'/capture_id)
    documents={kind+'.json':canonical(_envelope(kind,payloads.get(kind,{}),capture_id,stamp)) for kind in KINDS}
    readme=('Continuity capsule '+capture_id+'\n\nProject: DRAGONHYDRACHILD\n'
        'This immutable local capsule reconstructs awareness; it never restores or starts software.\n'
        'Verify hashes before use. Historical validation is not current liveness.\n'
        'Known model hashes are reused without reading model weights. No credentials or database copies are included.\n'
        'Read resume.json, repository.json and manifest.json, then compare current state.\n').encode()
    documents['CAPSULE_README.md']=readme
    if any(len(raw)>MAX_FILE for raw in documents.values()) or sum(map(len,documents.values()))>MAX_CAPSULE:raise ValueError('CAPSULE_TOO_LARGE')
    manifest=_envelope('manifest',{'files':{name:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in sorted(documents.items())},
        'git_commit':head,'git_tree':payloads['repository'].get('git_tree'),'branch':payloads['repository'].get('branch'),
        'delta_baseline_hash':digest(_semantic(payloads)),
        'integrity_scope':'LOCAL_HASHES_NOT_SIGNATURES','evidence_strategy':'REFERENCE_LARGE_ASSETS'},capture_id,stamp)
    documents['manifest.json']=canonical(manifest)
    folder.parent.mkdir(parents=True,exist_ok=True)
    folder.mkdir(exist_ok=False)
    for name,raw in documents.items():
        with (folder/name).open('xb') as stream:stream.write(raw)
    result=verify_capsule(base,capture_id)
    if not result['passed']:raise ValueError('CAPSULE_VERIFICATION_FAILED')
    pointer=_envelope('latest',{'capsule_manifest_hash':result['manifest_hash']},capture_id,stamp)
    _atomic_pointer(base,pointer)
    return folder

def _selected(base,capture_id):
    base=_safe_base(base)
    pointer=None
    if capture_id is None:
        pointer=_read(base/'latest.json');validate_document(pointer,'dragonhydra.continuity.latest')
        if set(pointer)!={'schema_name','schema_version','project_id','capture_id','created_at','data'} or set(pointer['data'])!={'capsule_manifest_hash'}:raise ValueError('INVALID_LATEST_POINTER')
        capture_id=pointer['capture_id']
    return _plain(base/'capsules'/_capture_id(capture_id)),pointer

def verify_capsule(base,capture_id=None):
    result={'passed':False,'capture_id':capture_id,'manifest_hash':None,'errors':[]}
    try:
        folder,pointer=_selected(base,capture_id);capture_id=folder.name;result['capture_id']=capture_id
        manifest=_read(folder/'manifest.json');validate_document(manifest,'dragonhydra.continuity.manifest')
        if manifest['capture_id']!=capture_id:raise ValueError('CAPTURE_ID_MISMATCH')
        mh=digest(manifest);result['manifest_hash']=mh
        if pointer and pointer['data']['capsule_manifest_hash']!=mh:raise ValueError('POINTER_HASH_MISMATCH')
        if set(manifest)!={'schema_name','schema_version','project_id','capture_id','created_at','data'}:raise ValueError('INVALID_MANIFEST')
        data=manifest['data']
        if set(data)!={'files','git_commit','git_tree','branch','delta_baseline_hash','integrity_scope','evidence_strategy'}:raise ValueError('INVALID_MANIFEST')
        expected={kind+'.json' for kind in KINDS}|{'CAPSULE_README.md'}
        if set(data['files'])!=expected or {p.name for p in folder.iterdir()}!=expected|{'manifest.json'}:raise ValueError('UNEXPECTED_OR_MISSING_FILES')
        total=0;payloads={}
        for name,record in data['files'].items():
            path=_plain(folder/name)
            if not path.is_file() or path.stat().st_size>MAX_FILE:raise ValueError('MISSING_OR_OVERSIZED_FILE')
            raw=path.read_bytes();total+=len(raw)
            if set(record)!={'sha256','bytes'} or record['bytes']!=len(raw) or record['sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('FILE_HASH_MISMATCH')
            if name.endswith('.json'):
                doc=_json(raw);kind=name[:-5];validate_document(doc,'dragonhydra.continuity.'+kind)
                if set(doc)!={'schema_name','schema_version','project_id','capture_id','created_at','data'} or doc['capture_id']!=capture_id or doc['created_at']!=manifest['created_at']:raise ValueError('IDENTITY_MISMATCH')
                payloads[kind]=doc['data']
            elif SENSITIVE_VALUE.search(raw.decode('utf-8')):raise ValueError('SECRET_MATERIAL_REJECTED')
        if total>MAX_CAPSULE:raise ValueError('CAPSULE_TOO_LARGE')
        if data['delta_baseline_hash']!=digest(_semantic(payloads)):raise ValueError('BASELINE_HASH_MISMATCH')
        for key in ('git_commit','git_tree'):
            if data[key]!=payloads['repository'].get(key) or (data[key] is not None and re.fullmatch('[0-9a-f]{40,64}',data[key]) is None):raise ValueError('INVALID_GIT_REFERENCE')
        if data['branch']!=payloads['repository'].get('branch'):raise ValueError('BRANCH_MISMATCH')
        result['passed']=True
    except (ValueError,OSError,KeyError,TypeError,UnicodeError) as exc:
        result['errors']=[str(exc) if isinstance(exc,ValueError) else type(exc).__name__]
    return result

def read_capsule(base,capture_id=None):
    result=verify_capsule(base,capture_id)
    if not result['passed']:raise ValueError('CAPSULE_INTEGRITY_FAILED')
    folder,_=_selected(base,capture_id)
    return {kind:_read(folder/(kind+'.json'))['data'] for kind in KINDS}

def _run(args,*,root=ROOT,timeout=10):
    run=subprocess.run(args,cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
    if run.returncode:raise ValueError('READ_ONLY_COMMAND_FAILED')
    if len(run.stdout)>131072:raise ValueError('OBSERVATION_TOO_LARGE')
    return run.stdout.strip()

def repository_state(root,remote=False):
    root=Path(root)
    def git(*args):return _run(['git','--no-optional-locks',*args],root=root)
    commit=git('rev-parse','HEAD');branch=git('branch','--show-current')
    try:origin=sanitize(git('remote','get-url','origin'))
    except ValueError:origin=None
    status=git('status','--porcelain=v1','--untracked-files=normal')
    value={'path':str(root),'branch':branch,'git_commit':commit,'git_tree':git('rev-parse','HEAD^{tree}'),
        'origin':origin,'working_tree_clean':not status,'status':sanitize(status.splitlines()),
        'staged_files':sanitize(git('diff','--cached','--name-only').splitlines()),
        'modified_files':sanitize(git('diff','--name-only').splitlines()),
        'untracked_files':sanitize(git('ls-files','--others','--exclude-standard').splitlines()),
        'remote_branch_head':None,'remote_verification':'NOT_QUERIED'}
    if remote and branch and origin not in (None,'OMITTED'):
        try:
            found=git('ls-remote','origin','refs/heads/'+branch)
            value['remote_branch_head']=found.split()[0] if found else None
            value['remote_verification']='OBSERVED' if found else 'BRANCH_NOT_PUBLISHED'
        except (OSError,ValueError,subprocess.SubprocessError):value['remote_verification']='UNAVAILABLE'
    return value

IGNORED_CLOCKS={'created_at','observed_at','available_at','as_of_at','captured_at','checked_at','modified_time','uptime_seconds','load_percent','available_bytes','utilization_percent','memory_used_mib','last_latency_ms','request_count','success_count','failure_count','last_success_at'}
def _semantic(value):
    if isinstance(value,dict):return {k:_semantic(v) for k,v in sorted(value.items()) if k not in IGNORED_CLOCKS}
    if isinstance(value,list):return sorted((_semantic(v) for v in value),key=lambda v:canonical(v))
    return value

def compare_states(before,after):
    changes=[]
    def add(code,a,b):
        if _semantic(a)!=_semantic(b):changes.append({'reason_code':code,'before':sanitize(a),'after':sanitize(b)})
    a,b=before.get('repository',{}),after.get('repository',{})
    for key,code in (('git_commit','REPOSITORY_COMMIT_CHANGED'),('branch','BRANCH_CHANGED'),('working_tree_clean','WORKING_TREE_CHANGED'),('status','WORKING_TREE_DETAILS_CHANGED')):add(code,a.get(key),b.get(key))
    old_machine,new_machine=before.get('machine',{}),after.get('machine',{})
    if new_machine.get('status')!='NOT_OBSERVED':
        if 'observations' in old_machine and 'observations' in new_machine:
            old={r['entity_id']:r for r in old_machine['observations']}
            new={r['entity_id']:r for r in new_machine['observations']}
            for key in sorted(set(old)|set(new)):
                a,b=old.get(key),new.get(key);kind=(a or b)['kind']
                code={'listener':'PORT_CHANGED','process':'PROCESS_OWNERSHIP_CHANGED','gpu':'GPU_CHANGED',
                    'service':'SERVICE_STATE_CHANGED','task':'PROJECT_TASK_CHANGED','tool':'DEPENDENCY_CHANGED',
                    'repository':'MACHINE_REPOSITORY_CHANGED'}.get(kind,'MACHINE_COMPONENT_CHANGED')
                if kind in ('listener','process') and (a is None or b is None):
                    code=('PORT_' if kind=='listener' else 'PROCESS_')+('APPEARED' if a is None else 'DISAPPEARED')
                add(code,a,b)
            add('PROBE_HEALTH_CHANGED',old_machine.get('status'),new_machine.get('status'))
        else:add('MACHINE_CHANGED',old_machine,new_machine)
    for section,code in (('environment','PYTHON_OR_ENVIRONMENT_CHANGED'),('runtime','RUNTIME_CHANGED'),('tools','DEPENDENCY_CHANGED'),('models','MODEL_METADATA_CHANGED')):
        add(code,before.get(section),after.get(section))
    a=before.get('important-files',{});b=after.get('important-files',{})
    def index(value):
        rows=value.get('files',[]) if isinstance(value,dict) else value
        return {r['path']:r for r in rows if isinstance(r,dict) and 'path' in r}
    for path,old in index(a).items():
        current=index(b).get(path)
        if current is None or (old.get('exists') and not current.get('exists')):add('IMPORTANT_FILE_MISSING',path,None)
        elif old.get('sha256') and old.get('sha256')!=current.get('sha256'):add('IMPORTANT_FILE_HASH_CHANGED',{'path':path,'sha256':old['sha256']},{'path':path,'sha256':current.get('sha256')})
    return {'changed':bool(changes),'changes':changes[:64],'omitted_change_count':max(0,len(changes)-64),
        'machine_comparison':'NOT_OBSERVED' if new_machine.get('status')=='NOT_OBSERVED' else 'OBSERVED',
        'timestamp_only_noise_ignored':True,'model_metadata_time_changes_retained':True}

def load_public(root=ROOT):
    folder=_plain(Path(root)/'docs/continuity/manifests')
    value={}
    for name in ('current-state','repository-state','capabilities','experiments','tests','limitations','important-artifacts','resume-manifest','decisions'):
        path=folder/(name+'.json')
        if path.exists():
            doc=_read(path);validate_document(doc);value[name]=doc
    if 'current-state' not in value or 'resume-manifest' not in value:raise ValueError('PUBLIC_CONTINUITY_UNAVAILABLE')
    return value

def resume_briefing(public,current=None,capsule=None,delta=None):
    state=public.get('current-state',public);resume=public.get('resume-manifest',state)
    repo=(current or {}).get('repository',{}) or (capsule or {}).get('repository',{})
    machine=(current or {}).get('machine',{}) or (capsule or {}).get('machine',{})
    brief={'PROJECT':state.get('project_id',PROJECT),'LAST_CHECKPOINT':resume.get('current_checkpoint',state.get('current_checkpoint')),
        'BRANCH':repo.get('branch',state.get('branch')),'COMMIT':repo.get('git_commit',state.get('git_commit')),
        'MATURITY':state.get('maturity','PARTIAL_EXPERIMENTAL'),'COMPLETED':state.get('completed',[]),
        'ACTIVE_SYSTEMS':state.get('active_systems',[]),'KNOWN_GOOD_TESTS':public.get('tests',{}),
        'KNOWN_FAILURES':state.get('known_failures',[]),'LIMITATIONS':public.get('limitations',{}),
        'MACHINE_CONTEXT':{'observation_status':machine.get('status','LOCAL_CAPSULE_UNAVAILABLE'),
            'summary':{k:v for k,v in machine.get('summary',{}).items() if k in ('os','gpu')},'observation_time':machine.get('observed_at')},
        'WHAT_CHANGED':[v.get('reason_code') for v in (delta or {}).get('changes',[])],
        'DO_NOT_REPEAT':resume.get('do_not_repeat',[]),'NEXT_ACTION':resume.get('next_action',state.get('next_action','Verify continuity before action.')),
        'AUTHORITATIVE_FILES':resume.get('authoritative_files',state.get('authoritative_files',[])),
        'LOCAL_CAPSULE_AVAILABLE':capsule is not None,'AUTOMATIC_RESTORATION':'DISABLED'}
    brief=sanitize(brief)
    if len(canonical(brief))>24576:raise ValueError('BRIEFING_TOO_LARGE')
    return brief

def _machine():
    from .machine import capture_machine
    snapshot=capture_machine()
    ports={8082,8083,11434,11435}
    rows=[]
    for o in snapshot.observations:
        if o.kind=='listener' and (o.data.get('port') not in ports or o.data.get('exposure')!='LOOPBACK'):continue
        if o.kind not in {'os','cpu','ram','gpu','process','service','listener','tool','repository','task','conda_environment','distribution'}:continue
        rows.append({'kind':o.kind,'entity_id':o.entity_id,'status':o.status,'observed_at':o.observed_at,'attributes':o.data})
    return {'status':snapshot.health.status,'observed_at':snapshot.as_of_at,'summary':{
        'os':next((o.data.get('name') for o in snapshot.observations if o.kind=='os'),None),
        'gpu':next((o.data.get('name') for o in snapshot.observations if o.kind=='gpu'),None)},
        'observations':rows,'probe_statuses':[{'probe_id':r.probe_id,'status':r.status,'failure_state':r.failure_state} for r in snapshot.receipts],
        'limitations':['BOUNDED_ARX_ALLOWLIST','NO_MODEL_INFERENCE','NO_MACHINE_WIDE_FILE_SCAN']}

def _tools():
    result={}
    for name,args in (('git',['git','--version']),('gh',['gh','--version'])):
        path=shutil.which(name)
        try:version=_run(args).splitlines()[0] if path else None
        except (ValueError,OSError,subprocess.SubprocessError):version=None
        result[name]={'path':path,'version':version}
    result['codex']={'path':shutil.which('codex'),'version':'UNKNOWN_NOT_EXECUTED'}
    if result['gh']['path']:
        try:result['gh']['authentication_present']=subprocess.run(['gh','auth','status'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8).returncode==0
        except (OSError,subprocess.SubprocessError):result['gh']['authentication_present']=None
    return result

def _important_files(root,public):
    paths=['AGENTS.md','README_CHILD_EXPERIMENT.md','docs/COGNITIVE_AWARENESS_V2.md','docs/COGNITIVE_V2_PROGRESS.md',
        'docs/CHILD_DECISIONS.md','docs/COGNITIVE_SECURITY_MODEL.md','docs/evidence/cognitive_v2_validation.json',
        'config/localai_runtime_manifest.json','scripts/continuity.py','src/dragonhydra/continuity.py',
        'docs/continuity/CURRENT_STATE.md','docs/continuity/NEXT_ACTION.md']
    rows=[]
    for name in paths:
        p=_plain(root/name);exists=p.is_file()
        rows.append({'path':name,'exists':exists,'type':'FILE','size':p.stat().st_size if exists else None,
            'modified_time':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat() if exists else None,
            'classification':'DOCUMENTATION' if name.startswith('docs/') else 'CONFIGURATION' if name.startswith('config/') else 'SOURCE','safe_to_commit':True,
            'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if exists and p.stat().st_size<=MAX_FILE else None,
            'owner':PROJECT,'purpose':'Authoritative reconstruction input','reconstruction_priority':'HIGH'})
    for name,kind,purpose in (('runtime/checkpoints/cognitive-awareness-v2-20260925T214532Z','CHECKPOINT','Prior V2 full local evidence'),
        ('runtime/child/predictions/00000001.json','EVIDENCE','Original immutable prospective prediction'),
        ('runtime/sqlserver-lab','DATABASE','Live CHILD database files; no copy or content read'),
        ('runtime/localai','RUNTIME','Owned gateway receipts and local credentials; no recursive read')):
        p=_plain(root/name);exists=p.exists();is_file=p.is_file()
        rows.append({'path':name,'exists':exists,'type':'FILE' if is_file else 'DIRECTORY','size':p.stat().st_size if exists and is_file else None,
            'modified_time':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat() if exists else None,
            'classification':kind,'safe_to_commit':False,'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if exists and is_file and p.stat().st_size<=MAX_FILE else None,
            'owner':PROJECT,'purpose':purpose,'reconstruction_priority':'HIGH'})
    return {'files':rows,'strategy':'IMPORTANT_SMALL_FILES_ONLY','large_evidence':'REFERENCES_ONLY'}

def observe(root=ROOT,*,remote=False,machine=True,public=None):
    root=Path(root);public=public or load_public(root)
    repo=repository_state(root,remote=remote)
    try:host=_machine() if machine else {'status':'NOT_OBSERVED'}
    except (OSError,ValueError,subprocess.SubprocessError):host={'status':'MACHINE_PROBE_FAILED'}
    runtime={}
    active=root/'runtime/localai/active.json';status=root/'runtime/localai/status.json'
    for label,path,fields in [('recorded_active',active,('session','pid','backend_pid','model_id','started_at')),
        ('recorded_status',status,('status','model_id','model_hash','runtime_id','checked_at','updated_at','created_at','last_success_at'))]:
        try:
            value=_read(path);runtime[label]={k:value[k] for k in fields if k in value}
        except (OSError,ValueError):runtime[label]={'status':'UNAVAILABLE'}
    runtime['liveness']='PROCESS_AND_PORT_OBSERVATION_ONLY_NO_TOKEN_READ'
    runtime['credentials']=[{'location_class':'LOCAL_SECRET','credential_required':True,
        'credential_present':_plain(root/name).is_file(),'credential_value':'OMITTED','path':name}
        for name in ('runtime/localai/gateway.key','runtime/secrets/child-maria-web.local.json')]
    from .localai.runtime import MODEL_PROFILES, RUNTIME_ID, SERVER_HASH
    models=[]
    for model_id,profile in MODEL_PROFILES.items():
        path=_plain(Path('C:/LocalAI/models')/profile['file'])
        try:metadata=path.stat();size=metadata.st_size;modified=metadata.st_mtime_ns
        except OSError:size=None;modified=None
        models.append({'model_id':model_id,'path':str(path),'exists':size is not None,'size':size,'mtime_ns':modified,
            'known_sha256':profile['sha256'],'hash_verification':'REUSED_NOT_REHASHED',
            'hash_source':'docs/evidence/cognitive_v2_validation.json','runtime_id':RUNTIME_ID,'known_server_sha256':SERVER_HASH,
            'safe_to_commit':False,'classification':'MODEL','reconstruction_priority':'HIGH'})
    env={'python_executable':sys.executable,'python_version':sys.version,'python_environment':Path(sys.executable).parent.name,
         'platform':sys.platform,'timezone':datetime.now().astimezone().tzname(),'package_scan':'NOT_REQUIRED'}
    return sanitize({'repository':repo,'machine':host,'runtime':runtime,'environment':env,'tools':_tools(),'models':models,
        'important-files':_important_files(root,public)})

def capture(base=CONTINUITY_ROOT,*,remote=True):
    public=load_public();data=observe(remote=remote,public=public)
    data.update({'tests':public.get('tests',{}),'experiments':public.get('experiments',{}),'decisions':public.get('decisions',{}),
        'limitations':public.get('limitations',{}),'resume':resume_briefing(public,current=data)})
    return create_capsule(base,data)
