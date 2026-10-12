'use strict';
// Only measured samples; dashed bridges mark unobserved intervals, not a predicted refill.
let usageView = 'weekly', usageData, usageLoading = false, usageRetryAt = 0;
let usageAccount = null, usageChartSignature, usageChartContext, usageHoverIndex = null;
let usageSelectedAccount = null, usageAccountsSignature;
const usageElement = id => document.getElementById('usage-' + id);
const usagePercent = value => Number.isFinite(value) ? value.toLocaleString('en-GB', {maximumFractionDigits: 1}) + '%' : '—';
const usageDate = stamp => new Date(stamp * 1000).toLocaleString('en-GB', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'});
function refreshUsageAccounts(state) {
  const accounts = state.accounts || [];
  if (!accounts.some(account => account.account_id === usageSelectedAccount)) usageSelectedAccount = null;
  const selected = usageSelectedAccount || state.active_account;
  usageElement('account-current').textContent = accounts.find(account => account.account_id === selected)?.name || 'Awaiting account';
  const signature = JSON.stringify([accounts.map(account => [account.account_id, account.name]), selected]);
  if (signature !== usageAccountsSignature) {
    usageAccountsSignature = signature;
    usageElement('account-options').replaceChildren(...accounts.map(account => {
      const option = document.createElement('button');
      option.type = 'button'; option.textContent = account.name;
      option.className = 'usage-account-option';
      option.setAttribute('aria-pressed', String(account.account_id === selected));
      option.onclick = () => {
        usageSelectedAccount = account.account_id; usageElement('account-menu').open = false;
        refreshUsageAccounts(state);
      };
      return option;
    }));
  }
  usageElement('account-menu').hidden = !accounts.length;
  refreshUsage(selected === state.active_account ? state.account_usage?.checked_at : undefined, selected);
}
usageElement('account-menu').onkeydown = event => {
  if (event.key === 'Escape') { usageElement('account-menu').open = false; usageElement('account-menu').querySelector('summary').focus(); }
};
function usageSvg(tag, attributes) {
  const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  return element;
}
function renderUsage() {
  if (!usageData) return;
  const {windows, history, checked_at: checked, server_time: now} = usageData;
  for (const series of ['daily', 'weekly']) {
    const window = windows[series], bar = usageElement(series + '-bar');
    usageElement(series + '-value').textContent = usagePercent(window?.remaining);
    bar.hidden = !window;
    if (window) { bar.value = window.remaining; bar.setAttribute('aria-valuetext', usagePercent(window.remaining) + ' remaining'); }
    usageElement(series + '-label').textContent = series === 'weekly' ? 'Weekly' : window?.duration === 1440 ? 'Daily / 24h' : 'Daily / 5h';
    const reset = window?.reset_at, seconds = reset - now;
    usageElement(series + '-reset').textContent = !window ? 'Usage unavailable' : !reset ? 'Reset unavailable'
      : seconds <= 0 ? 'Reset reached · awaiting confirmation'
      : 'Resets in ' + (seconds >= 86400 ? Math.ceil(seconds / 86400) + 'd' : seconds >= 3600 ? Math.ceil(seconds / 3600) + 'h' : Math.ceil(seconds / 60) + 'm') + ' · ' + usageDate(reset);
    usageElement(series).setAttribute('aria-pressed', String(series === usageView));
  }
  const stale = !checked || now - checked > 180;
  usageElement('freshness').textContent = usageData.error ? 'Usage unavailable' : stale ? checked ? 'Last updated ' + usageDate(checked) : 'Awaiting account data' : 'Live';
  usageElement('freshness').title = usageData.error || (checked ? 'Last measured ' + usageDate(checked) : '');
  usageElement('freshness').classList.toggle('account-warning', stale || Boolean(usageData.error));
  usageElement('chart-title').textContent = usageElement(usageView + '-label').textContent;
  usageElement('chart-value').textContent = usagePercent(windows[usageView]?.remaining);
  usageElement('chart-card').className = 'panel usage-' + usageView;
  const samples = history[usageView] || [];
  const signature = JSON.stringify([usageAccount, usageView, samples]);
  if (signature === usageChartSignature) return; // Unchanged polling must not restart the chart.
  usageChartSignature = signature; hideUsageTooltip();
  const context = JSON.stringify([usageAccount, usageView]), animatePoints = context === usageChartContext;
  usageChartContext = context;
  const span = usageView === 'weekly' ? 7 * 86400 : 86400;
  const end = samples.at(-1)?.observed_at ?? checked ?? now;
  const start = Math.max(end - span, Math.min(samples[0]?.observed_at ?? end - 1800, end - 1800));
  const x = stamp => 12 + (stamp - start) / (end - start) * 976, y = remaining => 178 - remaining * 1.64;
  const chart = usageElement('chart');
  let svg = chart.querySelector('svg');
  if (!svg) {
    svg = usageSvg('svg', {viewBox: '0 0 1000 190', preserveAspectRatio: 'none', 'aria-hidden': 'true'});
    const defs = usageSvg('defs', {}), gradient = usageSvg('linearGradient', {id: 'usage-fill', x1: '0%', x2: '0%', y1: '0%', y2: '100%'});
    gradient.append(usageSvg('stop', {offset: '0%', 'stop-color': 'var(--usage-accent)', 'stop-opacity': '.22'}), usageSvg('stop', {offset: '100%', 'stop-color': 'var(--usage-accent)', 'stop-opacity': '0'}));
    defs.append(gradient); svg.append(defs);
    for (const percent of [0, 50, 100]) svg.append(usageSvg('line', {x1: 12, x2: 988, y1: y(percent), y2: y(percent), class: 'usage-grid'}));
    for (const fraction of [.25, .5, .75]) svg.append(usageSvg('line', {x1: 12 + 976 * fraction, x2: 12 + 976 * fraction, y1: 14, y2: 178, class: 'usage-grid usage-grid-time'}));
    svg.append(usageSvg('g', {class: 'usage-plot'})); chart.append(svg);
  }
  const plot = svg.querySelector('.usage-plot'), groups = new Map();
  for (const sample of samples) {
    if (!groups.has(sample.segment)) groups.set(sample.segment, []);
    groups.get(sample.segment).push(sample);
  }
  const kept = new Set(); let previous;
  for (const [segment, points] of groups) {
    const key = String(segment); kept.add(key);
    let group = [...plot.children].find(el => el.dataset.segment === key);
    if (!group) {
      group = usageSvg('g', {}); group.dataset.segment = key;
      group.append(usageSvg('path', {class: 'usage-gap'}), usageSvg('path', {class: 'usage-area'}), usageSvg('path', {class: 'usage-line'}), usageSvg('circle', {r: 3, class: 'usage-point'}));
      plot.append(group);
    }
    const first = points[0], last = points.at(-1);
    const coordinate = point => x(point.observed_at).toFixed(2) + ',' + y(point.remaining).toFixed(2);
    // Bounded curves soften consumption; upward refills keep their explicit jump.
    const path = points.map((point, index) => {
      if (!index) return 'M' + coordinate(point);
      const previous = points[index - 1];
      if (point.remaining > previous.remaining) return 'L' + coordinate(point);
      const middle = ((x(previous.observed_at) + x(point.observed_at)) / 2).toFixed(2);
      return 'C' + middle + ',' + y(previous.remaining).toFixed(2) + ' ' + middle + ',' + y(point.remaining).toFixed(2) + ' ' + coordinate(point);
    }).join(' ');
    group.querySelector('.usage-line').setAttribute('d', points.length > 1 ? path : '');
    group.querySelector('.usage-area').setAttribute('d', points.length > 1 ? path + ' L' + x(last.observed_at).toFixed(2) + ',178 L' + x(first.observed_at).toFixed(2) + ',178 Z' : '');
    const gap = group.querySelector('.usage-gap');
    gap.setAttribute('d', previous && previous.duration === first.duration ? 'M' + coordinate(previous) + ' L' + coordinate(first) : '');
    if (!gap.firstChild) { gap.append(usageSvg('title', {})); gap.firstChild.textContent = 'Unobserved interval; only the endpoints were measured'; }
    const point = group.querySelector('.usage-point'), oldX = Number(point.getAttribute('cx')), oldY = Number(point.getAttribute('cy'));
    const moved = point.hasAttribute('cx') && (oldX !== x(last.observed_at) || oldY !== y(last.remaining));
    point.getAnimations().forEach(animation => animation.cancel());
    point.setAttribute('cx', x(last.observed_at)); point.setAttribute('cy', y(last.remaining));
    if (animatePoints && moved && !matchMedia('(prefers-reduced-motion: reduce)').matches)
      point.animate([{transform: 'translate(' + (oldX - x(last.observed_at)) + 'px,' + (oldY - y(last.remaining)) + 'px)'}, {transform: 'translate(0,0)'}], {duration: 350, easing: 'ease-out'});
    previous = last;
  }
  for (const group of [...plot.children]) if (!kept.has(group.dataset.segment)) group.remove();
  chart.setAttribute('aria-label', usageElement('chart-title').textContent + ': remaining usage, 0 to 100 percent. ' + samples.length + ' measured samples. Dashed lines mark unobserved intervals. Use left/right arrow keys to inspect measurements.');
  usageElement('empty').hidden = samples.length > 0;
  usageElement('from').textContent = samples.length ? usageDate(start) : '';
  usageElement('to').textContent = samples.length ? usageDate(end) : '';
}
function hideUsageTooltip() {
  usageHoverIndex = null;
  for (const id of ['tooltip', 'cursor', 'hover-point']) usageElement(id).hidden = true;
}
function showUsageTooltip(index) {
  const samples = usageData?.history[usageView] || [], sample = samples[index];
  if (!sample) return hideUsageTooltip();
  usageHoverIndex = index;
  const end = samples.at(-1).observed_at, span = usageView === 'weekly' ? 7 * 86400 : 86400;
  const start = Math.max(end - span, Math.min(samples[0].observed_at, end - 1800));
  const position = (12 + (sample.observed_at - start) / (end - start) * 976) / 10;
  const chart = usageElement('chart'), tooltip = usageElement('tooltip');
  for (const id of ['tooltip', 'cursor', 'hover-point']) usageElement(id).hidden = false;
  usageElement('tooltip-time').textContent = new Date(sample.observed_at * 1000).toLocaleString('en-GB');
  usageElement('tooltip-time').dateTime = new Date(sample.observed_at * 1000).toISOString();
  usageElement('tooltip-value').textContent = usagePercent(sample.remaining) + ' remaining';
  usageElement('cursor').style.left = position + '%';
  usageElement('hover-point').style.left = position + '%';
  usageElement('hover-point').style.top = (178 - sample.remaining * 1.64) / 1.9 + '%';
  tooltip.style.left = Math.max(8, Math.min(chart.clientWidth - tooltip.offsetWidth - 8, chart.clientWidth * position / 100 - tooltip.offsetWidth / 2)) + 'px';
}
const usageChart = usageElement('chart');
usageChart.onpointermove = event => {
  const samples = usageData?.history[usageView] || [];
  if (!samples.length) return;
  const bounds = usageChart.getBoundingClientRect(), end = samples.at(-1).observed_at;
  const span = usageView === 'weekly' ? 7 * 86400 : 86400;
  const start = Math.max(end - span, Math.min(samples[0].observed_at, end - 1800));
  const time = start + ((event.clientX - bounds.left) / bounds.width * 1000 - 12) / 976 * (end - start);
  const index = samples.reduce((best, sample, index) => Math.abs(sample.observed_at - time) < Math.abs(samples[best].observed_at - time) ? index : best, 0);
  showUsageTooltip(index);
};
usageChart.onpointerleave = usageChart.onblur = hideUsageTooltip;
usageChart.onkeydown = event => {
  if (event.key === 'Escape') return hideUsageTooltip();
  const count = usageData?.history[usageView]?.length || 0;
  const offset = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0;
  if (!offset || !count) return;
  event.preventDefault(); showUsageTooltip(Math.max(0, Math.min(count - 1, (usageHoverIndex ?? count - 1) + offset)));
};
async function refreshUsage(checked, accountId = null) {
  if (usageAccount !== accountId) {
    usageAccount = accountId; usageRetryAt = 0;
    usageData = {account_id: accountId, windows: {}, history: {}, checked_at: null, server_time: Date.now() / 1000};
    renderUsage(); // Clear the previous account immediately, including an in-flight response.
  }
  if (usageLoading || Date.now() < usageRetryAt || (usageData && checked === usageData.checked_at && Date.now() < usageData.refreshAfter)) return;
  usageLoading = true;
  try {
    const response = await fetch('/api/usage' + (accountId ? '?account_id=' + encodeURIComponent(accountId) : ''), {signal: AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error('Usage history unavailable (' + response.status + ')');
    const data = await response.json();
    if ((data.account_id ?? null) !== usageAccount) return;
    usageData = data; usageData.refreshAfter = Date.now() + 60000;
    renderUsage();
  } catch (error) {
    if (accountId !== usageAccount) return;
    usageElement('freshness').textContent = 'Usage unavailable · cached values'; usageElement('freshness').title = error.message;
    usageElement('freshness').classList.add('account-warning'); usageRetryAt = Date.now() + 60000;
  } finally {
    usageLoading = false;
    if (accountId !== usageAccount) refreshUsage(undefined, usageAccount);
  }
}
for (const series of ['weekly', 'daily']) usageElement(series).onclick = () => { usageView = series; renderUsage(); };
