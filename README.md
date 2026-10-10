# nGrave

**Gravesystem til alle G-CODE og CIPHER CEF maskiner**

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
- 18 single-stroke skrifttyper: Block (custom, med ÆØÅ), Sans, Roman, Times (normal/fed/kursiv), Script/Kursiv og Gotisk/Blackletter
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
git clone https://github.com/GregersK/debian-ngrave.git
cd debian-ngrave
sudo bash install.sh
```

Installeren:
- Opretter system-bruger `ngrave` (servicen kører ikke som root)
- Genererer et tilfældigt password og gemmer det i `/etc/ngrave/ngrave.env`
- Sætter daglig auto-opdatering der kun kører ved nye release-tags (ikke arbitrære main-commits)

Når den er færdig vises login-credentials i terminalen — gem dem.

Åbn derefter `http://SERVER_IP` i browser og log ind med `ngrave` + det genererede password.

> **Sikkerhed**: nGrave eksponerer adgang til CNC-maskiner. Eksponér det aldrig direkte mod internettet. Hvis du har brug for ekstern adgang, sæt en reverse proxy med TLS (nginx/caddy) foran og overvej VPN.

### Manuel installation

```bash
git clone https://github.com/GregersK/debian-ngrave.git
cd debian-ngrave
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
NGRAVE_AUTH_USER=ngrave NGRAVE_AUTH_PASS=skiftMig NGRAVE_PORT=8080 python app.py
```

---

## Konfiguration

### Maskiner

Tilføjes via UI'en under **Maskiner → + Ny maskine**. Udfyld navn, model, protokol (gcode for S5, cipher for S3), IP og port.

(Tidligere versioner krævede manuelle SQL inserts — det er ikke længere nødvendigt. Se [MACHINES.md](MACHINES.md) hvis du har brug for at scripte bulk-import.)

### Auth & runtime config

Service-config læses fra `/etc/ngrave/ngrave.env`:

```
NGRAVE_DB=/opt/ngrave/ngrave.db
NGRAVE_HOST=0.0.0.0
NGRAVE_PORT=80
NGRAVE_AUTH_USER=ngrave
NGRAVE_AUTH_PASS=<auto-genereret>
```

For at skifte password, rediger filen og kør `sudo systemctl restart ngrave`.

