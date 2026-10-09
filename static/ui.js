// ─── nGrave UI-basis: hjælpere, toasts, modal, navigation, statuslinje ───────

const $ = (id) => document.getElementById(id);

// HTML-escape af alt der kommer fra databasen/brugeren før det sættes i innerHTML.
function esc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

// "for 5 min siden" ud fra SQLite's CURRENT_TIMESTAMP (UTC, "YYYY-MM-DD HH:MM:SS")
function relTid(ts) {
  if (!ts) return '—';
  const d = new Date(String(ts).replace(' ', 'T') + (/[zZ]|[+-]\d\d:?\d\d$/.test(ts) ? '' : 'Z'));
  if (isNaN(d)) return esc(ts);
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 45) return 'lige nu';
  if (s < 3600) return `${Math.round(s / 60)} min siden`;
  if (s < 86400) return `${Math.round(s / 3600)} t siden`;
  return d.toLocaleDateString('da-DK', { day: 'numeric', month: 'short' });
}

// ─── API ─────────────────────────────────────────────────────────────────────
async function api(url, method = 'GET', data = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (data !== null) opts.body = JSON.stringify(data);
  const r = await fetch(url, opts);
  if (r.status === 401) {
    toast('Login påkrævet — genindlæs siden', 'fejl');
    throw new Error('Auth påkrævet');
  }
  let body;
  try { body = await r.json(); } catch (e) { throw new Error('Serveren svarede ikke som forventet (' + r.status + ')'); }
  return body;
}

// ─── Toasts ──────────────────────────────────────────────────────────────────
function toast(msg, type = 'info', handling = null, ms = 4200) {
  let c = $('toasts');
  if (!c) { c = document.createElement('div'); c.id = 'toasts'; document.body.appendChild(c); }
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.setAttribute('role', 'status');
  const sp = document.createElement('span');
  sp.textContent = msg;
  t.appendChild(sp);
  if (handling) {
    const b = document.createElement('button');
    b.textContent = handling.tekst;
    b.onclick = () => { handling.fn(); t.remove(); };
    t.appendChild(b);
  }
  c.appendChild(t);
  setTimeout(() => t.remove(), handling ? ms + 3000 : ms);
}

// ─── Modal ───────────────────────────────────────────────────────────────────
function aabnModal(titel, htmlIndhold) {
  let bg = $('modal-bg');
  if (!bg) {
    bg = document.createElement('div');
    bg.id = 'modal-bg';
    bg.className = 'modal-bg';
    bg.innerHTML = '<div class="modal" role="dialog" aria-modal="true"><div class="modal-head"><h2 id="modal-titel"></h2><button class="btn btn-ghost btn-sm" onclick="lukModal()" aria-label="Luk">✕</button></div><div id="modal-krop"></div></div>';
    bg.addEventListener('click', (e) => { if (e.target === bg) lukModal(); });
    document.body.appendChild(bg);
  }
  $('modal-titel').textContent = titel;
  $('modal-krop').innerHTML = htmlIndhold;
  bg.classList.add('vis');
}
function lukModal() { const bg = $('modal-bg'); if (bg) bg.classList.remove('vis'); }
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') lukModal(); });

// ─── Tema ────────────────────────────────────────────────────────────────────
function toggleTheme() {
  const next = (document.documentElement.getAttribute('data-theme') || 'dark') === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('theme', next); } catch (e) {}
}
try { document.documentElement.setAttribute('data-theme', localStorage.getItem('theme') || 'dark'); } catch (e) {}

// ─── Navigation: to produktioner (Nøgler / Skilte) + System ──────────────────
const NAV = {
  noegler: { label: '🔑 Nøgler', items: [['nyt-job', 'Nyt job'], ['koe-noegler', 'Kø'], ['templates', 'Templates']] },
  skilte:  { label: '🏷️ Skilte', items: [['skilte', 'Nyt skilt'], ['koe-skilte', 'Kø'], ['skilt-templates', 'Templates']] },
  system:  { label: '⚙ System',  items: [['maskiner', 'Maskiner & system']] },
};
let aktivSide = null;
let _refreshTimer = null;

function sektionFor(id) {
  return Object.keys(NAV).find((k) => NAV[k].items.some((i) => i[0] === id));
}

function byggNav() {
  $('nav-main').innerHTML = Object.entries(NAV).map(([k, v]) =>
    `<button data-sek="${k}" onclick="gaaTil('${NAV[k].items[0][0]}')">${v.label}</button>`).join('');
}

