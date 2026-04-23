-- nGrave Database Schema
-- Ryd maskine-info inden commit til GitHub

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
    aktiv       INTEGER DEFAULT 1,
    oprettet    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- nGrave Database Schema v5

CREATE TABLE IF NOT EXISTS maskiner (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    navn        TEXT NOT NULL,
    model       TEXT NOT NULL,
    ip          TEXT NOT NULL,
    port        INTEGER NOT NULL,
    protokol    TEXT NOT NULL,
    offset_x    REAL NOT NULL DEFAULT 0.0,
    offset_y    REAL NOT NULL DEFAULT 0.0,
    offset_z    REAL NOT NULL DEFAULT 0.0,
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
    markering_aktiv      INTEGER NOT NULL DEFAULT 1,
    markering_navn       TEXT NOT NULL DEFAULT 'Markering',
    markering_x          REAL NOT NULL DEFAULT 0.0,
    markering_y          REAL NOT NULL DEFAULT 0.0,
    markering_justering  TEXT NOT NULL DEFAULT 'venstre',
    markering_font                TEXT NOT NULL DEFAULT 'block',
    markering_hoejde_mm           REAL NOT NULL DEFAULT 0.0,
    markering_bogstav_afstand_mm  REAL NOT NULL DEFAULT 0.0,
    -- Felt 2 (System nr)
    system_aktiv         INTEGER NOT NULL DEFAULT 1,
    system_navn          TEXT NOT NULL DEFAULT 'System nr',
    system_x             REAL NOT NULL DEFAULT 0.0,
    system_y             REAL NOT NULL DEFAULT 5.0,
    system_justering     TEXT NOT NULL DEFAULT 'venstre',
    system_font                   TEXT NOT NULL DEFAULT 'block',
    system_hoejde_mm              REAL NOT NULL DEFAULT 0.0,
    system_bogstav_afstand_mm     REAL NOT NULL DEFAULT 0.0,
    -- Felt 3 (Løbenr - auto-inkrementer)
    loebe_aktiv          INTEGER NOT NULL DEFAULT 1,
    loebe_navn           TEXT NOT NULL DEFAULT 'Løbenr',
    loebe_x              REAL NOT NULL DEFAULT 0.0,
    loebe_y              REAL NOT NULL DEFAULT 0.0,
    loebe_justering      TEXT NOT NULL DEFAULT 'hoejre',
    loebe_font                    TEXT NOT NULL DEFAULT 'block',
    loebe_hoejde_mm               REAL NOT NULL DEFAULT 0.0,
    loebe_bogstav_afstand_mm      REAL NOT NULL DEFAULT 0.0,
    -- Felt 4 (Ekstra)
    ekstra_aktiv         INTEGER NOT NULL DEFAULT 0,
    ekstra_navn          TEXT NOT NULL DEFAULT 'Ekstra',
    ekstra_x             REAL NOT NULL DEFAULT 0.0,
    ekstra_y             REAL NOT NULL DEFAULT 10.0,
    ekstra_justering     TEXT NOT NULL DEFAULT 'venstre',
    ekstra_font                   TEXT NOT NULL DEFAULT 'block',
    ekstra_hoejde_mm              REAL NOT NULL DEFAULT 0.0,
    ekstra_bogstav_afstand_mm     REAL NOT NULL DEFAULT 0.0,
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
    loebe_fra   INTEGER NOT NULL DEFAULT 1,
    loebe_til   INTEGER NOT NULL,
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


INSERT OR IGNORE INTO templates (
    id, navn, beskrivelse, noejle_type,
    zone_bredde_mm, zone_hoejde_mm, tekst_hoejde_mm, linje_afstand,
    feed_xy, feed_z, spindle_rpm, z_op_mm, prox_offset_mm,
    markering_x, markering_y, markering_justering,
    system_x, system_y, system_justering,
    loebe_x, loebe_y, loebe_justering,
    maskine_id, grid_json
) VALUES (
    1, 'Ruko Triton 5x4', 'Ruko Triton / D1200', 'RUKO TRITON',
    18.0, 8.0, 3.5, 1.5,
    12, 40, 16000, 5.0, 1.5,
    0.0, 0.0, 'venstre',
    0.0, 5.0, 'venstre',
    0.0, 0.0, 'hoejre',
    1, '{
    "kolonner": 5, "raekker": 4,
    "slots": [
        {"nr":1,"x":24,"y":11},{"nr":2,"x":74,"y":11},{"nr":3,"x":124,"y":11},{"nr":4,"x":174,"y":11},{"nr":5,"x":224,"y":11},
        {"nr":6,"x":24,"y":77},{"nr":7,"x":74,"y":77},{"nr":8,"x":124,"y":77},{"nr":9,"x":174,"y":77},{"nr":10,"x":224,"y":77},
        {"nr":11,"x":24,"y":143},{"nr":12,"x":74,"y":143},{"nr":13,"x":124,"y":143},{"nr":14,"x":174,"y":143},{"nr":15,"x":224,"y":143},
        {"nr":16,"x":24,"y":208},{"nr":17,"x":74,"y":208},{"nr":18,"x":124,"y":208},{"nr":19,"x":174,"y":208},{"nr":20,"x":224,"y":208}
    ]
}'
);

INSERT OR IGNORE INTO skilt_templates (
    id, navn, beskrivelse, skilt_bredde_mm, skilt_hoejde_mm, antal_linjer, linjer_config, maskine_id
) VALUES (
    1, 'Dørskilt Standard', 'Standard dørskilt 200x100mm', 200, 100, 2, '[
        {"justering": "center", "hoejde_mm": 12, "font": "block"},
        {"justering": "center", "hoejde_mm": 8, "font": "block"}
    ]', 1
);

-- Eksempel maskiner (ret IP og port til din installation)
-- INSERT OR IGNORE INTO maskiner (id, navn, model, ip, port, protokol) VALUES
--     (1, 'Phoenix S5', 'S5', '192.168.1.100', 22000, 'gcode'),
--     (2, 'Phoenix S3', 'S3', '192.168.1.101', 5000, 'cipher');
