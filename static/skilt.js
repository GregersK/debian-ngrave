// ─── Skilte: forhåndsvisning (ægte gravér-streger), linje-editor, font-galleri ─
// Layout, fejl og advarsler kommer fra serveren (/api/skilt/preview), som bruger
// SAMME motor som graveringen — så forhåndsvisningen er præcis det der graveres.

const LINJE_FARVER = ['#e74c3c', '#2f80ed', '#27ae60', '#e08e0b', '#9b59b6', '#16a3a3', '#e67e22', '#d6336c', '#0097a7', '#7cb342'];
const SKILT_PRESETS = [[100, 50], [150, 75], [200, 100], [250, 125], [300, 150]];
const KLADDE_NOEGLE = 'ngrave_skilt_kladde';

let skiltLinjer = [];
let linjeConfig = [];          // layout-linjer i skilt-template-editoren (uden tekst)
let skiltType = 'template';
let skiltInitialiseret = false;
let _previewSeq = 0, _stSeq = 0;
let skiltSidstOk = false;

const farveFor = (i) => LINJE_FARVER[i % LINJE_FARVER.length];
const nyLinje = () => ({ tekst: '', justering: 'center', hoejde_mm: 10, font: 'block', x_mm: null, y_mm: null });
const fontNavn = (k) => (fonts && fonts[k]) || k || 'Block';
const talEllerNull = (id) => { const el = $(id); return el && el.value !== '' && !isNaN(+el.value) ? +el.value : null; };

// Hjælpere til font-visning i nøgle-template-preview (opdaterPreview i ngrave_b.js)
// Mapper Hershey font navne til CSS font-family approximationer
function fontTilCSS(font) {
  const m = {
    'block':     'monospace',
    // Sans
    'futural':   'Arial, sans-serif',
    'futuram':   'Arial, sans-serif',
    // Roman / serif
    'rowmans':   'Georgia, serif',
    'rowmand':   'Georgia, serif',
    'rowmant':   'Georgia, serif',
    // Times
    'timesr':    '"Times New Roman", serif',
    'timesrb':   '"Times New Roman", serif',
    'timesi':    'italic "Times New Roman", serif',
    'timesib':   'italic "Times New Roman", serif',
    // Script / kursiv
    'scripts':   'cursive',
    'scriptc':   'cursive',
    'cursive':   'cursive',
    // Gotisk / blackletter
    'gothgrt':   '"Palatino Linotype", fantasy',
    'gothgbt':   '"Palatino Linotype", fantasy',
    'gothiceng': '"Palatino Linotype", fantasy',
    'gothicger': '"Palatino Linotype", fantasy',
    'gothicita': '"Palatino Linotype", fantasy',
    // Gamle nøgler (bagudkompat i preview)
    'romans':'Georgia, serif','romanc':'Georgia, serif','romand':'Georgia, serif',
    'romant':'"Times New Roman", serif','italics':'italic Georgia, serif',
    'italiccs':'italic Georgia, serif','italict':'italic "Times New Roman", serif',
  };
  return m[font] || 'monospace';
}

function fontErItalic(font) {
  return font && (font.startsWith('italic') || font === 'timesi' || font === 'timesib' || font === 'cursive' || font === 'scripts' || font === 'scriptc');
}




