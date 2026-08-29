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
async function hentSkiltTemplates() {
  const rows = await api('/api/skilt-templates');
  skiltTemplates = rows; // opdater state så redigerSkiltTemplate kan finde dem
  document.getElementById('skilt-template-tabel').innerHTML = rows.map(r => `<tr>
    <td>#${r.id}</td>
    <td class="clickable" onclick="redigerSkiltTemplate(${r.id})">${esc(r.navn)}</td>
    <td>${r.skilt_bredde_mm}×${r.skilt_hoejde_mm} mm</td><td>${r.antal_linjer} linjer</td>
    <td class="gap">
      <button class="btn btn-secondary" onclick="redigerSkiltTemplate(${r.id})" style="padding:4px 10px;font-size:0.8rem">Rediger</button>
      <button class="btn btn-danger" onclick="sletSkiltTemplate(${r.id})" style="padding:4px 10px;font-size:0.8rem">Slet</button>
    </td>
  </tr>`).join('');
}

function visNySkiltTemplate() {
  redigerSkiltTemplateId = null;
  linjeConfig = [];
  document.getElementById('skilt-template-form-titel').textContent = 'Ny skilt-template';
  document.getElementById('st-id').value = '';
  document.getElementById('st-navn').value = '';
  document.getElementById('st-beskrivelse').value = '';
  document.getElementById('st-bredde').value = '200';
  document.getElementById('st-hoejde').value = '100';
  document.getElementById('st-antal').value = '2';
  document.getElementById('st-maskine').value = '';
  document.getElementById('st-margin-top').value = '';
  document.getElementById('st-margin-bund').value = '';
  document.getElementById('st-linje-afstand').value = '';
  opdaterLinjeConfig();
  document.getElementById('skilt-template-form').style.display = 'block';
}

async function redigerSkiltTemplate(id) {
  redigerSkiltTemplateId = id;
  // Hent altid frisk data fra API
  const all = await api('/api/skilt-templates');
  skiltTemplates = all;
  const tmpl = skiltTemplates.find(t => t.id == id);
  if (!tmpl) return;
  
  document.getElementById('skilt-template-form-titel').textContent = 'Rediger skilt-template';
  document.getElementById('st-id').value = id;
  document.getElementById('st-navn').value = tmpl.navn;
  document.getElementById('st-beskrivelse').value = tmpl.beskrivelse || '';
  document.getElementById('st-bredde').value = tmpl.skilt_bredde_mm;
  document.getElementById('st-hoejde').value = tmpl.skilt_hoejde_mm;
  document.getElementById('st-antal').value = tmpl.antal_linjer;
  document.getElementById('st-maskine').value = tmpl.maskine_id || '';
  document.getElementById('st-margin-top').value    = tmpl.margin_top_mm || '';
  document.getElementById('st-margin-bund').value   = tmpl.margin_bottom_mm || '';
  document.getElementById('st-linje-afstand').value = tmpl.linje_afstand_mm || '';
  opdaterLinjeConfig(JSON.parse(tmpl.linjer_config));
  document.getElementById('skilt-template-form').style.display = 'block';
}

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

function skjulSkiltTemplateForm() {
  document.getElementById('skilt-template-form').style.display = 'none';
  redigerSkiltTemplateId = null;
}

let linjeConfig = [];

function opdaterLinjeConfig(existing = null) {
  const antal = +document.getElementById('st-antal').value;
  if (existing) {
    linjeConfig = existing;
  } else {
    // Bevar eksisterende linjer, tilføj eller fjern efter behov
    while (linjeConfig.length < antal) {
      linjeConfig.push({ justering: 'center', hoejde_mm: 10, font: 'block' });
    }
    linjeConfig = linjeConfig.slice(0, antal);
  }
  tegnLinjeConfig();
}