Hvis `NGRAVE_AUTH_USER` eller `NGRAVE_AUTH_PASS` er tomme, kører API'et åbent — der logges en advarsel ved opstart.

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
├── ngrave-update.sh        # Tag-baseret auto-opdatering (stable/beta)
├── workers/
│   ├── block_font.py       # Custom single-stroke font med ÆØÅ
│   ├── font_manager.py     # Font router (block + Hershey fonts)
│   ├── gcode_worker.py     # G-code generator til S5
│   ├── cipher_worker.py    # CIPHER CEF generator til S3
│   ├── forbindelse.py      # Forbindelse, online-probe og status mod maskiner
│   └── skilt_worker.py     # Layout-motor + G-code til skilte (bruges også af preview)
├── templates/
│   └── index.html          # Web UI (HTML)
├── static/
│   ├── ngrave.css          # Designsystem (lyst/mørkt, mobil først)
│   ├── ui.js               # Hjælpere, toasts, modal, navigation, statuslinje
│   ├── ngrave_a.js         # Nøgle-job, plade-visning, køer
│   ├── skilt.js            # Skilt-editor, preview, skrifttype-galleri
│   └── ngrave_b.js         # Templates, maskiner, system, backup
└── tests/                  # Enhedstests (layout-motor + API)
```

### Kør tests

```bash
python3 -m unittest discover -s tests
```

Testene bruger en midlertidig database og rører aldrig en rigtig installations data.

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
SQLite (default `/opt/ngrave/ngrave.db`, kan overskrives med env var `NGRAVE_DB`) med automatisk migration. Nye kolonner tilføjes ved opstart uden at slette eksisterende data. Kører i WAL-mode for samtidig læse/skrive-adgang fra Flask + queue worker.

### Auto-opdatering
`/opt/ngrave/ngrave-update.sh` køres af systemd-timer. Den fetcher tags fra GitHub og opdaterer kun ved en ny release-tag (ikke ved arbitrære main-commits). Service restartes bagefter (med `reset-failed` + verifikation, så den ikke bliver liggende nede).

**Kanaler (staged rollout):** hver maskine vælger kanal i `/etc/ngrave/channel`:
- `stable` (standard) — henter kun endelige releases: `v6.3`, `v6.3.1`, …
- `beta` — henter også pre-releases: `v6.3-beta1`, `v6.3-rc1`, …

```bash
# Sæt en enkelt maskine på beta (til test før flåde-udrulning):
echo beta | sudo tee /etc/ngrave/channel
# Tilbage til stable:
echo stable | sudo tee /etc/ngrave/channel
```
Typisk flow: tag `v6.3-beta1` → kun beta-maskiner opdaterer → test → tag `v6.3` → resten (og beta-maskinerne rykker op til den endelige). Kanal + version vises i **Maskiner → System**.

### Kø og online-kontrol

- **Én arbejdstråd pr. maskine.** En maskine kører sine jobs ét ad gangen (nøgle-batches før skilte, ældste først), men maskiner er uafhængige — en slukket maskine med 30 jobs bremser ikke de andre.
- **Forbindelsesfejl prøves igen, andre fejl gør ikke.** Kan nGrave ikke oprette forbindelse, er *intet sendt*, så det er sikkert at prøve igen (3 forsøg, pause 5 og 20 s). Fejler sendingen *midt i* programmet, ved vi ikke hvor meget maskinen nåede — så gentager nGrave det aldrig automatisk (det kunne gravere to gange); jobbet får status Fejl og en forklaring.
- **Opgivet maskine = hurtig fejl.** Efter tre mislykkede forsøg fejler resten af maskinens ventende jobs med det samme (i 30 s) i stedet for at bruge 25 s hver. Knappen **»Prøv N jobs igen«** i køen sætter dem tilbage, når maskinen er tændt — kun jobs hvor intet blev sendt.
- **Online-status.** Hvert 30. sekund tjekkes det om maskinerne svarer (kun `connect` + luk — der sendes aldrig data). Status vises under **Maskiner**, i statuslinjen (`⚠ 1 maskine svarer ikke`) og i maskinvælgerne. Det blokerer ikke for at sende et job.
- **Maskinen røres ikke mens den graverer.** nGrave ved kun at et program er *sendt*, ikke hvornår maskinen er færdig. Derfor tjekkes en maskine ikke i 15 minutter efter en sending, og **Test-position** kræver en bekræftelse i samme periode.
- Skilte kan kun sendes til G-code-maskiner (S5).

Indstillinger (valgfrie, i `/etc/ngrave/ngrave.env`):

| Variabel | Standard | Betydning |
|----------|----------|-----------|
| `NGRAVE_PROBE_INTERVAL` | `30` | Sekunder mellem online-tjek. `0` slår baggrunds-tjek helt fra |
| `NGRAVE_PROBE_EFTER_SEND` | `900` | Sekunder efter en sending hvor maskinen ikke tjekkes/flyttes |
| `NGRAVE_SEND_FORSOEG` | `3` | Forsøg pr. job når maskinen ikke kan nås |

### Prox-sensor
`G30` bruges til at finde materialets overflade pr. streg. Offset justeres i template (`prox_offset_mm`).

---

## API

| Method | Endpoint | Beskrivelse |
|--------|----------|-------------|
| GET | `/api/maskiner` | Liste alle maskiner |
| PUT | `/api/maskiner/<id>/kalibrering` | Sæt kalibrerings-offset |
| POST | `/api/maskiner/<id>/test` | Kør til 0,0 position (kræver bekræftelse hvis der lige er sendt et program) |
| GET | `/api/maskiner/status` | Online-status + kø-tal pr. maskine (rører ikke maskinerne) |
| POST | `/api/maskiner/<id>/ping` | Tjek nu: opretter og lukker en forbindelse — sender aldrig data |
| GET | `/api/templates` | Liste nøgle-templates |
| POST | `/api/templates` | Opret template |
| PUT | `/api/templates/<id>` | Opdater template |
| DELETE | `/api/templates/<id>` | Slet template |
| GET | `/api/batches` | Jobkø (nøgler) |
| POST | `/api/batches` | Opret batch |
| POST | `/api/batches/<id>/frigiv` | Frigiv on-hold batch |
| POST | `/api/batches/<id>/annuller` | Annuller batch |
| POST | `/api/batches/<id>/gentag` | Sæt fejlet batch tilbage i køen |
| POST | `/api/skilte/<id>/gentag` | Sæt fejlet skilt tilbage i køen |
| POST | `/api/jobkoe/gentag-fejlede` | Sæt alle jobs tilbage der fejlede fordi maskinen ikke kunne nås (intet var sendt) |
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

*Bygget til bla. låsesmedevirksomheder med Vision Phoenix gravemaskiner*
