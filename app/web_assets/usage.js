'use strict';
// No chart dependency, synthetic samples or client-side quota reset predictions.
let usageView = 'weekly', usageData, usageLoading = false, usageRetryAt = 0;
let usageAccount = null;
const usageElement = id => document.getElementById('usage-' + id);
const usagePercent = value => Number.isFinite(value) ? value.toLocaleString('de-DE', {maximumFractionDigits: 1}) + ' %' : '—';
const usageDate = stamp => new Date(stamp * 1000).toLocaleString('de-DE', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'});
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
    if (window) { bar.value = window.remaining; bar.setAttribute('aria-valuetext', usagePercent(window.remaining) + ' verfügbar'); }
    usageElement(series + '-label').textContent = series === 'weekly' ? 'Weekly' : window?.duration === 1440 ? 'Daily / 24h' : 'Daily / 5h';
    const reset = window?.reset_at;
    usageElement(series + '-reset').textContent = !window ? 'Messwert nicht verfügbar' : !reset ? 'Reset-Zeit nicht verfügbar'
      : reset <= now ? 'Reset-Zeit erreicht · neue Bestätigung abwarten (' + usageDate(reset) + ')'
      : 'Reset ' + usageDate(reset) + ' · in ' + (reset - now >= 86400 ? Math.ceil((reset - now) / 86400) + ' Tagen' : Math.ceil((reset - now) / 3600) + ' h');
    usageElement(series).setAttribute('aria-pressed', String(series === usageView));
  }
  const stale = !checked || now - checked > 180;
  usageElement('freshness').textContent = (usageData.error ? 'Abruf fehlgeschlagen: ' + usageData.error + ' · ' : '')
    + (stale ? 'Veraltete / fehlende Daten · ' : '') + (checked ? 'Letzte Messung: ' + usageDate(checked) : 'Noch keine Kontomessung');
  usageElement('chart-title').textContent = usageElement(usageView + '-label').textContent;
  usageElement('chart-value').textContent = usagePercent(windows[usageView]?.remaining);
  usageElement('chart-card').className = 'panel usage-' + usageView;
  const samples = history[usageView] || [], span = usageView === 'weekly' ? 7 * 86400 : 86400;
  const end = now, start = Math.max(now - span, Math.min(samples[0]?.observed_at ?? now - 1800, now - 1800));
  const x = stamp => 26 + (stamp - start) / (end - start) * 948, y = remaining => 174 - remaining * 1.6;
  const svg = usageSvg('svg', {viewBox: '0 0 1000 190', preserveAspectRatio: 'none', 'aria-hidden': 'true'});
  for (const percent of [0, 50, 100]) {
    svg.append(usageSvg('line', {x1: 26, x2: 974, y1: y(percent), y2: y(percent), class: 'usage-grid'}));
  }
  for (const fraction of [.25, .5, .75]) svg.append(usageSvg('line', {x1: 26 + 948 * fraction, x2: 26 + 948 * fraction, y1: 14, y2: 174, class: 'usage-grid usage-grid-time'}));
  const plot = usageSvg('g', {class: 'usage-plot'}), segments = new Map();
  for (const sample of samples) {
    if (!segments.has(sample.segment)) segments.set(sample.segment, []);
    segments.get(sample.segment).push(sample);
  }
  for (const points of segments.values()) {
    const first = points[0], last = points[points.length - 1];
    // Straight connections with rounded joins avoid spline overshoot above 100 or below 0.
    const path = points.map((point, index) => (index ? 'L' : 'M') + x(point.observed_at).toFixed(2) + ',' + y(point.remaining).toFixed(2)).join(' ');
    if (points.length > 1) {
      plot.append(usageSvg('path', {d: path + ' L' + x(last.observed_at).toFixed(2) + ',174 L' + x(first.observed_at).toFixed(2) + ',174 Z', class: 'usage-area'}));
      plot.append(usageSvg('path', {d: path, class: 'usage-line'}));
    }
    plot.append(usageSvg('circle', {cx: x(last.observed_at), cy: y(last.remaining), r: 2.5, class: 'usage-point'}));
  }
  svg.append(plot);
  const chart = usageElement('chart');
  chart.setAttribute('aria-label', usageElement('chart-title').textContent + ': verbleibende Usage, 0 bis 100 Prozent. '
    + samples.length + ' echte Messpunkte. ' + (samples.length ? usageDate(samples[0].observed_at) + ' bis ' + usageDate(samples[samples.length - 1].observed_at) : 'Noch kein Verlauf.'));
  chart.replaceChildren(svg);
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches) plot.animate([{opacity: .25}, {opacity: 1}], {duration: 450, easing: 'ease-out'});
  usageElement('from').textContent = usageDate(start); usageElement('to').textContent = usageDate(end);
  usageElement('history-note').textContent = !samples.length ? 'Noch kein Verlauf · echte Messwerte werden ab jetzt gesammelt.'
    : samples.length === 1 ? 'Erster Messpunkt gespeichert · der Verlauf wächst mit weiteren Messungen.'
    : '0–100 % verfügbar · Linie verbindet echte Messpunkte · Messlücken bleiben offen · ältere Werte verdichtet.';
}
async function refreshUsage(checked, accountId = null) {
  if (usageAccount !== accountId) {
    usageAccount = accountId; usageRetryAt = 0;
    usageData = {account_id: accountId, windows: {}, history: {}, checked_at: null, server_time: Date.now() / 1000};
    renderUsage(); // Never leave another account's percentages/history on screen.
  }
  if (usageLoading || Date.now() < usageRetryAt || (usageData && checked === usageData.checked_at && Date.now() < usageData.refreshAfter)) return;
  usageLoading = true;
  try {
    const response = await fetch('/api/usage', {signal: AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error('Usage-Verlauf nicht erreichbar (' + response.status + ')');
    const data = await response.json();
    if ((data.account_id ?? null) !== usageAccount) return; // A previous account's in-flight response.
    usageData = data; usageData.refreshAfter = Date.now() + 60000;
    renderUsage();
  } catch (error) {
    if (accountId !== usageAccount) return;
    usageElement('freshness').textContent = error.message + ' · angezeigte Werte möglicherweise veraltet';
    usageRetryAt = Date.now() + 60000;
  } finally { usageLoading = false; }
}
for (const series of ['weekly', 'daily']) usageElement(series).onclick = () => { usageView = series; renderUsage(); };