// ─── SVG-tegning af et skilt ──────────────────────────────────────────────────
function tegnSkiltSvg(svg, lay, opt = {}) {
  const W = lay.bredde || 200, H = lay.hoejde || 100;
  let x0 = 0, y0 = 0, x1 = W, y1 = H;
  for (const l of lay.linjer || []) {
    if (l.bbox) { x0 = Math.min(x0, l.bbox[0]); y0 = Math.min(y0, l.bbox[1]); x1 = Math.max(x1, l.bbox[2]); y1 = Math.max(y1, l.bbox[3]); }
  }
  // Ved ekstrem overflow må visningen ikke zoome så langt ud at skiltet forsvinder:
  // begræns til ca. 0,6 skiltbredde/-højde uden for skiltet (resten klippes af kanten).
  x0 = Math.max(x0, -W * 0.6); x1 = Math.min(x1, W * 1.6); y0 = Math.max(y0, -H * 0.6); y1 = Math.min(y1, H * 1.6);
  const pad = Math.max(W, H) * 0.06, fs = Math.max(W, H) * 0.034;
  svg.setAttribute('viewBox', `${x0 - pad} ${y0 - pad * 1.7} ${(x1 - x0) + pad * 2} ${(y1 - y0) + pad * 2.7}`);
  let h = `<rect class="skilt-flade ${lay.ok === false ? 'fejl' : ''}" x="0" y="0" width="${W}" height="${H}" rx="${Math.min(W, H) * 0.012}"/>`;

  const mt = opt.margenTop, mb = opt.margenBund;
  if (mt != null) h += `<line class="guide" x1="0" x2="${W}" y1="${mt}" y2="${mt}"/>`;
  if (mb != null) h += `<line class="guide" x1="0" x2="${W}" y1="${H - mb}" y2="${H - mb}"/>`;

  for (const l of lay.linjer || []) {
    const farve = (opt.farveFor || (() => '#333'))(opt.indeks ? opt.indeks[l.i] : l.i);
    const d = l.paths.map((p) => 'M' + p.map((pt) => pt[0] + ' ' + pt[1]).join('L')).join('');
    if (l.fejl && l.fejl.length && l.bbox) {
      h += `<rect class="ramme-fejl" x="${l.bbox[0]}" y="${l.bbox[1]}" width="${l.bbox[2] - l.bbox[0]}" height="${l.bbox[3] - l.bbox[1]}"/>`;
    }
    h += `<path class="gravur ${l.fejl && l.fejl.length ? 'fejl' : ''}" d="${d}" style="stroke:${farve}"/>`;
  }
  const topY = Math.min(0, y0) - pad * 0.55;
  h += `<text class="mal" x="${W / 2}" y="${topY}" font-size="${fs}" text-anchor="middle">${W} mm</text>`;
  const rx = Math.max(W, x1) + pad * 0.65;
  h += `<text class="mal" x="${rx}" y="${H / 2}" font-size="${fs}" text-anchor="middle" transform="rotate(90 ${rx} ${H / 2})">${H} mm</text>`;
  if (!(lay.linjer || []).length) {
    h += `<text class="mal" x="${W / 2}" y="${H / 2}" font-size="${fs * 1.35}" text-anchor="middle">${esc(opt.tomTekst || 'Skriv tekst for at se skiltet')}</text>`;
  }
  svg.innerHTML = h;
}

function visBanner(el, lay, tom) {
  if (!el) return;
  if (lay.fejl && lay.fejl.length) {
    el.innerHTML = `<div class="banner fejl"><b>Passer ikke på skiltet</b><ul>${lay.fejl.map((f) => `<li>${esc(f)}</li>`).join('')}</ul></div>`;
  } else if (lay.advarsler && lay.advarsler.length) {
    el.innerHTML = `<div class="banner advarsel"><b>Tjek lige</b><ul>${lay.advarsler.map((f) => `<li>${esc(f)}</li>`).join('')}</ul></div>`;
  } else if (!tom) {
    el.innerHTML = `<div class="banner ok">✓ Alt passer på skiltet</div>`;
  } else {
    el.innerHTML = '';
  }
}

// ─── Nyt skilt: state → spec → preview ────────────────────────────────────────
function skiltSpec() {
  return {
    skilt_bredde_mm: +$('skilt-bredde').value || 0,
    skilt_hoejde_mm: +$('skilt-hoejde').value || 0,
    margin_top_mm: talEllerNull('skilt-margin-top'),
    margin_bottom_mm: talEllerNull('skilt-margin-bund'),
    linje_afstand_mm: talEllerNull('skilt-linje-afstand'),
    linjer: skiltLinjer,
  };
}

