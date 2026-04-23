"""
Gravesystem v4 - Flask Server
"""
import json, sqlite3, threading, time, os
from datetime import datetime
from flask import Flask, request, jsonify, render_template, g

from workers.gcode_worker  import byg_job as byg_gcode,  send as send_gcode
from workers.cipher_worker import byg_job as byg_cipher, send as send_cipher

app = Flask(__name__)
DB  = os.path.join(os.path.dirname(__file__), 'gravesystem.db')

# ─── Database ─────────────────────────────────────────────────────────────────
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()

def init_db():
    with sqlite3.connect(DB) as db:
        with open(os.path.join(os.path.dirname(__file__), 'schema.sql')) as f:
            db.executescript(f.read())
    migrate_db()

def migrate_db():
    """Tilføjer manglende kolonner til eksisterende databaser."""
    migrations = [
        ("maskiner",    "offset_x",           "REAL NOT NULL DEFAULT 0.0"),
        ("maskiner",    "offset_y",           "REAL NOT NULL DEFAULT 0.0"),
        ("maskiner",    "offset_z",           "REAL NOT NULL DEFAULT 0.0"),
        ("templates",   "markering_justering","TEXT NOT NULL DEFAULT 'venstre'"),
        ("templates",   "system_justering",   "TEXT NOT NULL DEFAULT 'venstre'"),
        ("templates",   "linje_afstand",      "REAL NOT NULL DEFAULT 1.5"),
        ("templates",   "prox_offset_mm",     "REAL NOT NULL DEFAULT 1.5"),
        ("templates",   "font",               "TEXT NOT NULL DEFAULT 'block'"),
        # Dynamiske felter
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
        ("job_batches", "ekstra_tekst",       "TEXT NOT NULL DEFAULT ''"),
        ("jobs",        "ekstra_tekst",       "TEXT NOT NULL DEFAULT ''"),
        ("skilt_templates","margin_top_mm",   "REAL"),
        ("skilt_templates","margin_bottom_mm","REAL"),
        ("skilt_templates","linje_afstand_mm","REAL"),
        ("skilte_jobs", "margin_top_mm",      "REAL"),
        ("skilte_jobs", "margin_bottom_mm",   "REAL"),
        ("skilte_jobs", "linje_afstand_mm",   "REAL"),
        ("skilte_jobs", "fejl_besked",        "TEXT"),
    ]
    with sqlite3.connect(DB) as db:
        for table, col, typedef in migrations:
            try:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
                print(f"Migration: tilføjede {table}.{col}")
            except Exception:
                pass

# ─── Job Queue Worker ─────────────────────────────────────────────────────────
stop_event = threading.Event()

