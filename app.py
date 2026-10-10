"""
nGrave - Flask Server
"""
import json, sqlite3, threading, time, os, signal, logging, secrets
from contextlib import closing
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, render_template, g, Response
from workers import forbindelse
from workers.forbindelse import ForbindelsesFejl

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

DB = os.environ.get('NGRAVE_DB', os.path.join(os.path.dirname(__file__), 'ngrave.db'))
PORT = int(os.environ.get('NGRAVE_PORT', '80'))
FALLBACK_PORT = 8080  # bruges kun hvis PORT ikke kan bindes (fx non-root uden CAP_NET_BIND_SERVICE)
MAX_EMNER_PR_ORDRE = 5000   # sikkerhedsgrænse mod tastefejl (fx 100000 i stedet for 100)
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
        ("job_batches", "fejl_besked",                    "TEXT"),
        ("job_batches", "fejl_kode",                      "TEXT"),
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
        ("skilte_jobs", "fejl_kode",          "TEXT"),
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

def _kort_fejl(e):
    """Menneskelig fejlbesked til jobkøen (i stedet for rå Python-fejl)."""
    if isinstance(e, (ValueError, ForbindelsesFejl)):
        return str(e)[:300]
    if isinstance(e, TimeoutError):
        return "Maskinen holdt op med at svare midt i sendingen (timeout) — tjek maskinen før jobbet gentages."
    if isinstance(e, ConnectionError):
        return "Forbindelsen til maskinen blev afbrudt under sendingen — tjek maskinen før jobbet gentages."
    if isinstance(e, OSError):
        return f"Netværksfejl mod maskinen: {e.strerror or e}"[:300]
    return f"Uventet fejl ({type(e).__name__}) — se server-log"

def _fejl_kode(e):
    """'forbindelse' = intet blev sendt (sikkert at prøve igen). Alt andet må
    ikke gentages automatisk — maskinen kan allerede have modtaget programmet."""
    if isinstance(e, ForbindelsesFejl):
        return 'forbindelse'
    return 'data' if isinstance(e, ValueError) else 'sending'

# ─── Job Queue: én arbejdstråd pr. maskine ────────────────────────────────────
# En maskine behandles serielt (den kan kun tage ét program ad gangen), men
# maskiner er uafhængige: en slukket maskine med 30 jobs bremser ikke de andre.
stop_event = threading.Event()

def _env_tal(navn, standard):
    try:
        return float(os.environ.get(navn, standard))
    except ValueError:
        return float(standard)

SEND_FORSOEG = max(1, int(_env_tal('NGRAVE_SEND_FORSOEG', 3)))   # forsøg ved forbindelsesfejl
SEND_PAUSE = (5.0, 20.0)       # sekunder før forsøg 2 og 3
NEDE_VINDUE = 30.0             # efter opgivet forbindelse fejler nye jobs straks i så mange sekunder
PROBE_INTERVAL = _env_tal('NGRAVE_PROBE_INTERVAL', 30)           # 0 = slå baggrunds-tjek fra
PROBE_EFTER_SEND = _env_tal('NGRAVE_PROBE_EFTER_SEND', 900)      # sek: rør ikke maskinen så længe efter en sending (den graverer formentlig stadig)

_maskine_traade = {}
_maskine_traade_laas = threading.Lock()
_nede_til = {}                 # maskine_id -> (til_tidspunkt, ForbindelsesFejl)