const opdaterSkiltPreview = debounce(async () => {
  const spec = skiltSpec();
  gemKladde();
  const seq = ++_previewSeq;
  const harTekst = skiltLinjer.some((l) => l.tekst.trim());
  const knap = $('skilt-send');
  let lay;
  try { lay = await api('/api/skilt/preview', 'POST', spec); }
  catch (e) {
    if (seq === _previewSeq) { $('skilt-banner').innerHTML = '<div class="banner advarsel">Kunne ikke hente forhåndsvisning — ingen forbindelse?</div>'; knap.disabled = true; }
    return;
  }
  if (seq !== _previewSeq) return;      // et nyere svar er på vej
  // server-linjer er filtreret for tomme → map tilbage til editor-indeks
  const indeks = skiltLinjer.map((l, i) => (l.tekst.trim() ? i : -1)).filter((i) => i >= 0);
  const lay2 = { ...lay, linjer: (lay.linjer || []).map((l, k) => ({ ...l, i: k })) };
  tegnSkiltSvg($('skilt-preview'), lay2, {
    margenTop: spec.margin_top_mm ?? spec.skilt_hoejde_mm * 0.1,
    margenBund: spec.margin_bottom_mm ?? spec.skilt_hoejde_mm * 0.1,
    farveFor, indeks,
  });
  visBanner($('skilt-banner'), lay, !harTekst);
  $('skilt-meta').textContent = `${spec.skilt_bredde_mm} × ${spec.skilt_hoejde_mm} mm · ${indeks.length} ${indeks.length === 1 ? 'linje' : 'linjer'}`;

  // pr.-linje fejl i editoren
  skiltLinjer.forEach((_, i) => { const el = $('linje-msg-' + i); if (el) el.textContent = ''; const k = $('linje-' + i); if (k) k.classList.remove('har-fejl'); });
  (lay.linjer || []).forEach((l, k) => {
    const ci = indeks[k], el = $('linje-msg-' + ci);
    if (el) el.textContent = [...l.fejl, ...l.advarsler].join(' · ');
    if (l.fejl.length && $('linje-' + ci)) $('linje-' + ci).classList.add('har-fejl');
  });

  skiltSidstOk = !!lay.ok && indeks.length > 0;
  knap.disabled = !skiltSidstOk;
  knap.title = skiltSidstOk ? '' : (harTekst ? 'Teksten passer ikke på skiltet' : 'Skriv tekst først');
}, 180);

// ─── Linje-editor (bruges både til skilte og skilt-templates) ─────────────────
function maal(mode) {
  return mode === 'config'
    ? { arr: () => linjeConfig, tegn: () => tegnLinjeConfig(), preview: () => opdaterStPreview(), beholder: 'st-linjer-container' }
    : { arr: () => skiltLinjer, tegn: () => tegnSkiltLinjer(), preview: () => opdaterSkiltPreview(), beholder: 'skilt-linjer-container' };
}