def queue_worker():
    while not stop_event.is_set():
        try:
            with sqlite3.connect(DB) as db:
                db.row_factory = sqlite3.Row

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

                    # Hent template og maskine separat for at undgå kolonne-konflikter
                    tmpl = dict(db.execute(
                        "SELECT * FROM templates WHERE id=?", (batch['template_id'],)
                    ).fetchone())
                    maskine = dict(db.execute(
                        "SELECT * FROM maskiner WHERE id=?", (batch['maskine_id'],)
                    ).fetchone())

                    # Tilføj maskin-offset til tmpl så byg_batch har adgang
                    tmpl['offset_x'] = maskine.get('offset_x', 0.0) or 0.0
                    tmpl['offset_y'] = maskine.get('offset_y', 0.0) or 0.0
                    tmpl['offset_z'] = maskine.get('offset_z', 0.0) or 0.0

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
                        print(f"Batch {batch_id} fejl: {e}")
                    db.commit()
                    continue

                # Næste pending skilt
                skilt = db.execute("""
                    SELECT s.*, m.ip, m.port, m.protokol
                    FROM skilte_jobs s
                    JOIN maskiner m ON s.maskine_id = m.id
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
                        db.execute("UPDATE skilte_jobs SET status='fejl' WHERE id=?", (skilt_id,))
                    db.commit()
                    continue

                time.sleep(1)

        except Exception as e:
            print(f"Queue worker fejl: {e}")
            time.sleep(2)

# ─── API Routes ───────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

# Maskiner
@app.route('/api/maskiner')
def get_maskiner():
    return jsonify([dict(r) for r in get_db().execute("SELECT * FROM maskiner WHERE aktiv=1")])

@app.route('/api/maskiner/<int:id>/kalibrering', methods=['PUT'])
def kalibrering(id):
    d = request.json
    db = get_db()
    db.execute("UPDATE maskiner SET offset_x=?, offset_y=?, offset_z=? WHERE id=?",
               (d.get('offset_x', 0), d.get('offset_y', 0), d.get('offset_z', 0), id))
    db.commit()
    return jsonify({'ok': True})

# Nøgle-Templates
@app.route('/api/templates')
def get_templates():
    rows = get_db().execute("SELECT * FROM templates WHERE aktiv=1")
    return jsonify([dict(r) for r in rows])

@app.route('/api/templates', methods=['POST'])
def create_template():
    d = request.json
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
                grid_json, maskine_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
              json.dumps(d.get('grid', {"kolonner":0,"raekker":0,"slots":[]})), d.get('maskine_id')))
        db.commit()
        return jsonify({'ok': True, 'id': cur.lastrowid})
    except Exception as e:
        return jsonify({'ok': False, 'fejl': str(e)}), 200

@app.route('/api/templates/<int:id>', methods=['PUT'])
def update_template(id):
    d = request.json
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
              json.dumps(d.get('grid', {"kolonner":0,"raekker":0,"slots":[]})),
              d.get('maskine_id'), id))
        db.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'fejl': str(e)}), 200

@app.route('/api/templates/<int:id>', methods=['DELETE'])
def delete_template(id):
    db = get_db()
    # Tjek om template er i brug
    in_use = db.execute("SELECT COUNT(*) FROM job_batches WHERE template_id=?", (id,)).fetchone()[0]
    if in_use > 0:
        db.execute("UPDATE templates SET aktiv=0 WHERE id=?", (id,))
    else:
        db.execute("DELETE FROM templates WHERE id=?", (id,))
    db.commit()
    return jsonify({'ok': True})

# Skilt-Templates
@app.route('/api/skilt-templates')
def get_skilt_templates():
    rows = get_db().execute("SELECT * FROM skilt_templates WHERE aktiv=1")
    return jsonify([dict(r) for r in rows])

@app.route('/api/skilt-templates', methods=['POST'])
def create_skilt_template():
    d = request.json
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
def update_skilt_template(id):
    d = request.json
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
def delete_skilt_template(id):
    db = get_db()
    db.execute("UPDATE skilt_templates SET aktiv=0 WHERE id=?", (id,))
    db.commit()
    return jsonify({'ok': True})

# Maskine test-kørsel
@app.route('/api/maskiner/<int:id>/test', methods=['POST'])
def test_maskine(id):
    db = get_db()
    maskine = db.execute("SELECT * FROM maskiner WHERE id=?", (id,)).fetchone()
    if not maskine:
        return jsonify({'ok': False, 'fejl': 'Maskine ikke fundet'})
    
    MM = 1 / 25.4
    ox = round((maskine['offset_x'] or 0) * MM, 4)
    oy = round(-(maskine['offset_y'] or 0) * MM, 4)
    
    # Kør til kalibreret 0,0 position med Z oppe - ingen spindle
    gcode = "\n".join([
        "M24",
        "G28 Z0",
        "G20",
        "G90",
        f"G0 X{ox} Y{oy}",
        "M30"
    ]) + "\n"
    
    try:
        from workers.gcode_worker import send as send_gcode
        send_gcode(gcode, maskine['ip'], maskine['port'])
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'fejl': str(e)})

# Batches (nøgle-jobs)
@app.route('/api/batches')
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
def create_batch():
    d = request.json
    db = get_db()

    tmpl = db.execute("SELECT * FROM templates WHERE id=?", (d['template_id'],)).fetchone()
    if not tmpl:
        return jsonify({'ok': False, 'fejl': 'Template findes ikke'})

    grid = json.loads(tmpl['grid_json'])
    slots = grid.get('slots', [])
    if not slots:
        return jsonify({'ok': False, 'fejl': 'Template har ingen slots'})

    # Felt-data — brug kun hvis aktivt i template
    type_felt    = d.get('type_felt', '') if tmpl['markering_aktiv'] else ''
    system_nr    = d.get('system_nr', '') if tmpl['system_aktiv'] else ''
    ekstra_tekst = d.get('ekstra_tekst', '') if tmpl['ekstra_aktiv'] else ''
    loebe_aktiv  = bool(tmpl['loebe_aktiv'])

    # Hvis løbenr ikke er aktiv, laver vi kun 1 job (ikke per slot)
    if loebe_aktiv:
        fra = int(d.get('loebe_fra', 1))
        til = int(d.get('loebe_til', 1))
    else:
        fra = 1
        til = int(d.get('antal', 1))  # antal emner

    antal = til - fra + 1
    start_slot = max(1, int(d.get('start_slot', 1))) - 1
    plade_size = len(slots)

    if antal <= 0:
        return jsonify({'ok': False, 'fejl': 'Ugyldigt antal/løbenummer-interval'})
    if start_slot >= plade_size:
        return jsonify({'ok': False, 'fejl': f'Start slot {start_slot+1} er større end antal slots ({plade_size})'})

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
            INSERT INTO job_batches (navn, template_id, maskine_id, system_nr, type_felt, ekstra_tekst, loebe_fra, loebe_til, status)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (navn, d['template_id'], d['maskine_id'], system_nr, type_felt, ekstra_tekst, loebe_cursor, batch_end, status))
        batch_id = cur.lastrowid

        for i, slot in enumerate(slots_i_batch):
            loebe = loebe_cursor + i
            if loebe > til:
                break
            loebe_str = str(loebe) if loebe_aktiv else ''
            db.execute("""
                INSERT INTO jobs (batch_id, slot_nr, slot_x_mm, slot_y_mm, type_felt, loebe_nr, system_nr, ekstra_tekst)
                VALUES (?,?,?,?,?,?,?,?)
            """, (batch_id, slot['nr'], slot['x'], slot['y'], type_felt, loebe_str, system_nr, ekstra_tekst))

        loebe_cursor = batch_end + 1

    db.commit()
    return jsonify({'ok': True, 'batches': batches, 'jobs': antal, 'plade_size': plade_size, 'start_slot': start_slot+1})

@app.route('/api/batches/<int:id>/frigiv', methods=['POST'])
def frigiv_batch(id):
    db = get_db()
    db.execute("UPDATE job_batches SET status='pending' WHERE id=?", (id,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/batches/<int:id>/annuller', methods=['POST'])
def annuller_batch(id):
    db = get_db()
    db.execute("DELETE FROM jobs WHERE batch_id=?", (id,))
    db.execute("DELETE FROM job_batches WHERE id=?", (id,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/jobkoe/ryd-op', methods=['POST'])
def ryd_op_jobkoe():
    """Slet alle færdige/fejlede jobs fra jobkøen."""
    d = request.json or {}
    db = get_db()
    slettet = 0
    if d.get('type') == 'noegler':
        # Find batches der er done/fejl
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
def create_skilt():
    d = request.json
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
def annuller_skilt(id):
    db = get_db()
    db.execute("DELETE FROM skilte_jobs WHERE id=?", (id,))
    db.commit()
    return jsonify({'ok': True})

# Status
@app.route('/api/status')
def get_status():
    db = get_db()
    pending = db.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0]
    running = db.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0]
    return jsonify({'pending': pending, 'running': running})

# Fonts
@app.route('/api/fonts')
def get_fonts():
    from workers.font_manager import FONTS
    return jsonify(FONTS)

# ─── Startup ──────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    t = threading.Thread(target=queue_worker, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=80, debug=False)
