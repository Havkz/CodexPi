"""Run preserved Linux CI inside a service-owned WSL distribution on this PC."""
import argparse
import csv
import hashlib
import os
from pathlib import Path
import re
import subprocess
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DISTRO = 'CodexPi-CI'
IMAGE = 'ubuntu-24.04.5-wsl-amd64.wsl'
BASE = 'https://releases.ubuntu.com/noble/'


def run(*args, **kwargs):
    result = subprocess.run(args, **kwargs)
    if result.returncode:
        raise RuntimeError('Linux CI command failed: ' + str(args[0]))
    return result


def linux_path(path):
    return run('wsl.exe', '-d', DISTRO, '--exec', 'wslpath', '-a', str(path),
               capture_output=True, text=True, timeout=30).stdout.strip()


def prepare():
    if os.name != 'nt':
        raise RuntimeError('This Linux CI entrypoint requires the Windows Actions service')
    account = run('whoami.exe', '/user', '/fo', 'csv', '/nh',
                  capture_output=True, text=True, timeout=10).stdout.strip()
    if next(csv.reader([account]))[1] != 'S-1-5-20':
        raise RuntimeError('Register Linux CI under the Actions service account, not the interactive user')
    listing = subprocess.run(['wsl.exe', '--list', '--quiet'], capture_output=True, timeout=30)
    if listing.returncode:
        raise RuntimeError('WSL is not ready for the Actions service; finish the pending Windows restart first. ' +
                           listing.stdout.decode('utf-16-le', errors='replace').replace('\x00', '')[-1800:])
    names = listing.stdout.decode('utf-16-le', errors='replace').replace('\x00', '').split()
    if DISTRO not in names:
        directory = ROOT / 'actions-linux'
        directory.mkdir(parents=True, exist_ok=True)
        image = directory / IMAGE
        sums = urllib.request.urlopen(BASE + 'SHA256SUMS', timeout=30).read().decode()
        digest = next((line.split()[0] for line in sums.splitlines()
                       if line.split()[-1].lstrip('*') == IMAGE), None)
        if not digest or not re.fullmatch('[0-9a-f]{64}', digest):
            raise RuntimeError('Ubuntu did not publish a valid SHA-256 for the pinned Linux CI image')
        if not image.exists():
            urllib.request.urlretrieve(BASE + IMAGE, image)
        with image.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != digest:
                raise RuntimeError('Ubuntu Linux CI image hash verification failed')
        destination = directory / 'distro'
        if destination.exists() and any(destination.iterdir()):
            raise RuntimeError('Unregistered Linux CI directory is not empty; preserving it')
        run('wsl.exe', '--import', DISTRO, str(destination), str(image), '--version', '2', timeout=300)
    initialization = '''set -eu
if [ ! -f /etc/codexpi-ci-ready-v1 ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y python3-venv git libegl1 libopengl0
  id ci >/dev/null 2>&1 || useradd --create-home --shell /bin/bash ci
  touch /etc/codexpi-ci-ready-v1
fi
'''
    run('wsl.exe', '-d', DISTRO, '-u', 'root', '--exec', 'bash', '-s',
        input=initialization, text=True, timeout=600)
    print('Confirmed Linux CI distribution owned by the Windows Actions service.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True, choices=['3.11', '3.12', '3.13', '3.14'])
    parser.add_argument('--project', required=True, choices=['codexpi', 'donut-order-trader'])
    args = parser.parse_args()
    workspace = Path(os.environ['GITHUB_WORKSPACE']).resolve()
    runner_root = (ROOT / 'actions-runner').resolve()
    if not workspace.is_relative_to(runner_root):
        raise RuntimeError('Linux CI source is outside the registered runner workspaces')
    prepare()
    source = linux_path(workspace)
    artifacts = linux_path(Path(os.environ['RUNNER_TEMP']).resolve())
    script = r'''set -eu
source="$1"; artifacts="$2"; version="$3"; project="$4"
python3 -m venv /home/ci/codexpi-bootstrap
/home/ci/codexpi-bootstrap/bin/python -m pip -q install uv==0.10.7
uv=/home/ci/codexpi-bootstrap/bin/uv
ci_tmp=$(mktemp -d /home/ci/codexpi-ci.XXXXXX)
finish() {
  status=$?
  find "$ci_tmp/artifacts" -maxdepth 1 -name '*.png' -exec cp -- {} "$artifacts/" \; 2>/dev/null || true
  case "$ci_tmp" in /home/ci/codexpi-ci.*) rm -rf -- "$ci_tmp";; esac
  exit "$status"
}
trap finish EXIT
mkdir "$ci_tmp/artifacts"
tar -C "$source" -cf - . | tar -C "$ci_tmp" -xf -
cd "$ci_tmp"
"$uv" venv --python "$version" .ci-venv
export PATH="$ci_tmp/.ci-venv/bin:$PATH"
python -c 'import platform; assert platform.system() == "Linux"; print(platform.platform())'
if [ "$project" = codexpi ]; then
  "$uv" pip install -r requirements.txt
  python -m unittest discover -s tests
else
  export QT_QPA_PLATFORM=offscreen
  export DONUT_GUI_RESEARCH_PREVIEW="$ci_tmp/artifacts/donut-gui-research.png"
  export DONUT_GUI_MARKERS_PREVIEW="$ci_tmp/artifacts/donut-gui-markers.png"
  export DONUT_GUI_PAPER_PREVIEW="$ci_tmp/artifacts/donut-gui-paper.png"
  export DONUT_GUI_PORTFOLIO_PREVIEW="$ci_tmp/artifacts/donut-gui-portfolio.png"
  export DONUT_GUI_ITEMS_PREVIEW="$ci_tmp/artifacts/donut-gui-items.png"
  "$uv" pip install -e '.[gui,discord,ml]'
  "$uv" pip check
  python -m unittest discover -s tests -v
  python headless_start.py --check-config
  python -m donut_order_trader.discord_bot --config discord-bot.toml --check-config
fi
'''
    run('wsl.exe', '-d', DISTRO, '-u', 'ci', '--exec', 'bash', '-s', '--',
        source, artifacts, args.python, args.project, input=script, text=True, timeout=1200)


if __name__ == '__main__':
    main()