function linjeKortHtml(l, i, mode, antal) {
  const tekstFelt = mode === 'config'
    ? `<div class="linje-tekst muted" style="padding:9px 4px;">Linje ${i + 1}</div>`
    : `<input class="linje-tekst" id="lt-${i}" value="${esc(l.tekst)}" placeholder="Tekst på linje ${i + 1}" autocomplete="off" autocorrect="off" oninput="linjeFelt('${mode}',${i},'tekst',this.value)" aria-label="Tekst på linje ${i + 1}">`;
  const just = [['venstre', '⇤', 'Venstre'], ['center', '↔', 'Center'], ['hoejre', '⇥', 'Højre']]
    .map(([v, ik, t]) => `<button class="${l.justering === v ? 'aktiv' : ''}" title="${t}" aria-label="${t}" onclick="linjeFelt('${mode}',${i},'justering','${v}',true)">${ik}</button>`).join('');
  return `<div class="linje" id="${mode === 'config' ? 'cfg' : 'linje'}-${i}" style="--lc:${farveFor(i)}">
    <div class="linje-top">
      <span class="linje-nr">${i + 1}</span>
      ${tekstFelt}
      <button class="btn btn-ghost btn-ikon btn-sm" title="Flyt op" aria-label="Flyt op" onclick="flytLinje('${mode}',${i},-1)" ${i === 0 ? 'disabled' : ''}>↑</button>
      <button class="btn btn-ghost btn-ikon btn-sm" title="Flyt ned" aria-label="Flyt ned" onclick="flytLinje('${mode}',${i},1)" ${i === antal - 1 ? 'disabled' : ''}>↓</button>
      <button class="btn btn-ghost btn-ikon btn-sm" title="Fjern linje" aria-label="Fjern linje" onclick="fjernLinje('${mode}',${i})">✕</button>
    </div>
    <div class="linje-rad">
      <div class="seg sm" role="group" aria-label="Justering">${just}</div>
      <button class="fontknap" onclick="aabnFontGalleri('${mode}',${i})" title="Vælg skrifttype"><span>${esc(fontNavn(l.font))}</span><span class="muted">Aa ▾</span></button>
      <div class="stepper">
        <button onclick="stepHoejde('${mode}',${i},-1)" aria-label="Mindre">−</button>
        <input type="number" inputmode="decimal" step="0.5" min="1" value="${l.hoejde_mm}" oninput="linjeFelt('${mode}',${i},'hoejde_mm',+this.value)" aria-label="Teksthøjde i mm">
        <button onclick="stepHoejde('${mode}',${i},1)" aria-label="Større">+</button>
        <span class="small muted">mm</span>
      </div>
    </div>
    <details class="linje-adv"${l.x_mm != null || l.y_mm != null ? ' open' : ''}><summary>Manuel placering (X/Y)</summary>
      <div class="adv-grid">
        <div><label>X (mm) — tom = efter justering</label><input type="number" step="0.5" inputmode="decimal" value="${l.x_mm ?? ''}" placeholder="auto" oninput="linjeFelt('${mode}',${i},'x_mm',this.value===''?null:+this.value)"></div>
        <div><label>Y baseline (mm) — tom = fordelt</label><input type="number" step="0.5" inputmode="decimal" value="${l.y_mm ?? ''}" placeholder="auto" oninput="linjeFelt('${mode}',${i},'y_mm',this.value===''?null:+this.value)"></div>
      </div>
    </details>
    <div class="linje-msg" id="linje-msg-${mode === 'config' ? 'c' : ''}${i}"></div>
  </div>`;
}

function tegnLinjer(mode) {
  const m = maal(mode), arr = m.arr();
  $(m.beholder).innerHTML = arr.map((l, i) => linjeKortHtml(l, i, mode, arr.length)).join('');
  m.preview();
}
function tegnSkiltLinjer() { tegnLinjer('skilt'); }
function tegnLinjeConfig() {
  tegnLinjer('config');
  const el = $('st-antal'); if (el) el.value = linjeConfig.length;
}

function linjeFelt(mode, i, key, val, rerender = false) {
  const arr = maal(mode).arr();
  if (!arr[i]) return;
  arr[i][key] = val;
  if (rerender) maal(mode).tegn(); else maal(mode).preview();
}
function stepHoejde(mode, i, d) {
  const l = maal(mode).arr()[i];
  l.hoejde_mm = Math.max(1, Math.round(((+l.hoejde_mm || 10) + d) * 2) / 2);
  maal(mode).tegn();
}
function flytLinje(mode, i, d) {
  const arr = maal(mode).arr(), j = i + d;
  if (j < 0 || j >= arr.length) return;
  [arr[i], arr[j]] = [arr[j], arr[i]];
  maal(mode).tegn();
}
function fjernLinje(mode, i) {
  const arr = maal(mode).arr();
  if (arr.length <= 1) {            // sidste linje: nulstil i stedet for at fjerne
    const n = nyLinje();
    if (mode === 'config') delete n.tekst;
    arr[0] = n;
  } else {
    arr.splice(i, 1);
  }
  maal(mode).tegn();
}
function tilfoejLinje() {
  if (skiltLinjer.length >= 10) { toast('Max 10 linjer pr. skilt', 'advarsel'); return; }
  const forrige = skiltLinjer[skiltLinjer.length - 1];
  skiltLinjer.push({ ...nyLinje(), ...(forrige ? { justering: forrige.justering, font: forrige.font, hoejde_mm: forrige.hoejde_mm } : {}) });
  tegnSkiltLinjer();
  setTimeout(() => { const el = $('lt-' + (skiltLinjer.length - 1)); if (el) el.focus(); }, 30);
}
function rydSkiltTekst() { skiltLinjer.forEach((l) => { l.tekst = ''; }); tegnSkiltLinjer(); const el = $('lt-0'); if (el) el.focus(); }