function tegnLinjeConfig() {
  const container = document.getElementById('st-linjer-container');
  container.innerHTML = linjeConfig.map((l, i) => `
    <div style="background:var(--bg-primary);padding:10px;border-radius:6px;margin-bottom:8px;border:1px solid var(--border);">
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr auto;gap:8px;margin-bottom:6px;">
        <div><label>Linje ${i+1}</label></div>
        <div>
          <label>Justering</label>
          <select onchange="linjeConfig[${i}].justering = this.value">
            <option value="venstre" ${l.justering==='venstre'?'selected':''}>Venstre</option>
            <option value="center" ${l.justering==='center'?'selected':''}>Center</option>
            <option value="hoejre" ${l.justering==='hoejre'?'selected':''}>Højre</option>
          </select>
        </div>
        <div>
          <label>Font</label>
          <select onchange="linjeConfig[${i}].font = this.value">
            ${Object.entries(fonts).map(([k,v]) => `<option value="${esc(k)}" ${l.font===k?'selected':''}>${esc(v)}</option>`).join('')}
          </select>
        </div>
        <div>
          <label>Højde (mm)</label>
          <input type="number" value="${l.hoejde_mm||10}" step="0.5" onchange="linjeConfig[${i}].hoejde_mm = +this.value">
        </div>
        <div><label>&nbsp;</label><button class="btn btn-danger" onclick="fjernLinjeConfig(${i})" style="padding:8px 12px;">✕</button></div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr 2fr;gap:8px;">
        <div>
          <label style="color:#3498db;">X (mm) <span style="font-weight:normal;font-size:0.7rem;">tom=auto</span></label>
          <input type="number" value="${l.x_mm!=null?l.x_mm:''}" step="0.5" placeholder="Auto" onchange="linjeConfig[${i}].x_mm = this.value!==''?+this.value:null">
        </div>
        <div>
          <label style="color:#e74c3c;">Y (mm) <span style="font-weight:normal;font-size:0.7rem;">tom=auto</span></label>
          <input type="number" value="${l.y_mm!=null?l.y_mm:''}" step="0.5" placeholder="Auto" onchange="linjeConfig[${i}].y_mm = this.value!==''?+this.value:null">
        </div>
        <div style="display:flex;align-items:flex-end;padding-bottom:2px;">
          <span style="font-size:0.75rem;color:var(--text-secondary);">Tom = auto placering fra margener</span>
        </div>
      </div>
    </div>
  `).join('') + `
  <div class="mt gap">
    <button class="btn btn-secondary" onclick="tilfoejLinjeConfig()">+ Tilføj linje</button>
    <span style="color:var(--text-secondary);font-size:0.8rem;">(${linjeConfig.length} linjer)</span>
  </div>`;
}

function tilfoejLinjeConfig() {
  if (linjeConfig.length >= 10) return;
  linjeConfig.push({ justering: 'center', hoejde_mm: 10, font: 'block', x_mm: null, y_mm: null });
  document.getElementById('st-antal').value = linjeConfig.length;
  tegnLinjeConfig();
}

function fjernLinjeConfig(idx) {
  if (linjeConfig.length <= 1) return;
  linjeConfig.splice(idx, 1);
  document.getElementById('st-antal').value = linjeConfig.length;
  tegnLinjeConfig();
}

async function gemSkiltTemplate() {
  const mtVal = document.getElementById('st-margin-top').value;
  const mbVal = document.getElementById('st-margin-bund').value;
  const laVal = document.getElementById('st-linje-afstand').value;

  const data = {
    navn: document.getElementById('st-navn').value,
    beskrivelse: document.getElementById('st-beskrivelse').value,
    skilt_bredde_mm: +document.getElementById('st-bredde').value,
    skilt_hoejde_mm: +document.getElementById('st-hoejde').value,
    antal_linjer: +document.getElementById('st-antal').value,
    linjer_config: linjeConfig,
    margin_top_mm: mtVal ? +mtVal : null,
    margin_bottom_mm: mbVal ? +mbVal : null,
    linje_afstand_mm: laVal ? +laVal : null,
    maskine_id: document.getElementById('st-maskine').value || null,
  };
  
  let res;
  if (redigerSkiltTemplateId) {
    res = await api(`/api/skilt-templates/${redigerSkiltTemplateId}`, 'PUT', data);
  } else {
    res = await api('/api/skilt-templates', 'POST', data);
  }
  
  if (res.ok) { 
    await initDropdowns();
    hentSkiltTemplates(); 
    skjulSkiltTemplateForm(); 
  }
}

// ─── Maskiner ──────────────────────────────────────────────────────────────────
async function hentMaskiner() {
  const rows = await api('/api/maskiner');
  document.getElementById('maskiner-tabel').innerHTML = rows.map(r => `<tr>
    <td>#${r.id}</td><td>${esc(r.navn)}</td><td>${esc(r.model)}</td><td>${esc(r.protokol)}</td><td>${esc(r.ip)}</td><td>${r.port}</td>
    <td>${r.offset_x || 0} mm</td><td>${r.offset_y || 0} mm</td><td>${r.offset_z || 0} mm</td>
    <td>${r.spejl_y ? '✓' : '—'}</td>
    <td class="gap">
      <button class="btn btn-secondary" onclick="redigerMaskine(${r.id})" style="padding:4px 10px;font-size:0.8rem">Rediger</button>
      <button class="btn btn-secondary" onclick="redigerKalibrering(${r.id})" style="padding:4px 10px;font-size:0.8rem">Kalibrér</button>
      <button class="btn btn-danger" onclick="sletMaskine(${r.id})" style="padding:4px 10px;font-size:0.8rem">Slet</button>
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

// System-info: kørende version + seneste auto-opdaterings-log (til at se
// hvorfor en opdatering evt. fejlede — også fra mobil, efter en reboot).
async function visSystemInfo() {
  const pre = document.getElementById('sys-log');
  const ver = document.getElementById('sys-version');
  pre.style.display = 'block';
  pre.textContent = 'Henter...';
  try {
    const info = await api('/api/systeminfo');
    if (ver) ver.textContent = info.version ? '· ' + info.version : '';
    pre.textContent = (info.update_log && info.update_log.length)
      ? info.update_log.join('\n')
      : '(ingen opdaterings-log endnu)';
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
  await initDropdowns();
  opdaterJobFelter();
  initSkilt();
  hentBatches();
})();
