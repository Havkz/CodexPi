#!/usr/bin/env python3
"""Privacy adapter around the unchanged upstream goal hook."""
import importlib.util
import json
from pathlib import Path
import sys

root = Path('/home/raspberry/CodexPi')
spec = importlib.util.spec_from_file_location('goal_status_report',
    root / 'Setup/upstream/goal-hooks/hooks/goal_status_report.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.preview_text = lambda *args, **kwargs: ''
incoming = json.load(sys.stdin)
safe = {k: incoming[k] for k in ('session_id', 'hook_event_name', 'tool_name', 'tool_use_id') if k in incoming}
if safe.get('tool_name') == 'update_goal':
    goal, _ = module.find_goal_object(incoming)
    safe['tool_response'] = {'goal': {k: v for k, v in goal.items() if k in
        ('threadId', 'status', 'tokensUsed', 'updatedAt', 'timeUsedSeconds', 'tokenBudget')}}
sys.exit(module.main(['--state-dir', str(root / 'state/goal-hooks'), '--config',
    str(root / 'config/goal-hooks.json'), *sys.argv[1:]], stdin_text=json.dumps(safe)))