// ─── Font-galleri (viser de faktiske gravér-streger) ──────────────────────────
async function aabnFontGalleri(mode, i) {
  const l = maal(mode).arr()[i];
  const prove = (mode === 'skilt' && l.tekst.trim()) ? l.tekst.trim().slice(0, 16) : 'Aa Bb Æøå 123';
  aabnModal('Vælg skrifttype', '<p class="small muted">Henter skrifttyper…</p>');
  let data;
  try { data = await api('/api/fonts/prove?tekst=' + encodeURIComponent(prove)); }
  catch (e) { lukModal(); toast('Kunne ikke hente skrifttyper', 'fejl'); return; }
  const tiles = Object.entries(data).map(([k, f]) => {
    const d = f.paths.map((p) => 'M' + p.map((pt) => pt[0] + ' ' + pt[1]).join('L')).join('');
    return `<div class="font-tile ${l.font === k ? 'valgt' : ''}" data-font="${esc(k)}" onclick="vaelgFont('${mode}',${i},this.dataset.font)">
      <svg viewBox="-1.5 -12.5 ${f.bredde + 3} 18" preserveAspectRatio="xMidYMid meet"><path d="${d}" fill="none" stroke="#222" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>
      <div class="fnavn">${esc(f.navn)}</div></div>`;
  }).join('');
  $('modal-krop').innerHTML = `<p class="small muted" style="margin-bottom:10px;">Prøve: »${esc(prove)}« — præcis som maskinen graverer den.</p><div class="font-grid">${tiles}</div>`;
}
function vaelgFont(mode, i, k) {
  const arr = maal(mode).arr();
  if (arr[i]) arr[i].font = k;
  lukModal();
  maal(mode).tegn();
}

// ─── Nyt skilt: type, template, størrelse ─────────────────────────────────────
function skiftSkiltType(type, opt = {}) {
  skiltType = type;
  document.querySelectorAll('#skilt-type-seg button').forEach((b) => b.classList.toggle('aktiv', b.dataset.type === type));
  $('skilt-template-sektion').style.display = type === 'template' ? 'block' : 'none';
  $('skilt-frit-sektion').style.display = type === 'frit' ? 'block' : 'none';
  if (type === 'template' && $('skilt-template-valg').value && !opt.stille) loadSkiltTemplate();
  else opdaterSkiltPreview();
}

function saetSkiltStr(b, h) { $('skilt-bredde').value = b; $('skilt-hoejde').value = h; opdaterSkiltPreview(); }

function loadSkiltTemplate() {
  const id = $('skilt-template-valg').value;
  const info = $('skilt-template-info');
  if (!id) { info.textContent = ''; opdaterSkiltPreview(); return; }
  const tmpl = skiltTemplates.find((t) => t.id == id);
  if (!tmpl) return;
  $('skilt-bredde').value = tmpl.skilt_bredde_mm;
  $('skilt-hoejde').value = tmpl.skilt_hoejde_mm;
  if (tmpl.maskine_id && $('skilt-maskine').querySelector(`option[value="${tmpl.maskine_id}"]`)) $('skilt-maskine').value = tmpl.maskine_id;
  $('skilt-margin-top').value = tmpl.margin_top_mm ?? '';
  $('skilt-margin-bund').value = tmpl.margin_bottom_mm ?? '';
  $('skilt-linje-afstand').value = tmpl.linje_afstand_mm ?? '';

  let config = [];
  try { config = JSON.parse(tmpl.linjer_config); } catch (e) {}
  if (!config.length) config = [{}];
  const tidligere = skiltLinjer.map((l) => l.tekst);   // allerede skrevet tekst følger med over i layoutet
  skiltLinjer = config.map((c, i) => ({
    ...nyLinje(), tekst: tidligere[i] || '', justering: c.justering || 'center', hoejde_mm: c.hoejde_mm || 10,
    font: c.font || 'block', x_mm: c.x_mm ?? null, y_mm: c.y_mm ?? null,
  }));
  info.textContent = `${tmpl.skilt_bredde_mm} × ${tmpl.skilt_hoejde_mm} mm · ${config.length} ${config.length === 1 ? 'linje' : 'linjer'}` +
    (tmpl.feed_xy || tmpl.spindle_rpm ? ' · egen gravehastighed' : '');
  tegnSkiltLinjer();
}

