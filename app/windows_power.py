"""Windows boot identity and desktop ownership, including Session 0 workers."""
import ctypes
from datetime import datetime
import json
import os
import re
import subprocess
from pathlib import Path


def boot_time():
    value = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
        '[DateTimeOffset]::new((Get-CimInstance Win32_OperatingSystem).LastBootUpTime).ToUnixTimeSeconds()'],
        capture_output=True, text=True, timeout=15, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return int(value.stdout.strip())


def network_wake_since(root, requested):
    config = json.loads((Path(root) / 'windows-worker/power.json').read_text(encoding='utf-8-sig'))
    mac = config.get('mac', '')
    if not isinstance(mac, str) or not re.fullmatch(r'(?:[0-9A-F]{2}-){5}[0-9A-F]{2}', mac):
        return False
    script = ("$adapter=Get-NetAdapter -Physical | Where-Object MacAddress -eq '" + mac + "'; "
        "$event=Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='Microsoft-Windows-Power-Troubleshooter';Id=1} "
        "-MaxEvents 1 -ErrorAction SilentlyContinue; if($adapter -and $event) { [xml]$xml=$event.ToXml(); "
        "$data=@{}; foreach($item in $xml.Event.EventData.Data){$data[$item.Name]=$item.'#text'}; "
        "@{source=$data.WakeSourceText; time=$data.WakeTime; adapter=$adapter.InterfaceDescription} | ConvertTo-Json -Compress }")
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
            capture_output=True, text=True, check=True, timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        event = json.loads(result.stdout)
        stamp = datetime.fromisoformat(event['time'].replace('Z', '+00:00'))
        return bool(stamp.tzinfo and isinstance(event['source'], str) and event['source'] == event['adapter']
                    and requested <= stamp.timestamp() <= datetime.now().timestamp())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return False  # Firmware-only S5 wakes may not expose a source; never guess ownership.


def desktop_in_use(since=None):
    if os.name != 'nt':
        return True
    # Session 0's GetLastInputInfo cannot detect a desktop or RDP user.
    class Session(ctypes.Structure):
        _fields_ = [('id', ctypes.c_uint32), ('name', ctypes.c_wchar_p), ('state', ctypes.c_int)]
    class Info(ctypes.Structure):
        _fields_ = [('state', ctypes.c_uint32), ('id', ctypes.c_uint32),
            ('incoming_bytes', ctypes.c_uint32), ('outgoing_bytes', ctypes.c_uint32),
            ('incoming_frames', ctypes.c_uint32), ('outgoing_frames', ctypes.c_uint32),
            ('incoming_compressed', ctypes.c_uint32), ('outgoing_compressed', ctypes.c_uint32),
            ('station', ctypes.c_wchar * 32), ('domain', ctypes.c_wchar * 17), ('user', ctypes.c_wchar * 21),
            ('connect', ctypes.c_int64), ('disconnect', ctypes.c_int64), ('last_input', ctypes.c_int64),
            ('logon', ctypes.c_int64), ('current', ctypes.c_int64)]
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
            if session.id == 0 or session.state not in (0, 1, 2, 3, 4, 5):
                continue
            buffer, length = ctypes.c_void_p(), ctypes.c_uint32()
            if not api.WTSQuerySessionInformationW(None, session.id, 5, ctypes.byref(buffer), ctypes.byref(length)):
                return True
            try:
                if length.value >= 2 and ctypes.wstring_at(buffer):
                    return True  # Even a locked/disconnected logged-in desktop belongs to its user.
            finally:
                api.WTSFreeMemory(buffer)
            if since is None:
                continue
            buffer, length = ctypes.c_void_p(), ctypes.c_uint32()
            if not api.WTSQuerySessionInformationW(None, session.id, 24, ctypes.byref(buffer), ctypes.byref(length)):
                return True
            try:
                if length.value < ctypes.sizeof(Info):
                    return True
                info = ctypes.cast(buffer, ctypes.POINTER(Info)).contents
                if info.last_input / 10000000 - 11644473600 > (since or 0):
                    return True  # Input at the sign-in screen also relinquishes automation ownership.
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
            'boot_at': boot_at, 'boot_worker': boot_worker, 'user_active': desktop_in_use(boot_at)}
