"""Explicit engineering launcher. Never a model-accessible capability.

Preserved assets are read-only inputs. No installer, service registration, shell,
download, automatic restart, or legacy LocalAI executable is invoked.
"""
from dataclasses import dataclass, field
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
import threading
import urllib.request
from urllib.parse import urlsplit

RUNTIME_ID = 'llama-b10665-ca3d5a3e1'
SERVER_HASH = '20a83f9ed723c6307749863842657da86918e8b612a3eaa44fe635d147341550'
MODEL_PROFILES = {
    'qwen3-4b': {'file': 'Qwen3-4B-Q4_K_M/Qwen3-4B-Q4_K_M.gguf',
                 'sha256': '7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5',
                 'gpu_layers': 99, 'cpu_moe': False},
    'qwen3-coder-30b': {'file': 'Qwen3-Coder-30B-A3B-Instruct-Q4_K_M/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf',
                      'sha256': 'fadc3e5f8d42bf7e894a785b05082e47daee4df26680389817e2093056f088ad',
                      'gpu_layers': 10, 'cpu_moe': True},
}

def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def require_plain_path(path):
    path = Path(path).absolute()
    if '..' in path.parts:
        raise ValueError('PATH_TRAVERSAL_FORBIDDEN')
    for candidate in (path, *path.parents):
        if candidate.is_symlink() or candidate.is_junction():
            raise ValueError('LINKED_PATH_FORBIDDEN')
    return path.resolve()

def local_runtime_dir(root):
    project = Path(__file__).resolve().parents[3]
    allowed = require_plain_path(project/'runtime/localai')
    root = require_plain_path(root)
    if root != allowed and allowed not in root.parents:
        raise ValueError('CHILD_RUNTIME_DIRECTORY_REQUIRED')
    root.mkdir(parents=True, exist_ok=True)
    return root

def create_token(path):
    """Create a new token; existing values are retained, never printed."""
    path = require_plain_path(path)
    if not path.exists():
        with path.open('x', encoding='ascii') as stream:
            stream.write(secrets.token_hex(32))
    token = path.read_text(encoding='ascii').strip()
    if len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
        raise ValueError('INVALID_AUTH_TOKEN')
    if os.name == 'nt':
        # Only new recovery files. No historical ACL is changed.
        identity = subprocess.run(['whoami'], capture_output=True, text=True, check=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r',
                        identity+':F', '*S-1-5-18:F'], capture_output=True, check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        path.chmod(0o600)
    return token

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('REDIRECT_FORBIDDEN')

def local_json(url, *, token, payload=None, timeout=30, limit=16384):
    parts=urlsplit(url)
    if (parts.scheme!='http' or parts.hostname!='127.0.0.1' or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in ('/health','/v1/models','/v1/chat/completions')):
        raise ValueError('LOOPBACK_ENDPOINT_REQUIRED')
    body = None if payload is None else json.dumps(payload, allow_nan=False).encode()
    connection=http.client.HTTPConnection('127.0.0.1',parts.port,timeout=timeout)
    expired=threading.Event()
    def close_at_deadline():
        expired.set()
        if connection.sock:
            try: connection.sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        connection.close()
    watchdog=threading.Timer(timeout,close_at_deadline)
    watchdog.daemon=True
    watchdog.start()
    try:
        connection.request('GET' if body is None else 'POST',parts.path,body=body,headers={
            'Authorization':'Bearer '+token,'Content-Type':'application/json','Connection':'close'})
        response=connection.getresponse()
        if response.status!=200: raise OSError('BACKEND_HTTP_FAILURE')
        if response.getheader('Content-Type','').split(';')[0].strip().lower()!='application/json':
            raise ValueError('INVALID_RESPONSE')
        raw = response.read(limit+1)
        if expired.is_set(): raise TimeoutError('TIMEOUT')
    except (OSError,http.client.HTTPException):
        if expired.is_set(): raise TimeoutError('TIMEOUT') from None
        raise
    finally:
        watchdog.cancel()
        connection.close()
    if len(raw)>limit:
        raise ValueError('RESPONSE_TOO_LARGE')
    from .contracts import strict_json
    return strict_json(raw,max_bytes=limit)