// ─── Kladde: overlever genindlæsning og skift mellem faner ────────────────────
const gemKladde = debounce(() => {
  try {
    localStorage.setItem(KLADDE_NOEGLE, JSON.stringify({
      t: Date.now(), type: skiltType, tmpl: $('skilt-template-valg').value,
      b: $('skilt-bredde').value, h: $('skilt-hoejde').value,
      mt: $('skilt-margin-top').value, mb: $('skilt-margin-bund').value, la: $('skilt-linje-afstand').value,
      linjer: skiltLinjer,
    }));
  } catch (e) {}
}, 400);

function gendanKladde() {
  let k = null;
  try { k = JSON.parse(localStorage.getItem(KLADDE_NOEGLE) || 'null'); } catch (e) {}
  if (!k || !Array.isArray(k.linjer) || !k.linjer.length || Date.now() - k.t > 7 * 864e5) return false;
  if (k.type === 'template' && k.tmpl && $('skilt-template-valg').querySelector(`option[value="${k.tmpl}"]`)) $('skilt-template-valg').value = k.tmpl;
  else k.type = 'frit';
  $('skilt-bredde').value = k.b || 200; $('skilt-hoejde').value = k.h || 100;
  $('skilt-margin-top').value = k.mt ?? ''; $('skilt-margin-bund').value = k.mb ?? ''; $('skilt-linje-afstand').value = k.la ?? '';
  skiltLinjer = k.linjer.slice(0, 10).map((l) => ({ ...nyLinje(), ...l }));
  skiftSkiltType(k.type, { stille: true });
  const tmpl = skiltTemplates.find((t) => t.id == k.tmpl);
  if (tmpl && k.type === 'template') $('skilt-template-info').textContent = `${tmpl.skilt_bredde_mm} × ${tmpl.skilt_hoejde_mm} mm`;
  return true;
}

function initSkilt() {
  if (skiltInitialiseret) { opdaterSkiltPreview(); return; }
  skiltInitialiseret = true;
  $('skilt-presets').innerHTML = SKILT_PRESETS.map(([b, h]) => `<button class="btn btn-ghost" onclick="saetSkiltStr(${b},${h})">${b}×${h}</button>`).join('');
  if (!gendanKladde()) {
    skiltLinjer = [nyLinje()];
    skiftSkiltType('template', { stille: true });
  }
  tegnSkiltLinjer();
}

// ─── Send / gem som template / lav igen ───────────────────────────────────────
async function sendSkilt() {
  const knap = $('skilt-send'), status = $('skilt-status');
  knap.disabled = true;
  status.textContent = 'Sender…';
  try {
    const res = await api('/api/skilte', 'POST', {
      ...skiltSpec(), maskine_id: $('skilt-maskine').value,
      template_id: skiltType === 'template' ? ($('skilt-template-valg').value || null) : null,
    });
    status.textContent = '';
    if (res.ok) {
      toast('Skilt lagt i køen', 'ok', { tekst: 'Se kø', fn: () => gaaTil('koe-skilte') });
    } else {
      toast(res.fejl || 'Kunne ikke oprette skiltet', 'fejl');
    }
  } catch (e) { status.textContent = ''; toast('Kunne ikke sende — ingen forbindelse?', 'fejl'); }
  knap.disabled = !skiltSidstOk;
}

async function gemSkiltSomTemplate() {
  const navn = (prompt('Navn på det nye skilt-template:') || '').trim();
  if (!navn) return;
  const s = skiltSpec();
  const res = await api('/api/skilt-templates', 'POST', {
    navn, beskrivelse: '', skilt_bredde_mm: s.skilt_bredde_mm, skilt_hoejde_mm: s.skilt_hoejde_mm,
    antal_linjer: skiltLinjer.length,
    linjer_config: skiltLinjer.map((l) => ({ justering: l.justering, hoejde_mm: l.hoejde_mm, font: l.font, x_mm: l.x_mm, y_mm: l.y_mm })),
    margin_top_mm: s.margin_top_mm, margin_bottom_mm: s.margin_bottom_mm, linje_afstand_mm: s.linje_afstand_mm,
    maskine_id: $('skilt-maskine').value || null,
  });
  if (!res.ok) { toast(res.fejl || 'Kunne ikke gemme template', 'fejl'); return; }
  await initDropdowns();
  $('skilt-template-valg').value = res.id;
  skiftSkiltType('template');
  toast(`Template »${navn}« gemt`, 'ok');
}

