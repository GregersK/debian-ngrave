# nGrave

**Gravesystem til Vision Phoenix CNC-gravemaskiner (S5/S3)**

Webbaseret system til nøgle- og skiltegravering med live jobkø, batch-håndtering og automatisk G-code/CIPHER CEF generering.

---

## Funktioner

### Nøglegravering
- Batch-gravering med auto-opdeling på plader (f.eks. 20 nøgler pr. plade)
- On-hold workflow — næste plade frigives manuelt
- Dynamiske felter per template (op til 4): Markering, System nr, Løbenr (auto), Ekstra
- Per-felt skrifttype, tekststørrelse, X/Y placering og justering
- Grid-editor med auto-udfyld (start X/Y + afstand)
- Maskin-kalibrering (global X/Y/Z offset per maskine)
- Start-slot valg (start ved slot 3 f.eks. hvis plade er halvt fuld)

### Skiltegravering
- Fri størrelse i mm
- 1–10 tekstlinjer med skrifttype, størrelse, justering og manuel X/Y
- Skilt-templates til genbrugelige layouts
- Live visualisering med korrekt fontrendring

### Generelt
- 🌓 Light/Dark mode (huskes i browser)
- Live preview for både nøgle-felter og skilte
- 13 skrifttyper: Block (custom single-stroke), Roman, Italic, Script, Gothic m.fl.
- Automatisk migration ved opgradering (ingen manuel SQL)
- Jobkø med ryd-op funktion

---

## Hardware support

| Maskine | Protokol | Forbindelse |
|---------|----------|-------------|
| Vision Phoenix S5 | G-code over TCP | Direkte netværk |
| Vision Phoenix S3 | CIPHER CEF over TCP | RS232 via RUT206/RUT145 Serial Over IP |

---

## Installation

### Krav
- Debian 12 (Bookworm) eller nyere
- Python 3.11+
- Netværksadgang til gravemaskine(r)

### Hurtig installation

```bash
# Download og installer
wget https://github.com/DITBRUGERNAVN/ngrave/archive/main.zip
unzip main.zip
cd ngrave-main
sudo bash install.sh
```

Åbn derefter `http://SERVER_IP` i browser.

### Manuel installation

```bash
git clone https://github.com/DITBRUGERNAVN/ngrave.git
cd ngrave
python3 -m venv venv
source venv/bin/activate
pip install flask hershey-fonts
python app.py
```

---

## Konfiguration

### Maskiner (kræver SQL — gøres kun én gang)

```bash
sqlite3 /opt/ngrave/ngrave.db
```

```sql
INSERT INTO maskiner (navn, model, ip, port, protokol) VALUES
    ('Phoenix S5', 'S5', '192.168.1.100', 22000, 'gcode'),
    ('Phoenix S3', 'S3', '192.168.1.101', 5000,  'cipher');
.quit
```

### Kalibrering

Gøres via UI → Maskiner → Kalibrér:
- **Offset X/Y/Z** lægges til alle koordinater for den pågældende maskine
- Test-knap kører maskinen til kalibreret 0,0 position uden spindle

### RUT206/RUT145 (S3 RS232 → netværk)

Konfigurer under **Services → Serial Utilities → Over IP**:
- Mode: TCP Server
- Protocol: Raw TCP
- Port: 5000
- Baud rate: 57600
- Data bits: 8 / Parity: None / Stop bits: 1

DB9 pinout: Pin 2 (RX) → S3 TX, Pin 3 (TX) → S3 RX, Pin 5 (GND) → S3 GND

---

## Struktur

```
ngrave/
├── app.py                  # Flask server + API + queue worker
├── schema.sql              # Database schema (auto-migrering)
├── requirements.txt        # Python dependencies
├── install.sh              # Debian 12 installationsscript
├── workers/
│   ├── block_font.py       # Custom single-stroke font med ÆØÅ
│   ├── font_manager.py     # Font router (block + Hershey fonts)
│   ├── gcode_worker.py     # G-code generator til S5
│   ├── cipher_worker.py    # CIPHER CEF generator til S3
│   └── skilt_worker.py     # G-code til skiltegravering
├── templates/
│   └── index.html          # Web UI (single-file SPA)
└── static/                 # Statiske filer (placeholder)
```

---

## Teknisk

### Custom Block Font
Single-stroke font håndkodet i `block_font.py` med fuld dansk tegnsæt (ÆØÅ/æøå). Designet specifikt til gravering — alle tegn graveres i én sammenhængende bevægelse uden løft.

### G-code workflow (S5)
```
M24 → G28 Z0 → G20 → M3 S16000
→ [per nøgle: G0 til position → G4 P25 → G30 (prox) → G1 gravér streger]
→ M5 → M30
```

Hele pladefulden sendes som ét G-code program — maskinen stopper ikke mellem nøgler.

### CIPHER CEF workflow (S3)
Tilsvarende — hele batchen sendes som én kommandostreng.

### Database
SQLite med automatisk migration. Nye kolonner tilføjes ved opstart uden at slette eksisterende data.

### Prox-sensor
`G30` bruges til at finde materialets overflade pr. streg. Offset justeres i template (`prox_offset_mm`).

---

## API

| Method | Endpoint | Beskrivelse |
|--------|----------|-------------|
| GET | `/api/maskiner` | Liste alle maskiner |
| PUT | `/api/maskiner/<id>/kalibrering` | Sæt kalibrerings-offset |
| POST | `/api/maskiner/<id>/test` | Kør til 0,0 position |
| GET | `/api/templates` | Liste nøgle-templates |
| POST | `/api/templates` | Opret template |
| PUT | `/api/templates/<id>` | Opdater template |
| DELETE | `/api/templates/<id>` | Slet template |
| GET | `/api/batches` | Jobkø (nøgler) |
| POST | `/api/batches` | Opret batch |
| POST | `/api/batches/<id>/frigiv` | Frigiv on-hold batch |
| POST | `/api/batches/<id>/annuller` | Annuller batch |
| POST | `/api/jobkoe/ryd-op` | Slet færdige jobs |
| GET/POST | `/api/skilt-templates` | Skilt-templates CRUD |
| GET/POST | `/api/skilte` | Skilte-jobkø |

---

## Licens

MIT License — brug frit, men del forbedringer gerne tilbage.

---

## Udviklet med

- Python / Flask
- SQLite
- Vanilla JavaScript (ingen frameworks)
- Hershey Fonts
- Custom single-stroke block font

*Bygget til Lås.dk — låsesmedevirksomhed med Vision Phoenix gravemaskiner*