function gaaTil(id, opts = {}) {
  let sek = sektionFor(id);
  if (!sek) { id = 'nyt-job'; sek = 'noegler'; }
  aktivSide = id;
  const panel = id.startsWith('koe-') ? 'jobkoe' : id;
  document.querySelectorAll('.panel').forEach((p) => p.classList.toggle('aktiv', p.id === 'panel-' + panel));
  document.querySelectorAll('#nav-main button').forEach((b) => b.classList.toggle('aktiv', b.dataset.sek === sek));
  $('nav-sub').innerHTML = NAV[sek].items.map(([i, l]) =>
    `<button class="${i === id ? 'aktiv' : ''}" onclick="gaaTil('${i}')">${l}</button>`).join('');

  _stopAutoRefresh();
  if (id === 'koe-noegler') { visKoeFane('noegler'); _startAutoRefresh(); }
  else if (id === 'koe-skilte') { visKoeFane('skilte'); _startAutoRefresh(); }
  else if (id === 'skilte') { if (typeof initSkilt === 'function') initSkilt(); }
  else if (id === 'templates') hentTemplates();
  else if (id === 'skilt-templates') hentSkiltTemplates();
  else if (id === 'maskiner') hentMaskiner();
  else if (id === 'nyt-job') { if (typeof opdaterPladeVisning === 'function') opdaterPladeVisning(); }

  if (!opts.noHash && location.hash.slice(1) !== id) history.pushState(null, '', '#' + id);
  if (!opts.noScroll) window.scrollTo({ top: 0 });
  maalHeader();
}
// Gamle navne bevares så eksisterende kald virker
function skift(panel) { gaaTil(panel); }
function visKoe(which) { gaaTil('koe-' + which); }
window.addEventListener('popstate', () => gaaTil(location.hash.slice(1) || 'nyt-job', { noHash: true, noScroll: true }));

function visKoeFane(which) {
  document.querySelectorAll('#panel-jobkoe .tab-btn').forEach((b) => b.classList.toggle('aktiv', b.dataset.tab === which));
  document.querySelectorAll('#panel-jobkoe .tab-content').forEach((c) => c.classList.toggle('aktiv', c.id === 'jobkoe-' + which));
  if (which === 'skilte') hentSkilteKoe(); else hentBatches();
}
function skiftJobkoTab(tab) { gaaTil('koe-' + tab); }

function skiftTab(tab) {
  document.querySelectorAll('#panel-templates .tab-btn').forEach((b) => b.classList.toggle('aktiv', b.dataset.tab === tab));
  document.querySelectorAll('#panel-templates .tab-content').forEach((c) => c.classList.toggle('aktiv', c.id === 'tab-' + tab));
  currentTab = tab;
  if (tab === 't-felt') setTimeout(opdaterPreview, 50);
}

function _startAutoRefresh() {
  _stopAutoRefresh();
  _refreshTimer = setInterval(() => {
    if (document.hidden) return;
    if (aktivSide === 'koe-skilte') hentSkilteKoe();
    else if (aktivSide === 'koe-noegler') hentBatches();
  }, 5000);
}
function _stopAutoRefresh() { if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; } }

// Header-højde til sticky preview
function maalHeader() {
  const h = document.querySelector('.topbar');
  if (h) document.documentElement.style.setProperty('--hdr-h', h.offsetHeight + 'px');
}
window.addEventListener('resize', debounce(maalHeader, 150));

// ─── Statuslinje ─────────────────────────────────────────────────────────────
async function opdaterStatus() {
  if (document.hidden) return;
  const bar = $('status-bar');
  const chip = (cls, tekst, mal) => `<span class="chip ${cls}" onclick="gaaTil('${mal}')"><span class="dot"></span>${tekst}</span>`;
  try {
    const r = await fetch('/api/status');
    if (!r.ok) throw new Error(r.status);
    const s = await r.json();
    const kls = (run, pend) => run ? 'koerer' : (pend ? 'venter' : 'ledig');
    const tekst = (ikon, pend, run, hold) => {
      if (run) return `${ikon} sender${pend ? ' · ' + pend + ' venter' : ''}`;
      if (pend) return `${ikon} ${pend} afventer`;
      return `${ikon}<span class="t"> ledig${hold ? ' · ' + hold + ' på hold' : ''}</span>`;
    };
    bar.innerHTML =
      chip(kls(s.noegler_running, s.noegler_pending), tekst('🔑', s.noegler_pending, s.noegler_running, s.noegler_hold), 'koe-noegler') +
      chip(kls(s.skilte_running, s.skilte_pending), tekst('🏷️', s.skilte_pending, s.skilte_running, 0), 'koe-skilte');
  } catch (e) {
    bar.innerHTML = '<span class="chip offline">Ingen forbindelse til nGrave</span>';
  }
}
setInterval(opdaterStatus, 4000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) opdaterStatus(); });