@dataclass
class LlamaRuntime:
    model_id: str
    workdir: Path
    port: int = 8082
    cpu_only: bool = False
    context_size: int = 4096
    process: object = field(default=None, init=False, repr=False)
    token: str = field(default='', init=False, repr=False)
    startup_seconds: float = field(default=0.0, init=False)
    _streams: list = field(default_factory=list, init=False, repr=False)

    @property
    def identity(self):
        return {'model_id':self.model_id, 'model_hash':MODEL_PROFILES[self.model_id]['sha256'],
                'runtime_id':RUNTIME_ID, 'context_size':self.context_size,
                'execution_mode':'CPU' if self.cpu_only else 'HYBRID_CPU_GPU' if MODEL_PROFILES[self.model_id]['cpu_moe'] else 'GPU'}

    def start(self, *, timeout=180):
        if self.process is not None or self.model_id not in MODEL_PROFILES:
            raise ValueError('INVALID_RUNTIME_STATE')
        if type(self.port) is not int or not 1024<=self.port<=65535:
            raise ValueError('INVALID_PORT')
        if self.context_size != 4096 or not 1<=timeout<=240:
            raise ValueError('INVALID_RESOURCE_LIMIT')
        self.workdir = local_runtime_dir(self.workdir)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',self.port))
        profile = MODEL_PROFILES[self.model_id]
        executable = require_plain_path(Path('C:/LocalAI/runtime/llama-b10665/llama-server.exe'))
        model = require_plain_path(Path('C:/LocalAI/models')/profile['file'])
        if not executable.is_file() or file_hash(executable)!=SERVER_HASH:
            raise ValueError('RUNTIME_HASH_MISMATCH')
        manifest_path=Path(__file__).resolve().parents[3]/'config/localai_runtime_manifest.json'
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest['runtime_id']!=RUNTIME_ID:
            raise ValueError('RUNTIME_HASH_MISMATCH')
        actual={p.name for p in executable.parent.iterdir() if p.suffix.lower() in ('.dll','.exe')}
        if actual != set(manifest['files']):
            raise ValueError('RUNTIME_HASH_MISMATCH')
        for name,digest in manifest['files'].items():
            if Path(name).name!=name or file_hash(require_plain_path(executable.parent/name))!=digest:
                raise ValueError('RUNTIME_HASH_MISMATCH')
        if not model.is_file():
            raise ValueError('MODEL_UNAVAILABLE')
        if file_hash(model)!=profile['sha256']:
            raise ValueError('MODEL_HASH_MISMATCH')
        self.token = create_token(self.workdir/'backend.key')
        command = [str(executable),'-m',str(model),'--host','127.0.0.1','--port',str(self.port),
                   '-c',str(self.context_size),'-np','1','-t','6','-b','128','-ub','128',
                   '-ngl','0' if self.cpu_only else str(profile['gpu_layers']),
                   '--fit','off','--flash-attn','on','--offline','--no-webui','--no-webui-mcp-proxy',
                   '--no-slots','--cache-ram','0','--no-cache-idle-slots','--reasoning','off','--reasoning-budget','0',
                   '--api-key-file',str(self.workdir/'backend.key'),'--alias',self.model_id]
        if self.cpu_only: command += ['--device','none']
        elif profile['cpu_moe']: command += ['--cpu-moe']
        system_root=os.environ.get('SystemRoot','C:/Windows')
        env={'SystemRoot':system_root,'WINDIR':system_root,
             'PATH':str(executable.parent)+os.pathsep+str(Path(system_root)/'System32'),
             'TEMP':str(self.workdir),'TMP':str(self.workdir),'HF_HUB_OFFLINE':'1',
             'LLAMA_CACHE':str(self.workdir/'cache'),'CUDA_CACHE_DISABLE':'1',
             'LOCALAPPDATA':str(self.workdir/'appdata')}
        self._streams=[(self.workdir/'backend.stdout.log').open('xb'),(self.workdir/'backend.stderr.log').open('xb')]
        started=time.monotonic()
        try:
            from .windows_process import start_restricted_process
            self.process=start_restricted_process(command,cwd=self.workdir,env=env,
                stdout=self._streams[0],stderr=self._streams[1])
            while time.monotonic()-started<timeout:
                if self.process.poll() is not None: raise RuntimeError('RUNTIME_FAILURE')
                try:
                    health=local_json(self.url+'/health',token=self.token,timeout=1)
                    if health.get('status')=='ok':
                        models=local_json(self.url+'/v1/models',token=self.token,timeout=2)
                        if not any(m.get('id')==self.model_id for m in models.get('data',[])):
                            raise RuntimeError('MODEL_IDENTITY_MISMATCH')
                        self.startup_seconds=round(time.monotonic()-started,3)
                        (self.workdir/'launch.json').write_text(json.dumps({'identity':self.identity,
                            'command':command,'pid':self.process.pid,'startup_seconds':self.startup_seconds},indent=2),encoding='utf-8')
                        return self
                except (OSError,ValueError): pass
                time.sleep(.25)
            raise TimeoutError('MODEL_STARTUP_TIMEOUT')
        except BaseException:
            self.stop()
            raise

    @property
    def url(self): return f'http://127.0.0.1:{self.port}'

    def healthy(self):
        if self.process is None or self.process.poll() is not None: return False
        try: return local_json(self.url+'/health',token=self.token,timeout=2).get('status')=='ok'
        except (OSError,ValueError): return False

    def stop(self):
        try:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                try: self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill(); self.process.wait(timeout=5)
        finally:
            if self.process is not None: self.process.close()
            for stream in self._streams: stream.close()
            self._streams=[]
