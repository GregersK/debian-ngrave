# Changelog

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
