// ─── State ────────────────────────────────────────────────────────────────────
let maskiner = [], templates = [], skiltTemplates = [], fonts = {};
let redigerTemplateId = null, redigerSkiltTemplateId = null;
let gridSlots = [];
let currentTab = 't-basis';

// ─── Init ─────────────────────────────────────────────────────────────────────
async function initDropdowns() {
  maskiner  = await api('/api/maskiner');
  templates = await api('/api/templates');
  skiltTemplates = await api('/api/skilt-templates');
  fonts = await api('/api/fonts');

  const jtempl = document.getElementById('job-template');
  jtempl.innerHTML = templates.map(t => `<option value="${t.id}" data-maskine="${t.maskine_id||''}">${esc(t.navn)}</option>`).join('');
  // Husk sidst brugte template og maskine
  const sidst = lsGet('sidst_template');
  if (sidst && jtempl.querySelector(`option[value="${sidst}"]`)) {
    jtempl.value = sidst;
  }

  const jmask = document.getElementById('job-maskine');
  jmask.innerHTML = maskiner.map(m => `<option value="${m.id}">${esc(m.navn)} (${esc(m.model)})</option>`).join('');
  const sm = lsGet('sidst_maskine');
  if (sm && jmask.querySelector(`option[value="${sm}"]`)) jmask.value = sm;
  opdaterTemplateMaskine();   // template's standardmaskine har forrang

  const smask = document.getElementById('skilt-maskine');
  const forrigeSkiltMaskine = smask.value || lsGet('sidst_skilt_maskine');
  smask.innerHTML = maskiner.map(m => `<option value="${m.id}">${esc(m.navn)}</option>`).join('');
  if (forrigeSkiltMaskine && smask.querySelector(`option[value="${forrigeSkiltMaskine}"]`)) smask.value = forrigeSkiltMaskine;

  const stvalg = document.getElementById('skilt-template-valg');
  stvalg.innerHTML = '<option value="">Vælg template...</option>' +
    skiltTemplates.map(t => `<option value="${t.id}">${esc(t.navn)}</option>`).join('');

  const tmask = document.getElementById('t-maskine');
  tmask.innerHTML = '<option value="">Valgfri</option>' + maskiner.map(m => `<option value="${m.id}">${esc(m.navn)}</option>`).join('');

  const stmask = document.getElementById('st-maskine');
  stmask.innerHTML = '<option value="">Valgfri</option>' + maskiner.map(m => `<option value="${m.id}">${esc(m.navn)}</option>`).join('');

  // Udfyld nøgle-template font-dropdowns dynamisk fra font-listen (så de
  // matcher de faktisk understøttede skrifttyper). '' = brug fælles font.
  const fontOpts = '<option value="">← Fælles font</option>' +
    Object.entries(fonts).map(([k,v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('');
  ['t-mark-font','t-sys-font','t-loebe-font','t-ekstra-font'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = fontOpts;
  });
}

// ─── Nyt nøgle-job ────────────────────────────────────────────────────────────
function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

function opdaterTemplateMaskine() {
  const sel = $('job-template');
  const opt = sel.options[sel.selectedIndex];
  const mid = opt ? opt.dataset.maskine : '';
  if (mid) $('job-maskine').value = mid;
  return !!mid;
}

function opdaterJobFelter() {
  opdaterTemplateMaskine();
  const tmpl = templates.find(t => t.id == +$('job-template').value);
  const container = $('job-felter-container');
  if (!tmpl) { container.innerHTML = ''; opdaterPladeVisning(); return; }

  // Alt der stammer fra databasen (felt-navne) escapes — templates kan have vilkårlige navne.
  const felt = (navn, def, id, extra = '') =>
    `<div><label for="${id}">${esc(navn || def)}</label><input id="${id}" autocomplete="off" ${extra}></div>`;
  const feltDefs = [
    { pos: tmpl.markering_position || 1, render: () => tmpl.markering_aktiv ? felt(tmpl.markering_navn, 'Markering', 'job-type') : '' },
    { pos: tmpl.system_position || 2,    render: () => tmpl.system_aktiv    ? felt(tmpl.system_navn, 'System nr', 'job-system') : '' },
    { pos: tmpl.ekstra_position || 4,    render: () => tmpl.ekstra_aktiv    ? felt(tmpl.ekstra_navn, 'Ekstra', 'job-ekstra') : '' },
    { pos: tmpl.loebe_position || 3, render: () => {
      if (!tmpl.loebe_aktiv) return `<div><label for="job-antal">Antal emner</label><input id="job-antal" type="number" inputmode="numeric" value="1" min="1" oninput="opdaterPladeVisning()"></div>`;
      const ln = esc(tmpl.loebe_navn || 'Løbenr');
      let h = `<div><label for="job-fra">${ln} fra</label><input id="job-fra" type="number" inputmode="numeric" value="1" min="1" oninput="opdaterPladeVisning()"></div>`;
      h    += `<div><label for="job-til">${ln} til</label><input id="job-til" type="number" inputmode="numeric" value="20" min="1" oninput="opdaterPladeVisning()"></div>`;
      if (tmpl.loebe_prefix_aktiv) h += `<div><label for="job-prefix">Prefix</label><input id="job-prefix" placeholder="f.eks. S"></div>`;
      if (tmpl.loebe_suffix_aktiv) h += `<div><label for="job-suffix">Suffix</label><input id="job-suffix"></div>`;
      return h;
    }},
  ].sort((a, b) => a.pos - b.pos);

  container.innerHTML = feltDefs.map(f => f.render()).join('');
  opdaterPladeVisning();
}

// Fordeling på plader — samme regneregel som serveren (create_batch).
function pladeFordeling(antal, start, N) {
  const foerste = N - start + 1;
  if (foerste <= 0 || antal <= 0) return [];
  if (antal <= foerste) return [antal];
  const res = [foerste];
  let rest = antal - foerste;
  while (rest > 0) { res.push(Math.min(N, rest)); rest -= N; }
  return res;
}

function jobTal() {
  const tmpl = templates.find(t => t.id == +$('job-template').value);
  if (!tmpl) return null;
  const num = (id, d) => { const el = $(id); return el && el.value !== '' ? Math.floor(+el.value) : d; };
  const antal = tmpl.loebe_aktiv ? num('job-til', 1) - num('job-fra', 1) + 1 : num('job-antal', 1);
  return { tmpl, antal, start: Math.max(1, num('job-startslot', 1)) };
}

function opdaterPladeVisning() {
  const wrap = $('plade-wrap'), svg = $('plade-svg'), op = $('job-opsummering'), knap = $('job-send');
  if (!wrap) return;
  const t = jobTal();
  let slots = [];
  try { slots = t ? (JSON.parse(t.tmpl.grid_json).slots || []) : []; } catch (e) {}
  if (!t || !slots.length) { wrap.style.display = 'none'; if (knap) knap.disabled = !t; return; }
  wrap.style.display = 'block';

  const N = slots.length, zw = +t.tmpl.zone_bredde_mm || 18, zh = +t.tmpl.zone_hoejde_mm || 8;
  const plader = pladeFordeling(t.antal, t.start, N);
  let fejl = '';
  if (!(t.antal > 0)) fejl = 'Slutnummeret skal være større end eller lig med startnummeret.';
  else if (t.start > N) fejl = `Start slot ${t.start} findes ikke — pladen har ${N} slots.`;
  knap.disabled = !!fejl;

  const brugt = fejl ? 0 : plader[0];
  // Skematisk plade: slots sidder på deres rigtige positioner, men tegnes som læsbare felter
  // (de fysiske graveringszoner er ca. 18×8 mm og ville blive frimærker).
  const xs = slots.map(s => +s.x), ys = slots.map(s => +s.y);
  const trin = (arr) => { const u = [...new Set(arr.map(v => Math.round(v * 10) / 10))].sort((p, q) => p - q); return u.length > 1 ? Math.min(...u.slice(1).map((v, i) => v - u[i])) : null; };
  const tw = Math.max(zw, (trin(xs) || zw * 2) * 0.8), th = Math.max(zh, (trin(ys) || zh * 2) * 0.72);
  const cx = (s) => +s.x + zw / 2, cy = (s) => +s.y + zh / 2;
  const x0 = Math.min(...slots.map(cx)) - tw / 2 - 3, y0 = Math.min(...slots.map(cy)) - th / 2 - 3;
  const bw = Math.max(...slots.map(cx)) + tw / 2 + 3 - x0, bh = Math.max(...slots.map(cy)) + th / 2 + 3 - y0;
  svg.setAttribute('viewBox', `${x0} ${y0} ${bw} ${bh}`);
  const fs = th * 0.42;
  svg.innerHTML = slots.map((s, i) => {
    const bruger = i >= t.start - 1 && i < t.start - 1 + brugt;
    return `<rect class="slot ${bruger ? 'brug' : ''}" x="${cx(s) - tw / 2}" y="${cy(s) - th / 2}" width="${tw}" height="${th}" rx="${th * 0.14}"/>` +
      `<text class="slot-nr" x="${cx(s)}" y="${cy(s)}" font-size="${fs}" style="${bruger ? 'fill:#fff;font-weight:700' : ''}">${esc(s.nr ?? i + 1)}</text>`;
  }).join('');

  op.innerHTML = fejl
    ? `<span style="color:var(--fejl)">${esc(fejl)}</span>`
    : `<b>${t.antal}</b> ${t.antal === 1 ? 'nøgle' : 'nøgler'} → <b>${plader.length}</b> ${plader.length === 1 ? 'plade' : 'plader'} (${plader.join(' + ')})` +
      (plader.length > 1 ? ` <span class="muted">· plade 2 og frem venter på hold, til du frigiver dem</span>` : '');
}

async function sendJob() {
  const status = $('job-status');
  const t = jobTal();
  if (!t) { toast('Vælg en template først', 'advarsel'); return; }
  if (t.antal > 200 && !confirm(`Du er ved at oprette ${t.antal} nøgler. Er det rigtigt?`)) return;
  status.textContent = 'Sender…';
  const getVal = (id) => { const el = $(id); return el ? el.value.trim() : ''; };
  const getNum = (id, def) => { const el = $(id); return el && el.value !== '' ? +el.value : def; };
  try {
    const res = await api('/api/batches', 'POST', {
      template_id: $('job-template').value,
      maskine_id:  $('job-maskine').value,
      type_felt:   getVal('job-type').toUpperCase(),
      system_nr:   getVal('job-system').toUpperCase(),
      ekstra_tekst: getVal('job-ekstra').toUpperCase(),
      loebe_fra:    getNum('job-fra', 1),
      loebe_til:    getNum('job-til', 1),
      loebe_prefix: getVal('job-prefix'),
      loebe_suffix: getVal('job-suffix'),
      antal:        getNum('job-antal', 1),
      navn:        getVal('job-navn') || null,
      start_slot:  getNum('job-startslot', 1) || 1,
    });
    if (res.ok) {
      status.textContent = '';
      toast(`${res.jobs} nøgler lagt i køen (${res.batches} ${res.batches === 1 ? 'plade' : 'plader'})`, 'ok',
            { tekst: 'Se kø', fn: () => gaaTil('koe-noegler') });
    } else {
      status.textContent = '';
      toast(res.fejl || 'Kunne ikke oprette jobbet', 'fejl');
    }
  } catch (e) { status.textContent = ''; toast('Kunne ikke sende — ingen forbindelse?', 'fejl'); }
}

// ─── Jobkøer ──────────────────────────────────────────────────────────────────
const STATUS_TEKST = { pending: 'Afventer', running: 'Sender…', done: 'Sendt', fejl: 'Fejl', 'on-hold': 'Venter på plade' };
function statusBadge(st, fejl) {
  const tip = st === 'done' ? 'Programmet er sendt til maskinen' : (st === 'on-hold' ? 'Frigiv når pladen er skiftet' : '');
  return `<span class="badge badge-${esc(st)}" title="${esc(tip)}">${esc(STATUS_TEKST[st] || st)}</span>` +
         (fejl ? `<div class="fejltekst">${esc(fejl)}</div>` : '');
}
function koeOpdateret() { const el = $('koe-opdateret'); if (el) el.textContent = 'opdateret ' + new Date().toLocaleTimeString('da-DK', { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }

let skilteKoeRows = [];

async function hentSkilteKoe() {
  const tbody = $('skilte-koe-tabel');
  try {
    const rows = await api('/api/skilte');
    skilteKoeRows = rows;
    tbody.innerHTML = rows.length === 0
      ? `<tr><td colspan="7" class="tomt"><span class="stor">🏷️</span>Ingen skilte i køen.<br><button class="btn btn-secondary btn-sm mt" onclick="gaaTil('skilte')">Lav et nyt skilt</button></td></tr>`
      : rows.map(r => {
          let tekst = '';
          try { tekst = JSON.parse(r.linjer_json).map(l => l.tekst).filter(Boolean).join(' / '); } catch (e) {}
          return `<tr>
            <td class="m-skjul" data-label="ID">#${r.id}</td>
            <td data-label="Tekst"><b>${esc(tekst || r.navn)}</b></td>
            <td class="m-skjul" data-label="Størrelse">${r.skilt_bredde_mm}×${r.skilt_hoejde_mm} mm</td>
            <td data-label="Maskine">${esc(r.maskine_navn)}</td>
            <td data-label="Status">${statusBadge(r.status, r.fejl_besked)}</td>
            <td data-label="Oprettet">${relTid(r.oprettet)}</td>
            <td class="act">
              ${r.status === 'fejl' ? `<button class="btn btn-secondary btn-sm" onclick="gentagSkilt(${r.id})">↻ Gentag</button>` : ''}
              <button class="btn btn-ghost btn-sm" onclick="skilteLavIgen(${r.id})" title="Åbn med samme tekst og layout i Nyt skilt">⎘ Lav igen</button>
              ${r.status === 'pending' ? `<button class="btn btn-danger btn-sm" onclick="annullerSkilt(${r.id})">Annuller</button>` : ''}
            </td></tr>`;
        }).join('');
    koeOpdateret();
  } catch (e) { tbody.innerHTML = `<tr><td colspan="7" class="tomt">Kunne ikke hente køen — <a href="#" onclick="hentSkilteKoe();return false;">prøv igen</a></td></tr>`; }
}

async function hentBatches() {
  const tbody = $('batch-tabel');
  try {
    const rows = await api('/api/batches');
    tbody.innerHTML = rows.length === 0
      ? `<tr><td colspan="10" class="tomt"><span class="stor">🔑</span>Ingen nøgle-jobs i køen.<br><button class="btn btn-secondary btn-sm mt" onclick="gaaTil('nyt-job')">Opret et nøgle-job</button></td></tr>`
      : rows.map(r => `<tr>
          <td class="m-skjul" data-label="ID">#${r.id}</td>
          <td data-label="Navn"><b>${esc(r.navn)}</b></td>
          <td class="m-skjul" data-label="Template">${esc(r.template_navn)}</td>
          <td data-label="Maskine">${esc(r.maskine_navn)}</td>
          <td class="m-skjul" data-label="Markering">${esc(r.type_felt) || '—'}</td>
          <td class="m-skjul" data-label="System">${esc(r.system_nr) || '—'}</td>
          <td data-label="Løbenr">${r.loebe_fra}–${r.loebe_til}</td>
          <td data-label="Status">${statusBadge(r.status, r.fejl_besked)}</td>
          <td data-label="Oprettet">${relTid(r.oprettet)}</td>
          <td class="act">
            ${r.status === 'on-hold' ? `<button class="btn btn-primary btn-sm" onclick="frigiv(${r.id})">▶ Frigiv</button>` : ''}
            ${r.status === 'fejl' ? `<button class="btn btn-secondary btn-sm" onclick="gentagBatch(${r.id})">↻ Gentag</button>` : ''}
            ${r.status === 'pending' || r.status === 'on-hold' ? `<button class="btn btn-danger btn-sm" onclick="annuller(${r.id})">Annuller</button>` : ''}
          </td></tr>`).join('');
    koeOpdateret();
  } catch (e) { tbody.innerHTML = `<tr><td colspan="10" class="tomt">Kunne ikke hente køen — <a href="#" onclick="hentBatches();return false;">prøv igen</a></td></tr>`; }
}

async function frigiv(id) { await api(`/api/batches/${id}/frigiv`, 'POST'); toast('Plade frigivet til maskinen', 'ok'); hentBatches(); }
async function annuller(id) { if (!confirm('Annuller dette job?')) return; await api(`/api/batches/${id}/annuller`, 'POST'); hentBatches(); }
async function annullerSkilt(id) { if (!confirm('Annuller dette skilt?')) return; await api(`/api/skilte/${id}/annuller`, 'POST'); hentSkilteKoe(); }
async function annullerAlle() {
  if (!confirm('Annuller ALLE ventende og on-hold nøgle-jobs?')) return;
  const res = await api('/api/jobkoe/annuller-alle', 'POST');
  if (res.ok) { toast(`${res.annulleret} jobs annulleret`, 'ok'); hentBatches(); }
}

const GENTAG_ADVARSEL = 'Send programmet til maskinen igen?\n\nHar maskinen allerede nået at gravere noget af dette job, bliver det graveret to gange. Tjek emnerne først.';
async function gentagBatch(id) {
  if (!confirm(GENTAG_ADVARSEL)) return;
  const r = await api(`/api/batches/${id}/gentag`, 'POST');
  toast(r.ok ? 'Sat tilbage i køen' : 'Kunne ikke gentage jobbet', r.ok ? 'ok' : 'fejl');
  hentBatches();
}
async function gentagSkilt(id) {
  if (!confirm(GENTAG_ADVARSEL)) return;
  const r = await api(`/api/skilte/${id}/gentag`, 'POST');
  toast(r.ok ? 'Sat tilbage i køen' : 'Kunne ikke gentage skiltet', r.ok ? 'ok' : 'fejl');
  hentSkilteKoe();
}

async function rydOpJobkoe(type) {
  if (!confirm('Fjern alle sendte og fejlede jobs fra listen?')) return;
  const res = await api('/api/jobkoe/ryd-op', 'POST', { type });
  if (res.ok) {
    toast(`${res.slettet} jobs fjernet`, 'ok');
    if (type === 'noegler') hentBatches(); else hentSkilteKoe();
  }
}

// ─── Nøgle-Templates ──────────────────────────────────────────────────────────
async function hentTemplates() {
  const rows = await api('/api/templates');
  templates = rows; // opdater state så redigerTemplate kan finde dem
  document.getElementById('template-tabel').innerHTML = rows.length === 0
    ? `<tr><td colspan="6" class="tomt">Ingen nøgle-templates endnu.</td></tr>`
    : rows.map(r => {
    let slots = 0;
    try { const g = JSON.parse(r.grid_json); slots = g.slots ? g.slots.length : 0; } catch (e) {}
    return `<tr>
      <td class="m-skjul" data-label="ID">#${r.id}</td>
      <td data-label="Navn"><span class="clickable" onclick="redigerTemplate(${r.id})">${esc(r.navn)}</span></td>
      <td data-label="Nøgletype">${esc(r.noejle_type)}</td>
      <td data-label="Zone">${r.zone_bredde_mm}×${r.zone_hoejde_mm} mm</td>
      <td data-label="Slots">${slots} slots</td>
      <td class="act">
        <button class="btn btn-secondary btn-sm" onclick="redigerTemplate(${r.id})">Rediger</button>
        <button class="btn btn-ghost btn-sm" onclick="kopierTemplate(${r.id})">Kopi</button>
        <button class="btn btn-danger btn-sm" onclick="sletTemplate(${r.id})">Slet</button>
      </td>
    </tr>`;
  }).join('');
}

function visNyTemplate() {
  redigerTemplateId = null;
  document.getElementById('template-form-titel').textContent = 'Ny template';
  document.getElementById('t-id').value = '';
  document.getElementById('t-navn').value = '';
  document.getElementById('t-type').value = '';
  document.getElementById('t-beskrivelse').value = '';
  document.getElementById('t-bredde').value = '18';
  document.getElementById('t-hoejde').value = '8';
  document.getElementById('t-th').value = '3.5';
  document.getElementById('t-fxy').value = '12';
  document.getElementById('t-fz').value = '40';
  document.getElementById('t-rpm').value = '16000';
  document.getElementById('t-zop').value = '5';
  document.getElementById('t-prox').value = '1.5';
  
  document.getElementById('t-maskine').value = '';
  document.getElementById('t-mark-aktiv').checked = true;
  document.getElementById('t-mark-navn').value = 'Markering';
  document.getElementById('t-mark-x').value = '0';
  document.getElementById('t-mark-y').value = '0';
  document.getElementById('t-mark-jus').value = 'venstre';
  document.getElementById('t-mark-font').value = '';
  document.getElementById('t-mark-hoejde').value = '';
  document.getElementById('t-sys-aktiv').checked = true;
  document.getElementById('t-sys-navn').value = 'System nr';
  document.getElementById('t-sys-x').value = '0';
  document.getElementById('t-sys-y').value = '5';
  document.getElementById('t-sys-jus').value = 'venstre';
  document.getElementById('t-sys-font').value = '';
  document.getElementById('t-sys-hoejde').value = '';
  document.getElementById('t-loebe-aktiv').checked = true;
  document.getElementById('t-loebe-navn').value = 'Løbenr';
  document.getElementById('t-loebe-x').value = '0';
  document.getElementById('t-loebe-y').value = '0';
  document.getElementById('t-loebe-jus').value = 'hoejre';
  document.getElementById('t-loebe-font').value = '';
  document.getElementById('t-loebe-hoejde').value = '';
  document.getElementById('t-loebe-min').value = '0';
  document.getElementById('t-loebe-prefix-aktiv').checked = false;
  document.getElementById('t-loebe-suffix-aktiv').checked = false;
  document.getElementById('t-mark-pos').value = '1';
  document.getElementById('t-sys-pos').value = '2';
  document.getElementById('t-loebe-pos').value = '3';
  document.getElementById('t-ekstra-pos').value = '4';
  document.getElementById('t-ekstra-aktiv').checked = false;
  document.getElementById('t-ekstra-navn').value = 'Ekstra';
  document.getElementById('t-ekstra-x').value = '0';
  document.getElementById('t-ekstra-y').value = '10';
  document.getElementById('t-ekstra-jus').value = 'venstre';
  document.getElementById('t-ekstra-font').value = '';
  document.getElementById('t-ekstra-hoejde').value = '';
  document.getElementById('t-grid-kol').value = '5';
  document.getElementById('t-grid-raek').value = '4';
  gridSlots = [];
  genererGrid();
  document.getElementById('template-form').style.display = 'block';
  skiftTab('t-basis');
  setTimeout(opdaterPreview, 100);
}

async function redigerTemplate(id) {
  redigerTemplateId = id;
  // Hent altid frisk data fra API
  const all = await api('/api/templates');
  templates = all;
  const tmpl = templates.find(t => t.id == id);
  if (!tmpl) return;
  
  document.getElementById('template-form-titel').textContent = 'Rediger template';
  document.getElementById('t-id').value = id;
  document.getElementById('t-navn').value = tmpl.navn;
  document.getElementById('t-type').value = tmpl.noejle_type;
  document.getElementById('t-beskrivelse').value = tmpl.beskrivelse || '';
  document.getElementById('t-bredde').value = tmpl.zone_bredde_mm;
  document.getElementById('t-hoejde').value = tmpl.zone_hoejde_mm;
  document.getElementById('t-th').value = tmpl.tekst_hoejde_mm;
  document.getElementById('t-fxy').value = tmpl.feed_xy;
  document.getElementById('t-fz').value = tmpl.feed_z;
  document.getElementById('t-rpm').value = tmpl.spindle_rpm;
  document.getElementById('t-zop').value = tmpl.z_op_mm;
  document.getElementById('t-prox').value = tmpl.prox_offset_mm || 1.5;
  
  document.getElementById('t-maskine').value = tmpl.maskine_id || '';
  document.getElementById('t-mark-aktiv').checked = !!tmpl.markering_aktiv;
  document.getElementById('t-mark-navn').value = tmpl.markering_navn || 'Markering';
  document.getElementById('t-mark-x').value = tmpl.markering_x || 0;
  document.getElementById('t-mark-y').value = tmpl.markering_y || 0;
  document.getElementById('t-mark-jus').value = tmpl.markering_justering || 'venstre';
  document.getElementById('t-mark-font').value = tmpl.markering_font || '';
  document.getElementById('t-mark-hoejde').value = tmpl.markering_hoejde_mm || '';
  document.getElementById('t-sys-aktiv').checked = !!tmpl.system_aktiv;
  document.getElementById('t-sys-navn').value = tmpl.system_navn || 'System nr';
  document.getElementById('t-sys-x').value = tmpl.system_x || 0;
  document.getElementById('t-sys-y').value = tmpl.system_y || 5;
  document.getElementById('t-sys-jus').value = tmpl.system_justering || 'venstre';
  document.getElementById('t-sys-font').value = tmpl.system_font || '';
  document.getElementById('t-sys-hoejde').value = tmpl.system_hoejde_mm || '';
  document.getElementById('t-loebe-aktiv').checked = !!tmpl.loebe_aktiv;
  document.getElementById('t-loebe-navn').value = tmpl.loebe_navn || 'Løbenr';
  document.getElementById('t-loebe-x').value = tmpl.loebe_x || 0;
  document.getElementById('t-loebe-y').value = tmpl.loebe_y || 0;
  document.getElementById('t-loebe-jus').value = tmpl.loebe_justering || 'hoejre';
  document.getElementById('t-loebe-font').value = tmpl.loebe_font || '';
  document.getElementById('t-loebe-hoejde').value = tmpl.loebe_hoejde_mm || '';
  document.getElementById('t-loebe-min').value = tmpl.loebe_min_laengde || 0;
  document.getElementById('t-loebe-prefix-aktiv').checked = !!tmpl.loebe_prefix_aktiv;
  document.getElementById('t-loebe-suffix-aktiv').checked = !!tmpl.loebe_suffix_aktiv;
  document.getElementById('t-mark-pos').value = tmpl.markering_position || 1;
  document.getElementById('t-sys-pos').value = tmpl.system_position || 2;
  document.getElementById('t-loebe-pos').value = tmpl.loebe_position || 3;
  document.getElementById('t-ekstra-pos').value = tmpl.ekstra_position || 4;
  document.getElementById('t-ekstra-aktiv').checked = !!tmpl.ekstra_aktiv;
  document.getElementById('t-ekstra-navn').value = tmpl.ekstra_navn || 'Ekstra';
  document.getElementById('t-ekstra-x').value = tmpl.ekstra_x ?? 0;
  document.getElementById('t-ekstra-y').value = tmpl.ekstra_y ?? 10;
  document.getElementById('t-ekstra-jus').value = tmpl.ekstra_justering || 'venstre';
  document.getElementById('t-ekstra-font').value = tmpl.ekstra_font || '';
  document.getElementById('t-ekstra-hoejde').value = tmpl.ekstra_hoejde_mm || '';
  
  const grid = JSON.parse(tmpl.grid_json);
  document.getElementById('t-grid-kol').value = grid.kolonner || 5;
  document.getElementById('t-grid-raek').value = grid.raekker || 4;
  gridSlots = grid.slots || [];
  tegnGrid();
  
  document.getElementById('template-form').style.display = 'block';
  skiftTab('t-basis');
  setTimeout(opdaterPreview, 100);
}

function skjulTemplateForm() {
  document.getElementById('template-form').style.display = 'none';
  redigerTemplateId = null;
}

function genererGrid() {
  const kol = +document.getElementById('t-grid-kol').value;
  const raek = +document.getElementById('t-grid-raek').value;
  gridSlots = [];
  for (let r = 0; r < raek; r++) {
    for (let c = 0; c < kol; c++) {
      gridSlots.push({ nr: gridSlots.length + 1, x: c * 50 + 24, y: r * 66 + 11 });
    }
  }
  tegnGrid();
}

function autoUdfyldGrid() {
  const kol    = +document.getElementById('t-grid-kol').value;
  const raek   = +document.getElementById('t-grid-raek').value;
  const startX = +document.getElementById('t-auto-startx').value;
  const startY = +document.getElementById('t-auto-starty').value;
  const dx     = +document.getElementById('t-auto-dx').value;
  const dy     = +document.getElementById('t-auto-dy').value;

  gridSlots = [];
  for (let r = 0; r < raek; r++) {
    for (let c = 0; c < kol; c++) {
      gridSlots.push({
        nr: gridSlots.length + 1,
        x: Math.round((startX + c * dx) * 10) / 10,
        y: Math.round((startY + r * dy) * 10) / 10,
      });
    }
  }
  tegnGrid();
}

function tegnGrid() {
  const tbody = document.getElementById('grid-tabel');
  tbody.innerHTML = gridSlots.map((s, i) => `
    <tr>
      <td>${s.nr}</td>
      <td><input type="number" value="${s.x}" step="0.1" style="width:80px;padding:4px;" onchange="gridSlots[${i}].x = +this.value"></td>
      <td><input type="number" value="${s.y}" step="0.1" style="width:80px;padding:4px;" onchange="gridSlots[${i}].y = +this.value"></td>
    </tr>
  `).join('');
}

async function gemTemplate() {
  try {
    const kol = +document.getElementById('t-grid-kol').value;
    const raek = +document.getElementById('t-grid-raek').value;
    
    const data = {
      navn: document.getElementById('t-navn').value,
      noejle_type: document.getElementById('t-type').value,
      beskrivelse: document.getElementById('t-beskrivelse').value,
      zone_bredde_mm: +document.getElementById('t-bredde').value,
      zone_hoejde_mm: +document.getElementById('t-hoejde').value,
      tekst_hoejde_mm: +document.getElementById('t-th').value,
      linje_afstand: 1.5,
      feed_xy: +document.getElementById('t-fxy').value,
      feed_z: +document.getElementById('t-fz').value,
      spindle_rpm: +document.getElementById('t-rpm').value,
      z_op_mm: +document.getElementById('t-zop').value,
      prox_offset_mm: +document.getElementById('t-prox').value,
      font: 'block',
      maskine_id: document.getElementById('t-maskine').value || null,
      markering_aktiv: document.getElementById('t-mark-aktiv') ? (document.getElementById('t-mark-aktiv').checked ? 1 : 0) : 1,
      markering_navn:  document.getElementById('t-mark-navn') ? document.getElementById('t-mark-navn').value : 'Markering',
      markering_x: document.getElementById('t-mark-x') ? +document.getElementById('t-mark-x').value : 0,
      markering_y: document.getElementById('t-mark-y') ? +document.getElementById('t-mark-y').value : 0,
      markering_justering: document.getElementById('t-mark-jus') ? document.getElementById('t-mark-jus').value : 'venstre',
      markering_font: document.getElementById('t-mark-font') ? (document.getElementById('t-mark-font').value || null) : null,
      markering_hoejde_mm: document.getElementById('t-mark-hoejde') ? (+document.getElementById('t-mark-hoejde').value || 0) : 0,
      system_aktiv: document.getElementById('t-sys-aktiv') ? (document.getElementById('t-sys-aktiv').checked ? 1 : 0) : 1,
      system_navn:  document.getElementById('t-sys-navn') ? document.getElementById('t-sys-navn').value : 'System nr',
      system_x: document.getElementById('t-sys-x') ? +document.getElementById('t-sys-x').value : 0,
      system_y: document.getElementById('t-sys-y') ? +document.getElementById('t-sys-y').value : 5,
      system_justering: document.getElementById('t-sys-jus') ? document.getElementById('t-sys-jus').value : 'venstre',
      system_font: document.getElementById('t-sys-font') ? (document.getElementById('t-sys-font').value || null) : null,
      system_hoejde_mm: document.getElementById('t-sys-hoejde') ? (+document.getElementById('t-sys-hoejde').value || 0) : 0,
      loebe_aktiv: document.getElementById('t-loebe-aktiv') ? (document.getElementById('t-loebe-aktiv').checked ? 1 : 0) : 1,
      loebe_navn:  document.getElementById('t-loebe-navn') ? document.getElementById('t-loebe-navn').value : 'Løbenr',
      loebe_x: document.getElementById('t-loebe-x') ? +document.getElementById('t-loebe-x').value : 0,
      loebe_y: document.getElementById('t-loebe-y') ? +document.getElementById('t-loebe-y').value : 0,
      loebe_justering: document.getElementById('t-loebe-jus') ? document.getElementById('t-loebe-jus').value : 'hoejre',
      loebe_font: document.getElementById('t-loebe-font') ? (document.getElementById('t-loebe-font').value || null) : null,
      loebe_hoejde_mm: document.getElementById('t-loebe-hoejde') ? (+document.getElementById('t-loebe-hoejde').value || 0) : 0,
      loebe_min_laengde: document.getElementById('t-loebe-min') ? +document.getElementById('t-loebe-min').value : 0,
      loebe_prefix_aktiv: document.getElementById('t-loebe-prefix-aktiv') ? (document.getElementById('t-loebe-prefix-aktiv').checked ? 1 : 0) : 0,
      loebe_suffix_aktiv: document.getElementById('t-loebe-suffix-aktiv') ? (document.getElementById('t-loebe-suffix-aktiv').checked ? 1 : 0) : 0,
      markering_position: document.getElementById('t-mark-pos') ? (+document.getElementById('t-mark-pos').value || 1) : 1,
      system_position:    document.getElementById('t-sys-pos')  ? (+document.getElementById('t-sys-pos').value  || 2) : 2,
      loebe_position:     document.getElementById('t-loebe-pos')? (+document.getElementById('t-loebe-pos').value|| 3) : 3,
      ekstra_position:    document.getElementById('t-ekstra-pos')?(+document.getElementById('t-ekstra-pos').value|| 4) : 4,
      ekstra_aktiv: document.getElementById('t-ekstra-aktiv') ? (document.getElementById('t-ekstra-aktiv').checked ? 1 : 0) : 0,
      ekstra_navn:  document.getElementById('t-ekstra-navn') ? document.getElementById('t-ekstra-navn').value : 'Ekstra',
      ekstra_x: document.getElementById('t-ekstra-x') ? +document.getElementById('t-ekstra-x').value : 0,
      ekstra_y: document.getElementById('t-ekstra-y') ? +document.getElementById('t-ekstra-y').value : 10,
      ekstra_justering: document.getElementById('t-ekstra-jus') ? document.getElementById('t-ekstra-jus').value : 'venstre',
      ekstra_font: document.getElementById('t-ekstra-font') ? (document.getElementById('t-ekstra-font').value || null) : null,
      ekstra_hoejde_mm: document.getElementById('t-ekstra-hoejde') ? (+document.getElementById('t-ekstra-hoejde').value || 0) : 0,
      grid: { kolonner: kol, raekker: raek, slots: gridSlots },
    };
    
    let res;
    if (redigerTemplateId) {
      res = await api(`/api/templates/${redigerTemplateId}`, 'PUT', data);
    } else {
      res = await api('/api/templates', 'POST', data);
    }
    
    if (res.ok) { 
      toast('Template gemt', 'ok');
      await initDropdowns();
      hentTemplates();
      skjulTemplateForm();
    } else {
      toast('Kunne ikke gemme: ' + (res.fejl || 'ukendt fejl'), 'fejl');
    }
  } catch(e) {
    toast('Fejl ved gem af template: ' + e.message, 'fejl');
  }
}

async function sletTemplate(id) {
  if (!confirm('Slet denne template? Hvis den er i brug bliver den kun deaktiveret.')) return;
  const res = await api(`/api/templates/${id}`, 'DELETE');
  if (res.ok) {
    await initDropdowns();
    hentTemplates();
  }
}

async function kopierTemplate(id) {
  const all = await api('/api/templates');
  templates = all;
  const tmpl = templates.find(t => t.id == id);
  if (!tmpl) return;

  // Load som ny template med "Kopi af" prefix
  redigerTemplateId = null;
  document.getElementById('template-form-titel').textContent = 'Ny template (kopi)';
  document.getElementById('t-navn').value = 'Kopi af ' + tmpl.navn;
  document.getElementById('t-type').value = tmpl.noejle_type;
  document.getElementById('t-beskrivelse').value = tmpl.beskrivelse || '';
  document.getElementById('t-bredde').value = tmpl.zone_bredde_mm;
  document.getElementById('t-hoejde').value = tmpl.zone_hoejde_mm;
  document.getElementById('t-th').value = tmpl.tekst_hoejde_mm;
  document.getElementById('t-fxy').value = tmpl.feed_xy;
  document.getElementById('t-fz').value = tmpl.feed_z;
  document.getElementById('t-rpm').value = tmpl.spindle_rpm;
  document.getElementById('t-zop').value = tmpl.z_op_mm;
  document.getElementById('t-prox').value = tmpl.prox_offset_mm || 1.5;
  document.getElementById('t-maskine').value = tmpl.maskine_id || '';
  document.getElementById('t-mark-aktiv').checked = !!tmpl.markering_aktiv;
  document.getElementById('t-mark-navn').value = tmpl.markering_navn || 'Markering';
  document.getElementById('t-mark-x').value = tmpl.markering_x || 0;
  document.getElementById('t-mark-y').value = tmpl.markering_y || 0;
  document.getElementById('t-mark-jus').value = tmpl.markering_justering || 'venstre';
  document.getElementById('t-mark-font').value = tmpl.markering_font || '';
  document.getElementById('t-mark-hoejde').value = tmpl.markering_hoejde_mm || '';
  document.getElementById('t-sys-aktiv').checked = !!tmpl.system_aktiv;
  document.getElementById('t-sys-navn').value = tmpl.system_navn || 'System nr';
  document.getElementById('t-sys-x').value = tmpl.system_x || 0;
  document.getElementById('t-sys-y').value = tmpl.system_y || 5;
  document.getElementById('t-sys-jus').value = tmpl.system_justering || 'venstre';
  document.getElementById('t-sys-font').value = tmpl.system_font || '';
  document.getElementById('t-sys-hoejde').value = tmpl.system_hoejde_mm || '';
  document.getElementById('t-loebe-aktiv').checked = !!tmpl.loebe_aktiv;
  document.getElementById('t-loebe-navn').value = tmpl.loebe_navn || 'Løbenr';
  document.getElementById('t-loebe-x').value = tmpl.loebe_x || 0;
  document.getElementById('t-loebe-y').value = tmpl.loebe_y || 0;
  document.getElementById('t-loebe-jus').value = tmpl.loebe_justering || 'hoejre';
  document.getElementById('t-loebe-font').value = tmpl.loebe_font || '';
  document.getElementById('t-loebe-hoejde').value = tmpl.loebe_hoejde_mm || '';
  document.getElementById('t-loebe-min').value = tmpl.loebe_min_laengde || 0;
  document.getElementById('t-loebe-prefix-aktiv').checked = !!tmpl.loebe_prefix_aktiv;
  document.getElementById('t-loebe-suffix-aktiv').checked = !!tmpl.loebe_suffix_aktiv;
  document.getElementById('t-mark-pos').value = tmpl.markering_position || 1;
  document.getElementById('t-sys-pos').value = tmpl.system_position || 2;
  document.getElementById('t-loebe-pos').value = tmpl.loebe_position || 3;
  document.getElementById('t-ekstra-pos').value = tmpl.ekstra_position || 4;
  document.getElementById('t-ekstra-aktiv').checked = !!tmpl.ekstra_aktiv;
  document.getElementById('t-ekstra-navn').value = tmpl.ekstra_navn || 'Ekstra';
  document.getElementById('t-ekstra-x').value = tmpl.ekstra_x ?? 0;
  document.getElementById('t-ekstra-y').value = tmpl.ekstra_y ?? 10;
  document.getElementById('t-ekstra-jus').value = tmpl.ekstra_justering || 'venstre';
  document.getElementById('t-ekstra-font').value = tmpl.ekstra_font || '';
  document.getElementById('t-ekstra-hoejde').value = tmpl.ekstra_hoejde_mm || '';

  const grid = JSON.parse(tmpl.grid_json);
  document.getElementById('t-grid-kol').value = grid.kolonner || 5;
  document.getElementById('t-grid-raek').value = grid.raekker || 4;
  gridSlots = grid.slots ? JSON.parse(JSON.stringify(grid.slots)) : [];
  tegnGrid();

  document.getElementById('template-form').style.display = 'block';
  skiftTab('t-basis');
  setTimeout(opdaterPreview, 100);
}

async function sletSkiltTemplate(id) {
  if (!confirm('Slet denne skilt-template?')) return;
  const res = await api(`/api/skilt-templates/${id}`, 'DELETE');
  if (res.ok) {
    await initDropdowns();
    hentSkiltTemplates();
  }
}