def _db():
    db = sqlite3.connect(DB, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=5000")
    return db

def queue_worker():
    """Dispatcher: sørger for at hver maskine med ventende jobs har sin egen tråd."""
    while not stop_event.is_set():
        try:
            with closing(_db()) as db:
                mids = [r[0] for r in db.execute(
                    "SELECT maskine_id FROM job_batches WHERE status='pending' "
                    "UNION SELECT maskine_id FROM skilte_jobs WHERE status='pending'")]
            for mid in mids:
                _start_maskine_traad(mid)
        except Exception as e:
            app.logger.exception("Queue worker fejl: %s", e)
            stop_event.wait(timeout=2)
        stop_event.wait(timeout=1)

def _start_maskine_traad(mid):
    with _maskine_traade_laas:
        t = _maskine_traade.get(mid)
        if t and t.is_alive():
            return
        t = threading.Thread(target=_maskine_arbejder, args=(mid,), name=f'maskine-{mid}', daemon=True)
        _maskine_traade[mid] = t
        t.start()

def _maskine_arbejder(mid):
    """Kører maskinens ventende jobs ét ad gangen (nøgle-batches før skilte)."""
    try:
        while not stop_event.is_set():
            with closing(_db()) as db:
                if not (_koer_naeste_batch(db, mid) or _koer_naeste_skilt(db, mid)):
                    return
    except Exception as e:
        app.logger.exception("Maskine-tråd %s fejlede: %s", mid, e)

def _send_med_retry(mid, send_fn, payload, ip, port, saet_note):
    """Sender et program. Kun forbindelsesfejl (intet sendt) prøves igen — med
    pause, så en maskine der lige genstarter får en chance."""
    nede = _nede_til.get(mid)
    if nede and time.time() < nede[0]:
        raise ForbindelsesFejl(nede[1].aarsag, nede[1].besked)   # fail-fast: maskinen er lige blevet opgivet
    for forsoeg in range(1, SEND_FORSOEG + 1):
        with forbindelse.send_laas(mid):
            try:
                send_fn(payload, ip, port)
            except ForbindelsesFejl as e:
                forbindelse.noter(mid, 'afviser' if e.aarsag == 'afvist' else 'offline', 'job', fejl=e.besked)
                if forsoeg >= SEND_FORSOEG:
                    _nede_til[mid] = (time.time() + NEDE_VINDUE, e)
                    raise
                pause = SEND_PAUSE[min(forsoeg - 1, len(SEND_PAUSE) - 1)]
                fejl = e
            except Exception:
                # Forbindelsen lykkedes, men sendingen fejlede undervejs → data kan være modtaget.
                forbindelse.noter(mid, 'online', 'job', sendt=True)
                raise
            else:
                forbindelse.noter(mid, 'online', 'job', sendt=True)
                _nede_til.pop(mid, None)
                return
        saet_note(f"Ingen forbindelse til maskinen — prøver igen om {pause:g} s (forsøg {forsoeg + 1} af {SEND_FORSOEG})")
        if stop_event.wait(pause):
            raise ValueError("Afbrudt ved nedlukning")

def _koer_naeste_batch(db, mid):
    """Sender maskinens ældste ventende nøgle-batch. Returnerer True hvis der var en."""
    row = db.execute("SELECT id FROM job_batches WHERE status='pending' AND maskine_id=? "
                     "ORDER BY id ASC LIMIT 1", (mid,)).fetchone()
    if not row:
        return False
    batch_id = row['id']
    cur = db.execute("UPDATE job_batches SET status='running', startet=?, fejl_besked=NULL, fejl_kode=NULL "
                     "WHERE id=? AND status='pending'", (datetime.now(), batch_id))
    db.commit()
    if cur.rowcount != 1:
        return True      # en anden tråd/annullering nåede den først
    def note(tekst):
        db.execute("UPDATE job_batches SET fejl_besked=? WHERE id=?", (tekst, batch_id))
        db.commit()
    try:
        batch = db.execute("SELECT * FROM job_batches WHERE id=?", (batch_id,)).fetchone()
        tmpl_row = db.execute("SELECT * FROM templates WHERE id=?", (batch['template_id'],)).fetchone()
        mask_row = db.execute("SELECT * FROM maskiner WHERE id=?", (mid,)).fetchone()
        if not tmpl_row:
            raise ValueError("Templaten til dette job findes ikke længere")
        if not mask_row:
            raise ValueError("Maskinen til dette job findes ikke længere")
        tmpl, maskine = dict(tmpl_row), dict(mask_row)
        jobs = [dict(j) for j in db.execute("SELECT * FROM jobs WHERE batch_id=? ORDER BY slot_nr ASC", (batch_id,))]

        tmpl['offset_x'] = maskine.get('offset_x', 0.0) or 0.0
        tmpl['offset_y'] = maskine.get('offset_y', 0.0) or 0.0
        tmpl['offset_z'] = maskine.get('offset_z', 0.0) or 0.0
        tmpl['spejl_y']  = bool(maskine.get('spejl_y', 0))
        for felt in ('markering', 'system', 'loebe', 'ekstra'):
            tmpl[f'felt_{felt}_dx'] = float(maskine.get(f'felt_{felt}_dx') or 0.0)
            tmpl[f'felt_{felt}_dy'] = float(maskine.get(f'felt_{felt}_dy') or 0.0)

        if maskine['protokol'] == 'gcode':
            from workers.gcode_worker import byg_batch, send
        else:
            from workers.cipher_worker import byg_batch, send
        program = byg_batch(jobs, tmpl)
        _send_med_retry(mid, send, program, maskine['ip'], maskine['port'], note)

        db.execute("UPDATE jobs SET status='done', udfoert=? WHERE batch_id=?", (datetime.now(), batch_id))
        db.execute("UPDATE job_batches SET status='done', faerdig=?, fejl_besked=NULL WHERE id=?",
                   (datetime.now(), batch_id))
    except Exception as e:
        db.execute("UPDATE job_batches SET status='fejl', fejl_besked=?, fejl_kode=? WHERE id=?",
                   (_kort_fejl(e), _fejl_kode(e), batch_id))
        if isinstance(e, (ForbindelsesFejl, ValueError)):
            app.logger.warning("Batch %s: %s", batch_id, e)       # forventet fejl — ingen stack trace
        else:
            app.logger.exception("Batch %s fejl: %s", batch_id, e)
    db.commit()
    return True

def _koer_naeste_skilt(db, mid):
    """Sender maskinens ældste ventende skilt. Returnerer True hvis der var et."""
    # LEFT JOIN skilt_templates så feed/rpm/z_op fra template'en sendes med til
    # worker'en. Fri-form skilte uden template -> NULL -> standardkonstanter.
    skilt = db.execute("""
        SELECT s.*, m.ip, m.port, m.protokol,
               st.feed_xy, st.feed_z, st.spindle_rpm, st.z_op_mm, st.prox_offset_mm
        FROM skilte_jobs s
        JOIN maskiner m ON s.maskine_id = m.id
        LEFT JOIN skilt_templates st ON s.template_id = st.id
        WHERE s.status = 'pending' AND s.maskine_id = ?
        ORDER BY s.id ASC LIMIT 1
    """, (mid,)).fetchone()
    if not skilt:
        return False
    skilt_id = skilt['id']
    cur = db.execute("UPDATE skilte_jobs SET status='running', startet=?, fejl_besked=NULL, fejl_kode=NULL "
                     "WHERE id=? AND status='pending'", (datetime.now(), skilt_id))
    db.commit()
    if cur.rowcount != 1:
        return True
    def note(tekst):
        db.execute("UPDATE skilte_jobs SET fejl_besked=? WHERE id=?", (tekst, skilt_id))
        db.commit()
    try:
        if skilt['protokol'] != 'gcode':
            raise ValueError("Skilte kan kun graveres på maskiner med G-code (S5) — ikke CIPHER (S3)")
        from workers.skilt_worker import byg_skilt
        from workers.gcode_worker import send
        gcode = byg_skilt(dict(skilt))
        _send_med_retry(mid, send, gcode, skilt['ip'], skilt['port'], note)
        db.execute("UPDATE skilte_jobs SET status='done', faerdig=?, fejl_besked=NULL WHERE id=?",
                   (datetime.now(), skilt_id))
    except Exception as e:
        db.execute("UPDATE skilte_jobs SET status='fejl', fejl_besked=?, fejl_kode=? WHERE id=?",
                   (_kort_fejl(e), _fejl_kode(e), skilt_id))
        if isinstance(e, (ForbindelsesFejl, ValueError)):
            app.logger.warning("Skilt %s: %s", skilt_id, e)       # forventet fejl — ingen stack trace
        else:
            app.logger.exception("Skilt %s fejl: %s", skilt_id, e)
    db.commit()
    return True

# ─── Online-kontrol ───────────────────────────────────────────────────────────
def _probe_alle(rolig_sek):
    with closing(_db()) as db:
        maskiner = db.execute("SELECT id, ip, port FROM maskiner WHERE aktiv=1").fetchall()
    aktive = {m['id'] for m in maskiner}
    for mid in forbindelse.kendte_ids():
        if mid not in aktive:
            forbindelse.glem(mid)
    for m in maskiner:
        if stop_event.is_set():
            return
        r = forbindelse.probe_maskine(m['id'], m['ip'], m['port'], kun_hvis_rolig_sek=rolig_sek)
        if r and r['status'] == 'online':
            _nede_til.pop(m['id'], None)

def probe_loop():
    """Tjekker jævnligt om maskinerne svarer (kun connect+luk — der sendes aldrig data,
    og en maskine der lige har fået et program lades i fred). Slås fra med
    NGRAVE_PROBE_INTERVAL=0."""
    if PROBE_INTERVAL <= 0:
        app.logger.info("Baggrunds-tjek af maskiner er slået fra (NGRAVE_PROBE_INTERVAL=0)")
        return
    stop_event.wait(2)
    while not stop_event.is_set():
        try:
            _probe_alle(PROBE_EFTER_SEND)
        except Exception as e:
            app.logger.exception("Probe-loop fejl: %s", e)
        stop_event.wait(PROBE_INTERVAL)

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

def _maskine_status_liste(db):
    """Aktive maskiner med online-status og kø-tal (uden at røre ved maskinerne)."""
    nu = time.time()
    koe = {}
    for tabel in ('job_batches', 'skilte_jobs'):
        for r in db.execute(f"SELECT maskine_id, status, COUNT(*) n FROM {tabel} "
                            "WHERE status IN ('pending','running') GROUP BY maskine_id, status"):
            koe.setdefault(r['maskine_id'], {'pending': 0, 'running': 0})[r['status']] += r['n']
    ud = []
    for m in db.execute("SELECT id, navn, model, ip, port FROM maskiner WHERE aktiv=1 ORDER BY id"):
        s = forbindelse.hent(m['id'])
        ud.append({
            'id': m['id'], 'navn': m['navn'], 'ip': m['ip'], 'port': m['port'],
            'status': s['status'], 'kilde': s['kilde'], 'fejl': s['fejl'], 'ms': s['ms'],
            'tjekket_sek_siden': None if s['sidst_tjekket'] is None else int(nu - s['sidst_tjekket']),
            'set_online_sek_siden': None if s['sidst_set'] is None else int(nu - s['sidst_set']),
            'sendt_sek_siden': None if s['sidst_sendt'] is None else int(nu - s['sidst_sendt']),
            'graverer_formentlig': forbindelse.sendt_for_nylig(m['id'], PROBE_EFTER_SEND) is not None,
            'koe': koe.get(m['id'], {'pending': 0, 'running': 0}),
        })
    return ud

@app.route('/api/maskiner/status')
@require_auth
def maskiner_status():
    return jsonify(_maskine_status_liste(get_db()))

@app.route('/api/maskiner/<int:id>/ping', methods=['POST'])
@require_auth
def ping_maskine(id):
    """Manuelt tjek: opretter og lukker en forbindelse (sender aldrig data)."""
    m = get_db().execute("SELECT id, ip, port FROM maskiner WHERE id=?", (id,)).fetchone()
    if not m:
        return jsonify({'ok': False, 'fejl': 'Maskine ikke fundet'}), 404
    r = forbindelse.probe_maskine(m['id'], m['ip'], m['port'])
    if r is None:
        return jsonify({'ok': True, 'status': 'optaget',
                        'besked': 'Maskinen modtager et program lige nu — prøv igen om lidt.'})
    if r['status'] == 'online':
        _nede_til.pop(m['id'], None)
    return jsonify({'ok': True, **r})

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

def _nul(v, typ=float):
    """Tom streng/None -> None, ellers typet tal (til valgfrie felter)."""
    if v is None or v == '':
        return None
    return typ(v)

def _skilt_template_vaerdier(d):
    return (d['navn'], d.get('beskrivelse', ''),
            d['skilt_bredde_mm'], d['skilt_hoejde_mm'], d['antal_linjer'],
            json.dumps(d['linjer_config']),
            _nul(d.get('margin_top_mm')), _nul(d.get('margin_bottom_mm')),
            _nul(d.get('linje_afstand_mm')),
            _nul(d.get('feed_xy'), int), _nul(d.get('feed_z'), int),
            _nul(d.get('spindle_rpm'), int), _nul(d.get('z_op_mm')),
            _nul(d.get('prox_offset_mm')), _nul(d.get('maskine_id'), int))

@app.route('/api/skilt-templates', methods=['POST'])
@require_auth
def create_skilt_template():
    d = request.json or {}
    db = get_db()
    try:
        cur = db.execute("""
            INSERT INTO skilt_templates (
                navn, beskrivelse, skilt_bredde_mm, skilt_hoejde_mm, antal_linjer,
                linjer_config, margin_top_mm, margin_bottom_mm, linje_afstand_mm,
                feed_xy, feed_z, spindle_rpm, z_op_mm, prox_offset_mm, maskine_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, _skilt_template_vaerdier(d))
    except (KeyError, ValueError, TypeError):
        return jsonify({'ok': False, 'fejl': 'Ugyldige eller manglende felter'}), 400
    db.commit()
    return jsonify({'ok': True, 'id': cur.lastrowid})

@app.route('/api/skilt-templates/<int:id>', methods=['PUT'])
@require_auth
def update_skilt_template(id):
    d = request.json or {}
    db = get_db()
    try:
        vals = _skilt_template_vaerdier(d)
    except (KeyError, ValueError, TypeError):
        return jsonify({'ok': False, 'fejl': 'Ugyldige eller manglende felter'}), 400
    db.execute("""
        UPDATE skilt_templates SET
            navn=?, beskrivelse=?, skilt_bredde_mm=?, skilt_hoejde_mm=?,
            antal_linjer=?, linjer_config=?,
            margin_top_mm=?, margin_bottom_mm=?, linje_afstand_mm=?,
            feed_xy=?, feed_z=?, spindle_rpm=?, z_op_mm=?, prox_offset_mm=?,
            maskine_id=?
        WHERE id=?
    """, vals + (id,))
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
    d = request.get_json(silent=True) or {}
    db = get_db()
    maskine = db.execute("SELECT * FROM maskiner WHERE id=?", (id,)).fetchone()
    if not maskine:
        return jsonify({'ok': False, 'fejl': 'Maskine ikke fundet'}), 404

    # Test-positionen flytter maskinen. Er der lige sendt et program, graverer den
    # formentlig stadig — kræv en eksplicit bekræftelse før vi blander os.
    siden = forbindelse.sendt_for_nylig(id, PROBE_EFTER_SEND)
    if siden is not None and not d.get('tving'):
        return jsonify({'ok': False, 'kraever_bekraeftelse': True,
                        'fejl': f"Der blev sendt et program til maskinen for {max(1, siden // 60)} min siden — "
                                "den graverer måske stadig. Kør alligevel til 0,0?"}), 409

    laas = forbindelse.send_laas(id)
    if not laas.acquire(timeout=3):
        return jsonify({'ok': False, 'fejl': 'Maskinen modtager et program lige nu — prøv igen om lidt'}), 409
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
        forbindelse.noter(id, 'online', 'job')     # ikke sendt=True: test-positionen graverer ikke
        return jsonify({'ok': True})
    except ForbindelsesFejl as e:
        forbindelse.noter(id, 'afviser' if e.aarsag == 'afvist' else 'offline', 'job', fejl=e.besked)
        return jsonify({'ok': False, 'fejl': e.besked}), 502
    except Exception:
        app.logger.exception("test_maskine fejl")
        return jsonify({'ok': False, 'fejl': 'Kunne ikke kontakte maskinen'}), 502
    finally:
        laas.release()

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

    try:
        template_id = int(d['template_id'])
        maskine_id = int(d['maskine_id'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'ok': False, 'fejl': 'Vælg template og maskine'}), 400
    if not db.execute("SELECT 1 FROM maskiner WHERE id=? AND aktiv=1", (maskine_id,)).fetchone():
        return jsonify({'ok': False, 'fejl': 'Maskinen findes ikke'}), 400

    tmpl = db.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
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

    try:
        if loebe_aktiv:
            fra = int(d.get('loebe_fra', 1))
            til = int(d.get('loebe_til', 1))
        else:
            fra = 1
            til = int(d.get('antal', 1))
        start_slot = max(1, int(d.get('start_slot', 1))) - 1
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'fejl': 'Løbenummer, antal og start-slot skal være hele tal'}), 400

    antal = til - fra + 1
    if antal > MAX_EMNER_PR_ORDRE:
        return jsonify({'ok': False, 'fejl': f'For mange emner ({antal}) — max {MAX_EMNER_PR_ORDRE} pr. ordre. Tastefejl?'}), 400
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
        """, (navn, template_id, maskine_id, system_nr, type_felt, ekstra_tekst, loebe_cursor, batch_end, loebe_prefix, loebe_suffix, status))
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

def _skilt_spec(d):
    """Bygger layout-input fra en request. Tomme linjer udelades (både i
    forhåndsvisning og gravering, så de to altid er ens)."""
    linjer = [l for l in (d.get('linjer') or [])
              if isinstance(l, dict) and str(l.get('tekst', '')).strip()]
    return {
        'skilt_bredde_mm': float(d['skilt_bredde_mm']),
        'skilt_hoejde_mm': float(d['skilt_hoejde_mm']),
        'linjer_json': linjer,
        'margin_top_mm': d.get('margin_top_mm'),
        'margin_bottom_mm': d.get('margin_bottom_mm'),
        'linje_afstand_mm': d.get('linje_afstand_mm'),
    }

@app.route('/api/skilt/preview', methods=['POST'])
@require_auth
def preview_skilt():
    """Præcis det layout der graveres (samme motor), inkl. fejl/advarsler."""
    from workers.skilt_worker import layout_skilt
    try:
        lay = layout_skilt(_skilt_spec(request.json or {}))
    except (KeyError, ValueError, TypeError):
        return jsonify({'ok': False, 'fejl': ['Ugyldig størrelse'], 'advarsler': [], 'linjer': []}), 400
    for l in lay['linjer']:
        l.pop('strokes', None)
    return jsonify(lay)

@app.route('/api/skilte', methods=['POST'])
@require_auth
def create_skilt():
    from workers.skilt_worker import layout_skilt
    d = request.json or {}
    db = get_db()
    try:
        spec = _skilt_spec(d)
        maskine_id = int(d['maskine_id'])
    except (KeyError, ValueError, TypeError):
        return jsonify({'ok': False, 'fejl': 'Vælg maskine og angiv skiltets størrelse'}), 400
    if not spec['linjer_json']:
        return jsonify({'ok': False, 'fejl': 'Skriv tekst på mindst én linje'}), 400
    maskine = db.execute("SELECT protokol FROM maskiner WHERE id=? AND aktiv=1", (maskine_id,)).fetchone()
    if not maskine:
        return jsonify({'ok': False, 'fejl': 'Maskinen findes ikke'}), 400
    if maskine['protokol'] != 'gcode':
        return jsonify({'ok': False, 'fejl': 'Skilte kan kun graveres på G-code-maskiner (S5), ikke CIPHER (S3)'}), 400
    # Afvis med det samme (ikke først i køen) hvis teksten ikke passer på skiltet.
    lay = layout_skilt(spec)
    if not lay['ok']:
        return jsonify({'ok': False, 'fejl': 'Passer ikke på skiltet: ' + '; '.join(lay['fejl'])}), 400

    navn = (d.get('navn') or '').strip() or \
        f"{spec['linjer_json'][0]['tekst'][:30]} ({spec['skilt_bredde_mm']:g}x{spec['skilt_hoejde_mm']:g})"
    cur = db.execute("""
        INSERT INTO skilte_jobs (navn, maskine_id, template_id, skilt_bredde_mm, skilt_hoejde_mm, linjer_json, margin_top_mm, margin_bottom_mm, linje_afstand_mm)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (navn, maskine_id, _nul(d.get('template_id'), int), spec['skilt_bredde_mm'], spec['skilt_hoejde_mm'],
          json.dumps(spec['linjer_json']), _nul(d.get('margin_top_mm')), _nul(d.get('margin_bottom_mm')),
          _nul(d.get('linje_afstand_mm'))))
    db.commit()
    return jsonify({'ok': True, 'id': cur.lastrowid, 'advarsler': lay['advarsler']})

@app.route('/api/skilte/<int:id>/gentag', methods=['POST'])
@require_auth
def gentag_skilt(id):
    db = get_db()
    r = db.execute("SELECT maskine_id FROM skilte_jobs WHERE id=? AND status='fejl'", (id,)).fetchone()
    cur = db.execute("UPDATE skilte_jobs SET status='pending', fejl_besked=NULL, fejl_kode=NULL, startet=NULL, faerdig=NULL "
                     "WHERE id=? AND status='fejl'", (id,))
    db.commit()
    if r:
        _nede_til.pop(r['maskine_id'], None)   # ny chance — ingen fail-fast fra et tidligere forsøg
    return jsonify({'ok': cur.rowcount == 1})

@app.route('/api/batches/<int:id>/gentag', methods=['POST'])
@require_auth
def gentag_batch(id):
    db = get_db()
    r = db.execute("SELECT maskine_id FROM job_batches WHERE id=? AND status='fejl'", (id,)).fetchone()
    cur = db.execute("UPDATE job_batches SET status='pending', fejl_besked=NULL, fejl_kode=NULL, startet=NULL, faerdig=NULL "
                     "WHERE id=? AND status='fejl'", (id,))
    if cur.rowcount == 1:
        db.execute("UPDATE jobs SET status='pending', fejl_besked=NULL, udfoert=NULL WHERE batch_id=?", (id,))
    db.commit()
    if r:
        _nede_til.pop(r['maskine_id'], None)
    return jsonify({'ok': cur.rowcount == 1})

@app.route('/api/jobkoe/gentag-fejlede', methods=['POST'])
@require_auth
def gentag_fejlede():
    """Sætter alle jobs der fejlede fordi maskinen ikke kunne nås tilbage i køen.
    Kun 'forbindelse'-fejl: dér blev intet sendt, så det kan ikke give dobbelt gravering."""
    d = request.json or {}
    db = get_db()
    ekstra, args = '', ()
    if d.get('maskine_id') not in (None, ''):
        try:
            args = (int(d['maskine_id']),)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'fejl': 'Ugyldig maskine'}), 400
        ekstra = ' AND maskine_id=?'
    kriterie = f"status='fejl' AND fejl_kode='forbindelse'{ekstra}"
    mids = {r[0] for r in db.execute(f"SELECT maskine_id FROM job_batches WHERE {kriterie} "
                                     f"UNION SELECT maskine_id FROM skilte_jobs WHERE {kriterie}", args + args)}
    db.execute(f"UPDATE jobs SET status='pending', fejl_besked=NULL, udfoert=NULL WHERE batch_id IN "
               f"(SELECT id FROM job_batches WHERE {kriterie})", args)
    b = db.execute(f"UPDATE job_batches SET status='pending', fejl_besked=NULL, fejl_kode=NULL, startet=NULL, faerdig=NULL "
                   f"WHERE {kriterie}", args).rowcount
    sk = db.execute(f"UPDATE skilte_jobs SET status='pending', fejl_besked=NULL, fejl_kode=NULL, startet=NULL, faerdig=NULL "
                    f"WHERE {kriterie}", args).rowcount
    db.commit()
    for mid in mids:
        _nede_til.pop(mid, None)
    return jsonify({'ok': True, 'noegler': b, 'skilte': sk})

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
    def n(sql): return db.execute(sql).fetchone()[0]
    nk = {st: n(f"SELECT COUNT(*) FROM job_batches WHERE status='{st}'") for st in ('pending', 'running', 'on-hold')}
    sk = {st: n(f"SELECT COUNT(*) FROM skilte_jobs WHERE status='{st}'") for st in ('pending', 'running')}
    ms = [(m['id'], forbindelse.hent(m['id'])['status'])
          for m in db.execute("SELECT id FROM maskiner WHERE aktiv=1")]
    return jsonify({
        'noegler_pending': nk['pending'], 'noegler_running': nk['running'], 'noegler_hold': nk['on-hold'],
        'skilte_pending': sk['pending'], 'skilte_running': sk['running'],
        'pending': nk['pending'] + sk['pending'], 'running': nk['running'] + sk['running'],
        'maskiner': {str(i): st for i, st in ms},
        'maskiner_offline': sum(1 for _, st in ms if st in ('offline', 'afviser')),
    })

# Fonts
@app.route('/api/fonts')
@require_auth
def get_fonts():
    from workers.font_manager import FONTS
    return jsonify(FONTS)

@app.route('/api/fonts/prove')
@require_auth
def fonts_prove():
    """Prøvetekst i ALLE skrifttyper (de faktiske gravér-streger) til galleriet.
    Koordinater i mm ved 10 mm teksthøjde; SVG-orienteret (baseline y=0, op = negativ)."""
    from workers.font_manager import FONTS, get_strokes
    tekst = (request.args.get('tekst') or 'Aa Bb Æøå 123').strip()[:24] or 'Aa'
    out = {}
    for key, navn in FONTS.items():
        strokes, w = get_strokes(tekst, 10.0, key)
        out[key] = {'navn': navn, 'bredde': round(w, 2),
                    'paths': [[[round(x, 2), round(-y, 2)] for x, y in st] for st in strokes if st]}
    resp = jsonify(out)
    resp.headers['Cache-Control'] = 'private, max-age=600'
    return resp

# ─── Backup: eksport/import af templates ───────────────────────────────────
# Kolonner der er PORTABLE på tværs af maskiner (dvs. ikke id/maskine_id/aktiv/
# oprettet, som er lokale til hver installation). Whitelist — bruges direkte i
# SQL som kolonnenavne, så den må ALDRIG bygges fra brugerinput.
TEMPLATE_EXPORT_COLS = [
    'navn', 'beskrivelse', 'noejle_type', 'zone_bredde_mm', 'zone_hoejde_mm',
    'tekst_hoejde_mm', 'linje_afstand', 'feed_xy', 'feed_z', 'spindle_rpm',
    'z_op_mm', 'prox_offset_mm', 'font',
    'markering_aktiv', 'markering_navn', 'markering_x', 'markering_y',
    'markering_justering', 'markering_font', 'markering_hoejde_mm',
    'markering_bogstav_afstand_mm', 'markering_position',
    'system_aktiv', 'system_navn', 'system_x', 'system_y',
    'system_justering', 'system_font', 'system_hoejde_mm',
    'system_bogstav_afstand_mm', 'system_position',
    'loebe_aktiv', 'loebe_navn', 'loebe_x', 'loebe_y',
    'loebe_justering', 'loebe_font', 'loebe_hoejde_mm',
    'loebe_bogstav_afstand_mm', 'loebe_min_laengde',
    'loebe_prefix_aktiv', 'loebe_suffix_aktiv', 'loebe_position',
    'ekstra_aktiv', 'ekstra_navn', 'ekstra_x', 'ekstra_y',
    'ekstra_justering', 'ekstra_font', 'ekstra_hoejde_mm',
    'ekstra_bogstav_afstand_mm', 'ekstra_position',
    'grid_json',
]
SKILT_TEMPLATE_EXPORT_COLS = [
    'navn', 'beskrivelse', 'skilt_bredde_mm', 'skilt_hoejde_mm',
    'antal_linjer', 'linjer_config', 'margin_top_mm', 'margin_bottom_mm',
    'linje_afstand_mm', 'feed_xy', 'feed_z', 'spindle_rpm', 'z_op_mm',
    'prox_offset_mm',
]

@app.route('/api/export')
@require_auth
def export_templates():
    """Eksporterer alle aktive nøgle- og skilt-templates som portabel JSON
    (uden id/maskine_id, som er lokale til denne installation)."""
    db = get_db()
    def dump(table, cols):
        rows = db.execute(
            f"SELECT {','.join(cols)} FROM {table} WHERE aktiv=1 ORDER BY navn"
        ).fetchall()
        return [dict(r) for r in rows]
    return jsonify({
        'exported_at': datetime.now().isoformat(timespec='seconds'),
        'templates': dump('templates', TEMPLATE_EXPORT_COLS),
        'skilt_templates': dump('skilt_templates', SKILT_TEMPLATE_EXPORT_COLS),
    })

def _import_rows(db, table, cols, rows):
    created = updated = 0
    for row in rows:
        if not isinstance(row, dict) or not row.get('navn'):
            continue
        present = [c for c in cols if c in row]  # kun whitelistede kolonner
        if 'navn' not in present:
            continue
        existing = db.execute(
            f"SELECT id FROM {table} WHERE navn=? AND aktiv=1", (row['navn'],)
        ).fetchone()
        values = [row[c] for c in present]
        if existing:
            set_clause = ','.join(f"{c}=?" for c in present)
            db.execute(f"UPDATE {table} SET {set_clause} WHERE id=?",
                      values + [existing['id']])
            updated += 1
        else:
            placeholders = ','.join('?' for _ in present)
            db.execute(f"INSERT INTO {table} ({','.join(present)}) VALUES ({placeholders})", values)
            created += 1
    return {'created': created, 'updated': updated}

@app.route('/api/import', methods=['POST'])
@require_auth
def import_templates():
    """Importerer templates fra en tidligere eksport. Opretter nye (match på
    navn) og opdaterer eksisterende — sletter ALDRIG noget."""
    d = request.json or {}
    db = get_db()
    try:
        result = {
            'templates': _import_rows(db, 'templates', TEMPLATE_EXPORT_COLS, d.get('templates') or []),
            'skilt_templates': _import_rows(db, 'skilt_templates', SKILT_TEMPLATE_EXPORT_COLS, d.get('skilt_templates') or []),
        }
        db.commit()
        return jsonify({'ok': True, **result})
    except Exception:
        db.rollback()
        app.logger.exception("import_templates fejl")
        return jsonify({'ok': False, 'fejl': 'Import fejlede — ugyldigt format?'}), 400

# System-diagnostik: seneste linjer af auto-opdaterings-loggen + kørende version.
# Gør det muligt at se hvorfor en opdatering evt. fejlede — også fra mobil.
@app.route('/api/systeminfo')
@require_auth
def get_systeminfo():
    import subprocess
    info = {'version': None, 'channel': 'stable', 'update_log': [],
            'last_check': None, 'stale_hours': None, 'advarsel': None}
    try:
        info['version'] = subprocess.run(
            ['git', 'describe', '--tags', '--always'],
            cwd=os.path.dirname(__file__), capture_output=True, text=True, timeout=5
        ).stdout.strip() or None
    except Exception:
        pass
    for cf in ('/etc/ngrave/channel', os.path.join(os.path.dirname(__file__), 'channel')):
        try:
            with open(cf, encoding='utf-8') as f:
                ch = f.readline().strip().lower()
                if ch:
                    info['channel'] = 'beta' if ch == 'beta' else 'stable'
                break
        except Exception:
            continue
    # Heartbeat: hvornår tjekkede auto-updateren sidst med succes?
    hb_path = os.environ.get('NGRAVE_HEARTBEAT',
                             os.path.join(os.path.dirname(__file__), '.last-update-check'))
    try:
        from datetime import datetime as _dt, timezone as _tz
        ts = os.path.getmtime(hb_path)
        info['last_check'] = _dt.fromtimestamp(ts).isoformat(timespec='seconds')
        age_h = (_dt.now().timestamp() - ts) / 3600.0
        info['stale_hours'] = round(age_h, 1)
        if age_h > 48:
            info['advarsel'] = (f"Auto-opdatering har ikke tjekket ind i {int(age_h)} timer "
                                "— maskinen henter måske ikke opdateringer (udløbet token/netværk?). "
                                "Se opdaterings-loggen.")
    except Exception:
        info['advarsel'] = ("Ingen heartbeat fundet — auto-opdatering har aldrig kørt med denne version, "
                            "eller er ikke aktiv.")

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
    from werkzeug.serving import make_server

    init_db()
    if not AUTH_USER or not AUTH_PASS:
        app.logger.warning(
            "ADVARSEL: NGRAVE_AUTH_USER/NGRAVE_AUTH_PASS er ikke sat — API er åbent. "
            "Sæt dem i /etc/ngrave/ngrave.env for at aktivere Basic Auth."
        )
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    threading.Thread(target=queue_worker, name='koe-dispatcher', daemon=True).start()
    threading.Thread(target=probe_loop, name='maskine-probe', daemon=True).start()

    # Standard-port er 80. Kan vi ikke binde den (fx non-root uden
    # CAP_NET_BIND_SERVICE), falder vi tilbage til 8080 i stedet for at crashe.
    # (make_server binder med det samme, så bind-fejl kan fanges — modsat
    # app.run() der selv printer og kalder sys.exit.)
    try:
        # OSError = permission denied (non-root uden capability).
        # SystemExit = Werkzeug's egen sys.exit(1) når porten er optaget.
        srv = make_server(HOST, PORT, app, threaded=True)
    except (PermissionError, OSError, SystemExit) as e:
        if PORT == FALLBACK_PORT:
            raise
        app.logger.warning("Kunne ikke binde port %d (%s) — falder tilbage til %d",
                           PORT, e, FALLBACK_PORT)
        globals()['PORT'] = FALLBACK_PORT
        srv = make_server(HOST, FALLBACK_PORT, app, threaded=True)

    # Redirect fra 80 → hvis vi ikke selv kører på 80 (best-effort).
    _start_port80_redirector()
    app.logger.info("nGrave lytter på port %d", PORT)
    try:
        srv.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        srv.server_close()
