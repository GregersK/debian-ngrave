// ─── Forhåndsvisning af nøgle-template (de rigtige gravér-streger) ────────────
// Serveren lægger felterne ud med SAMME motor som graveringen (/api/templates/preview),
// så det man ser er det der graveres — inkl. skrifttype, ÆØÅ og bogstavafstand.
const FELT_FARVER = { markering: '#2f80ed', system: '#27ae60', loebe: '#e08e0b', ekstra: '#9b59b6' };
let _tPrevSeq = 0;

const opdaterPreview = debounce(async () => {
  const svg = document.getElementById('felt-preview');
  if (!svg || !$('template-form') || $('template-form').style.display === 'none') return;
  const seq = ++_tPrevSeq;
  const data = templateFormData();
  data.eksempel = {
    type_felt: ($('t-eks-mark').value || '').toUpperCase(), system_nr: ($('t-eks-sys').value || '').toUpperCase(),
    loebe_nr: $('t-eks-loebe').value || '', ekstra_tekst: ($('t-eks-ekstra').value || '').toUpperCase(),
  };
  let lay;
  try { lay = await api('/api/templates/preview', 'POST', data); } catch (e) { return; }
  if (seq !== _tPrevSeq || !lay || !lay.zone) return;

  const z = lay.zone, pad = Math.max(z.bredde, z.hoejde) * 0.12 + 1;
  let x0 = -pad, y0 = z.top - pad, x1 = z.bredde + pad, y1 = z.top + z.hoejde + pad;
  lay.felter.forEach((f) => { if (f.bbox) { x0 = Math.min(x0, f.bbox[0] - 1); y0 = Math.min(y0, f.bbox[1] - 2.2); x1 = Math.max(x1, f.bbox[2] + 1); y1 = Math.max(y1, f.bbox[3] + 1); } });
  svg.setAttribute('viewBox', `${x0} ${y0} ${x1 - x0} ${y1 - y0}`);
  const navne = { markering: $('t-mark-navn').value, system: $('t-sys-navn').value, loebe: $('t-loebe-navn').value, ekstra: $('t-ekstra-navn').value };
  const fs = Math.max(0.9, z.hoejde * 0.09);
  let h = `<rect class="zone" x="0" y="${z.top}" width="${z.bredde}" height="${z.hoejde}" rx="0.4"/>`;
  lay.felter.forEach((f) => {
    const farve = FELT_FARVER[f.felt] || '#333';
    const d = f.paths.map((p) => 'M' + p.map((pt) => pt[0] + ' ' + pt[1]).join('L')).join('');
    h += `<path d="${d}" fill="none" stroke="${farve}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`;
    if (f.bbox) h += `<text x="${f.bbox[0]}" y="${f.bbox[1] - 0.5}" font-size="${fs}" fill="${farve}" font-family="system-ui,sans-serif">${esc(navne[f.felt] || f.felt)}</text>`;
  });
  svg.innerHTML = h;

  const b = $('felt-banner');
  if (lay.fejl.length) b.innerHTML = `<div class="banner fejl"><b>Passer ikke i zonen</b><ul>${lay.fejl.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
  else if (lay.advarsler.length) b.innerHTML = `<div class="banner advarsel"><b>Tjek lige</b><ul>${lay.advarsler.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
  else b.innerHTML = lay.felter.length ? '<div class="banner ok">✓ Alle felter passer i zonen</div>' : '';
  const st = lay.statistik || {};
  $('felt-preview-info').textContent = `Zone ${z.bredde} × ${z.hoejde} mm · pr. nøgle: ${st.loeft ?? 0} penneløft, ${Math.round(st.fraesevej_mm || 0)} mm fræsevej`;
}, 150);

// ─── Skilt-Templates ──────────────────────────────────────────────────────────
async function testMaskine() {
  const id = document.getElementById('k-id').value;
  const status = document.getElementById('k-status');
  status.textContent = '⏳ Sender test-kommando...';
  status.style.color = 'var(--text-secondary)';
  let res = await api(`/api/maskiner/${id}/test`, 'POST');
  if (res.kraever_bekraeftelse) {            // maskinen har lige fået et program og graverer formentlig stadig
    if (!confirm(res.fejl)) { status.textContent = ''; return; }
    res = await api(`/api/maskiner/${id}/test`, 'POST', { tving: true });
  }
  if (res.ok) {
    status.textContent = '✓ Maskinen kører til kalibreret position (0,0) med Z oppe';
    status.style.color = '#27ae60';
  } else {
    status.textContent = `✗ Fejl: ${res.fejl}`;
    status.style.color = 'var(--accent)';
  }
}


// ─── Maskiner ──────────────────────────────────────────────────────────────────
async function hentMaskiner() {
  const rows = await api('/api/maskiner');
  document.getElementById('maskiner-tabel').innerHTML = rows.length === 0
    ? `<tr><td colspan="13" class="tomt"><span class="stor">⚙</span>Ingen maskiner endnu.<br><button class="btn btn-secondary btn-sm mt" onclick="visNyMaskine()">+ Tilføj den første maskine</button></td></tr>`
    : rows.map(r => `<tr>
    <td data-label="ID">#${r.id}</td><td data-label="Navn"><b>${esc(r.navn)}</b></td><td data-label="Model">${esc(r.model)}</td>
    <td data-label="Protokol">${esc(r.protokol)}</td><td data-label="IP">${esc(r.ip)}</td><td data-label="Port">${r.port}</td>
    <td data-label="Forbindelse" id="ms-${r.id}"><span class="ms ukendt"><span class="dot"></span>Tjekker…</span></td>
    <td data-label="Offset X">${r.offset_x || 0} mm</td><td data-label="Offset Y">${r.offset_y || 0} mm</td><td data-label="Offset Z">${r.offset_z || 0} mm</td>
    <td data-label="Spejl Y">${r.spejl_y ? '✓' : '—'}</td>
    <td data-label="Hastighed">${esc({ fuld: 'Fuld', let: 'Let', ingen: 'Ingen' }[r.optimering] || 'Fuld')}</td>
    <td class="act">
      <button class="btn btn-secondary btn-sm" onclick="pingMaskine(${r.id})" title="Opretter og lukker en forbindelse — sender ingen data">Tjek nu</button>
      <button class="btn btn-secondary btn-sm" onclick="redigerMaskine(${r.id})">Rediger</button>
      <button class="btn btn-secondary btn-sm" onclick="redigerKalibrering(${r.id})">Kalibrér</button>
      <button class="btn btn-danger btn-sm" onclick="sletMaskine(${r.id})">Slet</button>
    </td>
  </tr>`).join('');
  hentMaskinStatus();
}

const MS_TEKST = { online: 'Online', offline: 'Svarer ikke', afviser: 'Afviser forbindelsen', ukendt: 'Ikke tjekket endnu' };
async function hentMaskinStatus() {
  let liste;
  try { liste = await api('/api/maskiner/status'); } catch (e) { return; }
  liste.forEach(m => {
    const el = document.getElementById('ms-' + m.id);
    if (!el) return;
    maskinStatus[m.id] = m.status;
    let sub = '';
    if (m.koe && m.koe.running) sub = 'Sender nu';
    else if (m.graverer_formentlig) sub = `Program sendt for ${sekTekst(m.sendt_sek_siden)} — graverer formentlig (tjekker ikke forbindelsen imens)`;
    else if (m.status === 'online') sub = `svarede ${sekTekst(m.tjekket_sek_siden)}${m.ms != null ? ' · ' + m.ms + ' ms' : ''}`;
    else if (m.status === 'ukendt') sub = 'Første tjek kommer om lidt';
    else sub = `${esc(m.fejl || '')}${m.set_online_sek_siden != null ? ' · sidst online ' + sekTekst(m.set_online_sek_siden) : ''}`;
    if (m.koe && m.koe.pending) sub += `${sub ? ' · ' : ''}${m.koe.pending} i kø`;
    el.innerHTML = `<span class="ms ${esc(m.status)}"><span class="dot"></span>${esc(MS_TEKST[m.status] || m.status)}</span><span class="ms-sub">${sub}</span>`;
  });
  opdaterMaskineAdvarsler();
}

async function pingMaskine(id) {
  const el = document.getElementById('ms-' + id);
  if (el) el.innerHTML = '<span class="ms ukendt"><span class="dot"></span>Tjekker…</span>';
  try {
    const r = await api(`/api/maskiner/${id}/ping`, 'POST');
    if (r.status === 'online') toast(`Maskinen svarer (${r.ms} ms)`, 'ok');
    else if (r.status === 'optaget') toast(r.besked, 'info');
    else toast(r.fejl || 'Maskinen svarer ikke', 'fejl');
  } catch (e) { toast('Kunne ikke tjekke maskinen', 'fejl'); }
  hentMaskinStatus();
}

function visNyMaskine() {
  document.getElementById('maskine-form-titel').textContent = 'Ny maskine';
  document.getElementById('m-id').value = '';
  document.getElementById('m-navn').value = '';
  document.getElementById('m-model').value = '';
  document.getElementById('m-protokol').value = 'gcode';
  document.getElementById('m-ip').value = '';
  document.getElementById('m-port').value = '22000';
  document.getElementById('m-optimering').value = 'fuld';
  document.getElementById('m-status').textContent = '';
  document.getElementById('maskine-form').style.display = 'block';
  document.getElementById('maskine-form').scrollIntoView({behavior:'smooth'});
}

async function redigerMaskine(id) {
  const rows = await api('/api/maskiner');
  const r = rows.find(m => m.id === id);
  if (!r) return;
  document.getElementById('maskine-form-titel').textContent = `Rediger — ${r.navn}`;
  document.getElementById('m-id').value = r.id;
  document.getElementById('m-navn').value = r.navn || '';
  document.getElementById('m-model').value = r.model || '';
  document.getElementById('m-protokol').value = r.protokol || 'gcode';
  document.getElementById('m-ip').value = r.ip || '';
  document.getElementById('m-port').value = r.port || '';
  document.getElementById('m-optimering').value = r.optimering || 'fuld';
  document.getElementById('m-status').textContent = '';
  document.getElementById('maskine-form').style.display = 'block';
  document.getElementById('maskine-form').scrollIntoView({behavior:'smooth'});
}

async function gemMaskine() {
  const id = document.getElementById('m-id').value;
  const data = {
    navn: document.getElementById('m-navn').value.trim(),
    model: document.getElementById('m-model').value.trim(),
    protokol: document.getElementById('m-protokol').value,
    ip: document.getElementById('m-ip').value.trim(),
    port: +document.getElementById('m-port').value,
    optimering: document.getElementById('m-optimering').value,
  };
  if (!data.navn || !data.model || !data.ip || !data.port) {
    document.getElementById('m-status').textContent = '✗ Udfyld alle felter';
    document.getElementById('m-status').style.color = 'var(--accent)';
    return;
  }
  let res;
  if (id) {
    res = await api(`/api/maskiner/${id}`, 'PUT', data);
  } else {
    res = await api('/api/maskiner', 'POST', data);
  }
  if (res.ok) {
    document.getElementById('maskine-form').style.display = 'none';
    await initDropdowns();
    hentMaskiner();
  } else {
    document.getElementById('m-status').textContent = '✗ ' + (res.fejl || 'Fejl');
    document.getElementById('m-status').style.color = 'var(--accent)';
  }
}

async function sletMaskine(id) {
  if (!confirm('Slet (deaktivér) denne maskine? Eksisterende jobs bevares.')) return;
  const res = await api(`/api/maskiner/${id}`, 'DELETE');
  if (res.ok) {
    await initDropdowns();
    hentMaskiner();
  }
}

// ─── Backup: eksport/import af templates ─────────────────────────────────────
async function eksporterTemplates() {
  const status = document.getElementById('backup-status');
  status.textContent = 'Eksporterer...';
  status.style.color = 'var(--text-secondary)';
  try {
    const data = await api('/api/export');
    const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const dato = new Date().toISOString().slice(0, 10);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ngrave-templates-${dato}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    status.textContent = `✓ Eksporteret: ${data.templates.length} nøgle-templates, ${data.skilt_templates.length} skilt-templates`;
    status.style.color = '#27ae60';
  } catch (e) {
    status.textContent = '✗ Eksport fejlede';
    status.style.color = 'var(--accent)';
  }
}

async function importerTemplates(input) {
  const file = input.files[0];
  if (!file) return;
  const status = document.getElementById('backup-status');
  status.textContent = 'Importerer...';
  status.style.color = 'var(--text-secondary)';
  try {
    const text = await file.text();
    const data = JSON.parse(text);
    const res = await api('/api/import', 'POST', data);
    if (res.ok) {
      status.textContent = `✓ Nøgle-templates: ${res.templates.created} nye, ${res.templates.updated} opdateret · ` +
        `Skilt-templates: ${res.skilt_templates.created} nye, ${res.skilt_templates.updated} opdateret`;
      status.style.color = '#27ae60';
      await initDropdowns();
      hentTemplates();
      hentSkiltTemplates();
    } else {
      status.textContent = '✗ Import fejlede: ' + (res.fejl || 'ukendt fejl');
      status.style.color = 'var(--accent)';
    }
  } catch (e) {
    status.textContent = '✗ Ugyldig fil: ' + e.message;
    status.style.color = 'var(--accent)';
  }
  input.value = '';
}

// System-info: kørende version + seneste auto-opdaterings-log (til at se
// hvorfor en opdatering evt. fejlede — også fra mobil, efter en reboot).
async function visSystemInfo() {
  const pre = document.getElementById('sys-log');
  const ver = document.getElementById('sys-version');
  pre.style.display = 'block';
  pre.textContent = 'Henter...';
  try {
    const info = await api('/api/systeminfo');
    if (ver) ver.textContent = (info.version ? '· ' + info.version : '') +
      (info.channel === 'beta' ? '  ⚠️ BETA-kanal' : '') +
      (info.last_check ? '  · sidst tjekket ' + info.last_check.replace('T',' ') : '');
    const adv = info.advarsel
      ? `⚠️ ${info.advarsel}\n${'─'.repeat(40)}\n`
      : '';
    pre.textContent = adv + ((info.update_log && info.update_log.length)
      ? info.update_log.join('\n')
      : '(ingen opdaterings-log endnu)');
    pre.style.borderLeft = info.advarsel ? '4px solid var(--accent)' : '';
  } catch (e) {
    pre.textContent = 'Kunne ikke hente system-info';
  }
}

async function redigerKalibrering(id) {
  const rows = await api('/api/maskiner');
  const r = rows.find(m => m.id === id);
  if (!r) return;
  document.getElementById('kalibrering-titel').textContent = `Kalibrering — ${r.navn}`;
  document.getElementById('k-id').value = r.id;
  document.getElementById('k-x').value = r.offset_x || 0;
  document.getElementById('k-y').value = r.offset_y || 0;
  document.getElementById('k-z').value = r.offset_z || 0;
  document.getElementById('k-spejl-y').checked = !!r.spejl_y;
  document.getElementById('k-markering-dx').value = r.felt_markering_dx || 0;
  document.getElementById('k-markering-dy').value = r.felt_markering_dy || 0;
  document.getElementById('k-system-dx').value    = r.felt_system_dx    || 0;
  document.getElementById('k-system-dy').value    = r.felt_system_dy    || 0;
  document.getElementById('k-loebe-dx').value     = r.felt_loebe_dx     || 0;
  document.getElementById('k-loebe-dy').value     = r.felt_loebe_dy     || 0;
  document.getElementById('k-ekstra-dx').value    = r.felt_ekstra_dx    || 0;
  document.getElementById('k-ekstra-dy').value    = r.felt_ekstra_dy    || 0;
  document.getElementById('k-status').textContent = '';
  document.getElementById('kalibrering-form').style.display = 'block';
  document.getElementById('kalibrering-form').scrollIntoView({behavior:'smooth'});
}

async function gemKalibrering() {
  const id = document.getElementById('k-id').value;
  const res = await api(`/api/maskiner/${id}/kalibrering`, 'PUT', {
    offset_x: +document.getElementById('k-x').value,
    offset_y: +document.getElementById('k-y').value,
    offset_z: +document.getElementById('k-z').value,
    spejl_y:  document.getElementById('k-spejl-y').checked,
    felt_markering_dx: +document.getElementById('k-markering-dx').value,
    felt_markering_dy: +document.getElementById('k-markering-dy').value,
    felt_system_dx:    +document.getElementById('k-system-dx').value,
    felt_system_dy:    +document.getElementById('k-system-dy').value,
    felt_loebe_dx:     +document.getElementById('k-loebe-dx').value,
    felt_loebe_dy:     +document.getElementById('k-loebe-dy').value,
    felt_ekstra_dx:    +document.getElementById('k-ekstra-dx').value,
    felt_ekstra_dy:    +document.getElementById('k-ekstra-dy').value,
  });
  if (res.ok) {
    document.getElementById('k-status').textContent = '✓ Gemt';
    document.getElementById('k-status').style.color = 'var(--accent)';
    await initDropdowns();
    hentMaskiner();
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────
(async () => {
  byggNav();
  maalHeader();
  try { await initDropdowns(); } catch (e) { toast('Kunne ikke hente data fra serveren', 'fejl'); }
  opdaterJobFelter();
  gaaTil(location.hash.slice(1) || 'nyt-job', { noHash: true, noScroll: true });
  opdaterStatus();
})();
