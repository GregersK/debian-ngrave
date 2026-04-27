# Maskine-konfiguration

Maskiner konfigureres via SQL ved første installation.

## Vision Phoenix S5 (G-code over TCP)

```bash
sqlite3 /opt/ngrave/ngrave.db
```

```sql
INSERT INTO maskiner (navn, model, ip, port, protokol) VALUES
    ('Phoenix S5', 'S5', 'DIN_S5_IP', 22000, 'gcode');
```

## Vision Phoenix S3 (CIPHER CEF over TCP)

S3 understøtter to forbindelsesmetoder — begge bruger CIPHER CEF over TCP:

### Direkte Ethernet (anbefalet)
```sql
INSERT INTO maskiner (navn, model, ip, port, protokol) VALUES
    ('Phoenix S3', 'S3', 'DIN_S3_IP', PORT, 'cipher');
```
Erstat `PORT` med S3'ens Ethernet-lytteport (typisk 3001 — tjek maskinens netværksopsætning).

### Via RUT206 / RUT145 Serial Over IP (alternativ)
```sql
INSERT INTO maskiner (navn, model, ip, port, protokol) VALUES
    ('Phoenix S3', 'S3', 'DIN_RUT206_IP', 5000, 'cipher');
```

## RUT206 / RUT145 Serial Over IP setup (kun ved RS232-forbindelse)

1. Log ind på routerens WebUI
2. Gå til **Services → Serial Utilities → Over IP**
3. Indstil:
   - Mode: **TCP Server**
   - Protocol: **Raw TCP**
   - Port: **5000**
   - Baud rate: **57600**
   - Data bits: 8
   - Parity: Even (2)
   - Stop bits: 1
   - Flow control: None

### DB9 pinout (router → S3)
| DB9 Pin | Signal | S3 forbindelse |
|---------|--------|---------------|
| 2 | RX | TX |
| 3 | TX | RX |
| 5 | GND | GND |

## S3 CIPHER CEF parametre (bekræftet fra maskinkonfiguration)

| Parameter | Værdi |
|-----------|-------|
| Steps per mm (X/Y) | 40 |
| Steps per mm (Z) | 40 |
| Baud rate (RS232) | 57600 |
| Parity | Even |
| Init-streng | `IN;ZD0;` |
| Separator | `;` |
| Koordinat-separator | `,` |
| PA-format | `PA{x},{y}` |

## Kalibrering

1. Gå til **Maskiner** i UI
2. Klik **Kalibrér** på maskinen
3. Sæt offset i mm (+ = højre/frem/dybere)
4. Tryk **▶ Test position** — maskinen kører til (0,0) uden spindle
5. Juster til teksten er korrekt placeret
6. Gem

## Nøgle-templates

1. Gå til **Nøgle-templates → + Ny template**
2. Udfyld Basis-info (feeds, RPM, prox-offset)
3. Gå til **Grid** → Auto-udfyld grid:
   - Mål X/Y for første slot på pladen
   - Mål afstand mellem slots
4. Gå til **Felt-placering** → juster X/Y per felt
5. Gem og test

## Test workflow

1. Opret job med 1 nøgle (Løbenr fra: 1, til: 1)
2. Start med `SPINDLE_RPM = 0` i template for at køre uden gravering
3. Verificer koordinater visuelt
4. Sæt korrekt RPM og test rigtig gravering


## Kalibrering

1. Gå til **Maskiner** i UI
2. Klik **Kalibrér** på maskinen
3. Sæt offset i mm (+ = højre/frem/dybere)
4. Tryk **▶ Test position** — maskinen kører til (0,0) uden spindle
5. Juster til teksten er korrekt placeret
6. Gem

## Nøgle-templates

1. Gå til **Nøgle-templates → + Ny template**
2. Udfyld Basis-info (feeds, RPM, prox-offset)
3. Gå til **Grid** → Auto-udfyld grid:
   - Mål X/Y for første slot på pladen
   - Mål afstand mellem slots
4. Gå til **Felt-placering** → juster X/Y per felt
5. Gem og test

## Test workflow

1. Opret job med 1 nøgle (Løbenr fra: 1, til: 1)
2. Start med `SPINDLE_RPM = 0` i template for at køre uden gravering
3. Verificer koordinater visuelt
4. Sæt korrekt RPM og test rigtig gravering
