"""
nGrave - Flask Server
"""
import json, sqlite3, threading, time, os, signal, logging, secrets
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, render_template, g, Response

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

DB = os.environ.get('NGRAVE_DB', os.path.join(os.path.dirname(__file__), 'ngrave.db'))
PORT = int(os.environ.get('NGRAVE_PORT', '8080'))
HOST = os.environ.get('NGRAVE_HOST', '0.0.0.0')
AUTH_USER = os.environ.get('NGRAVE_AUTH_USER') or ''
AUTH_PASS = os.environ.get('NGRAVE_AUTH_PASS') or ''

# ─── Auth ───────────────────────────────────────────────────────────────
def _check_auth(user, pw):
    if not AUTH_USER or not AUTH_PASS:
        return True  # auth deaktiveret (logget ved opstart)
    return secrets.compare_digest(user or '', AUTH_USER) and secrets.compare_digest(pw or '', AUTH_PASS)

def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not AUTH_USER or not AUTH_PASS:
            return fn(*args, **kwargs)
        a = request.authorization
        if not a or not _check_auth(a.username, a.password):
            return Response('Auth påkrævet', 401, {'WWW-Authenticate': 'Basic realm="nGrave"'})
        return fn(*args, **kwargs)
    return wrapper

# ─── Database ─────────────────────────────────────────────────────────────
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB, timeout=5)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA busy_timeout=5000")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()

def init_db():
    with sqlite3.connect(DB) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        with open(os.path.join(os.path.dirname(__file__), 'schema.sql')) as f:
            db.executescript(f.read())
    migrate_db()
    seed_defaults()
    cleanup_running_on_startup()

def seed_defaults():
    """Indsætter standard-templates hvis de ikke findes.

    Kører EFTER migrate_db, så vi kan referere migrations-kolonner.
    Bruger INSERT OR IGNORE → eksisterende rækker (også custom) bevares.
    """
    default_grid = json.dumps({
        "kolonner": 5, "raekker": 4,
        "slots": [
            {"nr":1,"x":24,"y":11},{"nr":2,"x":74,"y":11},{"nr":3,"x":124,"y":11},{"nr":4,"x":174,"y":11},{"nr":5,"x":224,"y":11},
            {"nr":6,"x":24,"y":77},{"nr":7,"x":74,"y":77},{"nr":8,"x":124,"y":77},{"nr":9,"x":174,"y":77},{"nr":10,"x":224,"y":77},
            {"nr":11,"x":24,"y":143},{"nr":12,"x":74,"y":143},{"nr":13,"x":124,"y":143},{"nr":14,"x":174,"y":143},{"nr":15,"x":224,"y":143},
            {"nr":16,"x":24,"y":208},{"nr":17,"x":74,"y":208},{"nr":18,"x":124,"y":208},{"nr":19,"x":174,"y":208},{"nr":20,"x":224,"y":208}
        ]
    })
    default_linjer = json.dumps([
        {"justering": "center", "hoejde_mm": 12, "font": "block"},
        {"justering": "center", "hoejde_mm": 8,  "font": "block"}
    ])
    with sqlite3.connect(DB) as db:
        db.execute("""
            INSERT OR IGNORE INTO templates (
                id, navn, beskrivelse, noejle_type,
                zone_bredde_mm, zone_hoejde_mm, tekst_hoejde_mm, linje_afstand,
                feed_xy, feed_z, spindle_rpm, z_op_mm, prox_offset_mm,
                markering_x, markering_y, markering_justering,
                system_x, system_y, system_justering,
                loebe_x, loebe_y, loebe_justering,
                maskine_id, grid_json
            ) VALUES (1, 'Ruko Triton 5x4', 'Ruko Triton / D1200', 'RUKO TRITON',
                      18.0, 8.0, 3.5, 1.5,
                      12, 40, 16000, 5.0, 1.5,
                      0.0, 0.0, 'venstre',
                      0.0, 5.0, 'venstre',
                      0.0, 0.0, 'hoejre',
                      NULL, ?)
        """, (default_grid,))
        db.execute("""
            INSERT OR IGNORE INTO skilt_templates (
                id, navn, beskrivelse, skilt_bredde_mm, skilt_hoejde_mm, antal_linjer, linjer_config, maskine_id
            ) VALUES (1, 'Dørskilt Standard', 'Standard dørskilt 200x100mm', 200, 100, 2, ?, NULL)
        """, (default_linjer,))
        db.commit()

