"""Udrulning fra v6.1.x og sikkerhed i køen.

- En database fra v6.1.1 (rigtigt skema i fixtures/schema_v611.sql) opgraderes,
  og nøgle-templates der havde valgt en anden skrifttype end Block bliver ved
  med at gravere i Block — for det var det v6.1.1 faktisk gjorde.
- De gamle filnavne static/ngrave_a.js og ngrave_b.js skal fortsat levere
  v6.1.1-koden (en ikke-genstartet v6.1-proces henter dem).
- Frigiv/annullér, nedlukning og skrifttyper der ikke kan indlæses.
"""
import base64, json, os, sqlite3, sys, tempfile, threading, time, unittest
from contextlib import closing
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

_tmp0 = tempfile.mkdtemp()
os.environ.setdefault('NGRAVE_DB', os.path.join(_tmp0, 'r.db'))
os.environ.setdefault('NGRAVE_AUTH_USER', 'u')
os.environ.setdefault('NGRAVE_AUTH_PASS', 'p')
os.environ.setdefault('NGRAVE_UPDATE_LOG', os.path.join(_tmp0, 'u.log'))
os.environ.setdefault('NGRAVE_HEARTBEAT', os.path.join(_tmp0, 'hb'))
import app as A  # noqa: E402
from tests import golden_cases  # noqa: E402
from workers import gcode_worker, cipher_worker, font_manager  # noqa: E402

HER = os.path.dirname(os.path.abspath(__file__))
ROD = os.path.dirname(HER)
AUTH = {'Authorization': 'Basic ' + base64.b64encode(
    f"{os.environ['NGRAVE_AUTH_USER']}:{os.environ['NGRAVE_AUTH_PASS']}".encode()).decode()}


def laes(*dele):
    with open(os.path.join(ROD, *dele), encoding='utf-8') as f:
        return f.read()


class FraV611(unittest.TestCase):
    def v611_db(self):
        sti = os.path.join(tempfile.mkdtemp(), 'v611.db')
        with sqlite3.connect(sti) as db, open(os.path.join(HER, 'fixtures', 'schema_v611.sql'), encoding='utf-8') as f:
            db.executescript(f.read())
            for navn, fonte in (('Kun block', ('block', 'block', 'block', 'block')), ('Tom', ('', '', '', '')),
                                ('Roman', ('romans', 'block', 'block', 'block')), ('Ekstra gotisk', ('block', 'block', 'block', 'gothgbt'))):
                db.execute("INSERT INTO templates (navn, noejle_type, zone_bredde_mm, zone_hoejde_mm, grid_json, "
                           "markering_font, system_font, loebe_font, ekstra_font) VALUES (?,?,?,?,?,?,?,?,?)",
                           (navn, 'X', 18, 8, '{"slots":[]}', *fonte))
            db.execute("INSERT INTO maskiner (navn,model,ip,port,protokol) VALUES ('M','S5','1.2.3.4',1,'gcode')")
        return sti

    def test_templates_med_anden_font_laases_til_block_ved_opgradering(self):
        sti, gammel = self.v611_db(), A.DB
        try:
            A.DB = sti
            A.migrate_db()
            with sqlite3.connect(sti) as db:
                flag = dict(db.execute("SELECT navn, kun_block FROM templates"))
            self.assertEqual(flag, {'Kun block': 0, 'Tom': 0, 'Roman': 1, 'Ekstra gotisk': 1})
            # brugeren slår det fra på én template → en senere genstart må ikke slå det til igen
            with sqlite3.connect(sti) as db:
                db.execute("UPDATE templates SET kun_block=0 WHERE navn='Roman'")
            A.migrate_db()
            with sqlite3.connect(sti) as db:
                self.assertEqual(db.execute("SELECT kun_block FROM templates WHERE navn='Roman'").fetchone()[0], 0)
                # og intet er forsvundet
                self.assertEqual(db.execute("SELECT COUNT(*) FROM templates").fetchone()[0], 4)
        finally:
            A.DB = gammel

    def test_laast_template_graverer_praecis_som_v611(self):
        """v6.1.1 graverede ALT i Block (verificeret mod v6.1.1-koden: alle fontvalg
        gav samme output som 'block'). En låst template skal give netop det output."""
        with open(golden_cases.GOLDEN, encoding='utf-8') as fh:
            golden = json.load(fh)
        for f in golden_cases.FONTE:
            t = golden_cases.tmpl(f, kun_block=1)
            self.assertEqual(golden_cases._h(gcode_worker.byg_batch(golden_cases.JOBS, t)), golden['gcode/block'], f)
            self.assertEqual(golden_cases._h(cipher_worker.byg_batch(golden_cases.JOBS, t)), golden['cipher/block'], f)
            self.assertEqual(golden_cases._h(cipher_worker.byg_batch(golden_cases.JOBS, {**t, 'spejl_y': True})),
                             golden['cipher-spejl/block'], f)

    def test_umigreret_raekke_behandles_som_v61(self):
        """En v6.1-proces der ikke er genstartet kan indlæse de nye moduler mod en
        database uden de nye kolonner: også dér skal alt graveres i Block."""
        with open(golden_cases.GOLDEN, encoding='utf-8') as fh:
            golden = json.load(fh)
        t = golden_cases.tmpl('gothgbt')
        del t['kun_block']
        self.assertEqual(golden_cases._h(gcode_worker.byg_batch(golden_cases.JOBS, t)), golden['gcode/block'])
        self.assertEqual(golden_cases._h(cipher_worker.byg_batch(golden_cases.JOBS, t)), golden['cipher/block'])

    def test_nye_installationer_laaser_intet(self):
        A.init_db()
        with sqlite3.connect(A.DB) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM templates WHERE kun_block=1").fetchone()[0], 0)


