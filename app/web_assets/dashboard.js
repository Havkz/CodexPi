let state, dragging;
const $ = id => document.getElementById(id);
function node(tag, text, cls) { const el = document.createElement(tag); el.textContent = text; if(cls) el.className=cls; return el; }
async function act(action, project_id, extra={}) {
  try {
    const res=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},body:JSON.stringify({action,project_id,...extra})});
    if(!res.ok) throw new Error((await res.text()).slice(0,300));
    if(action==='logout') location.reload(); else await refresh();
  } catch(err) { $('notice').textContent=err.message; }
}
function projectCard(p) {
  const card=node('details','','project'); card.append(node('summary',`${p.display_name} · ${p.goal_status}`));
  for(const [label,value] of [['Blocker',p.block_reason],['Commit',p.last_commit],['CI',p.last_ci_status],['Session',p.codex_session_id],['Pfad',p.project_path],['Discord',p.discord_channel_id],['Letzte Aktivität',p.last_activity?new Date(p.last_activity*1000).toLocaleString():'—']]) card.append(node('p',`${label}: ${value||'—'}`));
  if(p.github_repo){const link=node('a','GitHub-Repository');link.href='https://github.com/'+p.github_repo;link.target='_blank';link.rel='noopener';card.append(link);}
  const actions=node('div','','actions');
  for(const [label,action] of [['Run now','run-now'],['Pause','pause'],['Resume','resume']]){const b=node('button',label);b.onclick=()=>act(action,p.project_id);if(p.goal_status==='complete')b.disabled=true;actions.append(b);}
  card.append(actions);return card;
}
async function refresh(){
  const response=await fetch('/api/state');if(response.status===401){location.reload();return;}if(!response.ok)throw Error('Dashboard nicht erreichbar');state=await response.json();
  $('infra').replaceChildren(...[['Pi','online'],['Windows',state.windows_online?'online':'offline'],['Discord',state.discord_online?'online':'offline'],['Unsnooze',state.unsnooze.daemonRunning?'online':'offline'],['GitHub',state.github_account]].map(([a,b])=>node('div',`${a}: ${b}`,'card')));
  $('projects').replaceChildren(...state.projects.map(projectCard));
  const active=state.projects.find(p=>p.project_id===state.selected);$('active').replaceChildren(active?projectCard(active):node('p',state.pause_all?'Alle Arbeit pausiert.':'Kein aktives Projekt.'));
  const queue=state.projects.filter(p=>p.queue_position!==null);$('queue').replaceChildren();
  const reorder=ids=>act('reorder',null,{ids});
  queue.forEach((p,i)=>{const row=node('div',`${p.queue_position}. ${p.display_name} · ${p.goal_status}`,'queue-row');row.draggable=true;row.dataset.id=p.project_id;row.ondragstart=()=>{dragging=p.project_id;row.classList.add('dragging');};row.ondragend=()=>{dragging=null;row.classList.remove('dragging');};row.ondragover=e=>e.preventDefault();row.ondrop=e=>{e.preventDefault();const ids=queue.map(p=>p.project_id).filter(id=>id!==dragging);ids.splice(ids.indexOf(p.project_id),0,dragging);if(dragging!==p.project_id)reorder(ids);};const buttons=node('span','');for(const [text,offset] of [['↑',-1],['↓',1]]){const button=node('button',text);button.setAttribute('aria-label',`${p.display_name} ${offset<0?'nach oben':'nach unten'}`);button.disabled=i+offset<0||i+offset>=queue.length;button.onclick=()=>{const ids=queue.map(p=>p.project_id);[ids[i],ids[i+offset]]=[ids[i+offset],ids[i]];reorder(ids);};buttons.append(button);}row.append(buttons);$('queue').append(row);});
  $('limits').replaceChildren(...(state.unsnooze.sessions||[]).filter(s=>s.status==='stopped').map(s=>node('p',`${s.agent}: ${s.limitType||'Usage limit'} · Reset: ${s.resetAt?new Date(s.resetAt).toLocaleString():'unbekannt'}`)));
}
$('pause-all').onclick=()=>act('pause-all');$('logout').onclick=()=>act('logout');refresh().catch(e=>$('notice').textContent=e.message);setInterval(()=>{if(!dragging)refresh().catch(e=>$('notice').textContent=e.message);},5000);