def migrate_db():
    """Tilføjer manglende kolonner til eksisterende databaser."""
    migrations = [
        ("maskiner",    "offset_x",           "REAL NOT NULL DEFAULT 0.0"),
        ("maskiner",    "offset_y",           "REAL NOT NULL DEFAULT 0.0"),
        ("maskiner",    "offset_z",           "REAL NOT NULL DEFAULT 0.0"),
        ("maskiner",    "spejl_y",            "INTEGER NOT NULL DEFAULT 0"),
        ("maskiner",    "felt_markering_dx",  "REAL NOT NULL DEFAULT 0.0"),
        ("maskiner",    "felt_markering_dy",  "REAL NOT NULL DEFAULT 0.0"),
        ("maskiner",    "felt_system_dx",     "REAL NOT NULL DEFAULT 0.0"),
        ("maskiner",    "felt_system_dy",     "REAL NOT NULL DEFAULT 0.0"),
        ("maskiner",    "felt_loebe_dx",      "REAL NOT NULL DEFAULT 0.0"),
        ("maskiner",    "felt_loebe_dy",      "REAL NOT NULL DEFAULT 0.0"),
        ("maskiner",    "felt_ekstra_dx",     "REAL NOT NULL DEFAULT 0.0"),
        ("maskiner",    "felt_ekstra_dy",     "REAL NOT NULL DEFAULT 0.0"),
        ("templates",   "markering_justering","TEXT NOT NULL DEFAULT 'venstre'"),
        ("templates",   "system_justering",   "TEXT NOT NULL DEFAULT 'venstre'"),
        ("templates",   "linje_afstand",      "REAL NOT NULL DEFAULT 1.5"),
        ("templates",   "prox_offset_mm",     "REAL NOT NULL DEFAULT 1.5"),
        ("templates",   "font",               "TEXT NOT NULL DEFAULT 'block'"),
        ("templates",   "markering_aktiv",    "INTEGER NOT NULL DEFAULT 1"),
        ("templates",   "markering_navn",     "TEXT NOT NULL DEFAULT 'Markering'"),
        ("templates",   "system_aktiv",       "INTEGER NOT NULL DEFAULT 1"),
        ("templates",   "system_navn",        "TEXT NOT NULL DEFAULT 'System nr'"),
        ("templates",   "loebe_aktiv",        "INTEGER NOT NULL DEFAULT 1"),
        ("templates",   "loebe_navn",         "TEXT NOT NULL DEFAULT 'Løbenr'"),
        ("templates",   "ekstra_aktiv",       "INTEGER NOT NULL DEFAULT 0"),
        ("templates",   "ekstra_navn",        "TEXT NOT NULL DEFAULT 'Ekstra'"),
        ("templates",   "ekstra_x",           "REAL NOT NULL DEFAULT 0.0"),
        ("templates",   "ekstra_y",           "REAL NOT NULL DEFAULT 10.0"),
        ("templates",   "ekstra_justering",   "TEXT NOT NULL DEFAULT 'venstre'"),
        ("templates",   "markering_font",     "TEXT NOT NULL DEFAULT 'block'"),
        ("templates",   "markering_hoejde_mm","REAL NOT NULL DEFAULT 0.0"),
        ("templates",   "system_font",        "TEXT NOT NULL DEFAULT 'block'"),
        ("templates",   "system_hoejde_mm",   "REAL NOT NULL DEFAULT 0.0"),
        ("templates",   "loebe_font",         "TEXT NOT NULL DEFAULT 'block'"),
        ("templates",   "loebe_hoejde_mm",    "REAL NOT NULL DEFAULT 0.0"),
        ("templates",   "ekstra_font",                    "TEXT NOT NULL DEFAULT 'block'"),
        ("templates",   "ekstra_hoejde_mm",               "REAL NOT NULL DEFAULT 0.0"),
        ("templates",   "markering_bogstav_afstand_mm",   "REAL NOT NULL DEFAULT 0.0"),
        ("templates",   "system_bogstav_afstand_mm",      "REAL NOT NULL DEFAULT 0.0"),
        ("templates",   "loebe_bogstav_afstand_mm",       "REAL NOT NULL DEFAULT 0.0"),
        ("templates",   "ekstra_bogstav_afstand_mm",      "REAL NOT NULL DEFAULT 0.0"),
        ("templates",   "loebe_min_laengde",              "INTEGER NOT NULL DEFAULT 0"),
        ("templates",   "loebe_prefix_aktiv",             "INTEGER NOT NULL DEFAULT 0"),
        ("templates",   "loebe_suffix_aktiv",             "INTEGER NOT NULL DEFAULT 0"),
        ("templates",   "markering_position",             "INTEGER NOT NULL DEFAULT 1"),
        ("templates",   "system_position",                "INTEGER NOT NULL DEFAULT 2"),
        ("templates",   "loebe_position",                 "INTEGER NOT NULL DEFAULT 3"),
        ("templates",   "ekstra_position",                "INTEGER NOT NULL DEFAULT 4"),
        ("job_batches", "loebe_prefix",                   "TEXT NOT NULL DEFAULT ''"),
        ("job_batches", "loebe_suffix",                   "TEXT NOT NULL DEFAULT ''"),
        ("job_batches", "ekstra_tekst",       "TEXT NOT NULL DEFAULT ''"),
        ("jobs",        "ekstra_tekst",       "TEXT NOT NULL DEFAULT ''"),
        ("skilt_templates","margin_top_mm",   "REAL"),
        ("skilt_templates","margin_bottom_mm","REAL"),
        ("skilt_templates","linje_afstand_mm","REAL"),
        ("skilt_templates","feed_xy",         "INTEGER"),
        ("skilt_templates","feed_z",          "INTEGER"),
        ("skilt_templates","spindle_rpm",     "INTEGER"),
        ("skilt_templates","z_op_mm",         "REAL"),
        ("skilt_templates","prox_offset_mm",  "REAL"),
        ("skilte_jobs", "margin_top_mm",      "REAL"),
        ("skilte_jobs", "margin_bottom_mm",   "REAL"),
        ("skilte_jobs", "linje_afstand_mm",   "REAL"),
        ("skilte_jobs", "fejl_besked",        "TEXT"),
    ]
    with sqlite3.connect(DB) as db:
        for table, col, typedef in migrations:
            try:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
                app.logger.info("Migration: tilføjede %s.%s", table, col)
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    app.logger.warning("Migration %s.%s fejlede: %s", table, col, e)

