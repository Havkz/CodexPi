'use strict';
let state, dragging, refreshing = false, busy = false, connected = false, detailId = null, lifecycleIntent, pendingAction, submittingProject;
const $ = id => document.getElementById(id);
const node = (tag, text = '', cls = '') => {
  const el = document.createElement(tag); el.textContent = text; el.className = cls; return el;
};
const date = stamp => stamp ? new Date(stamp * 1000).toLocaleString('de-DE') : 'Noch nicht verfügbar';
const badge = status => node('span', status || 'unknown', 'badge status-' + (status || 'unknown').replaceAll(' ', '-'));
function button(text, callback, key, cls = '') {
  const el = node('button', text, cls); el.type = 'button'; el.onclick = callback;
  if (key) el.dataset.key = key;
  return el;
}
function link(text, url) {
  const el = node('a', text); el.href = url; el.target = '_blank'; el.rel = 'noopener noreferrer'; return el;
}
function metadata(rows) {
  const dl = node('dl', '', 'metadata');
  for (const [label, value, technical] of rows) {
    const entry = node('div'), dd = node('dd'); entry.append(node('dt', label));
    dd.append(value instanceof Node ? value : node(technical ? 'code' : 'span', value || '—'));
    entry.append(dd); dl.append(entry);
  }
  return dl;
}
function repo(p) { return p.github_repo ? link(p.github_repo, 'https://github.com/' + p.github_repo) : '—'; }
function block(p) {
  if (!p.block_reason) return null;
  let reason; try { reason = JSON.parse(p.block_reason); } catch { reason = {reason: p.block_reason}; }
  const box = node('div', '', 'block-reason'); box.append(node('strong', 'Block Reason'));
  box.append(node('p', reason.reason || String(p.block_reason)));
  if (reason.details) box.append(node('p', reason.details));
  if (reason.requires_user) box.append(node('p', 'Benutzereingabe erforderlich. Kein automatisches Resume.'));
  return box;
}
async function act(action, project_id, extra = {}) {
  if (busy || !connected) return;
  busy = true; submittingProject = ['resume', 'run-now'].includes(action) ? project_id : null;
  $('notice').textContent = 'Änderung wird ausgeführt …'; render();
  let success = false;
  try {
    const res = await fetch('/api/action', {method: 'POST', signal: AbortSignal.timeout(45000), headers: {'Content-Type': 'application/json', 'X-CSRF-Token': state.csrf}, body: JSON.stringify({action, project_id, ...extra})});
    if (!res.ok) { const text = await res.text(); let error; try { error = JSON.parse(text).error; } catch {} throw new Error(error || text.slice(0, 300)); }
    if (action === 'logout') { location.reload(); return; }
    const response = await res.json();
    if (response.operation_id) {
      pendingAction = {project_id, id: response.operation_id, deadline: Date.now() + 90000};
      $('notice').textContent = 'Native Session wird wiederhergestellt und bestätigt …';
    } else $('notice').textContent = '';
    success = true;
  } catch (err) { $('notice').textContent = err.message; }
  finally { submittingProject = null; busy = Boolean(pendingAction); await refresh(); }
  return success;
}
function actions(p, compact = false, inDetail = false) {
  const result = node('div', '', 'actions' + (compact ? ' queue-actions' : ''));
  let operation; try { operation = JSON.parse(p.operation || '{}'); } catch { operation = {}; }
  const resuming = operation.kind === 'resume' && !operation.error && state.selected === p.project_id;
  const list = [['Resume', 'resume'], ['Pause', 'pause']];
  if (p.queue_position > 1 && state.selected !== p.project_id) list.unshift(['Run now', 'run-now']);
  for (const [label, action] of list) {
    const b = button(label, () => act(action, p.project_id), p.project_id + ':' + action, action === 'run-now' ? 'primary' : '');
    const loading = action === 'resume' && (resuming || pendingAction?.project_id === p.project_id || submittingProject === p.project_id);
    if (loading) { b.textContent = 'Resume …'; b.classList.add('loading'); b.setAttribute('aria-busy', 'true'); }
    b.disabled = busy || !connected || p.lifecycle !== 'ready' || p.goal_status === 'complete' ||
      (action === 'resume' && (p.goal_status === 'active' || resuming)) ||
      (action === 'pause' && p.goal_status === 'paused' && p.manual_paused && !operation.kind);
    result.append(b);
  }
  if (!inDetail) result.append(button('Details', () => showDetail(p.project_id), p.project_id + ':details'));
  if (!compact) for (const action of ['rename', 'delete']) {
    const b = button(action === 'rename' ? 'Rename' : 'Delete', () => showLifecycle(p, action), p.project_id + ':' + action, action === 'delete' ? 'danger' : '');
    let pending; try { pending = JSON.parse(p.operation || '{}'); } catch { pending = {kind: 'unknown'}; }
    b.disabled = busy || !connected || p.lifecycle !== 'ready' || Boolean(p.operation && !(action === 'delete' && pending.kind === 'resume')); result.append(b);
  }
  return result;
}
function projectOverview(p, inDetail = false) {
  const body = node('div'), header = node('div', '', 'project-header'), name = node('div', '', 'project-name');
  name.append(node('h3', p.display_name), badge(p.goal_status)); header.append(name);
  header.append(node('span', p.queue_position == null ? 'Nicht in Queue' : 'Priority ' + p.queue_position, 'counter')); body.append(header);
  body.append(metadata([
    ['Repo', repo(p)], ['Session', p.codex_session_id, true], ['tmux', p.tmux_session_name, true], ['CI', p.last_ci_status || 'unknown'],
    ['Letzte Aktivität', date(p.last_activity)], ['Commit', p.last_commit?.slice(0, 12), true],
    ['Windows Requirement', p.windows_required ? 'Required' : 'Nicht angefordert'], ['Discord Channel', p.discord_channel_id, true]
  ]));
  const blocker = block(p); if (blocker) body.append(blocker);
  const controls = actions(p, false, inDetail); controls.classList.add('active-actions'); body.append(controls);
  if (p.resume_result) { const result = JSON.parse(p.resume_result); body.append(node('p', result.message, result.status === 'failed' ? 'error' : 'notice')); }
  if (p.lifecycle !== 'ready' || p.operation) {
    let operation; try { operation = JSON.parse(p.operation || '{}'); } catch { operation = {}; }
    body.append(node('p', 'Lifecycle: ' + p.lifecycle + ' · ' + (operation.error || 'Wird ausgeführt. Bei Unterbrechung automatisch fortgesetzt.'), 'notice'));
  }
  return body;
}
function renderQueue(queue) {
  $('queue-count').textContent = queue.length + ' projects'; $('queue-empty').hidden = queue.length > 0;
  const rows = queue.map((p, index) => {
    const row = node('tr'); row.dataset.id = p.project_id; row.draggable = connected && !busy;
    const position = node('td'), controls = node('div', '', 'queue-position'); controls.append(node('span', String(p.queue_position).padStart(2, '0')));
    for (const [text, offset] of [['↑', -1], ['↓', 1]]) {
      const b = button(text, () => {
        const ids = queue.map(item => item.project_id); [ids[index], ids[index + offset]] = [ids[index + offset], ids[index]];
        act('reorder', null, {ids});
      }, p.project_id + ':move' + offset);
      b.setAttribute('aria-label', p.display_name + (offset < 0 ? ' nach oben' : ' nach unten'));
      b.disabled = busy || !connected || index + offset < 0 || index + offset >= queue.length; controls.append(b);
    }
    position.append(controls);
    const name = node('td'); name.append(button(p.display_name, () => showDetail(p.project_id), p.project_id + ':name', 'queue-name'), node('span', p.github_repo || 'Repo nicht verfügbar', 'queue-repo mono'));
    const status = node('td'); status.append(badge(p.goal_status));
    const actionCell = node('td'); actionCell.append(actions(p, true));
    row.append(position, name, status, node('td', date(p.last_activity), 'muted'), node('td', p.windows_required ? 'Required' : '—'), actionCell);
    row.ondragstart = event => { dragging = p.project_id; event.dataTransfer.setData('text/plain', dragging); event.dataTransfer.effectAllowed = 'move'; row.classList.add('dragging'); };
    row.ondragend = () => { dragging = null; row.classList.remove('dragging'); document.querySelectorAll('.drop-target').forEach(el => el.classList.remove('drop-target')); };
    row.ondragover = event => { if (dragging) { event.preventDefault(); row.classList.add('drop-target'); } };
    row.ondragleave = () => row.classList.remove('drop-target');
    row.ondrop = event => {
      event.preventDefault(); row.classList.remove('drop-target');
      if (!dragging || dragging === p.project_id) return;
      const ids = queue.map(item => item.project_id), from = ids.indexOf(dragging);
      if (from < 0) return;
      ids.splice(from, 1); ids.splice(index, 0, dragging); dragging = null; act('reorder', null, {ids});
    };
    return row;
  });
  $('queue').replaceChildren(...rows);
}
function render() {
  if (!state) return;
  const focused = document.activeElement, focus = focused?.dataset.key;
  const queue = state.projects.filter(p => p.queue_position !== null);
  const active = state.projects.find(p => p.project_id === state.selected);
  const stalled = state.projects.filter(p => p.goal_status === 'stalled').length;
  $('pause-all').disabled = busy || !connected; $('logout').disabled = busy || !connected;
  const summary = [
    [String(state.projects.filter(p => p.goal_status === 'active').length), 'Active Project', active?.display_name || 'Kein aktives Projekt'],
    [String(queue.filter(p => p.project_id !== state.selected).length), 'Queue Length', 'Wartende Projekte'],
    [state.windows_online ? 'Online' : 'Offline', 'Windows Worker', 'Heartbeat alle 20 Sekunden'],
    [String(state.projects.filter(p => p.goal_status === 'complete').length), 'Completed Projects', stalled + ' stalled']
  ];
  $('summary').replaceChildren(...summary.map(([value, label, note]) => {
    const card = node('div', '', 'kpi'); card.append(node('div', value, 'kpi-value' + (/\D/.test(value) ? ' word' : '')), node('div', label, 'kpi-label'), node('div', note, 'kpi-note')); return card;
  }));
  $('top-status').replaceChildren(...[['Pi', connected], ['Windows', state.windows_online], ['Discord', state.discord_online], ['Unsnooze', state.unsnooze.daemonRunning]].map(([name, online]) => {
    const item = node('span'), dot = node('i', '', 'dot ' + (online ? 'online' : 'offline')); dot.setAttribute('aria-hidden', 'true'); item.append(dot, document.createTextNode(name + ' ' + (online ? 'online' : 'offline'))); return item;
  }));
  $('work-state').textContent = state.pause_all ? 'Alle Arbeit pausiert' : 'Single-worker policy';
  $('active').replaceChildren(active ? projectOverview(active) : node('p', state.pause_all ? 'Alle Arbeit pausiert. Mit Resume das erste Projekt fortsetzen.' : 'Kein Projekt ausgewählt. Die Queue wartet auf deine Freigabe.', 'empty'));
  renderQueue(queue);
  $('projects').replaceChildren(...state.projects.map(p => {
    const card = node('article', '', 'project-card'); card.append(badge(p.goal_status), node('h3', p.display_name));
    const repository = node('p', '', 'mono'); repository.append(repo(p)); card.append(repository, node('p', 'CI · ' + (p.last_ci_status || 'unknown'), 'muted'));
    card.append(actions(p, true)); return card;
  }));
  if (!state.projects.length) $('projects').append(node('p', 'Noch keine Projekte. Neue Projekte entstehen über codexpi.', 'empty'));
  const icons = ['Pi', '>_', 'W', 'git', '#', 'zZ'];
  $('infra').replaceChildren(...state.infrastructure.map((item, index) => {
    const card = node('article', '', 'infra-card'), header = node('div', '', 'card-heading');
    const icon = node('span', icons[index], 'infra-icon'); icon.setAttribute('aria-hidden', 'true');
    header.append(icon, node('h3', item.name), badge(item.status)); card.append(header, node('p', item.detail));
    card.append(node('p', 'Geprüft: ' + date(item.checked_at)));
    if ('heartbeat_age' in item) card.append(node('p', item.heartbeat_age === null ? 'Heartbeat: noch nicht empfangen' : 'Heartbeat: vor ' + Math.floor(item.heartbeat_age) + ' s'));
    if (item.error) card.append(node('p', item.error, 'error')); return card;
  }));
  const limits = state.projects.filter(p => p.goal_status === 'usage limited');
  $('limits').replaceChildren(...limits.map(p => {
    const row = node('div', '', 'limit-row'), item = JSON.parse(p.usage_limit || '{}');
    row.append(badge('usage limited'), node('strong', p.display_name), node('span', 'Reset: ' + (item.resetAt ? new Date(item.resetAt).toLocaleString('de-DE') : 'unbekannt'), 'muted')); return row;
  }));
  if (state.account_usage?.ordinaryUsageAllowed === false) $('limits').append(node('p', 'Konto: Nutzung derzeit nicht verfügbar. Eine wiederhergestellte Session ohne Goal bleibt ohne Goal.', 'notice'));
  for (const [name, window] of Object.entries(state.account_usage?.rateLimits || {}).filter(([key, value]) => ['primary', 'secondary'].includes(key) && value)) {
    $('limits').append(node('p', 'Konto · ' + name + ': ' + window.usedPercent + '% verwendet · Reset: ' + date(window.resetsAt), 'muted'));
  }
  for (const p of state.projects.filter(p => p.goal_status === 'limited by budget')) {
    const row = node('div', '', 'limit-row'); row.append(badge(p.goal_status), node('strong', p.display_name), node('span', 'Manuelle Freigabe erforderlich.', 'muted')); $('limits').append(row);
  }
  if (!$('limits').children.length) $('limits').append(node('p', 'Kein Usage-Limit gemeldet. Verbrauchsprozentwerte sind derzeit nicht verfügbar.', 'muted'));
  const detailOverview = $('detail-overview'), currentDetail = state.projects.find(p => p.project_id === detailId);
  if (detailOverview && currentDetail) detailOverview.replaceChildren(node('h3', 'Overview'), projectOverview(currentDetail, true));
  if (detailId && !currentDetail) $('project-dialog').close();
  if (focus && !focused.isConnected) document.querySelector('[data-key="' + CSS.escape(focus) + '"]')?.focus({preventScroll: true});
}
async function refresh() {
  if (refreshing || dragging) return;
  refreshing = true;
  try {
    const response = await fetch('/api/state');
    if (response.status === 401) { location.reload(); return; }
    if (!response.ok) throw new Error('Dashboard nicht erreichbar');
    state = await response.json(); connected = true;
    if (pendingAction) {
      const project = state.projects.find(p => p.project_id === pendingAction.project_id);
      const result = project?.resume_result ? JSON.parse(project.resume_result) : null;
      if (result?.id === pendingAction.id) {
        $('notice').textContent = result.message; pendingAction = null; busy = false;
      } else if (!project || Date.now() > pendingAction.deadline) {
        $('notice').textContent = !project ? 'Projekt wurde gelöscht.' : 'Keine Resume-Bestätigung innerhalb von 90 Sekunden. Projektzustand prüfen; kein automatischer erneuter Versuch.';
        pendingAction = null; busy = false;
      }
    }
    $('freshness').textContent = 'Live · ' + new Date().toLocaleTimeString('de-DE'); render();
  } catch (err) {
    connected = false; $('freshness').textContent = 'Verbindung unterbrochen · Daten möglicherweise veraltet';
    if (pendingAction && Date.now() > pendingAction.deadline) { pendingAction = null; busy = false; }
    $('notice').textContent = err.message; render();
  } finally { refreshing = false; }
}
async function showDetail(id) {
  detailId = id; $('detail-title').textContent = state.projects.find(p => p.project_id === id)?.display_name || 'Project';
  $('detail-body').replaceChildren(node('p', 'Details werden geladen …', 'muted'));
  if (!$('project-dialog').open) $('project-dialog').showModal();
  try {
    const response = await fetch('/api/projects/' + encodeURIComponent(id));
    if (!response.ok) throw new Error('Projekt-Details nicht verfügbar (' + response.status + ')');
    const detail = await response.json(); if (detailId !== id) return;
    const p = detail.project, grid = node('div', '', 'detail-grid');
    function panel(title, wide = false) { const card = node('section', '', 'panel' + (wide ? ' detail-wide' : '')); card.append(node('h3', title)); grid.append(card); return card; }
    const overview = panel('Overview', true); overview.id = 'detail-overview'; overview.append(projectOverview(p, true));
    panel('Session / tmux').append(metadata([['Session', p.codex_session_id, true], ['tmux', p.tmux_session_name, true], ['Project path', p.project_path, true], ['Lifecycle', p.lifecycle]]));
    panel('Integrations').append(metadata([['Repo', repo(p)], ['CI', p.last_ci_status || 'unknown'], ['Discord Channel', p.discord_channel_id, true], ['Windows Worker', state.windows_online ? 'online' : 'offline']]));
    const commits = panel('Commits', true);
    for (const commit of detail.commits) {
      const row = node('div', '', 'event');
      row.append(link(commit.sha.slice(0, 12), 'https://github.com/' + p.github_repo + '/commit/' + commit.sha), node('p', commit.subject), node('time', new Date(commit.date).toLocaleString('de-DE'))); commits.append(row);
    }
    if (!detail.commits.length) commits.append(node('p', detail.git_error || 'Noch keine Commits verfügbar.', 'muted'));
    const logs = panel('Windows Worker / Logs', true);
    for (const job of detail.jobs) {
      const row = node('details', '', 'event'); row.append(node('summary', job.status + ' · ' + job.job_id + ' · Exit ' + (job.exit_code ?? '—')));
      row.append(node('pre', 'stdout\n' + (job.stdout || '—') + '\n\nstderr\n' + (job.stderr || '—')));
      if (job.artifacts?.length) row.append(node('pre', JSON.stringify(job.artifacts, null, 2))); logs.append(row);
    }
    if (!detail.jobs.length) logs.append(node('p', 'Noch keine Windows-Jobs für dieses Projekt.', 'muted'));
    const events = panel('Lifecycle Events', true);
    for (const event of detail.events) {
      const row = node('details', '', 'event'); row.append(node('summary', event.kind + ' · ' + date(event.created_at)), node('pre', JSON.stringify(event.payload, null, 2))); events.append(row);
    }
    if (!detail.events.length) events.append(node('p', 'Noch keine Events erfasst.', 'muted'));
    $('detail-body').replaceChildren(grid);
  } catch (err) { if (detailId === id) $('detail-body').replaceChildren(node('p', err.message, 'notice')); }
}
function showLifecycle(project, action) {
  if ($('project-dialog').open) $('project-dialog').close();
  lifecycleIntent = {project, action};
  $('lifecycle-title').textContent = action === 'rename' ? 'Project umbenennen' : 'Project löschen';
  $('lifecycle-description').textContent = action === 'rename'
    ? 'Das Projekt wird pausiert. Name, Ordner, Repo, Discord und Session-Zuordnung werden konsistent aktualisiert. Anschließend kannst du es wieder starten.'
    : 'Das Projekt wird gestoppt und aus CodexPi entfernt. Der Discord Channel wird gelöscht. GitHub bleibt erhalten; lokale Pi-Daten bleiben in einem Recovery-Backup. Windows-Checkouts werden nicht gelöscht.';
  $('lifecycle-label').textContent = action === 'rename' ? 'Neuer Projektname' : 'Zur Bestätigung exakt eingeben: ' + project.display_name;
  $('lifecycle-input').value = action === 'rename' ? project.display_name : '';
  $('lifecycle-error').textContent = '';
  $('lifecycle-submit').textContent = action === 'rename' ? 'Umbenennen' : 'Löschen bestätigen';
  $('lifecycle-submit').className = action === 'rename' ? 'primary' : 'danger';
  $('lifecycle-dialog').showModal(); $('lifecycle-input').focus();
}
$('lifecycle-cancel').onclick = () => $('lifecycle-dialog').close();
$('lifecycle-form').onsubmit = async event => {
  event.preventDefault(); if (busy) return;
  const {project, action} = lifecycleIntent, value = $('lifecycle-input').value;
  if (action === 'delete' && value !== project.display_name) { $('lifecycle-error').textContent = 'Der Projektname stimmt nicht überein.'; return; }
  $('lifecycle-submit').disabled = true; $('lifecycle-cancel').disabled = true;
  const ok = await act(action, project.project_id, action === 'rename' ? {name: value} : {confirmation: value});
  $('lifecycle-submit').disabled = false; $('lifecycle-cancel').disabled = false;
  if (ok) { $('lifecycle-dialog').close(); if (action === 'delete') $('notice').textContent = 'Projekt entfernt. GitHub und das lokale Recovery-Backup bleiben erhalten.'; }
  else $('lifecycle-error').textContent = $('notice').textContent;
};
$('pause-all').onclick = () => act('pause-all'); $('logout').onclick = () => act('logout');
$('close-detail').onclick = () => $('project-dialog').close();
$('project-dialog').addEventListener('close', () => { detailId = null; });
refresh(); setInterval(() => { if (!dragging && (!busy || pendingAction) && (!document.hidden || pendingAction)) refresh(); }, 2000);
