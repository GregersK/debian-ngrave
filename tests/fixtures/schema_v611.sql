-- nGrave Database Schema v5

CREATE TABLE IF NOT EXISTS maskiner (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    navn        TEXT NOT NULL,
    model       TEXT NOT NULL,        -- 'S5' eller 'S3'
    ip          TEXT NOT NULL,
    port        INTEGER NOT NULL,
    protokol    TEXT NOT NULL,        -- 'gcode' eller 'cipher'
    offset_x    REAL NOT NULL DEFAULT 0.0,
    offset_y    REAL NOT NULL DEFAULT 0.0,
    offset_z    REAL NOT NULL DEFAULT 0.0,
    spejl_y     INTEGER NOT NULL DEFAULT 0,
    felt_markering_dx REAL NOT NULL DEFAULT 0.0,
    felt_markering_dy REAL NOT NULL DEFAULT 0.0,
    felt_system_dx    REAL NOT NULL DEFAULT 0.0,
    felt_system_dy    REAL NOT NULL DEFAULT 0.0,
    felt_loebe_dx     REAL NOT NULL DEFAULT 0.0,
    felt_loebe_dy     REAL NOT NULL DEFAULT 0.0,
    felt_ekstra_dx    REAL NOT NULL DEFAULT 0.0,
    felt_ekstra_dy    REAL NOT NULL DEFAULT 0.0,
    aktiv       INTEGER DEFAULT 1,
    oprettet    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS templates (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    navn                 TEXT NOT NULL,
    beskrivelse          TEXT,
    noejle_type          TEXT NOT NULL,
    zone_bredde_mm       REAL NOT NULL,
    zone_hoejde_mm       REAL NOT NULL,
    tekst_hoejde_mm      REAL NOT NULL DEFAULT 3.5,
    linje_afstand        REAL NOT NULL DEFAULT 1.5,
    feed_xy              INTEGER NOT NULL DEFAULT 12,
    feed_z               INTEGER NOT NULL DEFAULT 40,
    spindle_rpm          INTEGER NOT NULL DEFAULT 16000,
    z_op_mm              REAL NOT NULL DEFAULT 5.0,
    prox_offset_mm       REAL NOT NULL DEFAULT 1.5,
    font                 TEXT NOT NULL DEFAULT 'block',
    -- Felt 1 (Markering)
    markering_aktiv               INTEGER NOT NULL DEFAULT 1,
    markering_navn                TEXT NOT NULL DEFAULT 'Markering',
    markering_x                   REAL NOT NULL DEFAULT 0.0,
    markering_y                   REAL NOT NULL DEFAULT 0.0,
    markering_justering           TEXT NOT NULL DEFAULT 'venstre',
    markering_font                TEXT NOT NULL DEFAULT 'block',
    markering_hoejde_mm           REAL NOT NULL DEFAULT 0.0,
    markering_bogstav_afstand_mm  REAL NOT NULL DEFAULT 0.0,
    markering_position            INTEGER NOT NULL DEFAULT 1,
    -- Felt 2 (System nr)
    system_aktiv                  INTEGER NOT NULL DEFAULT 1,
    system_navn                   TEXT NOT NULL DEFAULT 'System nr',
    system_x                      REAL NOT NULL DEFAULT 0.0,
    system_y                      REAL NOT NULL DEFAULT 5.0,
    system_justering              TEXT NOT NULL DEFAULT 'venstre',
    system_font                   TEXT NOT NULL DEFAULT 'block',
    system_hoejde_mm              REAL NOT NULL DEFAULT 0.0,
    system_bogstav_afstand_mm     REAL NOT NULL DEFAULT 0.0,
    system_position               INTEGER NOT NULL DEFAULT 2,
    -- Felt 3 (Løbenr - auto-inkrementer)
    loebe_aktiv                   INTEGER NOT NULL DEFAULT 1,
    loebe_navn                    TEXT NOT NULL DEFAULT 'Løbenr',
    loebe_x                       REAL NOT NULL DEFAULT 0.0,
    loebe_y                       REAL NOT NULL DEFAULT 0.0,
    loebe_justering               TEXT NOT NULL DEFAULT 'hoejre',
    loebe_font                    TEXT NOT NULL DEFAULT 'block',
    loebe_hoejde_mm               REAL NOT NULL DEFAULT 0.0,
    loebe_bogstav_afstand_mm      REAL NOT NULL DEFAULT 0.0,
    loebe_min_laengde             INTEGER NOT NULL DEFAULT 0,
    loebe_prefix_aktiv            INTEGER NOT NULL DEFAULT 0,
    loebe_suffix_aktiv            INTEGER NOT NULL DEFAULT 0,
    loebe_position                INTEGER NOT NULL DEFAULT 3,
    -- Felt 4 (Ekstra)
    ekstra_aktiv                  INTEGER NOT NULL DEFAULT 0,
    ekstra_navn                   TEXT NOT NULL DEFAULT 'Ekstra',
    ekstra_x                      REAL NOT NULL DEFAULT 0.0,
    ekstra_y                      REAL NOT NULL DEFAULT 10.0,
    ekstra_justering              TEXT NOT NULL DEFAULT 'venstre',
    ekstra_font                   TEXT NOT NULL DEFAULT 'block',
    ekstra_hoejde_mm              REAL NOT NULL DEFAULT 0.0,
    ekstra_bogstav_afstand_mm     REAL NOT NULL DEFAULT 0.0,
    ekstra_position               INTEGER NOT NULL DEFAULT 4,
    grid_json            TEXT NOT NULL,
    maskine_id           INTEGER REFERENCES maskiner(id),
    aktiv                INTEGER DEFAULT 1,
    oprettet             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS skilt_templates (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    navn             TEXT NOT NULL,
    beskrivelse      TEXT,
    skilt_bredde_mm  REAL NOT NULL,
    skilt_hoejde_mm  REAL NOT NULL,
    antal_linjer     INTEGER NOT NULL DEFAULT 1,
    linjer_config    TEXT NOT NULL,
    margin_top_mm    REAL,
    margin_bottom_mm REAL,
    linje_afstand_mm REAL,
    feed_xy          INTEGER,
    feed_z           INTEGER,
    spindle_rpm      INTEGER,
    z_op_mm          REAL,
    prox_offset_mm   REAL,
    maskine_id       INTEGER REFERENCES maskiner(id),
    aktiv            INTEGER DEFAULT 1,
    oprettet         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_batches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    navn        TEXT NOT NULL,
    template_id INTEGER NOT NULL REFERENCES templates(id),
    maskine_id  INTEGER NOT NULL REFERENCES maskiner(id),
    system_nr   TEXT NOT NULL DEFAULT '',
    type_felt   TEXT NOT NULL DEFAULT '',
    ekstra_tekst TEXT NOT NULL DEFAULT '',
    loebe_fra      INTEGER NOT NULL DEFAULT 1,
    loebe_til      INTEGER NOT NULL,
    loebe_prefix   TEXT NOT NULL DEFAULT '',
    loebe_suffix   TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    oprettet    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    startet     TIMESTAMP,
    faerdig     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id    INTEGER NOT NULL REFERENCES job_batches(id),
    slot_nr     INTEGER NOT NULL,
    slot_x_mm   REAL NOT NULL,
    slot_y_mm   REAL NOT NULL,
    type_felt   TEXT NOT NULL DEFAULT '',
    loebe_nr    TEXT NOT NULL DEFAULT '',
    system_nr   TEXT NOT NULL DEFAULT '',
    ekstra_tekst TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    fejl_besked TEXT,
    oprettet    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    udfoert     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS skilte_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    navn            TEXT NOT NULL,
    maskine_id      INTEGER NOT NULL REFERENCES maskiner(id),
    template_id     INTEGER REFERENCES skilt_templates(id),
    skilt_bredde_mm REAL NOT NULL,
    skilt_hoejde_mm REAL NOT NULL,
    linjer_json     TEXT NOT NULL,
    margin_top_mm   REAL,
    margin_bottom_mm REAL,
    linje_afstand_mm REAL,
    status          TEXT NOT NULL DEFAULT 'pending',
    fejl_besked     TEXT,
    oprettet        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    startet         TIMESTAMP,
    faerdig         TIMESTAMP
);


-- Seed-rows oprettes i app.py:seed_defaults() efter migrate_db, så de
-- kan referere kolonner der er tilføjet via migrations.