def cleanup_running_on_startup():
    """Marker jobs der var 'running' ved restart som fejlede."""
    with sqlite3.connect(DB) as db:
        for tbl in ('jobs', 'job_batches', 'skilte_jobs'):
            try:
                db.execute(f"UPDATE {tbl} SET status='fejl', fejl_besked='Afbrudt ved restart' WHERE status='running'")
            except sqlite3.OperationalError:
                # Tabel har ikke fejl_besked-kolonne (job_batches mangler den)
                db.execute(f"UPDATE {tbl} SET status='fejl' WHERE status='running'")
        db.commit()

# ─── Job Queue Worker ─────────────────────────────────────────────────────────
stop_event = threading.Event()

def queue_worker():
    while not stop_event.is_set():
        try:
            with sqlite3.connect(DB, timeout=5) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA busy_timeout=5000")

                # Find næste pending BATCH — sender alle jobs samlet
                batch = db.execute("""
                    SELECT b.*, m.ip, m.port, m.protokol,
                           m.offset_x, m.offset_y, m.offset_z,
                           t.*
                    FROM job_batches b
                    JOIN maskiner m  ON b.maskine_id = m.id
                    JOIN templates t ON b.template_id = t.id
                    WHERE b.status = 'pending'
                    ORDER BY b.id ASC LIMIT 1
                """).fetchone()

                if batch:
                    batch_id = batch['id']
                    db.execute("UPDATE job_batches SET status='running', startet=? WHERE id=?",
                               (datetime.now(), batch_id))
                    db.commit()

                    jobs = db.execute(
                        "SELECT * FROM jobs WHERE batch_id=? ORDER BY slot_nr ASC",
                        (batch_id,)
                    ).fetchall()

                    tmpl = dict(db.execute(
                        "SELECT * FROM templates WHERE id=?", (batch['template_id'],)
                    ).fetchone())
                    maskine = dict(db.execute(
                        "SELECT * FROM maskiner WHERE id=?", (batch['maskine_id'],)
                    ).fetchone())

                    tmpl['offset_x'] = maskine.get('offset_x', 0.0) or 0.0
                    tmpl['offset_y'] = maskine.get('offset_y', 0.0) or 0.0
                    tmpl['offset_z'] = maskine.get('offset_z', 0.0) or 0.0
                    tmpl['spejl_y']  = bool(maskine.get('spejl_y', 0))
                    for felt in ('markering', 'system', 'loebe', 'ekstra'):
                        tmpl[f'felt_{felt}_dx'] = float(maskine.get(f'felt_{felt}_dx') or 0.0)
                        tmpl[f'felt_{felt}_dy'] = float(maskine.get(f'felt_{felt}_dy') or 0.0)

                    try:
                        if maskine['protokol'] == 'gcode':
                            from workers.gcode_worker import byg_batch, send as send_gcode
                            gcode = byg_batch([dict(j) for j in jobs], tmpl)
                            send_gcode(gcode, maskine['ip'], maskine['port'])
                        else:
                            from workers.cipher_worker import byg_batch as byg_cipher_batch, send as send_cipher
                            cipher = byg_cipher_batch([dict(j) for j in jobs], tmpl)
                            send_cipher(cipher, maskine['ip'], maskine['port'])

                        db.execute("UPDATE jobs SET status='done', udfoert=? WHERE batch_id=?",
                                   (datetime.now(), batch_id))
                        db.execute("UPDATE job_batches SET status='done', faerdig=? WHERE id=?",
                                   (datetime.now(), batch_id))
                    except Exception as e:
                        db.execute("UPDATE job_batches SET status='fejl' WHERE id=?", (batch_id,))
                        app.logger.exception("Batch %s fejl: %s", batch_id, e)
                    db.commit()
                    continue

                # Næste pending skilt. LEFT JOIN skilt_templates så feed/rpm/z_op
                # fra template'en sendes med til worker'en (skilte_jobs har ikke
                # selv disse kolonner). Fri-form skilte uden template -> NULL ->
                # worker falder tilbage til standardkonstanter.
                skilt = db.execute("""
                    SELECT s.*, m.ip, m.port, m.protokol,
                           st.feed_xy, st.feed_z, st.spindle_rpm, st.z_op_mm, st.prox_offset_mm
                    FROM skilte_jobs s
                    JOIN maskiner m ON s.maskine_id = m.id
                    LEFT JOIN skilt_templates st ON s.template_id = st.id
                    WHERE s.status = 'pending'
                    ORDER BY s.id ASC LIMIT 1
                """).fetchone()

                if skilt:
                    skilt_id = skilt['id']
                    db.execute("UPDATE skilte_jobs SET status='running' WHERE id=?", (skilt_id,))
                    db.commit()
                    try:
                        from workers.skilt_worker import byg_skilt
                        from workers.gcode_worker import send as send_gcode
                        gcode = byg_skilt(dict(skilt))
                        send_gcode(gcode, skilt['ip'], skilt['port'])
                        db.execute("UPDATE skilte_jobs SET status='done', faerdig=? WHERE id=?",
                                   (datetime.now(), skilt_id))
                    except Exception as e:
                        db.execute("UPDATE skilte_jobs SET status='fejl', fejl_besked=? WHERE id=?",
                                   (str(e)[:200], skilt_id))
                        app.logger.exception("Skilt %s fejl: %s", skilt_id, e)
                    db.commit()
                    continue

                # Vent op til 1 sekund eller indtil stop_event sættes
                stop_event.wait(timeout=1)

        except Exception as e:
            app.logger.exception("Queue worker fejl: %s", e)
            stop_event.wait(timeout=2)

