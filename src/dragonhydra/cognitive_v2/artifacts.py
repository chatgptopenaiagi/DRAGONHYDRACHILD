"""Explicit immutable cognitive handoffs. No private IPC or arbitrary file reader."""
from pathlib import Path
import re

from ..localai.contracts import canonical_bytes, content_hash, strict_json

PROJECT_RUNTIME = Path(__file__).resolve().parents[3]/'runtime/cognitive-v2'
KINDS = frozenset({'snapshots','requests','actor_results','reconciliations','receipts','experiments'})
FORBIDDEN = frozenset({'chain_of_thought','reasoning_content','scratchpad','hidden_reasoning','cot',
    'password','api_key','access_token','authorization','cookie','private_key','raw_commandline','raw_prompt'})

def _inspect(value):
    if isinstance(value,dict):
        if any(str(k).lower() in FORBIDDEN for k in value): raise ValueError('UNTRUSTED_CONTEXT')
        for v in value.values(): _inspect(v)
    elif isinstance(value,(list,tuple)):
        for v in value: _inspect(v)

def _safe_root(root):
    path=Path(root).absolute()
    if '..' in path.parts: raise ValueError('PATH_TRAVERSAL_FORBIDDEN')
    for part in (path,*path.parents):
        if part.is_symlink() or part.is_junction(): raise ValueError('LINKED_PATH_FORBIDDEN')
    path=path.resolve()
    allowed=PROJECT_RUNTIME.resolve()
    if path!=allowed and allowed not in path.parents: raise ValueError('CHILD_RUNTIME_REQUIRED')
    return path

class ArtifactStore:
    def __init__(self,root=PROJECT_RUNTIME,*,max_files=4096,max_bytes=256*1024*1024):
        self.root=_safe_root(root)
        if type(max_files) is not int or not 1<=max_files<=4096 or type(max_bytes) is not int or not 1<=max_bytes<=256*1024*1024:
            raise ValueError('INVALID_QUOTA')
        self.max_files,self.max_bytes=max_files,max_bytes
    def _path(self,kind,artifact_hash):
        if kind not in KINDS or re.fullmatch('[0-9a-f]{64}',artifact_hash or '') is None:
            raise ValueError('INVALID_ARTIFACT_REFERENCE')
        self.root=_safe_root(self.root)
        path=self.root/kind/(artifact_hash+'.json')
        if path.is_symlink() or path.parent.is_symlink() or path.parent.is_junction():
            raise ValueError('LINKED_PATH_FORBIDDEN')
        return path
    def put(self,kind,payload):
        _inspect(payload)
        raw=canonical_bytes(payload)
        if len(raw)>262144: raise ValueError('REQUEST_TOO_LARGE')
        digest=content_hash(payload)
        path=self._path(kind,digest)
        if path.exists():
            if path.read_bytes()!=raw: raise ValueError('ARTIFACT_HASH_MISMATCH')
            return digest
        existing=list(self.root.rglob('*.json')) if self.root.exists() else []
        if len(existing)>=self.max_files or sum(p.stat().st_size for p in existing)+len(raw)>self.max_bytes:
            raise ValueError('ARTIFACT_QUOTA_EXCEEDED')
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream: stream.write(raw)
        return digest
    def get(self,kind,digest):
        path=self._path(kind,digest)
        if not path.is_file(): raise ValueError('MEMORY_REFERENCE_MISSING')
        if path.stat().st_size>262144: raise ValueError('REQUEST_TOO_LARGE')
        value=strict_json(path.read_bytes(),max_bytes=262144)
        _inspect(value)
        if content_hash(value)!=digest: raise ValueError('ARTIFACT_HASH_MISMATCH')
        return value

def export_codex_request(store,snapshot,task_kind):
    """The receiver reads data, then submits a separate typed actor artifact."""
    snapshot_ref=store.put('snapshots',snapshot.to_dict())
    packet={'schema_version':'2','kind':'CODEX_REVIEW_REQUEST','actor_id':'CODEX',
        'task_kind':task_kind,'state_hash':snapshot.state_hash,'snapshot_ref':snapshot_ref,
        'permitted_product':'STRUCTURED_NON_EVIDENCE_CONCLUSIONS','execution_authority':'NONE'}
    return store.put('requests',packet)

def load_codex_result(store,reference,snapshot):
    from .contracts import CognitiveActorResult
    result=CognitiveActorResult.from_dict(store.get('actor_results',reference))
    if result.actor_id!='CODEX': raise ValueError('UNTRUSTED_CONTEXT')
    if result.state_hash!=snapshot.state_hash: raise ValueError('STATE_CHANGED_SINCE_PROPOSAL')
    return result
