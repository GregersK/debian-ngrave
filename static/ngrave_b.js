// ─── Visualisering af felt-placering ────────────────────────────────────────────
function opdaterPreview() {
  const svg = document.getElementById('felt-preview');
  if (!svg) return;
  
  const zoneB = +document.getElementById('t-bredde').value || 18;
  const zoneH = +document.getElementById('t-hoejde').value || 8;
  const th = +document.getElementById('t-th').value || 3.5;
  
  const felter = [
    { aktiv: document.getElementById('t-mark-aktiv').checked,  navn: document.getElementById('t-mark-navn').value || 'Markering',
      tekst: 'L1', x: +document.getElementById('t-mark-x').value, y: +document.getElementById('t-mark-y').value,
      jus: document.getElementById('t-mark-jus').value, color: '#3498db',
      font: document.getElementById('t-mark-font').value || 'block',
      fth: +document.getElementById('t-mark-hoejde').value || th },
    { aktiv: document.getElementById('t-sys-aktiv').checked, navn: document.getElementById('t-sys-navn').value || 'System',
      tekst: 'A0938E', x: +document.getElementById('t-sys-x').value, y: +document.getElementById('t-sys-y').value,
      jus: document.getElementById('t-sys-jus').value, color: '#27ae60',
      font: document.getElementById('t-sys-font').value || 'block',
      fth: +document.getElementById('t-sys-hoejde').value || th },
    { aktiv: document.getElementById('t-loebe-aktiv').checked, navn: document.getElementById('t-loebe-navn').value || 'Løbenr',
      tekst: '1', x: +document.getElementById('t-loebe-x').value, y: +document.getElementById('t-loebe-y').value,
      jus: document.getElementById('t-loebe-jus').value, color: '#f39c12',
      font: document.getElementById('t-loebe-font').value || 'block',
      fth: +document.getElementById('t-loebe-hoejde').value || th },
    { aktiv: document.getElementById('t-ekstra-aktiv').checked, navn: document.getElementById('t-ekstra-navn').value || 'Ekstra',
      tekst: 'EKS', x: +document.getElementById('t-ekstra-x').value, y: +document.getElementById('t-ekstra-y').value,
      jus: document.getElementById('t-ekstra-jus').value, color: '#9b59b6',
      font: document.getElementById('t-ekstra-font').value || 'block',
      fth: +document.getElementById('t-ekstra-hoejde').value || th },
  ];
  
  const scale = 8;
  const pad = 30;
  const zoneW_px = zoneB * scale;
  const zoneH_px = zoneH * scale + 60;
  const svgW = Math.max(zoneW_px + pad * 2, 400);
  const svgH = Math.max(zoneH_px + pad * 2, 250);
  
  svg.setAttribute('viewBox', `0 0 ${svgW} ${svgH}`);
  svg.setAttribute('width', svgW);
  svg.setAttribute('height', svgH);
  
  function calcX(offsetX, tekst, jus) {
    const tw = tekst.length * th * 0.6;
    if (jus === 'hoejre') return offsetX + zoneB - tw;
    if (jus === 'center') return offsetX + (zoneB - tw) / 2;
    return offsetX;
  }
  
  const zoneX0 = pad;
  const zoneY0 = pad;
  
  let html = '';
  html += `<rect x="${zoneX0}" y="${zoneY0}" width="${zoneW_px}" height="${zoneH*scale}" fill="#e0e0e0" stroke="#999" stroke-dasharray="4,2"/>`;
  html += `<rect x="${zoneX0}" y="${zoneY0 + zoneH*scale}" width="${zoneW_px}" height="60" fill="#f5f5f5" stroke="#ccc" stroke-dasharray="2,2"/>`;
  
  felter.forEach(f => {
    if (!f.aktiv) return;
    const fth = f.fth || th;
    const cssFont = fontTilCSS(f.font);
    const isItalic = fontErItalic(f.font);
    const fx = calcX(f.x, f.tekst, f.jus);
    const yPos = zoneY0 + f.y * scale + fth * scale;
    html += `<text x="${zoneX0 + fx*scale}" y="${yPos}" font-size="${fth*scale}" fill="${f.color}" font-family="${cssFont}" font-style="${isItalic?'italic':'normal'}">${f.tekst}</text>`;
    html += `<circle cx="${zoneX0 + fx*scale}" cy="${yPos}" r="3" fill="${f.color}"/>`;
    html += `<text x="${zoneX0 + fx*scale + 8}" y="${yPos - fth*scale - 2}" font-size="8" fill="${f.color}" font-family="sans-serif">${esc(f.navn)}</text>`;
  });
  
  html += `<circle cx="${zoneX0}" cy="${zoneY0}" r="4" fill="#e94560" stroke="#fff" stroke-width="1"/>`;
  html += `<text x="${zoneX0 - 25}" y="${zoneY0 - 5}" font-size="10" fill="#666">0,0</text>`;
  html += `<text x="${zoneX0 + zoneW_px/2}" y="${zoneY0 - 8}" font-size="10" fill="#666" text-anchor="middle">Zone: ${zoneB}×${zoneH} mm</text>`;
  
  svg.innerHTML = html;
}

// ─── Skilt-Templates ──────────────────────────────────────────────────────────
async function testMaskine() {
  const id = document.getElementById('k-id').value;
  const status = document.getElementById('k-status');
  status.textContent = '⏳ Sender test-kommando...';
  status.style.color = 'var(--text-secondary)';
  const res = await api(`/api/maskiner/${id}/test`, 'POST');
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
    ? `<tr><td colspan="11" class="tomt"><span class="stor">⚙</span>Ingen maskiner endnu.<br><button class="btn btn-secondary btn-sm mt" onclick="visNyMaskine()">+ Tilføj den første maskine</button></td></tr>`
    : rows.map(r => `<tr>
    <td data-label="ID">#${r.id}</td><td data-label="Navn"><b>${esc(r.navn)}</b></td><td data-label="Model">${esc(r.model)}</td>
    <td data-label="Protokol">${esc(r.protokol)}</td><td data-label="IP">${esc(r.ip)}</td><td data-label="Port">${r.port}</td>
    <td data-label="Offset X">${r.offset_x || 0} mm</td><td data-label="Offset Y">${r.offset_y || 0} mm</td><td data-label="Offset Z">${r.offset_z || 0} mm</td>
    <td data-label="Spejl Y">${r.spejl_y ? '✓' : '—'}</td>
    <td class="act">
      <button class="btn btn-secondary btn-sm" onclick="redigerMaskine(${r.id})">Rediger</button>
      <button class="btn btn-secondary btn-sm" onclick="redigerKalibrering(${r.id})">Kalibrér</button>
      <button class="btn btn-danger btn-sm" onclick="sletMaskine(${r.id})">Slet</button>
    </td>
  </tr>`).join('');
}

function visNyMaskine() {
  document.getElementById('maskine-form-titel').textContent = 'Ny maskine';
  document.getElementById('m-id').value = '';
  document.getElementById('m-navn').value = '';
  document.getElementById('m-model').value = '';
  document.getElementById('m-protokol').value = 'gcode';
  document.getElementById('m-ip').value = '';
  document.getElementById('m-port').value = '22000';
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