# ─── API Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

# Maskiner
@app.route('/api/maskiner')
@require_auth
def get_maskiner():
    return jsonify([dict(r) for r in get_db().execute("SELECT * FROM maskiner WHERE aktiv=1")])

@app.route('/api/maskiner', methods=['POST'])
@require_auth
def create_maskine():
    d = request.json or {}
    required = ('navn', 'model', 'ip', 'port', 'protokol')
    missing = [k for k in required if not d.get(k)]
    if missing:
        return jsonify({'ok': False, 'fejl': f'Manglende felter: {", ".join(missing)}'}), 400
    if d['protokol'] not in ('gcode', 'cipher'):
        return jsonify({'ok': False, 'fejl': 'Ugyldig protokol (gcode/cipher)'}), 400
    db = get_db()
    cur = db.execute("""
        INSERT INTO maskiner (navn, model, ip, port, protokol)
        VALUES (?,?,?,?,?)
    """, (d['navn'], d['model'], d['ip'], int(d['port']), d['protokol']))
    db.commit()
    return jsonify({'ok': True, 'id': cur.lastrowid})

@app.route('/api/maskiner/<int:id>', methods=['PUT'])
@require_auth
def update_maskine(id):
    d = request.json or {}
    db = get_db()
    db.execute("""
        UPDATE maskiner SET navn=?, model=?, ip=?, port=?, protokol=? WHERE id=?
    """, (d.get('navn'), d.get('model'), d.get('ip'), int(d.get('port', 0)), d.get('protokol'), id))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/maskiner/<int:id>', methods=['DELETE'])
