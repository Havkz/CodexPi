'use strict';
let state, dragging, refreshing = false, busy = false, connected = false, detailId = null, lifecycleIntent, pendingAction, submittingProject;
let accountSubmitting = false, pendingAccount, removingAccount;
const $ = id => document.getElementById(id);
const node = (tag, text = '', cls = '') => {
  const el = document.createElement(tag); el.textContent = text; el.className = cls; return el;
};
const date = stamp => stamp ? new Date(stamp * 1000).toLocaleString('de-DE') : 'Noch nicht verfügbar';
const badge = status => node('span', status || 'unknown', 'badge status-' + (status || 'unknown').replaceAll(' ', '-'));
const projectStatus = p => p.goal_status === 'complete' && !p.completion_notified ? 'verifying' : p.goal_status;
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
  const summary = p.block_summary; if (!summary) return null;
  const box = node('div', '', 'block-reason');
  function section(title, values) {
    const part = node('section'); part.append(node('strong', title));
    if (values.length === 1) part.append(node('p', values[0]));
    else { const list = node('ol'); values.forEach(text => list.append(node('li', text))); part.append(list); }
    box.append(part);
  }
  section(summary.reasons.length > 1 ? 'Reasons' : 'Reason', summary.reasons);
  section('Erklärung', [summary.explanation]);
  const solutions = [...summary.solution];
  if (summary.reset_at) solutions.push('Reset: ' + new Date(summary.reset_at).toLocaleString('de-DE'));
  section('Lösung', solutions);
  if (summary.requires_user) box.append(node('p', 'Kein automatisches Resume ohne Nutzerfreigabe.', 'muted'));
  if (summary.details) {
    const details = node('details'); details.dataset.project = p.project_id;
    details.append(node('summary', 'Technische Details'), node('pre', summary.details)); box.append(details);
  }
  return box;
}
function accountPending() {
  return accountSubmitting || Boolean(state?.account_operation?.phase && !['complete', 'failed', 'recovery_required'].includes(state.account_operation.phase));
}
function renderAccounts() {
  const current = state.accounts?.find(a => a.account_id === state.active_account), operation = state.account_operation || {};
  $('account-current').textContent = current?.name || 'Account noch nicht bestätigt';
  const pending = accountPending(), blocked = pending || operation.phase === 'recovery_required';
  const summary = $('account-menu').querySelector('summary');
  summary.setAttribute('aria-disabled', String(blocked || !connected));
  summary.classList.toggle('loading', pending); summary.setAttribute('aria-busy', String(pending));
  if (blocked) $('account-menu').open = false;
  $('account-options').replaceChildren(...(state.accounts || []).map(account => {
    const row = node('div', '', 'account-option'), invalid = account.status !== 'ready';
    const choose = button((invalid ? '⚠ ' : '') + account.name + (account.account_id === state.active_account ? ' · aktiv' : ''),
      () => accountAct(invalid ? 'account-add' : 'account-switch', {account_id: account.account_id}), null, invalid ? 'account-warning' : '');
    choose.disabled = blocked || !connected || !invalid && account.account_id === state.active_account;
    if (invalid) choose.title = 'Erneute reguläre Anmeldung erforderlich';
    const remove = button('×', () => {
      removingAccount = account; $('account-remove-name').textContent = account.name;
      $('account-remove-error').textContent = ''; $('account-menu').open = false;
      $('account-remove-dialog').showModal();
    }, null, 'danger');
    remove.setAttribute('aria-label', account.name + ' entfernen');
    remove.disabled = blocked || !connected || account.account_id === state.active_account;
    if (account.account_id === state.active_account) remove.title = 'Vor dem Entfernen zu einem anderen Account wechseln';
    row.append(choose, remove); return row;
  }));
  const add = button('＋ Account hinzufügen', () => accountAct('account-add'));
  add.disabled = blocked || !connected; $('account-options').append(add);
  const labels = {waiting_turn: 'Accountwechsel wartet auf den Abschluss des aktuellen Turns …',
    checkpointing: 'Bisherige Anmeldung wird sicher gespeichert …', installing: 'Anmeldung wird gewechselt …',
    reloading: 'Native Codex-Verbindung wird wiederhergestellt …', starting_login: 'Regulärer Browserlogin wird gestartet …',
    logging_in: 'Login im Windows-Browser abschließen (maximal 10 Minuten).',
    verifying: 'Aktiver Account und echte Limits werden bestätigt …', resuming: 'Bestehende Session wird fortgesetzt …',
    confirming_resume: 'Account bestätigt; native Fortsetzung wird noch überprüft …'};
  $('account-status').textContent = accountSubmitting ? 'Anfrage wird übermittelt …' : operation.error || operation.message || labels[operation.phase]
    || (state.account_wait ? (state.account_wait.reason === 'queue' ? 'Account bestätigt; Fortsetzung wartet auf Queue-Position 1' : 'Account bestätigt; auf echte verfügbare Usage warten') + (state.account_wait.reset_at ? ' · Reset: ' + date(state.account_wait.reset_at) : '')
      : operation.phase === 'complete' ? 'Account und Limits bestätigt.' : 'Anmeldungen bleiben geschützt auf dem Pi.');
  $('account-status').classList.toggle('account-warning', Boolean(operation.error));
  $('account-recovery').hidden = operation.phase !== 'recovery_required' && operation.phase !== 'logging_in';
  $('account-retry').hidden = operation.phase !== 'recovery_required' || operation.failed_phase === 'starting_login';
  $('account-restore').textContent = operation.phase === 'logging_in' ? 'Login abbrechen · bisherigen Account wiederherstellen' : 'Bisherigen Account wiederherstellen';
  for (const id of ['account-retry', 'account-restore']) $(id).disabled = accountSubmitting || !connected;
  if (!busy) $('auto-account-change').checked = Boolean(state.auto_account_change);
  $('auto-account-change').disabled = busy || accountSubmitting || !connected;
}
async function accountAct(action, extra = {}) {
  if (accountSubmitting || !connected || busy) return false;
  if (accountPending() && action !== 'account-restore') return false;
  accountSubmitting = true; $('account-menu').open = false; render();
  try {
    const response = await fetch('/api/action', {method: 'POST', signal: AbortSignal.timeout(45000),
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': state.csrf}, body: JSON.stringify({action, ...extra})});
    const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Account-Aktion fehlgeschlagen');
    if (result.operation_id) pendingAccount = {id: result.operation_id, deadline: Date.now() + 75 * 60000};
    return true;
  } catch (error) { $('notice').textContent = error.message; return false; }
  finally { accountSubmitting = false; await refresh(); render(); }
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
      (['resume', 'run-now'].includes(action) && (accountPending() || state.account_operation?.phase === 'recovery_required')) ||
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
  name.append(node('h3', p.display_name), badge(projectStatus(p))); header.append(name);
  header.append(node('span', p.queue_position == null ? 'Nicht in Queue' : 'Priority ' + p.queue_position, 'counter')); body.append(header);
  body.append(metadata([
    ['Repo', repo(p)], ['Session', p.codex_session_id, true], ['tmux', p.tmux_session_name, true], ['CI', p.last_ci_status || 'unknown'],
    ['Letzte Aktivität', date(p.last_activity)], ['Commit', p.last_commit?.slice(0, 12), true],
    ['Windows Requirement', p.windows_required ? 'Required' : 'Nicht angefordert'], ['Discord Channel', p.discord_channel_id, true]
  ]));
  const blocker = block(p); if (blocker) body.append(blocker);
  if (projectStatus(p) === 'verifying') body.append(node('p', p.completion_check?.message || 'Goal beendet. Abschlussprüfung läuft.', 'notice'));
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
    const status = node('td'); status.append(badge(projectStatus(p)));
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
  const expandedBlocks = new Set([...document.querySelectorAll('.block-reason details[open]')].map(el => el.dataset.project));
  const focused = document.activeElement, focus = focused?.dataset.key;
  const queue = state.projects.filter(p => p.queue_position !== null);
  const active = state.projects.find(p => p.project_id === state.selected);
  const stalled = state.projects.filter(p => p.goal_status === 'stalled').length;
  renderAccounts();
  $('pause-all').disabled = busy || !connected; $('logout').disabled = busy || !connected;
  if (!busy) $('auto-continue').checked = Boolean(state.auto_continue);
  $('auto-continue').disabled = busy || !connected;
  if (!busy) $('auto-boot-windows').checked = Boolean(state.auto_boot_windows);
  $('auto-boot-windows').disabled = busy || !connected;
  $('windows-power-state').textContent = state.windows_power?.message || '';
  const summary = [
    [String(state.projects.filter(p => p.goal_status === 'active').length), 'Active Project', active?.display_name || 'Kein aktives Projekt'],
    [String(queue.filter(p => p.project_id !== state.selected).length), 'Queue Length', 'Wartende Projekte'],
    [state.windows_online ? 'Online' : 'Offline', 'Windows Worker', 'Heartbeat alle 20 Sekunden'],
    [String(state.projects.filter(p => p.goal_status === 'complete' && p.completion_notified).length), 'Completed Projects', stalled + ' stalled']
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
    const card = node('article', '', 'project-card'); card.append(badge(projectStatus(p)), node('h3', p.display_name));
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
  for (const p of state.projects.filter(p => p.goal_status === 'limited by budget')) {
    const row = node('div', '', 'limit-row'); row.append(badge(p.goal_status), node('strong', p.display_name), node('span', 'Manuelle Freigabe erforderlich.', 'muted')); $('limits').append(row);
  }
  if (!$('limits').children.length) $('limits').append(node('p', 'Kein projektbezogenes Usage- oder Budget-Limit gemeldet.', 'muted'));
  const detailOverview = $('detail-overview'), currentDetail = state.projects.find(p => p.project_id === detailId);
  if (detailOverview && currentDetail) detailOverview.replaceChildren(node('h3', 'Overview'), projectOverview(currentDetail, true));
  if (detailId && !currentDetail) $('project-dialog').close();
  document.querySelectorAll('.block-reason details').forEach(el => { el.open = expandedBlocks.has(el.dataset.project); });
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
    if (pendingAccount) {
      const operation = state.account_operation || {};
      if (operation.id === pendingAccount.id && ['complete', 'failed', 'recovery_required'].includes(operation.phase)) {
        if (operation.error) $('notice').textContent = operation.error;
        pendingAccount = null;
      } else if (Date.now() > pendingAccount.deadline) {
        $('notice').textContent = 'Keine Account-Bestätigung erhalten. Controller-Zustand prüfen; kein automatischer erneuter Wechsel.';
        pendingAccount = null;
      }
    }
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
    refreshUsage(state.account_usage?.checked_at, state.active_account);
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
    : 'Das Projekt wird gestoppt und aus CodexPi entfernt. Der Discord Channel wird gelöscht. GitHub bleibt standardmäßig erhalten; lokale Pi-Daten bleiben in einem Recovery-Backup. Windows-Checkouts werden nicht gelöscht.';
  $('lifecycle-label').textContent = action === 'rename' ? 'Neuer Projektname' : 'Zur Bestätigung exakt eingeben: ' + project.display_name;
  $('lifecycle-input').value = action === 'rename' ? project.display_name : '';
  $('lifecycle-github-option').hidden = action !== 'delete';
  $('lifecycle-delete-github').checked = false;
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
  const deleteGithub = action === 'delete' && $('lifecycle-delete-github').checked;
  const ok = await act(action, project.project_id, action === 'rename' ? {name: value} : {confirmation: value, delete_github: deleteGithub});
  $('lifecycle-submit').disabled = false; $('lifecycle-cancel').disabled = false;
  if (ok) { $('lifecycle-dialog').close(); if (action === 'delete') $('notice').textContent = deleteGithub
    ? 'Projekt und GitHub-Repository entfernt. Das lokale Recovery-Backup bleibt erhalten.'
    : 'Projekt entfernt. GitHub und das lokale Recovery-Backup bleiben erhalten.'; }
  else $('lifecycle-error').textContent = $('notice').textContent;
};
$('pause-all').onclick = () => act('pause-all'); $('logout').onclick = () => act('logout');
$('auto-continue').onchange = event => act('auto-continue', null, {enabled: event.target.checked});
$('auto-account-change').onchange = event => act('auto-account-change', null, {enabled: event.target.checked});
$('auto-boot-windows').onchange = event => act('auto-boot-windows', null, {enabled: event.target.checked});
$('account-retry').onclick = () => accountAct('account-retry');
$('account-restore').onclick = () => accountAct('account-restore');
$('account-remove-cancel').onclick = () => $('account-remove-dialog').close();
$('account-remove-form').onsubmit = async event => {
  event.preventDefault(); if (accountSubmitting || !removingAccount) return;
  $('account-remove-submit').disabled = true; $('account-remove-cancel').disabled = true;
  const ok = await accountAct('account-remove', {account_id: removingAccount.account_id, confirmation: removingAccount.name});
  $('account-remove-submit').disabled = false; $('account-remove-cancel').disabled = false;
  if (ok) { $('account-remove-dialog').close(); removingAccount = null; }
  else $('account-remove-error').textContent = $('notice').textContent;
};
$('close-detail').onclick = () => $('project-dialog').close();
$('project-dialog').addEventListener('close', () => { detailId = null; });
refresh(); setInterval(() => { if (!dragging && (!busy || pendingAction) && (!document.hidden || pendingAction || pendingAccount || accountPending())) refresh(); }, 2000);
