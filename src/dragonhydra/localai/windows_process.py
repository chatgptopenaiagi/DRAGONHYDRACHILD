"""Engineering-only Windows process restriction; no model-accessible executor.

Uses a restricted copy of the current token, deny-only administrator groups,
DISABLE_MAX_PRIVILEGE, Medium integrity, explicit inherited handles and a job.
This is privilege reduction, NOT filesystem read isolation or a network sandbox.
No accounts, services, historical ACLs or registry state are changed. Failure has
no ordinary/elevated subprocess fallback.

References: Microsoft CreateRestrictedToken, CreateProcessAsUserW and
JOBOBJECT_EXTENDED_LIMIT_INFORMATION API documentation.
"""
import ctypes as C
from ctypes import wintypes as W
import math
import os
from pathlib import PureWindowsPath
import subprocess
import threading
import uuid

_desktop_lock = threading.Lock()


def _launch_arguments(command, cwd, env):
    if not isinstance(command, (list, tuple)) or not command:
        raise ValueError('NATIVE_ARGUMENT_LIST_REQUIRED')
    if any(not isinstance(x, str) or '\0' in x for x in command):
        raise ValueError('INVALID_NATIVE_ARGUMENT')
    executable = PureWindowsPath(command[0])
    if not executable.is_absolute() or executable.suffix.lower() != '.exe':
        raise ValueError('ABSOLUTE_NATIVE_EXECUTABLE_REQUIRED')
    if executable.name.lower() in {'cmd.exe', 'powershell.exe', 'pwsh.exe', 'wscript.exe', 'cscript.exe'}:
        raise ValueError('SHELL_EXECUTABLE_FORBIDDEN')
    if not isinstance(cwd, (str, os.PathLike)) or '\0' in str(cwd) or not PureWindowsPath(cwd).is_absolute():
        raise ValueError('ABSOLUTE_WORKING_DIRECTORY_REQUIRED')
    if '..' in executable.parts or '..' in PureWindowsPath(cwd).parts:
        raise ValueError('PARENT_TRAVERSAL_FORBIDDEN')
    if not isinstance(env, dict) or not env:
        raise ValueError('EXPLICIT_ENVIRONMENT_REQUIRED')
    seen = set()
    for key, value in env.items():
        if not isinstance(key, str) or not key or '=' in key or '\0' in key or not isinstance(value, str) or '\0' in value:
            raise ValueError('INVALID_ENVIRONMENT')
        if key.casefold() in seen:
            raise ValueError('DUPLICATE_ENVIRONMENT_KEY')
        seen.add(key.casefold())
    line = subprocess.list2cmdline(command)
    if len(line) >= 32767:
        raise ValueError('COMMAND_TOO_LARGE')
    block = '\0'.join(f'{key}={env[key]}' for key in sorted(env, key=str.casefold)) + '\0\0'
    if len(block) > 131072:
        raise ValueError('ENVIRONMENT_TOO_LARGE')
    return line, block


class _SidAttributes(C.Structure):
    _fields_ = [('Sid', C.c_void_p), ('Attributes', W.DWORD)]


class _SecurityAttributes(C.Structure):
    _fields_ = [('nLength',W.DWORD),('lpSecurityDescriptor',C.c_void_p),('bInheritHandle',W.BOOL)]


class _StartupInfo(C.Structure):
    _fields_ = [('cb', W.DWORD), ('lpReserved', W.LPWSTR), ('lpDesktop', W.LPWSTR),
                ('lpTitle', W.LPWSTR), ('dwX', W.DWORD), ('dwY', W.DWORD),
                ('dwXSize', W.DWORD), ('dwYSize', W.DWORD), ('dwXCountChars', W.DWORD),
                ('dwYCountChars', W.DWORD), ('dwFillAttribute', W.DWORD),
                ('dwFlags', W.DWORD), ('wShowWindow', W.WORD), ('cbReserved2', W.WORD),
                ('lpReserved2', C.c_void_p), ('hStdInput', W.HANDLE),
                ('hStdOutput', W.HANDLE), ('hStdError', W.HANDLE)]


class _StartupInfoEx(C.Structure):
    _fields_ = [('StartupInfo', _StartupInfo), ('lpAttributeList', C.c_void_p)]