@require_auth
def delete_maskine(id):
    db = get_db()
    db.execute("UPDATE maskiner SET aktiv=0 WHERE id=?", (id,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/maskiner/<int:id>/kalibrering', methods=['PUT'])
@require_auth
def kalibrering(id):
    d = request.json or {}
    db = get_db()
    db.execute("""UPDATE maskiner SET offset_x=?, offset_y=?, offset_z=?, spejl_y=?,
                    felt_markering_dx=?, felt_markering_dy=?,
                    felt_system_dx=?,   felt_system_dy=?,
                    felt_loebe_dx=?,    felt_loebe_dy=?,
                    felt_ekstra_dx=?,   felt_ekstra_dy=?
               WHERE id=?""",
               (d.get('offset_x', 0), d.get('offset_y', 0), d.get('offset_z', 0), 1 if d.get('spejl_y') else 0,
                d.get('felt_markering_dx', 0), d.get('felt_markering_dy', 0),
                d.get('felt_system_dx', 0),   d.get('felt_system_dy', 0),
                d.get('felt_loebe_dx', 0),    d.get('felt_loebe_dy', 0),
                d.get('felt_ekstra_dx', 0),   d.get('felt_ekstra_dy', 0),
                id))
    db.commit()
    return jsonify({'ok': True})

# Nøgle-Templates
@app.route('/api/templates')
@require_auth
def get_templates():
    rows = get_db().execute("SELECT * FROM templates WHERE aktiv=1")
    return jsonify([dict(r) for r in rows])

@app.route('/api/templates', methods=['POST'])
@require_auth
def create_template():
    d = request.json or {}
    db = get_db()
    try:
        cur = db.execute("""
            INSERT INTO templates (
                navn, beskrivelse, noejle_type, zone_bredde_mm, zone_hoejde_mm,
                tekst_hoejde_mm, linje_afstand, feed_xy, feed_z, spindle_rpm,
                z_op_mm, prox_offset_mm, font,
                markering_aktiv, markering_navn, markering_x, markering_y, markering_justering, markering_font, markering_hoejde_mm,
                system_aktiv, system_navn, system_x, system_y, system_justering, system_font, system_hoejde_mm,
                loebe_aktiv, loebe_navn, loebe_x, loebe_y, loebe_justering, loebe_font, loebe_hoejde_mm,
                ekstra_aktiv, ekstra_navn, ekstra_x, ekstra_y, ekstra_justering, ekstra_font, ekstra_hoejde_mm,
                loebe_min_laengde, loebe_prefix_aktiv, loebe_suffix_aktiv,
                markering_position, system_position, loebe_position, ekstra_position,
                grid_json, maskine_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (d['navn'], d.get('beskrivelse',''), d.get('noejle_type',''),
              d['zone_bredde_mm'], d['zone_hoejde_mm'], d['tekst_hoejde_mm'], d['linje_afstand'],
              d['feed_xy'], d['feed_z'], d['spindle_rpm'], d['z_op_mm'], d['prox_offset_mm'], d.get('font') or 'block',
              int(d.get('markering_aktiv', 1)), d.get('markering_navn','Markering'),
              d.get('markering_x',0), d.get('markering_y',0), d.get('markering_justering','venstre'), d.get('markering_font') or 'block', d.get('markering_hoejde_mm',0) or 0,
              int(d.get('system_aktiv', 1)), d.get('system_navn','System nr'),
              d.get('system_x',0), d.get('system_y',5), d.get('system_justering','venstre'), d.get('system_font') or 'block', d.get('system_hoejde_mm',0) or 0,
              int(d.get('loebe_aktiv', 1)), d.get('loebe_navn','Løbenr'),
              d.get('loebe_x',0), d.get('loebe_y',0), d.get('loebe_justering','hoejre'), d.get('loebe_font') or 'block', d.get('loebe_hoejde_mm',0) or 0,
              int(d.get('ekstra_aktiv', 0)), d.get('ekstra_navn','Ekstra'),
              d.get('ekstra_x',0), d.get('ekstra_y',10), d.get('ekstra_justering','venstre'), d.get('ekstra_font') or 'block', d.get('ekstra_hoejde_mm',0) or 0,
              int(d.get('loebe_min_laengde', 0)), int(d.get('loebe_prefix_aktiv', 0)), int(d.get('loebe_suffix_aktiv', 0)),
              int(d.get('markering_position', 1)), int(d.get('system_position', 2)), int(d.get('loebe_position', 3)), int(d.get('ekstra_position', 4)),
              json.dumps(d.get('grid', {"kolonner":0,"raekker":0,"slots":[]})), d.get('maskine_id')))
        db.commit()
        return jsonify({'ok': True, 'id': cur.lastrowid})
    except Exception as e:
        app.logger.exception("create_template fejl")
        return jsonify({'ok': False, 'fejl': 'Kunne ikke oprette template'}), 500

@app.route('/api/templates/<int:id>', methods=['PUT'])
@require_auth
def update_template(id):
    d = request.json or {}
    db = get_db()
    try:
        db.execute("""
            UPDATE templates SET
                navn=?, beskrivelse=?, noejle_type=?,
                zone_bredde_mm=?, zone_hoejde_mm=?, tekst_hoejde_mm=?, linje_afstand=?,
                feed_xy=?, feed_z=?, spindle_rpm=?, z_op_mm=?, prox_offset_mm=?, font=?,
                markering_aktiv=?, markering_navn=?, markering_x=?, markering_y=?, markering_justering=?, markering_font=?, markering_hoejde_mm=?,
                system_aktiv=?, system_navn=?, system_x=?, system_y=?, system_justering=?, system_font=?, system_hoejde_mm=?,
                loebe_aktiv=?, loebe_navn=?, loebe_x=?, loebe_y=?, loebe_justering=?, loebe_font=?, loebe_hoejde_mm=?,
                ekstra_aktiv=?, ekstra_navn=?, ekstra_x=?, ekstra_y=?, ekstra_justering=?, ekstra_font=?, ekstra_hoejde_mm=?,
                loebe_min_laengde=?, loebe_prefix_aktiv=?, loebe_suffix_aktiv=?,
                markering_position=?, system_position=?, loebe_position=?, ekstra_position=?,
                grid_json=?, maskine_id=?
            WHERE id=?
        """, (d['navn'], d.get('beskrivelse',''), d.get('noejle_type',''),
              d['zone_bredde_mm'], d['zone_hoejde_mm'], d['tekst_hoejde_mm'], d['linje_afstand'],
              d['feed_xy'], d['feed_z'], d['spindle_rpm'], d['z_op_mm'], d['prox_offset_mm'], d.get('font') or 'block',
              int(d.get('markering_aktiv', 1)), d.get('markering_navn','Markering'),
              d.get('markering_x',0), d.get('markering_y',0), d.get('markering_justering','venstre'), d.get('markering_font') or 'block', d.get('markering_hoejde_mm',0) or 0,
              int(d.get('system_aktiv', 1)), d.get('system_navn','System nr'),
              d.get('system_x',0), d.get('system_y',5), d.get('system_justering','venstre'), d.get('system_font') or 'block', d.get('system_hoejde_mm',0) or 0,
              int(d.get('loebe_aktiv', 1)), d.get('loebe_navn','Løbenr'),
              d.get('loebe_x',0), d.get('loebe_y',0), d.get('loebe_justering','hoejre'), d.get('loebe_font') or 'block', d.get('loebe_hoejde_mm',0) or 0,
              int(d.get('ekstra_aktiv', 0)), d.get('ekstra_navn','Ekstra'),
              d.get('ekstra_x',0), d.get('ekstra_y',10), d.get('ekstra_justering','venstre'), d.get('ekstra_font') or 'block', d.get('ekstra_hoejde_mm',0) or 0,
              int(d.get('loebe_min_laengde', 0)), int(d.get('loebe_prefix_aktiv', 0)), int(d.get('loebe_suffix_aktiv', 0)),
              int(d.get('markering_position', 1)), int(d.get('system_position', 2)), int(d.get('loebe_position', 3)), int(d.get('ekstra_position', 4)),
              json.dumps(d.get('grid', {"kolonner":0,"raekker":0,"slots":[]})),
              d.get('maskine_id'), id))
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        app.logger.exception("update_template fejl")
        return jsonify({'ok': False, 'fejl': 'Kunne ikke opdatere template'}), 500

@app.route('/api/templates/<int:id>', methods=['DELETE'])
@require_auth
def delete_template(id):
    db = get_db()
    in_use = db.execute("SELECT COUNT(*) FROM job_batches WHERE template_id=?", (id,)).fetchone()[0]
    if in_use > 0:
        db.execute("UPDATE templates SET aktiv=0 WHERE id=?", (id,))
    else:
        db.execute("DELETE FROM templates WHERE id=?", (id,))
    db.commit()
    return jsonify({'ok': True})

# Skilt-Templates
@app.route('/api/skilt-templates')
@require_auth
def get_skilt_templates():
    rows = get_db().execute("SELECT * FROM skilt_templates WHERE aktiv=1")
    return jsonify([dict(r) for r in rows])

@app.route('/api/skilt-templates', methods=['POST'])
@require_auth
def create_skilt_template():
    d = request.json or {}
    db = get_db()
    cur = db.execute("""
        INSERT INTO skilt_templates (
            navn, beskrivelse, skilt_bredde_mm, skilt_hoejde_mm, antal_linjer,
            linjer_config, margin_top_mm, margin_bottom_mm, linje_afstand_mm, maskine_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (d['navn'], d.get('beskrivelse',''),
          d['skilt_bredde_mm'], d['skilt_hoejde_mm'], d['antal_linjer'],
          json.dumps(d['linjer_config']),
          d.get('margin_top_mm'), d.get('margin_bottom_mm'), d.get('linje_afstand_mm'),
          d.get('maskine_id')))
    db.commit()
    return jsonify({'ok': True, 'id': cur.lastrowid})

@app.route('/api/skilt-templates/<int:id>', methods=['PUT'])
@require_auth
def update_skilt_template(id):
    d = request.json or {}
    db = get_db()
    db.execute("""
        UPDATE skilt_templates SET
            navn=?, beskrivelse=?, skilt_bredde_mm=?, skilt_hoejde_mm=?,
            antal_linjer=?, linjer_config=?,
            margin_top_mm=?, margin_bottom_mm=?, linje_afstand_mm=?
        WHERE id=?
    """, (d['navn'], d.get('beskrivelse',''),
          d['skilt_bredde_mm'], d['skilt_hoejde_mm'], d['antal_linjer'],
          json.dumps(d['linjer_config']),
          d.get('margin_top_mm'), d.get('margin_bottom_mm'), d.get('linje_afstand_mm'), id))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/skilt-templates/<int:id>', methods=['DELETE'])
@require_auth
def delete_skilt_template(id):
    db = get_db()
    db.execute("UPDATE skilt_templates SET aktiv=0 WHERE id=?", (id,))
    db.commit()
    return jsonify({'ok': True})

# Maskine test-kørsel
@app.route('/api/maskiner/<int:id>/test', methods=['POST'])
@require_auth
def test_maskine(id):
    db = get_db()
    maskine = db.execute("SELECT * FROM maskiner WHERE id=?", (id,)).fetchone()
    if not maskine:
        return jsonify({'ok': False, 'fejl': 'Maskine ikke fundet'}), 404

    try:
        if maskine['protokol'] == 'cipher':
            # CIPHER: kør til 0,0 (offsets håndteres ikke her — S3 forventer steps,
            # ikke mm, og test-pos skal være maskinens 0,0)
            from workers.cipher_worker import send as send_cipher
            send_cipher("IN;ZD0;PA0,0;|", maskine['ip'], maskine['port'])
        else:
            # G-code: kalibreret 0,0 med Z oppe, ingen spindle
            MM = 1 / 25.4
            ox = round((maskine['offset_x'] or 0) * MM, 4)
            oy = round(-(maskine['offset_y'] or 0) * MM, 4)
            gcode = "\n".join([
                "M24",
                "G28 Z0",
                "G20",
                "G90",
                f"G0 X{ox} Y{oy}",
                "M30"
            ]) + "\n"
            from workers.gcode_worker import send as send_gcode
            send_gcode(gcode, maskine['ip'], maskine['port'])
        return jsonify({'ok': True})
    except Exception as e:
        app.logger.exception("test_maskine fejl")
        return jsonify({'ok': False, 'fejl': 'Kunne ikke kontakte maskinen'}), 502

# Batches (nøgle-jobs)
@app.route('/api/batches')
@require_auth
def get_batches():
    rows = get_db().execute("""
        SELECT b.*, t.navn as template_navn, m.navn as maskine_navn
        FROM job_batches b
        JOIN templates t ON b.template_id = t.id
        JOIN maskiner m ON b.maskine_id = m.id
        ORDER BY b.id DESC
    """)
    return jsonify([dict(r) for r in rows])

@app.route('/api/batches', methods=['POST'])
@require_auth
def create_batch():
    d = request.json or {}
    db = get_db()

    tmpl = db.execute("SELECT * FROM templates WHERE id=?", (d['template_id'],)).fetchone()
    if not tmpl:
        return jsonify({'ok': False, 'fejl': 'Template findes ikke'}), 404

    grid = json.loads(tmpl['grid_json'])
    slots = grid.get('slots', [])
    if not slots:
        return jsonify({'ok': False, 'fejl': 'Template har ingen slots'}), 400

    type_felt    = d.get('type_felt', '') if tmpl['markering_aktiv'] else ''
    system_nr    = d.get('system_nr', '') if tmpl['system_aktiv'] else ''
    ekstra_tekst = d.get('ekstra_tekst', '') if tmpl['ekstra_aktiv'] else ''
    loebe_aktiv  = bool(tmpl['loebe_aktiv'])
    loebe_prefix = d.get('loebe_prefix', '').strip() if tmpl['loebe_prefix_aktiv'] else ''
    loebe_suffix = d.get('loebe_suffix', '').strip() if tmpl['loebe_suffix_aktiv'] else ''
    loebe_min    = int(tmpl['loebe_min_laengde'] or 0)

    if loebe_aktiv:
        fra = int(d.get('loebe_fra', 1))
        til = int(d.get('loebe_til', 1))
    else:
        fra = 1
        til = int(d.get('antal', 1))

    antal = til - fra + 1
    start_slot = max(1, int(d.get('start_slot', 1))) - 1
    plade_size = len(slots)

    if antal <= 0:
        return jsonify({'ok': False, 'fejl': 'Ugyldigt antal/løbenummer-interval'}), 400
    if start_slot >= plade_size:
        return jsonify({'ok': False, 'fejl': f'Start slot {start_slot+1} er større end antal slots ({plade_size})'}), 400

    foerste_batch_size = plade_size - start_slot
    if antal <= foerste_batch_size:
        batches = 1
    else:
        batches = 1 + ((antal - foerste_batch_size) + plade_size - 1) // plade_size

    loebe_cursor = fra
    for b_idx in range(batches):
        status = 'pending' if b_idx == 0 else 'on-hold'
        slot_start = start_slot if b_idx == 0 else 0
        slots_i_batch = slots[slot_start:]

        batch_end = min(loebe_cursor + len(slots_i_batch) - 1, til)
        navn = d.get('navn') or f"{type_felt or system_nr or ekstra_tekst or 'Batch'}_{loebe_cursor}-{batch_end}"

        cur = db.execute("""
            INSERT INTO job_batches (navn, template_id, maskine_id, system_nr, type_felt, ekstra_tekst, loebe_fra, loebe_til, loebe_prefix, loebe_suffix, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (navn, d['template_id'], d['maskine_id'], system_nr, type_felt, ekstra_tekst, loebe_cursor, batch_end, loebe_prefix, loebe_suffix, status))
        batch_id = cur.lastrowid

        for i, slot in enumerate(slots_i_batch):
            loebe = loebe_cursor + i
            if loebe > til:
                break
            loebe_num = str(loebe).zfill(loebe_min) if loebe_min > 0 else str(loebe)
            loebe_str = f"{loebe_prefix}{loebe_num}{loebe_suffix}" if loebe_aktiv else ''
            db.execute("""
                INSERT INTO jobs (batch_id, slot_nr, slot_x_mm, slot_y_mm, type_felt, loebe_nr, system_nr, ekstra_tekst)
                VALUES (?,?,?,?,?,?,?,?)
            """, (batch_id, slot['nr'], slot['x'], slot['y'], type_felt, loebe_str, system_nr, ekstra_tekst))

        loebe_cursor = batch_end + 1

    db.commit()
    return jsonify({'ok': True, 'batches': batches, 'jobs': antal, 'plade_size': plade_size, 'start_slot': start_slot+1})

@app.route('/api/batches/<int:id>/frigiv', methods=['POST'])
@require_auth
def frigiv_batch(id):
    db = get_db()
    db.execute("UPDATE job_batches SET status='pending' WHERE id=?", (id,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/batches/<int:id>/annuller', methods=['POST'])
@require_auth
def annuller_batch(id):
    db = get_db()
    db.execute("DELETE FROM jobs WHERE batch_id=?", (id,))
    db.execute("DELETE FROM job_batches WHERE id=?", (id,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/jobkoe/annuller-alle', methods=['POST'])
@require_auth
def annuller_alle_batches():
    db = get_db()
    batches = db.execute("SELECT id FROM job_batches WHERE status IN ('pending','on-hold')").fetchall()
    for b in batches:
        db.execute("DELETE FROM jobs WHERE batch_id=?", (b['id'],))
    cur = db.execute("DELETE FROM job_batches WHERE status IN ('pending','on-hold')")
    db.commit()
    return jsonify({'ok': True, 'annulleret': cur.rowcount})

@app.route('/api/jobkoe/ryd-op', methods=['POST'])
@require_auth
def ryd_op_jobkoe():
    """Slet alle færdige/fejlede jobs fra jobkøen."""
    d = request.json or {}
    db = get_db()
    slettet = 0
    if d.get('type') == 'noegler':
        batches = db.execute("SELECT id FROM job_batches WHERE status IN ('done','fejl')").fetchall()
        for b in batches:
            db.execute("DELETE FROM jobs WHERE batch_id=?", (b['id'],))
        cur = db.execute("DELETE FROM job_batches WHERE status IN ('done','fejl')")
        slettet = cur.rowcount
    elif d.get('type') == 'skilte':
        cur = db.execute("DELETE FROM skilte_jobs WHERE status IN ('done','fejl')")
        slettet = cur.rowcount
    db.commit()
    return jsonify({'ok': True, 'slettet': slettet})

# Skilte
@app.route('/api/skilte')
@require_auth
def get_skilte():
    rows = get_db().execute("""
        SELECT s.*, m.navn as maskine_navn,
               st.navn as template_navn
        FROM skilte_jobs s
        JOIN maskiner m ON s.maskine_id = m.id
        LEFT JOIN skilt_templates st ON s.template_id = st.id
        ORDER BY s.id DESC
    """)
    return jsonify([dict(r) for r in rows])

@app.route('/api/skilte', methods=['POST'])
@require_auth
def create_skilt():
    d = request.json or {}
    db = get_db()

    navn = d.get('navn') or f"Skilt_{d['skilt_bredde_mm']}x{d['skilt_hoejde_mm']}"

    cur = db.execute("""
        INSERT INTO skilte_jobs (navn, maskine_id, template_id, skilt_bredde_mm, skilt_hoejde_mm, linjer_json, margin_top_mm, margin_bottom_mm, linje_afstand_mm)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (navn, d['maskine_id'], d.get('template_id'), d['skilt_bredde_mm'], d['skilt_hoejde_mm'],
          json.dumps(d['linjer']), d.get('margin_top_mm'), d.get('margin_bottom_mm'), d.get('linje_afstand_mm')))
    db.commit()
    return jsonify({'ok': True, 'id': cur.lastrowid})

@app.route('/api/skilte/<int:id>/annuller', methods=['POST'])
@require_auth
def annuller_skilt(id):
    db = get_db()
    db.execute("DELETE FROM skilte_jobs WHERE id=?", (id,))
    db.commit()
    return jsonify({'ok': True})

# Status
@app.route('/api/status')
@require_auth
def get_status():
    db = get_db()
    pending = db.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0]
    running = db.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0]
    return jsonify({'pending': pending, 'running': running})

# Fonts
@app.route('/api/fonts')
@require_auth
def get_fonts():
    from workers.font_manager import FONTS
    return jsonify(FONTS)

# System-diagnostik: seneste linjer af auto-opdaterings-loggen + kørende version.
# Gør det muligt at se hvorfor en opdatering evt. fejlede — også fra mobil.
@app.route('/api/systeminfo')
@require_auth
def get_systeminfo():
    import subprocess
    info = {'version': None, 'update_log': []}
    try:
        info['version'] = subprocess.run(
            ['git', 'describe', '--tags', '--always'],
            cwd=os.path.dirname(__file__), capture_output=True, text=True, timeout=5
        ).stdout.strip() or None
    except Exception:
        pass
    log_path = os.environ.get('NGRAVE_UPDATE_LOG', '/var/log/ngrave-update.log')
    try:
        with open(log_path, encoding='utf-8', errors='replace') as f:
            info['update_log'] = f.read().splitlines()[-60:]
    except Exception as e:
        info['update_log'] = [f'(kunne ikke læse {log_path}: {e})']
    return jsonify(info)

# ─── Startup ───────────────────────────────────────────────────────────────────
def _handle_signal(signum, frame):
    # Sæt stop-flaget OG afslut processen. Hvis vi kun satte flaget (uden at
    # afslutte), ville en custom SIGTERM-handler undertrykke Pythons default-
    # terminering, og `systemctl stop ngrave` ville hænge indtil SIGKILL.
    app.logger.info("Modtog signal %s — lukker ned", signum)
    stop_event.set()
    raise SystemExit(0)

def _start_port80_redirector():
    """Tiny HTTP-server på :80 der 302-redirecter alle requests til :PORT.

    Best-effort: hvis port 80 ikke kan bindes (manglende privilegier, port
    optaget, allerede vores main-server) → log og fortsæt. Springes over hvis
    PORT==80 (for at undgå loop).

    Aktiveres når NGRAVE_REDIRECT_FROM_80 != '0' (default 'on'). Bevarer den
    forventede UX hvor brugere kan skrive 'http://ngrave.laas.local' uden port.
    """
    if PORT == 80 or os.environ.get('NGRAVE_REDIRECT_FROM_80', '1') == '0':
        return
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    target_port = PORT
    class Redirect(BaseHTTPRequestHandler):
        def _redirect(self):
            host = (self.headers.get('Host') or 'localhost').split(':')[0]
            self.send_response(302)
            self.send_header('Location', f'http://{host}:{target_port}{self.path}')
            self.send_header('Content-Length', '0')
            self.end_headers()
        do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = do_PATCH = _redirect
        def log_message(self, *a, **kw): pass
    try:
        srv = ThreadingHTTPServer(('0.0.0.0', 80), Redirect)
    except OSError as e:
        app.logger.info("Port-80-redirector kunne ikke starte (%s) — springer over", e)
        return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    app.logger.info("Port-80-redirector aktiv → :%d", target_port)

if __name__ == '__main__':
    init_db()
    if not AUTH_USER or not AUTH_PASS:
        app.logger.warning(
            "ADVARSEL: NGRAVE_AUTH_USER/NGRAVE_AUTH_PASS er ikke sat — API er åbent. "
            "Sæt dem i /etc/ngrave/ngrave.env for at aktivere Basic Auth."
        )
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    t = threading.Thread(target=queue_worker, daemon=True)
    t.start()
    _start_port80_redirector()
    app.run(host=HOST, port=PORT, debug=False)
