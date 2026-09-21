"""Read-only Pi resource sample; refuse to label an active-goal run as idle."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.native import GoalSource

UNITS = ('codexpi', 'codexpi-native', 'codexpi-unsnooze')


def sample():
    goals = GoalSource(ROOT).rows()
    assert not any(row['status'] == 'active' for row in goals.values()), 'A native goal is active'
    panes = subprocess.run(['tmux', 'list-panes', '-a'], capture_output=True, text=True)
    assert not panes.stdout.strip(), 'A tmux pane is still running; not a clean idle sample'
    result = {}
    for unit in UNITS:
        output = subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'ActiveState',
            '-p', 'MainPID', '-p', 'MemoryCurrent', '-p', 'CPUUsageNSec', '-p', 'ControlGroup'], text=True)
        data = dict(line.split('=', 1) for line in output.splitlines())
        assert data['ActiveState'] == 'active', unit + ' is not active'
        cgroup = Path('/sys/fs/cgroup') / data['ControlGroup'].lstrip('/')
        pids = {int(pid) for file in cgroup.rglob('cgroup.procs') for pid in file.read_text().split()}
        pids.update(map(int, (cgroup / 'cgroup.procs').read_text().split()))
        processes = []
        for pid in sorted(pids):
            try:
                memory = dict(line.split(':', 1) for line in Path(f'/proc/{pid}/smaps_rollup').read_text().splitlines()[1:])
                processes.append({'pid': pid, 'name': Path(f'/proc/{pid}/comm').read_text().strip(),
                    'rss_kib': int(memory['Rss'].split()[0]), 'pss_kib': int(memory['Pss'].split()[0])})
            except FileNotFoundError:
                pass  # a short-lived diagnostic child exited between the two reads
        result[unit] = {'main_pid': int(data['MainPID']), 'cgroup_bytes': int(data['MemoryCurrent']),
                        'cpu_nsec': int(data['CPUUsageNSec']), 'processes': processes}
    return result


before = sample()
started = time.monotonic()
time.sleep(60)  # include the once-per-minute Unsnooze CLI health poll
after = sample()
elapsed = time.monotonic() - started
for unit, values in after.items():
    assert values['main_pid'] == before[unit]['main_pid'], unit + ' restarted during sample'
    values['cpu_percent_one_core'] = round((values['cpu_nsec'] - before[unit]['cpu_nsec']) / (elapsed * 1e7), 2)
    del values['cpu_nsec']
print(json.dumps({'sample_seconds': round(elapsed, 2), 'units': after,
    'total_cgroup_mib': round(sum(v['cgroup_bytes'] for v in after.values()) / 2**20, 2),
    'total_process_pss_mib': round(sum(p['pss_kib'] for v in after.values() for p in v['processes']) / 1024, 2),
    'cpu_percent_one_core': round(sum(v['cpu_percent_one_core'] for v in after.values()), 2)}, indent=2))
