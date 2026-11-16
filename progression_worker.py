"""Isolated reconstruction of a seed, then generic AP rule evaluation. No UT."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys


def limit_memory():
    """Hard 2 GiB address-space/process memory limit; fail closed if unavailable."""
    amount = 2 * 1024**3
    if os.name != 'nt':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (amount, amount))
        return None
    import ctypes
    from ctypes import wintypes
    class Basic(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
                    ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ('ReadOperationCount','WriteOperationCount','OtherOperationCount',
                                                         'ReadTransferCount','WriteTransferCount','OtherTransferCount')]
    class Extended(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', IO), ('ProcessMemoryLimit', ctypes.c_size_t),
                    ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    job = kernel.CreateJobObjectW(None, None)
    info = Extended()
    info.BasicLimitInformation.LimitFlags = 0x100 | 0x2000  # PROCESS_MEMORY + KILL_ON_JOB_CLOSE
    info.ProcessMemoryLimit = amount
    if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        raise RuntimeError('Memory limit unavailable')
    return job  # Keep the handle open until process exit.


def evaluate(request):
    from progression_model import FORMAT, SOURCE, Unsupported, analyze, describe, digest, runtime_fingerprint, rule_probes
    manifest = request['manifest']
    if manifest.get('version') != FORMAT or manifest.get('source') != SOURCE:
        raise Unsupported('manifest')
    if manifest['runtime'] != runtime_fingerprint(os.getcwd()):
        raise Unsupported('runtime_changed')
    players = Path(request['players'])
    if {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in players.glob('*.yaml')} != manifest['yamls']:
        raise Unsupported('yaml_changed')
    from ap_runner import hide_builtin_worlds
    hide_builtin_worlds(set(request.get('hide', [])))
    sys.path.insert(0, os.getcwd())
    sys.argv = ['Generate.py', '--player_files_path', str(players), '--outputpath', request['output'],
                '--spoiler', '0', '--skip_output', '--seed', str(manifest['seed'])]
    import settings
    settings.no_gui = True
    settings.skip_autosave = True
    from Utils import __version__
    if __version__ != manifest['ap_version']:
        raise Unsupported('runtime_changed')
    import Generate
    from Main import main
    args, seed = Generate.main()
    mw = main(args, seed)
    if digest(describe(mw)) != manifest['model_hash']:
        raise Unsupported('reconstruction_mismatch')
    if not manifest.get('static',{}).get('rule_probes') or rule_probes(mw)!=manifest['static']['rule_probes']:
        raise Unsupported('reconstruction_mismatch')
    result = analyze(mw, request['live'], request.get('target'))
    result.update(verified_model=manifest['model_hash'], ap_version=__version__)
    return result


def main():
    output = sys.stdout
    try:
        memory_guard = limit_memory()
        request = json.loads(sys.stdin.read(32 * 1024**2))
        with contextlib.redirect_stdout(sys.stderr):
            result = evaluate(request)
    except Exception as exc:
        from progression_model import Unsupported
        result = dict(state='unsupported', reason=str(exc) if isinstance(exc, Unsupported) else 'worker_failed')
    output.write(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