function skilteLavIgen(id) {
  const r = skilteKoeRows.find((x) => x.id === id);
  if (!r) return;
  let linjer = [];
  try { linjer = JSON.parse(r.linjer_json); } catch (e) {}
  skiltLinjer = (linjer.length ? linjer : [{}]).slice(0, 10).map((l) => ({ ...nyLinje(), ...l }));
  skiltInitialiseret = true;
  skiltType = 'frit';
  $('skilt-bredde').value = r.skilt_bredde_mm; $('skilt-hoejde').value = r.skilt_hoejde_mm;
  $('skilt-margin-top').value = r.margin_top_mm ?? ''; $('skilt-margin-bund').value = r.margin_bottom_mm ?? ''; $('skilt-linje-afstand').value = r.linje_afstand_mm ?? '';
  if ($('skilt-maskine').querySelector(`option[value="${r.maskine_id}"]`)) $('skilt-maskine').value = r.maskine_id;
  gaaTil('skilte');
  skiftSkiltType('frit', { stille: true });
  tegnSkiltLinjer();
  toast('Skiltet er åbnet — ret teksten og send igen', 'info');
}

// ─── Skilt-templates: liste + editor ──────────────────────────────────────────
async function hentSkiltTemplates() {
  const rows = await api('/api/skilt-templates');
  skiltTemplates = rows;
  $('skilt-template-tabel').innerHTML = rows.length === 0
    ? `<tr><td colspan="5" class="tomt">Ingen skilt-templates endnu.</td></tr>`
    : rows.map((r) => `<tr>
      <td data-label="ID">#${r.id}</td>
      <td data-label="Navn"><span class="clickable" onclick="redigerSkiltTemplate(${r.id})">${esc(r.navn)}</span></td>
      <td data-label="Størrelse">${r.skilt_bredde_mm}×${r.skilt_hoejde_mm} mm</td>
      <td data-label="Linjer">${r.antal_linjer}</td>
      <td class="act">
        <button class="btn btn-secondary btn-sm" onclick="redigerSkiltTemplate(${r.id})">Rediger</button>
        <button class="btn btn-ghost btn-sm" onclick="kopierSkiltTemplate(${r.id})">Kopi</button>
        <button class="btn btn-danger btn-sm" onclick="sletSkiltTemplate(${r.id})">Slet</button>
      </td></tr>`).join('');
}

