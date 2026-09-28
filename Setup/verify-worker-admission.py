"""Verify real local-API rejection without starting a goal or a Windows command.

Requires idle mapped projects; never changes their selection or native status.
"""
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery_check', ROOT / 'Setup/verify-controller-recovery.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def main():
    result = check.helper.remote(check.SNAPSHOT + '''
from aiohttp import ClientSession, UnixConnector
async def verify():
 before=await snapshot()
 db=Database('state/codexpi.db')
 counts=lambda: [db.conn.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('jobs','events')]
 before_counts=counts()
 results=[]
 async with ClientSession(connector=UnixConnector(path='state/local.sock')) as client:
  for project in before['projects']:
   body={'project_id':project['project_id'], 'commit':'a'*40, 'argv':['python','--version'],
         'reason':'CodexPi admission regression: inactive project must not dispatch'}
   async with client.post('http://localhost/jobs',json=body) as response:
    data=await response.json()
    assert response.status==400 and 'selected, executing' in data.get('error',''), (response.status,data)
    results.append({'project_id':project['project_id'],'status':project['goal_status'],
                    'http':response.status,'error':data['error']})
 after=await snapshot()
 for key in ('projects','selected','manual_holds','native_statuses'):
  assert before[key]==after[key], key
 assert before_counts==counts(), 'Rejected requests wrote jobs/events'
 db.conn.close()
 return {'passed':True,'requests':results,'native_and_queue_unchanged':True,
         'jobs_and_events_unchanged':True,'positive_live_dispatch_tested':False}
print(json.dumps(asyncio.run(verify())))
''')
    record = ROOT / 'state' / ('worker-admission-' + time.strftime('%Y%m%d-%H%M%S') + '.json')
    record.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'record': str(record), **result}))


if __name__ == '__main__':
    main()
