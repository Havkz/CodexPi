"""Trust only the reviewed goal/Ponytail and optional Token Optimizer definitions."""
import asyncio
import json
from pathlib import Path
import shutil
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.native import Native

REVIEWED = {
    'sha256:f78f99d5b9726a62d625a9f002d368f758995899a7f0f9501a96312bf408932d',
    'sha256:b05e5cc08fb1d406854075a60fd161a94883e34ab3d3afd573c0058fee7058e8',
    'sha256:46e5d5665528383aa1dfdb75daf62f61c73f862251809e5be177592f3b440eaa',
    'sha256:3a2be7adeb2ba96422fbab80af8a2926939bf37a06a8fc06fd7a34f6d4096185',
    'sha256:5f81d38f47448a1581c08ec877e044d9e04dd6f814dce3f2671f7a8edadd719b',
    'sha256:6a6f42bc3b58d6262db38bfd74d7f340fcca2b09cdb134aad365063f0bfefca4',
    'sha256:1423b56c1322f96c8f74c51c1e7ae9a047b904c1fa43ee9165d462fd7a6e70ef',
}
TOKEN_OPTIMIZER_REVIEWED = {
    'sha256:0a1302b63344411fc1f5bc1be3e62d8abe1c832194b8434856adaf9cb9fdcb91',
    'sha256:311c9ebcbaad6d473663fd84631d0983dd9a9b28895dfefde4c3321cf03414e3',
    'sha256:82023c13698028cdaca771b0e03521185c6db18608bfc58c7a77ca7c9495783c',
}
# Reviewed 4.12.0 Node launchers and their local runtime/config/instruction modules.
# Keep complete version sets: mixed or future plugin definitions still fail closed.
REVIEWED_4_12 = (REVIEWED - {
    'sha256:5f81d38f47448a1581c08ec877e044d9e04dd6f814dce3f2671f7a8edadd719b',
    'sha256:6a6f42bc3b58d6262db38bfd74d7f340fcca2b09cdb134aad365063f0bfefca4',
    'sha256:1423b56c1322f96c8f74c51c1e7ae9a047b904c1fa43ee9165d462fd7a6e70ef',
}) | {
    'sha256:7ee5d5ae1f4a9e55f1f429f2960c2f9f32293f198c0e8e2e42b2fb3b4eeda142',
    'sha256:8c9efc5a5e649c8cdca3f0b7bf4cba81d9717d1bc930c7dbc18b6efd66c7c58c',
    'sha256:7954d675ef3bafd5e5a6073ae51d7de57a08f21340f241c332f99078e955675d',
}


async def main():
    root = Path(__file__).resolve().parents[1]
    native = await Native(root / 'state/native.sock').connect()
    try:
        result = await native.rpc('hooks/list', {'cwds': [str(root)]})
        hooks = [h for group in result['data'] for h in group['hooks']]
        if any(group['errors'] or group['warnings'] for group in result['data']):
            raise RuntimeError('Resolve hook loading errors before granting trust')
        hashes = {h['currentHash'] for h in hooks}
        accepted = (REVIEWED, REVIEWED | TOKEN_OPTIMIZER_REVIEWED,
                    REVIEWED_4_12, REVIEWED_4_12 | TOKEN_OPTIMIZER_REVIEWED)
        if len(hooks) != len(hashes) or hashes not in accepted:
            raise RuntimeError('Hook definitions changed; review them before updating this allowlist')
        config = Path.home() / '.codex/config.toml'
        backup = root / 'backups' / ('hook-trust-' + str(time.time_ns()) + '.toml')
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(config, backup)
        await native.rpc('config/batchWrite', {'edits': [{'keyPath': 'hooks.state',
            'value': {h['key']: {'trusted_hash': h['currentHash']} for h in hooks},
            'mergeStrategy': 'upsert'}], 'reloadUserConfig': True})
        result = await native.rpc('hooks/list', {'cwds': [str(root)]})
        hooks = [h for group in result['data'] for h in group['hooks']]
        assert {h['currentHash'] for h in hooks} == hashes and len(hooks) == len(hashes), result
        assert all(h['trustStatus'] == 'trusted' for h in hooks), result
        print(json.dumps({'trusted_hooks': len(hooks), 'backup': str(backup)}))
    finally:
        await native.close()


if __name__ == '__main__':
    asyncio.run(main())
