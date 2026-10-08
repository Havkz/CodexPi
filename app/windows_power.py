"""Windows boot identity and desktop ownership, including Session 0 workers."""
import ctypes
import json
import os
import subprocess
from pathlib import Path


def boot_time():
    value = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
        '[DateTimeOffset]::new((Get-CimInstance Win32_OperatingSystem).LastBootUpTime).ToUnixTimeSeconds()'],
        capture_output=True, text=True, timeout=15, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return int(value.stdout.strip())


def desktop_in_use():
    if os.name != 'nt':
        return True
    # Session 0's GetLastInputInfo cannot detect a desktop or RDP user.
    class Session(ctypes.Structure):
        _fields_ = [('id', ctypes.c_uint32), ('name', ctypes.c_wchar_p), ('state', ctypes.c_int)]
    api = ctypes.WinDLL('wtsapi32', use_last_error=True)
    api.WTSEnumerateSessionsW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                         ctypes.POINTER(ctypes.POINTER(Session)), ctypes.POINTER(ctypes.c_uint32)]
    api.WTSEnumerateSessionsW.restype = ctypes.c_int
    api.WTSQuerySessionInformationW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
                                               ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32)]
    api.WTSQuerySessionInformationW.restype = ctypes.c_int
    api.WTSFreeMemory.argtypes = [ctypes.c_void_p]
    sessions, count = ctypes.POINTER(Session)(), ctypes.c_uint32()
    if not api.WTSEnumerateSessionsW(None, 0, 1, ctypes.byref(sessions), ctypes.byref(count)):
        return True
    try:
        for session in sessions[:count.value]:
            if session.id == 0:
                continue
            buffer, length = ctypes.c_void_p(), ctypes.c_uint32()
            if not api.WTSQuerySessionInformationW(None, session.id, 5, ctypes.byref(buffer), ctypes.byref(length)):
                return True
            try:
                if length.value >= 2 and ctypes.wstring_at(buffer):
                    return True  # Even a locked/disconnected logged-in desktop belongs to its user.
            finally:
                api.WTSFreeMemory(buffer)
        return False
    finally:
        api.WTSFreeMemory(sessions)


def observation(root, boot_at, boot_worker):
    path = Path(root) / 'windows-worker/power.json'
    if not path.exists() or boot_at is None:
        return None
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    return {'mac': config['mac'], 'address': config['address'], 'startup_ready': config['startup_ready'],
            'boot_at': boot_at, 'boot_worker': boot_worker, 'user_active': desktop_in_use()}