class BlandedeModuler(unittest.TestCase):
    def test_ny_gcode_worker_genindlaeser_foraeldet_font_manager(self):
        """Gammel proces (v6.1-font_manager i hukommelsen) indlæser ny gcode_worker
        fra disken: uden beskyttelsen fejler hvert job med en TypeError."""
        import subprocess
        kode = '''
import sys
import workers.font_manager as fm
del fm.API                                            # som v6.1: intet API-tal
fm.get_strokes = lambda tekst, h, font="block", afstand=0.0: ([], 0.0)   # v6.1-signatur (4 argumenter)
from tests import golden_cases
from workers import gcode_worker, cipher_worker
t = golden_cases.tmpl("gothgbt"); del t["kun_block"]   # umigreret række
import json
g = json.load(open(golden_cases.GOLDEN))
assert golden_cases._h(gcode_worker.byg_batch(golden_cases.JOBS, t)) == g["gcode/block"]
assert golden_cases._h(cipher_worker.byg_batch(golden_cases.JOBS, t)) == g["cipher/block"]
print("OK")
'''
        r = subprocess.run([sys.executable, '-c', kode], cwd=ROD, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.stdout.strip(), 'OK', r.stderr[-600:])


class GamleFilnavne(unittest.TestCase):
    """En v6.1-proces der ikke er genstartet efter opdateringen, har den gamle
    side i hukommelsen og henter /static/ngrave_a.js + ngrave_b.js fra disken."""
    def test_gamle_filnavne_er_v611_kode(self):
        for navn in ('ngrave_a.js', 'ngrave_b.js'):
            s = laes('static', navn)
            self.assertIn('KOMPATIBILITETS-KOPI fra v6.1.1', s)
            for nyt in ('debounce(', 'toast(', 'gaaTil('):       # hjælpere der kun findes i den nye ui.js
                self.assertNotIn(nyt, s, f'{navn} må ikke indeholde ny kode ({nyt})')
        self.assertIn('ngrave-genstart-banner', laes('static', 'ngrave_b.js'))

    def test_ny_side_bruger_nye_filnavne(self):
        html = laes('templates', 'index.html')
        self.assertNotIn('ngrave_a.js', html)
        self.assertNotIn('ngrave_b.js', html)
        for navn in ('ui.js', 'noegler.js', 'skilt.js', 'system.js'):
            self.assertIn(f'/static/{navn}', html)
            self.assertTrue(os.path.exists(os.path.join(ROD, 'static', navn)))