function fyldSkiltTemplateForm(tmpl) {
  let cfg = [];
  try { cfg = tmpl && tmpl.linjer_config ? JSON.parse(tmpl.linjer_config) : []; } catch (e) {}
  linjeConfig = (cfg.length ? cfg : [{}, {}]).map((c) => ({ ...nyLinje(), ...c }));
  linjeConfig.forEach((l) => { delete l.tekst; });
  const v = (id, x) => { $(id).value = x ?? ''; };
  v('st-navn', tmpl ? tmpl.navn : ''); v('st-beskrivelse', tmpl ? tmpl.beskrivelse : '');
  v('st-bredde', tmpl ? tmpl.skilt_bredde_mm : 200); v('st-hoejde', tmpl ? tmpl.skilt_hoejde_mm : 100);
  v('st-maskine', tmpl ? tmpl.maskine_id : '');
  v('st-margin-top', tmpl && tmpl.margin_top_mm); v('st-margin-bund', tmpl && tmpl.margin_bottom_mm); v('st-linje-afstand', tmpl && tmpl.linje_afstand_mm);
  v('st-feed-xy', tmpl && tmpl.feed_xy); v('st-feed-z', tmpl && tmpl.feed_z); v('st-rpm', tmpl && tmpl.spindle_rpm);
  v('st-zop', tmpl && tmpl.z_op_mm); v('st-prox', tmpl && tmpl.prox_offset_mm);
  $('skilt-template-form').style.display = 'grid';
  tegnLinjeConfig();
  $('skilt-template-form').scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function visNySkiltTemplate() {
  redigerSkiltTemplateId = null;
  $('skilt-template-form-titel').textContent = 'Ny skilt-template';
  $('st-id').value = '';
  fyldSkiltTemplateForm(null);
}
async function redigerSkiltTemplate(id) {
  const all = await api('/api/skilt-templates');
  skiltTemplates = all;
  const tmpl = all.find((t) => t.id == id);
  if (!tmpl) return;
  redigerSkiltTemplateId = id;
  $('skilt-template-form-titel').textContent = 'Rediger skilt-template';
  $('st-id').value = id;
  fyldSkiltTemplateForm(tmpl);
}
async function kopierSkiltTemplate(id) {
  const all = await api('/api/skilt-templates');
  const tmpl = all.find((t) => t.id == id);
  if (!tmpl) return;
  redigerSkiltTemplateId = null;
  $('skilt-template-form-titel').textContent = 'Ny skilt-template (kopi)';
  $('st-id').value = '';
  fyldSkiltTemplateForm({ ...tmpl, navn: 'Kopi af ' + tmpl.navn });
}
function skjulSkiltTemplateForm() {
  $('skilt-template-form').style.display = 'none';
  redigerSkiltTemplateId = null;
}
function opdaterLinjeConfig() {
  const antal = Math.max(1, Math.min(10, +$('st-antal').value || 1));
  while (linjeConfig.length < antal) { const n = nyLinje(); delete n.tekst; linjeConfig.push(n); }
  linjeConfig = linjeConfig.slice(0, antal);
  tegnLinjeConfig();
}
function tilfoejLinjeConfig() { $('st-antal').value = Math.min(10, linjeConfig.length + 1); opdaterLinjeConfig(); }

const opdaterStPreview = debounce(async () => {
  const seq = ++_stSeq;
  const spec = {
    skilt_bredde_mm: +$('st-bredde').value || 0, skilt_hoejde_mm: +$('st-hoejde').value || 0,
    margin_top_mm: talEllerNull('st-margin-top'), margin_bottom_mm: talEllerNull('st-margin-bund'), linje_afstand_mm: talEllerNull('st-linje-afstand'),
    linjer: linjeConfig.map((c, i) => ({ ...c, tekst: 'Linje ' + (i + 1) })),
  };
  let lay;
  try { lay = await api('/api/skilt/preview', 'POST', spec); } catch (e) { return; }
  if (seq !== _stSeq) return;
  tegnSkiltSvg($('st-preview'), lay, {
    margenTop: spec.margin_top_mm ?? spec.skilt_hoejde_mm * 0.1, margenBund: spec.margin_bottom_mm ?? spec.skilt_hoejde_mm * 0.1, farveFor,
  });
  visBanner($('st-banner'), lay, false);
}, 180);

async function gemSkiltTemplate() {
  const navn = $('st-navn').value.trim();
  if (!navn) { toast('Giv templaten et navn', 'advarsel'); $('st-navn').focus(); return; }
  const num = (id) => { const el = $(id); return el.value === '' ? null : +el.value; };
  const data = {
    navn, beskrivelse: $('st-beskrivelse').value,
    skilt_bredde_mm: +$('st-bredde').value, skilt_hoejde_mm: +$('st-hoejde').value,
    antal_linjer: linjeConfig.length, linjer_config: linjeConfig,
    margin_top_mm: num('st-margin-top'), margin_bottom_mm: num('st-margin-bund'), linje_afstand_mm: num('st-linje-afstand'),
    feed_xy: num('st-feed-xy'), feed_z: num('st-feed-z'), spindle_rpm: num('st-rpm'), z_op_mm: num('st-zop'), prox_offset_mm: num('st-prox'),
    maskine_id: $('st-maskine').value || null,
  };
  const res = redigerSkiltTemplateId
    ? await api(`/api/skilt-templates/${redigerSkiltTemplateId}`, 'PUT', data)
    : await api('/api/skilt-templates', 'POST', data);
  if (res.ok) {
    toast('Template gemt', 'ok');
    await initDropdowns();
    hentSkiltTemplates();
    skjulSkiltTemplateForm();
  } else {
    toast(res.fejl || 'Kunne ikke gemme template', 'fejl');
  }
}
