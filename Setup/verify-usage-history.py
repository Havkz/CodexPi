"""Read-only evidence for the real mapped usage-limit attempts of 2026-09-23.

Checks native provider errors, persisted reset/outbox records and actual Discord
messages. Does not set a goal status, force exhaustion or resume any session.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lifecycle_e2e', ROOT / 'Setup/test-live-lifecycle.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def main():
    result = helper.remote('''import asyncio,datetime,json
from pathlib import Path
from aiohttp import ClientSession
from app.common import read_env
from app.db import Database
from app.native import Native
async def main():
 db=Database('state/codexpi.db')
 project=db.get('4b1ac552-e54f-41ac-9598-1328cdb252de')
 assert project['codex_session_id']=='01a0cf79-e7a6-74f2-adb7-66a6dcb6c46f'
 n=await Native('state/native.sock').connect()
 try:
  thread=(await n.rpc('thread/read',{'threadId':project['codex_session_id']}))['thread']
 finally: await n.close()
 errors=[]
 with Path(thread['path']).open() as stream:
  for line in stream:
   row=json.loads(line)
   payload=row.get('payload',{})
   if row['type']=='event_msg' and payload.get('type')=='task_complete' and (payload.get('error') or {}).get('codex_error_info')=='usage_limit_exceeded':
    errors.append({'turn_id':payload['turn_id'],'completed_at':payload['completed_at']})
 events=[dict(e) for e in db.conn.execute("SELECT * FROM events WHERE project_id=? AND kind='usage limited' ORDER BY event_id",(project['project_id'],))]
 names={project['display_name']}
 for rename in db.conn.execute("SELECT payload FROM events WHERE project_id=? AND kind='renamed'",(project['project_id'],)):
  names.update(json.loads(rename['payload'])[k] for k in ('from','to'))
 assert len(errors)==2 and len(events)==2, (len(errors),len(events))
 messages=[]
 async with ClientSession(headers={'Authorization':'Bot '+read_env('.env')['DISCORD_BOT_TOKEN']}) as client:
  before=None
  while True:
   params={'limit':'100'}
   if before: params['before']=before
   async with client.get('https://discord.com/api/v10/channels/'+project['discord_channel_id']+'/messages',params=params) as response:
    assert response.status==200,response.status
    batch=await response.json()
   messages.extend(batch)
   if len(batch)<100: break
   before=batch[-1]['id']
 checks=[]
 for event in events:
  candidates=[e for e in errors if 0 <= event['created_at']-e['completed_at'] < 10]
  assert len(candidates)==1, event['event_id']
  metadata=json.loads(event['payload'])['usage_limit']
  assert metadata['resetSource'] in ('native-account','unsnooze') and metadata['resetAt']>event['created_at']*1000
  matched=[m for m in messages if any(e.get('footer',{}).get('text')=='CodexPi \\u2022 Event '+str(event['event_id']) for e in m.get('embeds',[]))]
  assert len(matched)==1, (event['event_id'],len(matched))
  embed=matched[0]['embeds'][0]
  text=json.dumps(embed)
  assert 'usage limited' in text.lower() and project['codex_session_id'] in text
  assert any(name in text for name in names)
  assert str(metadata['resetAt']//1000) in json.dumps(embed)
  assert event['sent_at'] and event['sent_at']>=event['created_at']
  checks.append({'native_turn_id':candidates[0]['turn_id'],'event_id':event['event_id'],
    'discord_message_id':matched[0]['id'],'matching_messages':len(matched),
    'reset_utc':datetime.datetime.fromtimestamp(metadata['resetAt']/1000,datetime.timezone.utc).isoformat()})
 assert len({c['native_turn_id'] for c in checks})==2
 print(json.dumps({'project_id':project['project_id'],'native_session_id':project['codex_session_id'],
  'genuine_provider_limit_persisted_and_notified':checks,
  'automatic_reset_resume_verified':False,'current_status':project['goal_status']}))
 db.conn.close()
asyncio.run(main())
''')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