class Koe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        A.init_db()
        cls.c = A.app.test_client()

    def setUp(self):
        A.stop_event.clear()
        with sqlite3.connect(A.DB) as db:
            self.mid = db.execute("INSERT INTO maskiner (navn,model,ip,port,protokol) VALUES ('K','S5','127.0.0.1',1,'gcode')").lastrowid
            self.tid = db.execute("SELECT id FROM templates ORDER BY id LIMIT 1").fetchone()[0]

    def tearDown(self):
        A.stop_event.clear()

    def batch(self, status='pending', system='A1'):
        with sqlite3.connect(A.DB) as db:
            b = db.execute("INSERT INTO job_batches (navn,template_id,maskine_id,loebe_til,status) VALUES ('b',?,?,1,?)",
                           (self.tid, self.mid, status)).lastrowid
            db.execute("INSERT INTO jobs (batch_id,slot_nr,slot_x_mm,slot_y_mm,system_nr) VALUES (?,1,0,0,?)", (b, system))
        return b

    def status(self, b):
        with sqlite3.connect(A.DB) as db:
            r = db.execute("SELECT status, fejl_besked, fejl_kode FROM job_batches WHERE id=?", (b,)).fetchone()
        return r

    def post(self, url, body=None):
        r = self.c.post(url, json=body, headers=AUTH)
        return r.status_code, r.get_json()

    def test_frigiv_kun_plader_paa_hold(self):
        """Et klik fra en forældet fane må ikke sætte en færdig plade i kø igen."""
        b = self.batch('on-hold')
        self.assertEqual(self.post(f'/api/batches/{b}/frigiv')[0], 200)
        self.assertEqual(self.status(b)[0], 'pending')
        for st in ('done', 'running', 'fejl'):
            b = self.batch(st)
            kode, svar = self.post(f'/api/batches/{b}/frigiv')
            self.assertEqual((kode, svar['ok']), (409, False), st)
            self.assertEqual(self.status(b)[0], st)

    def test_kan_ikke_annullere_mens_der_sendes(self):
        b = self.batch('running')
        self.assertEqual(self.post(f'/api/batches/{b}/annuller')[0], 409)
        self.assertIsNotNone(self.status(b))
        b = self.batch('pending')
        self.assertEqual(self.post(f'/api/batches/{b}/annuller')[0], 200)
        self.assertIsNone(self.status(b))

    def test_nedlukning_laegger_jobbet_tilbage_i_koeen(self):
        """Lukker tjenesten ned før der er sendt noget, skal jobbet køre efter genstarten."""
        b = self.batch('pending')
        send = mock.Mock(return_value=b'')
        A.stop_event.set()
        with mock.patch('workers.gcode_worker.send', send), closing(A._db()) as db:
            A._koer_naeste_batch(db, self.mid)
        self.assertEqual(send.call_count, 0)
        self.assertEqual(tuple(self.status(b)), ('pending', None, None))

    def test_nedlukning_venter_paa_igangvaerende_sending(self):
        faerdig = []
        t = threading.Thread(target=lambda: (time.sleep(0.3), faerdig.append(1)), name='maskine-test')
        with A._maskine_traade_laas:
            A._maskine_traade['test'] = t
        t.start()
        try:
            A._vent_paa_sendinger(timeout=5)
            self.assertEqual(faerdig, [1])
        finally:
            with A._maskine_traade_laas:
                A._maskine_traade.pop('test', None)

    def test_font_der_ikke_kan_indlaeses_stopper_jobbet(self):
        """Før: stille tilbagefald til Block (forkert skrift på en hel plade). Nu: tydelig fejl."""
        with mock.patch.object(font_manager, '_hent', side_effect=ImportError('No module named HersheyFonts')):
            with self.assertRaises(font_manager.FontFejl) as cm:
                font_manager.get_strokes('ABC', 5, 'futural')
            self.assertIn('Sans simpel', str(cm.exception))
            self.assertTrue(font_manager.get_strokes('ABC', 5, 'block')[0])        # Block virker altid
            self.assertTrue(font_manager.get_strokes('ABC', 5, 'findes_ikke')[0])  # ukendt id → Block som før
            with sqlite3.connect(A.DB) as db:
                db.execute("UPDATE templates SET system_font='futural', kun_block=0 WHERE id=?", (self.tid,))
            b = self.batch('pending')
            send = mock.Mock(return_value=b'')
            with mock.patch('workers.gcode_worker.send', send), closing(A._db()) as db:
                A._koer_naeste_batch(db, self.mid)
            st = self.status(b)
            self.assertEqual((st[0], st[2], send.call_count), ('fejl', 'data', 0))
            self.assertIn('kunne ikke indlæses', st[1])
            # forhåndsvisningen siger det samme i stedet for at vise Block
            r = self.c.post('/api/skilt/preview', headers=AUTH, json={
                'skilt_bredde_mm': 200, 'skilt_hoejde_mm': 100, 'linjer': [{'tekst': 'Hej', 'font': 'futural', 'hoejde_mm': 10}]}).get_json()
            self.assertFalse(r['ok'])
            self.assertIn('kunne ikke indlæses', ' '.join(r['fejl']))
        with sqlite3.connect(A.DB) as db:
            db.execute("UPDATE templates SET system_font='block' WHERE id=?", (self.tid,))

    def test_lavt_loeft_minimum_gaelder_efter_maskinens_z_offset(self):
        import re
        t = {**golden_cases.tmpl('block'), 'prox_offset_mm': 0, 'offset_z': -1.0, 'z_loeft_inde_mm': 2.0}
        g = gcode_worker.byg_batch(golden_cases.JOBS, t)
        loeft = {round(float(z) * 25.4, 2) for z in re.findall(r'G91\nG0 Z([\d.]+)\nG90', g)}
        self.assertEqual(min(loeft), gcode_worker.MIN_LOEFT_INDE_MM)       # 2,0 − 1,0 = 1,0 → løftes til 1,5
        self.assertEqual(max(loeft), 4.0)                                  # fuldt løft 5,0 − 1,0

    def test_tal_valideres(self):
        kode, svar = self.c.put(f'/api/maskiner/{self.mid}/kalibrering', json={'offset_x': '<b>x</b>'}, headers=AUTH).status_code, None
        self.assertEqual(kode, 400)
        self.assertEqual(self.c.put(f'/api/maskiner/{self.mid}/kalibrering', json={'offset_x': '1.5', 'offset_y': ''}, headers=AUTH).status_code, 200)
        with sqlite3.connect(A.DB) as db:
            self.assertEqual(db.execute("SELECT offset_x, offset_y FROM maskiner WHERE id=?", (self.mid,)).fetchone(), (1.5, 0.0))
        t = {'navn': 'tal', 'noejle_type': 'X', 'zone_bredde_mm': 'bred', 'zone_hoejde_mm': 8, 'tekst_hoejde_mm': 3.5,
             'linje_afstand': 1.5, 'feed_xy': 12, 'feed_z': 40, 'spindle_rpm': 16000, 'z_op_mm': 5, 'prox_offset_mm': 1.5}
        kode, svar = self.post('/api/templates', t)
        self.assertEqual(kode, 400)
        self.assertIn('zone_bredde_mm', svar['fejl'])
        kode, svar = self.post('/api/templates', {**t, 'zone_bredde_mm': 0})
        self.assertEqual(kode, 400)
        kode, svar = self.post('/api/templates', {**t, 'zone_bredde_mm': '18'})
        self.assertTrue(svar['ok'])
        with sqlite3.connect(A.DB) as db:
            r = db.execute("SELECT zone_bredde_mm, feed_xy, typeof(feed_xy), kun_block FROM templates WHERE id=?", (svar['id'],)).fetchone()
        self.assertEqual(r, (18.0, 12, 'integer', 0))


if __name__ == '__main__':
    unittest.main()
