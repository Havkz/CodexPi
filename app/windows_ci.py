"""One Windows execution slot shared by Actions job hooks and the native worker."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sqlite3
import time


ROOT = Path(__file__).resolve().parents[1]


def identity(pid):
    """Creation time prevents PID reuse; an inaccessible process is never declared dead."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return None
        raise OSError('Cannot verify Windows execution owner')
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise OSError('Cannot verify Windows execution state')
        if code.value != 259:
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            raise OSError('Cannot verify Windows execution identity')
        return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    finally:
        kernel.CloseHandle(handle)


class ExecutionSlot:
    def __init__(self, root=ROOT):
        directory = Path(root) / 'actions-coordination'
        directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / 'execution.db', isolation_level=None, timeout=10)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS execution '
                        '(pid INTEGER PRIMARY KEY, born TEXT NOT NULL, kind TEXT NOT NULL, acquired INTEGER NOT NULL)')

    def _reap(self):
        for pid, born in self.db.execute('SELECT pid,born FROM execution'):
            live = identity(pid)
            if live is None or str(live) != born:
                self.db.execute('DELETE FROM execution WHERE pid=? AND born=?', (pid, born))

    def claim(self, pid, born, kind):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self._reap()
            if str(identity(pid)) != str(born):
                raise RuntimeError('Windows execution owner exited or changed')
            self.db.execute('INSERT OR IGNORE INTO execution VALUES (?,?,?,0)', (pid, str(born), kind))
            row = self.db.execute('SELECT kind,born FROM execution WHERE pid=?', (pid,)).fetchone()
            if row != (kind, str(born)):
                raise RuntimeError('Windows execution owner conflicts with existing admission')
            occupied = self.db.execute('SELECT 1 FROM execution WHERE acquired=1 AND pid!=?', (pid,)).fetchone()
            preferred = kind == 'worker' and self.db.execute("SELECT 1 FROM execution WHERE kind='ci'").fetchone()
            if not occupied and not preferred:
                self.db.execute('UPDATE execution SET acquired=1 WHERE pid=?', (pid,))
            acquired = bool(self.db.execute('SELECT acquired FROM execution WHERE pid=?', (pid,)).fetchone()[0])
            self.db.execute('COMMIT')
            return acquired
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def release(self, pid, born):
        self.db.execute('DELETE FROM execution WHERE pid=? AND born=?', (pid, str(born)))

    def ci_busy(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self._reap()
            busy = bool(self.db.execute("SELECT 1 FROM execution WHERE kind='ci'").fetchone())
            self.db.execute('COMMIT')
            return busy
        except BaseException:
            self.db.execute('ROLLBACK')
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'finish'])
    parser.add_argument('--pid', required=True, type=int)
    args = parser.parse_args()
    born = identity(args.pid)
    if born is None:
        raise RuntimeError('Actions job process is no longer running')
    slot = ExecutionSlot()
    try:
        if args.action == 'finish':
            slot.release(args.pid, born)
            return
        # Never execute an external fork on the personal Windows PC.
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
        repository = os.environ['GITHUB_REPOSITORY']
        allowed = json.loads((ROOT / 'actions-coordination/repositories.json').read_text())
        if repository.lower() not in {name.lower() for name in allowed}:
            raise RuntimeError('Actions repository is not registered with CodexPi')
        pull = event.get('pull_request')
        if pull and pull.get('head', {}).get('repo', {}).get('full_name', '').lower() != repository.lower():
            raise RuntimeError('External pull-request code cannot run on this personal PC')
        deadline = time.monotonic() + 900
        while not slot.claim(args.pid, born, 'ci'):
            if time.monotonic() > deadline:
                slot.release(args.pid, born)
                raise TimeoutError('Actions waited 15 minutes for the Windows execution slot')
            time.sleep(1)
        print('CodexPi Windows execution slot confirmed; CI has priority.')
    finally:
        slot.db.close()


if __name__ == '__main__':
    main()
