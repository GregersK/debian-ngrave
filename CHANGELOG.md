# Changelog

## v6.0 (Maj 2026)

### Sikkerhed
- Servicen kører ikke længere som root. Ny system-bruger `ngrave` får `CAP_NET_BIND_SERVICE` så port 80 stadig virker.
- HTTP Basic Auth på alle `/api/*`-endpoints. Credentials autogenereres ved første install og lægges i `/etc/ngrave/ngrave.env`.
- Stored XSS i template-/maskine-navne mv. blokeret via central `esc()`-helper i UI.
- Auto-opdatering fra GitHub er nu **tag-baseret** og kører **dagligt** i stedet for hvert 5. minut fra `main`. Update-scriptet kører som `ngrave`-bruger; restart sker via en sudoers-regel der kun tillader `systemctl restart ngrave`.
- `apt upgrade -y` fjernet fra installer (uventet system-bred sideeffekt).

### Nyt
- **Maskine-CRUD i UI**: opret/rediger/slet maskiner direkte under fanen Maskiner. Manuel `sqlite3` ikke længere nødvendig.
- Test-position-knappen understøtter nu både G-code (S5) og CIPHER (S3) maskiner.
- Skilt-templates kan overskrive feed/feed_z/rpm/z_op_mm/prox_offset_mm i stedet for at bruge globale konstanter.
- DB-sti konfigurerbar via env var `NGRAVE_DB`.

### Robusthed
- SQLite kører nu i WAL-mode → ingen "database is locked"-fejl under last.
- Jobs der var `running` ved restart markeres `fejl` med begrundelse "Afbrudt ved restart" i stedet for at hænge for evigt.
- API'et returnerer korrekte HTTP-statuskoder (4xx/5xx ved fejl, ikke 200).
- Stack traces eksponeres ikke længere til klienter — logges server-side via `app.logger.exception`.
- `migrate_db()` skelner mellem "kolonne findes allerede" (tavst) og rigtige fejl (logges).
- `signal.SIGTERM`/`SIGINT` håndteret så queue worker kan stoppe pænt.

### Rettelser
- `schema.sql` havde en duplikeret `CREATE TABLE maskiner` — fjernet.
- `schema.sql` mangledes mange kolonner som kun blev tilføjet via migration. Fresh installs har nu alle kolonner i CREATE TABLE.
- `gcode_worker.byg_job()` og `cipher_worker.byg_job()` (forældet single-job-kode uden ekstra-felt-support) fjernet.
- Bare `except:` udskiftet med `except Exception:`.
- Lowercase `æ/ø/å` fjernet fra `block_font.CHAR_MAP` (uopnåelig kode efter `tekst.upper()`).

## v5.0 (April 2026)

### Nyt
- Dynamiske felter per nøgle-template (op til 4 med custom navne)
- Per-felt skrifttype og tekststørrelse
- X/Y placering per skilt-linje (manuel eller auto)
- Skilt-template: tilføj/fjern linjer + per-linje størrelse
- Font-visualisering i live preview (approximeret med web fonts)
- Kopi-funktion for nøgle-templates
- Ryd-op knap i jobkø
- Light/Dark mode med browser-hukommelse
- 13 skrifttyper via Hershey Fonts + custom Block font

### Rettelser
- Batch-gravering: hele plade sendes nu som ét G-code program
- Kalibrering: decimaler (f.eks. 3.5mm) gemmes korrekt
- Template gem: null-font fejl rettet
- JavaScript syntaksfejl (ubalancerede klammer) systematisk rettet

## v4.0 (April 2026)

### Nyt
- Maskin-kalibrering (X/Y/Z offset per maskine)
- Test-position knap (kører til 0,0 uden spindle)
- Start-slot valg ved job-oprettelse
- Skiltegravering med live visualisering
- Skilt-templates med margin/linje-afstand
- Ryd-op funktion for jobkø
- Farvetema huskes (light/dark)

## v3.0 (April 2026)

### Nyt
- Dynamisk job-form baseret på aktive template-felter
- On-hold batch workflow
- Auto-udfyld grid (start X/Y + afstand)
- Jobkø opdelt i Nøgle-jobs og Skilte-jobs
- Per-felt visualisering med SVG preview

## v2.0 (April 2026)

### Nyt
- Plader fjernet — grid direkte i templates
- Skilt-gravering (1-10 linjer, font, justering, højde)
- Automatisk DB-migration ved opstart
- Port 80 support

## v1.0 (April 2026)

### Initial release
- Flask-baseret gravesystem
- G-code generering til Vision Phoenix S5
- CIPHER CEF generering til Vision Phoenix S3
- Custom single-stroke block font med ÆØÅ
- Prox-sensor integration
- Batch-opdeling med on-hold workflow
- Web UI med dark mode
