# Changelog

## v6.2 (Juni 2026)

Skrifttyper + skilt-sikkerhed + menu-opdeling + robust auto-opdatering + port 80 som standard.

### Port 80 som standard
- Standard-porten er nu **80** igen (var midlertidigt 8080 i v6.1). Kan overskrives med `NGRAVE_PORT`.
- Hvis port 80 ikke kan bindes (fx en non-root proces uden `CAP_NET_BIND_SERVICE`, eller porten er optaget) falder servicen **automatisk tilbage til 8080** i stedet for at crashe — og starter en redirect fra 80 hvis muligt. Så maskinen kommer altid op, uanset opsætning.
- Kører man på en anden port end 80, 302-redirecter en lille server på port 80 til den rigtige port (uændret), så `http://ngrave.laas.local` uden port stadig virker.

### Robust auto-opdatering (service døde efter opdatering)
- Servicen kunne blive liggende nede efter en opdatering, indtil maskinen blev genstartet. Årsag: rammer systemd's start-rate-limit → `failed`-tilstand som først ryddes ved reboot.
- Update-scriptet kører nu `systemctl reset-failed` før genstart, verificerer at servicen faktisk kom op, prøver igen hvis ikke, og gemmer diagnostik (`systemctl status` + `journalctl`) i opdaterings-loggen ved fejl.
- Ny **System**-sektion under Maskiner viser kørende version + seneste opdaterings-log (`/api/systeminfo`) — så man kan se hvorfor en opdatering evt. fejlede, også fra mobil efter en reboot.
- Sudoers-reglen (nye installs) udvidet til også at tillade `start` og `reset-failed`.

### Menu opdelt i to produktioner
- Nøgler og skilte er to helt forskellige produktioner og har nu hver deres sektion i menuen: **🔑 Nøgler** (Nyt nøgle-job · Nøgle-kø · Nøgle-templates) og **🏷️ Skilte** (Nyt skilt · Skilte-kø · Skilt-templates), adskilt af skillelinjer, med **⚙ Maskiner** som fælles. Jobkøen kan nu åbnes direkte på den rigtige produktion.
- Menuen scroller vandret på mobil.

### Kritisk fejlrettelse: skrifttyper virkede ikke
- Alle ikke-block skrifttyper (Roman, Italic, Script, Gothic, Sans) faldt **stille tilbage til block-fonten** ved gravering. To fejl oven i hinanden i `font_manager.py`: forkert import (`hershey_fonts` i stedet for `HersheyFonts`) + kald til metoder der ikke findes (`load_font`/`get_glyph` i stedet for `load_default_font`/`glyphs_for_text`). SVG-preview'en brugte CSS-webfonts og så derfor korrekt ud, men maskinen skar block på alt.
- Rettet med korrekt import + API. Verificeret at alle skrifttyper nu renderer med rigtig orientering, højde og bredde.

### Flere skrifttyper
- Udvidet fra 13 (hvoraf 12 var i stykker) til **18 fungerende single-stroke skrifttyper**: Block, Sans (simpel/fed), Roman (simpel/normal/fed), Times (normal/fed/kursiv/fed-kursiv), Script/Kursiv (3) og Gotisk/Blackletter (5).
- Gamle font-nøgler i eksisterende templates/skilte (`romans`, `italict`, …) mappes automatisk til nærmeste rigtige skrifttype (bagudkompatibelt — ingen data mistes).
- Nøgle-template og skilt font-dropdowns udfyldes nu dynamisk fra font-listen.

### Dansk tegnsæt i skilte
- Hershey-skrifttyperne indeholder ikke ÆØÅ (de rendrede som blanke huller). De substitueres nu til AE/OE/AA (bevarer versal/minuskel) — samme princip som block-fonten — så danske skilte kan graveres i alle skrifttyper.

### Skilt-sikkerhed (vigtigt før go-live)
- **Bounds-check**: `skilt_worker` validerer nu at ALLE linjer passer inden for skiltets bredde/højde FØR spindlen tændes. Tekst der er for bred (eller manuel X/Y uden for kanten) afviser jobbet med en klar fejlbesked i stedet for at gravere ud over kanten ind i emne-holder/bord.
- Skilte-køen viser nu fejl-beskeden ved fejlede jobs, så operatøren kan se hvorfor.

## v6.1.1 (Juni 2026)

### Hotfix: port-80-redirector

v6.1 ændrede app.py's default-port fra 80 til 8080 (af hensyn til non-root install-modellen, hvor porte < 1024 kræver capability). Det brød eksisterende installs hvis systemd-unit ikke sender `NGRAVE_PORT` env-var — servicen kører fint, bare på 8080 i stedet for 80, og browsere fik `ERR_CONNECTION_FAILED` på den forventede URL.

- Tilføjet `_start_port80_redirector()` der starter en lille `http.server` på port 80 og 302-redirecter alle requests til `:NGRAVE_PORT`. Best-effort: hvis port 80 ikke kan bindes (ingen privilegier, allerede optaget), logges en INFO og servicen fortsætter uden redirector.
- Aktiveres automatisk når `PORT != 80`. Kan slås fra med `NGRAVE_REDIRECT_FROM_80=0`.
- Bevarer den forventede UX hvor brugere kan skrive `http://ngrave.laas.local` uden eksplicit port.

## v6.1 (Maj 2026)

Selv-review fixes oven på v6.0 — fundet ved kritisk gennemgang af v6.0-branchen før merge.

### Sikkerhed
- **Stored XSS i SVG-previews**: tre oversete sinks hvor bruger-strenge blev indsat råt i `innerHTML` — skilt-linjetekst, font-label og felt-navn. Alle wrappet i `esc()`. (v6.0's XSS-fix dækkede kun tabellerne, ikke SVG-renderene.)

### Kritisk regression
- **SIGTERM hængte service-shutdown**: v6.0's nye SIGTERM-handler satte kun `stop_event` uden at afslutte processen, hvilket undertrykte Pythons default-terminering. `systemctl stop ngrave` ville hænge i 90s indtil SIGKILL. Handleren rejser nu `SystemExit(0)` efter at have sat flaget.

### Robusthed
- **Skilt-template feed/rpm-feature virkede ikke**: `skilte_jobs` har ikke feed-kolonner, så worker'en faldt altid tilbage til konstanter selvom v6.0 påstod at templates kunne overskrive dem. `queue_worker` LEFT JOIN'er nu `skilt_templates`. Verificeret end-to-end at en template med rpm=12345 nu giver `M3 S12345` i G-koden.
- `PRAGMA busy_timeout=5000` + `connect(timeout=5)` på get_db og queue_worker → eliminerer spuriøs "database is locked" ved samtidig skrivning.

### Mindre
- `visNyTemplate` nulstiller nu `loebe_min_laengde`, `loebe_prefix_aktiv`, `loebe_suffix_aktiv` og felt-positioner — stale værdier fra sidst redigerede template hænger ikke længere ved i "Ny template"-formularen.
- `MACHINES.md` opdateret med note om at UI er den anbefalede metode (SQL er nu kun et alternativ til scripting/bulk-import).

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