class _ProcessInfo(C.Structure):
    _fields_ = [('hProcess', W.HANDLE), ('hThread', W.HANDLE),
                ('dwProcessId', W.DWORD), ('dwThreadId', W.DWORD)]


class _BasicLimits(C.Structure):
    _fields_ = [('PerProcessUserTimeLimit', C.c_longlong), ('PerJobUserTimeLimit', C.c_longlong),
                ('LimitFlags', W.DWORD), ('MinimumWorkingSetSize', C.c_size_t),
                ('MaximumWorkingSetSize', C.c_size_t), ('ActiveProcessLimit', W.DWORD),
                ('Affinity', C.c_size_t), ('PriorityClass', W.DWORD), ('SchedulingClass', W.DWORD)]


class _IoCounters(C.Structure):
    _fields_ = [(name, C.c_ulonglong) for name in ('ReadOperationCount', 'WriteOperationCount',
                 'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class _ExtendedLimits(C.Structure):
    _fields_ = [('BasicLimitInformation', _BasicLimits), ('IoInfo', _IoCounters),
                ('ProcessMemoryLimit', C.c_size_t), ('JobMemoryLimit', C.c_size_t),
                ('PeakProcessMemoryUsed', C.c_size_t), ('PeakJobMemoryUsed', C.c_size_t)]


class _MemoryCounters(C.Structure):
    _fields_ = [('cb', W.DWORD), ('PageFaultCount', W.DWORD)] + [
        (name, C.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
        'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
        'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]


class _Api:
    def __init__(self):
        if os.name != 'nt':
            raise OSError('WINDOWS_RESTRICTION_REQUIRED')
        self.k = C.WinDLL('kernel32', use_last_error=True)
        self.a = C.WinDLL('advapi32', use_last_error=True)
        self.p = C.WinDLL('psapi', use_last_error=True)
        self.u = C.WinDLL('user32', use_last_error=True)
        specs = [
            (self.k, 'GetCurrentProcess', W.HANDLE, []),
            (self.k, 'OpenProcess', W.HANDLE, [W.DWORD,W.BOOL,W.DWORD]),
            (self.k, 'CloseHandle', W.BOOL, [W.HANDLE]),
            (self.k, 'LocalFree', C.c_void_p, [C.c_void_p]),
            (self.k, 'DuplicateHandle', W.BOOL, [W.HANDLE,W.HANDLE,W.HANDLE,C.POINTER(W.HANDLE),W.DWORD,W.BOOL,W.DWORD]),
            (self.k, 'InitializeProcThreadAttributeList', W.BOOL, [C.c_void_p,W.DWORD,W.DWORD,C.POINTER(C.c_size_t)]),
            (self.k, 'UpdateProcThreadAttribute', W.BOOL, [C.c_void_p,W.DWORD,C.c_size_t,C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p]),
            (self.k, 'DeleteProcThreadAttributeList', None, [C.c_void_p]),
            (self.k, 'CreateJobObjectW', W.HANDLE, [C.c_void_p,W.LPCWSTR]),
            (self.k, 'SetInformationJobObject', W.BOOL, [W.HANDLE,C.c_int,C.c_void_p,W.DWORD]),
            (self.k, 'AssignProcessToJobObject', W.BOOL, [W.HANDLE,W.HANDLE]),
            (self.k, 'ResumeThread', W.DWORD, [W.HANDLE]),
            (self.k, 'WaitForSingleObject', W.DWORD, [W.HANDLE,W.DWORD]),
            (self.k, 'GetExitCodeProcess', W.BOOL, [W.HANDLE,C.POINTER(W.DWORD)]),
            (self.k, 'TerminateProcess', W.BOOL, [W.HANDLE,W.UINT]),
            (self.k, 'GetProcessTimes', W.BOOL, [W.HANDLE,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p]),
            (self.a, 'OpenProcessToken', W.BOOL, [W.HANDLE,W.DWORD,C.POINTER(W.HANDLE)]),
            (self.a, 'CreateRestrictedToken', W.BOOL, [W.HANDLE,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,C.c_void_p,W.DWORD,C.c_void_p,C.POINTER(W.HANDLE)]),
            (self.a, 'ConvertStringSidToSidW', W.BOOL, [W.LPCWSTR,C.POINTER(C.c_void_p)]),
            (self.a, 'ConvertSidToStringSidW', W.BOOL, [C.c_void_p,C.POINTER(C.c_void_p)]),
            (self.a, 'ConvertStringSecurityDescriptorToSecurityDescriptorW', W.BOOL, [W.LPCWSTR,W.DWORD,C.POINTER(C.c_void_p),C.c_void_p]),
            (self.a, 'GetSecurityDescriptorDacl', W.BOOL, [C.c_void_p,C.POINTER(W.BOOL),C.POINTER(C.c_void_p),C.POINTER(W.BOOL)]),
            (self.a, 'GetLengthSid', W.DWORD, [C.c_void_p]),
            (self.a, 'SetTokenInformation', W.BOOL, [W.HANDLE,C.c_int,C.c_void_p,W.DWORD]),
            (self.a, 'GetTokenInformation', W.BOOL, [W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.POINTER(W.DWORD)]),
            (self.a, 'CreateProcessAsUserW', W.BOOL, [W.HANDLE,W.LPCWSTR,W.LPWSTR,C.c_void_p,C.c_void_p,W.BOOL,W.DWORD,C.c_void_p,W.LPCWSTR,C.c_void_p,C.POINTER(_ProcessInfo)]),
            (self.p, 'GetProcessMemoryInfo', W.BOOL, [W.HANDLE,C.c_void_p,W.DWORD]),
            (self.u, 'GetProcessWindowStation', W.HANDLE, []),
            (self.u, 'SetProcessWindowStation', W.BOOL, [W.HANDLE]),
            (self.u, 'CreateWindowStationW', W.HANDLE, [W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p]),
            (self.u, 'CreateDesktopW', W.HANDLE, [W.LPCWSTR,W.LPCWSTR,C.c_void_p,W.DWORD,W.DWORD,C.c_void_p]),
            (self.u, 'CloseDesktop', W.BOOL, [W.HANDLE]),
            (self.u, 'CloseWindowStation', W.BOOL, [W.HANDLE]),
        ]
        for dll, name, result, args in specs:
            function = getattr(dll, name)
            function.restype, function.argtypes = result, args

    @staticmethod
    def check(result, name):
        if not result:
            raise OSError(C.get_last_error(), name + '_FAILED')
        return result

    def sid(self, text):
        result = C.c_void_p()
        self.check(self.a.ConvertStringSidToSidW(text,C.byref(result)), 'SID_CONVERSION')
        return result

    def sid_text(self, sid):
        text = C.c_void_p()
        self.check(self.a.ConvertSidToStringSidW(sid,C.byref(text)), 'SID_READ')
        try:
            return C.wstring_at(text)
        finally:
            self.k.LocalFree(text)

    def token_info(self, token, kind):
        size = W.DWORD()
        self.a.GetTokenInformation(token,kind,None,0,C.byref(size))
        if not size.value:
            raise OSError(C.get_last_error(),'TOKEN_INFORMATION_SIZE_FAILED')
        data = C.create_string_buffer(size.value)
        self.check(self.a.GetTokenInformation(token,kind,data,size,C.byref(size)), 'TOKEN_INFORMATION')
        return data

    def token_security(self, token):
        groups = self.token_info(token,2)
        count = W.DWORD.from_buffer(groups).value
        class Groups(C.Structure):
            _fields_ = [('count',W.DWORD),('groups',_SidAttributes*count)]
        disabled = {}
        for group in Groups.from_buffer(groups).groups:
            sid = self.sid_text(group.Sid)
            if sid in {'S-1-5-32-544','S-1-5-114'}:
                disabled[sid] = {'enabled':bool(group.Attributes & 4),
                                 'deny_only':bool(group.Attributes & 16)}
        integrity = _SidAttributes.from_buffer(self.token_info(token,25))
        level = self.sid_text(integrity.Sid)
        privileges = self.token_info(token,3)
        return {'integrity_sid':level,'administrator_groups':disabled,
                'privilege_count':W.DWORD.from_buffer(privileges).value,
                'filesystem_read_isolated':False,'network_os_sandboxed':False}

    def private_desktop(self, token):
        """Ephemeral private GUI objects; existing desktop/ACLs are unchanged."""
        user_buffer = self.token_info(token,1)
        sid = self.sid_text(_SidAttributes.from_buffer(user_buffer).Sid)
        descriptor = C.c_void_p()
        self.check(self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            f'D:P(A;;GA;;;{sid})S:(ML;;NW;;;ME)',1,C.byref(descriptor),None),'DESKTOP_SECURITY')
        attributes = _SecurityAttributes(C.sizeof(_SecurityAttributes),descriptor,False)
        name = 'LocalAI-'+uuid.uuid4().hex
        station,desktop = None,None
        try:
            station = self.check(self.u.CreateWindowStationW(name,0,0xF037F,C.byref(attributes)),'CREATE_PRIVATE_STATION')
            with _desktop_lock:
                previous = self.check(self.u.GetProcessWindowStation(),'GET_CURRENT_STATION')
                self.check(self.u.SetProcessWindowStation(station),'SELECT_PRIVATE_STATION')
                try:
                    desktop = self.check(self.u.CreateDesktopW('analysis',None,None,0,0xF01FF,C.byref(attributes)),'CREATE_PRIVATE_DESKTOP')
                finally:
                    self.check(self.u.SetProcessWindowStation(previous),'RESTORE_ORIGINAL_STATION')
            return station,desktop,name+'\\analysis'
        except BaseException:
            if desktop:self.u.CloseDesktop(desktop)
            if station:self.u.CloseWindowStation(station)
            raise
        finally:
            self.k.LocalFree(descriptor)

    def restrict_default_dacl(self, token):
        # A built-in Administrator's original default DACL may grant only the
        # group we just disabled. Give the same user access to its NEW objects.
        user_buffer = self.token_info(token,1)
        sid = self.sid_text(_SidAttributes.from_buffer(user_buffer).Sid)
        descriptor,dacl = C.c_void_p(),C.c_void_p()
        present,defaulted = W.BOOL(),W.BOOL()
        self.check(self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            f'D:P(A;;GA;;;{sid})(A;;GA;;;SY)',1,C.byref(descriptor),None),'TOKEN_DEFAULT_SECURITY')
        try:
            self.check(self.a.GetSecurityDescriptorDacl(descriptor,C.byref(present),C.byref(dacl),C.byref(defaulted)),'TOKEN_DEFAULT_DACL_READ')
            if not present.value or not dacl.value:
                raise OSError('TOKEN_DEFAULT_DACL_MISSING')
            self.check(self.a.SetTokenInformation(token,6,C.byref(dacl),C.sizeof(dacl)),'TOKEN_DEFAULT_DACL_SET')
        finally:
            self.k.LocalFree(descriptor)


class RestrictedProcess:
    """Small process interface; closing the job kills any remaining child."""
    def __init__(self, api, handle, job, pid, command, security, desktop, station):
        self._api,self._handle,self._job = api,handle,job
        self._desktop,self._station = desktop,station
        self.pid,self.args,self.security,self.returncode = pid,command,security,None

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        state = self._api.k.WaitForSingleObject(self._handle,0)
        if state == 258:
            return None
        if state != 0:
            raise OSError('PROCESS_WAIT_FAILED')
        code = W.DWORD()
        self._api.check(self._api.k.GetExitCodeProcess(self._handle,C.byref(code)), 'PROCESS_EXIT_CODE')
        self.returncode = code.value
        return self.returncode

    def wait(self, timeout=None):
        if timeout is not None and (not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or not 0<=timeout<=86400):
            raise ValueError('INVALID_WAIT_TIMEOUT')
        if self.poll() is not None:
            return self.returncode
        duration = 0xffffffff if timeout is None else math.ceil(timeout*1000)
        state = self._api.k.WaitForSingleObject(self._handle,duration)
        if state == 258:
            raise subprocess.TimeoutExpired(self.args,timeout)
        if state != 0:
            raise OSError('PROCESS_WAIT_FAILED')
        return self.poll()

    def terminate(self):
        if self.poll() is None:
            self._api.check(self._api.k.TerminateProcess(self._handle,1),'PROCESS_TERMINATION')

    kill = terminate

    def close(self):
        if self._job:
            self._api.k.CloseHandle(self._job)
            self._job = None
        if self._handle:
            self._api.k.CloseHandle(self._handle)
            self._handle = None
        if self._desktop:
            self._api.u.CloseDesktop(self._desktop)
            self._desktop = None
        if self._station:
            self._api.u.CloseWindowStation(self._station)
            self._station = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def start_restricted_process(command, *, cwd, env, stdout, stderr, allow_children=False):
    """Launch a fixed engineering command with no elevated-process fallback."""
    line, block = _launch_arguments(command,cwd,env)
    if type(allow_children) is not bool:
        raise ValueError('BOOLEAN_CHILD_POLICY_REQUIRED')
    if not all(hasattr(stream,'fileno') and not stream.closed for stream in (stdout,stderr)):
        raise ValueError('OPEN_OUTPUT_STREAMS_REQUIRED')
    if os.name != 'nt':
        raise OSError('WINDOWS_RESTRICTION_REQUIRED')
    return _spawn_windows(command,str(cwd),line,block,stdout,stderr,allow_children)


def _spawn_windows(command,cwd,line,block,stdout,stderr,allow_children):
    import msvcrt
    api = _Api()
    original, restricted = W.HANDLE(),W.HANDLE()
    sids, handles = [],[]
    job, attributes, initialized = None,None,False
    station,desktop = None,None
    info = _ProcessInfo()
    transferred = False
    try:
        api.check(api.a.OpenProcessToken(api.k.GetCurrentProcess(),0x18b,C.byref(original)), 'OPEN_CURRENT_TOKEN')
        sids = [api.sid(sid) for sid in ('S-1-5-32-544','S-1-5-114','S-1-16-8192')]
        disable = (_SidAttributes*2)(*[_SidAttributes(sid,0) for sid in sids[:2]])
        api.check(api.a.CreateRestrictedToken(original,1,2,disable,0,None,0,None,C.byref(restricted)), 'CREATE_RESTRICTED_TOKEN')
        label = _SidAttributes(sids[2],0x20)
        api.check(api.a.SetTokenInformation(restricted,25,C.byref(label),C.sizeof(label)+api.a.GetLengthSid(sids[2])), 'SET_MEDIUM_INTEGRITY')
        api.restrict_default_dacl(restricted)
        security = api.token_security(restricted)
        if security['integrity_sid']!='S-1-16-8192' or security['privilege_count']>1 or any(g['enabled'] or not g['deny_only'] for g in security['administrator_groups'].values()):
            raise OSError('TOKEN_RESTRICTION_NOT_PROVEN')
        station,desktop,desktop_name = api.private_desktop(restricted)
        with open(os.devnull,'rb') as devnull:
            for stream in (devnull,stdout,stderr):
                duplicate = W.HANDLE()
                api.check(api.k.DuplicateHandle(api.k.GetCurrentProcess(),msvcrt.get_osfhandle(stream.fileno()),
                    api.k.GetCurrentProcess(),C.byref(duplicate),0,True,2),'DUPLICATE_STREAM_HANDLE')
                handles.append(duplicate)
        size = C.c_size_t()
        api.k.InitializeProcThreadAttributeList(None,1,0,C.byref(size))
        if not size.value:
            raise OSError('HANDLE_LIST_SIZE_FAILED')
        attributes = C.create_string_buffer(size.value)
        api.check(api.k.InitializeProcThreadAttributeList(attributes,1,0,C.byref(size)),'INITIALIZE_HANDLE_LIST')
        initialized = True
        inherited = (W.HANDLE*len(handles))(*[handle.value for handle in handles])
        api.check(api.k.UpdateProcThreadAttribute(attributes,0,0x20002,inherited,C.sizeof(inherited),None,None),'SET_HANDLE_LIST')
        startup = _StartupInfoEx()
        startup.StartupInfo.cb = C.sizeof(startup)
        startup.StartupInfo.lpDesktop = desktop_name
        startup.StartupInfo.dwFlags = 0x100 | 1
        startup.StartupInfo.wShowWindow = 0
        startup.StartupInfo.hStdInput,startup.StartupInfo.hStdOutput,startup.StartupInfo.hStdError = [h.value for h in handles]
        startup.lpAttributeList = C.cast(attributes,C.c_void_p)
        job = api.check(api.k.CreateJobObjectW(None,None),'CREATE_JOB')
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000 | (0 if allow_children else 0x8)
        limits.BasicLimitInformation.ActiveProcessLimit = 0 if allow_children else 1
        api.check(api.k.SetInformationJobObject(job,9,C.byref(limits),C.sizeof(limits)),'SET_JOB_LIMITS')
        environment = C.create_unicode_buffer(block)
        flags = 0x08000000 | 0x400 | 0x80000 | 4
        api.check(api.a.CreateProcessAsUserW(restricted,command[0],C.create_unicode_buffer(line),None,None,
            True,flags,environment,cwd,C.byref(startup),C.byref(info)),'CREATE_RESTRICTED_PROCESS')
        api.check(api.k.AssignProcessToJobObject(job,info.hProcess),'ASSIGN_PROCESS_JOB')
        child_security = _security_for_handle(api,info.hProcess)
        if child_security != security:
            raise OSError('CHILD_TOKEN_MISMATCH')
        if api.k.ResumeThread(info.hThread)==0xffffffff:
            raise OSError(C.get_last_error(),'RESUME_PROCESS_FAILED')
        child_security['job_kill_on_close'] = True
        child_security['child_processes_allowed'] = allow_children
        child_security['private_desktop'] = True
        result = RestrictedProcess(api,info.hProcess,job,info.dwProcessId,list(command),child_security,desktop,station)
        transferred = True
        return result
    finally:
        if info.hProcess and not transferred:
            api.k.TerminateProcess(info.hProcess,1)
            api.k.WaitForSingleObject(info.hProcess,5000)
            api.k.CloseHandle(info.hProcess)
        if info.hThread:
            api.k.CloseHandle(info.hThread)
        if job and not transferred:
            api.k.CloseHandle(job)
        if desktop and not transferred:
            api.u.CloseDesktop(desktop)
        if station and not transferred:
            api.u.CloseWindowStation(station)
        if initialized:
            api.k.DeleteProcThreadAttributeList(attributes)
        for handle in handles:
            api.k.CloseHandle(handle)
        for sid in sids:
            api.k.LocalFree(sid)
        for handle in (restricted,original):
            if handle:
                api.k.CloseHandle(handle)


def _security_for_handle(api, handle):
    token = W.HANDLE()
    api.check(api.a.OpenProcessToken(handle,8,C.byref(token)),'OPEN_INSPECTION_TOKEN')
    try:
        return api.token_security(token)
    finally:
        api.k.CloseHandle(token)


def process_security(pid):
    """Read actual token properties without modifying the inspected process."""
    if type(pid) is not int or pid<=0:
        raise ValueError('INVALID_PROCESS_ID')
    api = _Api()
    handle = api.check(api.k.OpenProcess(0x1000,False,pid),'OPEN_INSPECTION_PROCESS')
    try:
        return _security_for_handle(api,handle)
    finally:
        api.k.CloseHandle(handle)


def sample_metrics(pid):
    """Read process RAM and CPU time; GPU metrics are measured separately."""
    if type(pid) is not int or pid<=0:
        raise ValueError('INVALID_PROCESS_ID')
    api = _Api()
    handle = api.check(api.k.OpenProcess(0x410,False,pid),'OPEN_METRICS_PROCESS')
    try:
        memory = _MemoryCounters()
        memory.cb = C.sizeof(memory)
        api.check(api.p.GetProcessMemoryInfo(handle,C.byref(memory),C.sizeof(memory)),'READ_PROCESS_MEMORY')
        created,exited,kernel,user = (C.c_ulonglong() for _ in range(4))
        api.check(api.k.GetProcessTimes(handle,C.byref(created),C.byref(exited),C.byref(kernel),C.byref(user)),'READ_PROCESS_TIMES')
        return {'working_set_bytes':memory.WorkingSetSize,'peak_working_set_bytes':memory.PeakWorkingSetSize,
                'cpu_seconds':round((kernel.value+user.value)/10000000,6)}
    finally:
        api.k.CloseHandle(handle)
