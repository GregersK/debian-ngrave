"""Materiale-profiler (messing, plast …) og lavt løft mellem bogstaverne."""
import base64, os, re, sqlite3, sys, tempfile, unittest
from collections import Counter
from contextlib import closing
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

_tmp0 = tempfile.mkdtemp()
os.environ.setdefault('NGRAVE_DB', os.path.join(_tmp0, 'm.db'))
os.environ.setdefault('NGRAVE_AUTH_USER', 'u')
os.environ.setdefault('NGRAVE_AUTH_PASS', 'p')
os.environ.setdefault('NGRAVE_UPDATE_LOG', os.path.join(_tmp0, 'u.log'))
os.environ.setdefault('NGRAVE_HEARTBEAT', os.path.join(_tmp0, 'hb'))
import app as A  # noqa: E402
from tests import golden_cases  # noqa: E402
from workers import gcode_worker  # noqa: E402

AUTH = {'Authorization': 'Basic ' + base64.b64encode(
    f"{os.environ['NGRAVE_AUTH_USER']}:{os.environ['NGRAVE_AUTH_PASS']}".encode()).decode()}


def loeft(gcode):
    """Alle relative Z-bevægelser efter en streg (G91 / G0 Z… / G90) i mm."""
    return [round(float(z) * 25.4, 2) for z in re.findall(r'G91\nG0 Z([\d.]+)\nG90\n(?!G1)', gcode)]


class LavtLoeft(unittest.TestCase):
    def tmpl(self, **kw):
        return {**golden_cases.tmpl('block'), 'offset_z': 0.0, 'prox_offset_mm': 0, 'optimering': 'ingen', **kw}

    def test_uden_indstilling_er_alt_som_foer(self):
        self.assertEqual(gcode_worker.byg_batch(golden_cases.JOBS, self.tmpl()),
                         gcode_worker.byg_batch(golden_cases.JOBS, self.tmpl(z_loeft_inde_mm=None)))

    def test_lavt_inde_i_noeglen_fuldt_mellem_noegler(self):
        g = gcode_worker.byg_batch(golden_cases.JOBS, self.tmpl(z_loeft_inde_mm=2.0))
        c = Counter(loeft(g))
        self.assertEqual(c[5.0], len(golden_cases.JOBS))        # ét fuldt løft pr. nøgle
        self.assertEqual(set(c), {2.0, 5.0})
        # og det fulde løft kommer lige før kørslen til næste nøgle
        blokke = g.split('G0 Z0.1969')
        self.assertEqual(len(blokke) - 1, len(golden_cases.JOBS))

    def test_aldrig_under_minimum(self):
        g = gcode_worker.byg_batch(golden_cases.JOBS, self.tmpl(z_loeft_inde_mm=0.3))
        self.assertEqual(min(loeft(g)), gcode_worker.MIN_LOEFT_INDE_MM)

    def test_hoejere_end_z_op_ignoreres(self):
        self.assertEqual(gcode_worker.byg_batch(golden_cases.JOBS, self.tmpl(z_loeft_inde_mm=9)),
                         gcode_worker.byg_batch(golden_cases.JOBS, self.tmpl()))


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        A.init_db()
        cls.c = A.app.test_client()

    def j(self, method, url, body=None):
        r = getattr(self.c, method)(url, json=body, headers=AUTH)
        return r.status_code, r.get_json(silent=True)

    def materiale(self, **kw):
        d = {'navn': 'Plast-' + os.urandom(3).hex(), 'feed_xy': 30, 'feed_z': 50, 'spindle_rpm': 12000,
             'z_op_mm': 4, 'z_loeft_inde_mm': 2, 'prox_offset_mm': 0.8, 'fraeser': 'V 30°', 'fraeser_bredde_mm': 0.3}
        d.update(kw)
        return d

    def template(self, **kw):
        d = {'navn': 'T-' + os.urandom(4).hex(), 'noejle_type': 'X', 'zone_bredde_mm': 18, 'zone_hoejde_mm': 8,
             'tekst_hoejde_mm': 3.5, 'linje_afstand': 1.5, 'feed_xy': 12, 'feed_z': 40, 'spindle_rpm': 16000,
             'z_op_mm': 5, 'prox_offset_mm': 1.5, 'grid': {'kolonner': 1, 'raekker': 1, 'slots': [{'nr': 1, 'x': 0, 'y': 0}]}}
        d.update(kw)
        return d

    def test_messing_oprettes_fra_template_vaerdier(self):
        st, rows = self.j('get', '/api/materialer')
        messing = next(m for m in rows if m['id'] == 1)
        self.assertEqual(messing['navn'], 'Messing')
        self.assertEqual((messing['feed_xy'], messing['feed_z'], messing['spindle_rpm'], messing['z_op_mm']),
                         (12, 40, 16000, 5.0))
        with sqlite3.connect(A.DB) as db:      # ingen templates er koblet på automatisk
            self.assertEqual(db.execute("SELECT COUNT(*) FROM templates WHERE materiale_id IS NOT NULL "
                                        "AND navn='Ruko Triton 5x4'").fetchone()[0], 0)

    def test_validering(self):
        for d, tekst in ((self.materiale(navn=''), 'navn'), (self.materiale(z_loeft_inde_mm=1.0), '1.5'),
                         (self.materiale(z_loeft_inde_mm=6), 'højere'), (self.materiale(feed_xy='x'), 'tal')):
            st, r = self.j('post', '/api/materialer', d)
            self.assertEqual(st, 400, d)
            self.assertIn(tekst, r['fejl'])
        st, r = self.j('post', '/api/materialer', self.materiale(z_loeft_inde_mm=''))   # tomt = som Z-løft
        self.assertTrue(r['ok'])

    def test_template_bruger_materialets_vaerdier_ved_gravering(self):
        st, m = self.j('post', '/api/materialer', self.materiale(feed_xy=33, spindle_rpm=11000))
        st, t = self.j('post', '/api/templates', self.template(materiale_id=m['id'], z_op_mm=5))
        self.assertTrue(t['ok'], t)
        with sqlite3.connect(A.DB) as db:
            mid = db.execute("INSERT INTO maskiner (navn,model,ip,port,protokol) VALUES ('M','S5','127.0.0.1',1,'gcode')").lastrowid
            b = db.execute("INSERT INTO job_batches (navn,template_id,maskine_id,loebe_til,status) VALUES ('b',?,?,1,'pending')",
                           (t['id'], mid)).lastrowid
            db.execute("INSERT INTO jobs (batch_id,slot_nr,slot_x_mm,slot_y_mm,system_nr,type_felt,loebe_nr) "
                       "VALUES (?,1,0,0,'A12','L1','7')", (b,))
            db.commit()
        sendt = []
        with mock.patch('workers.gcode_worker.send', lambda p, ip, port: sendt.append(p) or b''), closing(A._db()) as db:
            A._koer_naeste_batch(db, mid)
        self.assertEqual(len(sendt), 1)
        g = sendt[0]
        self.assertIn('M3 S11000', g)
        self.assertIn(' F33', g)
        self.assertNotIn(' F12', g)
        c = Counter(loeft(g))
        self.assertEqual(c[4.0], 1)              # materialets Z-løft, én gang (én nøgle)
        self.assertGreater(c[2.0], 1)            # materialets løft mellem bogstaver

    def test_slet_kun_naar_ubrugt_og_opdatering_bevarer_kobling(self):
        st, m = self.j('post', '/api/materialer', self.materiale())
        st, t = self.j('post', '/api/templates', self.template(materiale_id=m['id']))
        st, r = self.j('delete', f"/api/materialer/{m['id']}")
        self.assertEqual(st, 409)
        # ældre klient uden materiale_id i requesten rører ikke koblingen
        self.j('put', f"/api/templates/{t['id']}", self.template(navn='x-' + os.urandom(3).hex()))
        with sqlite3.connect(A.DB) as db:
            self.assertEqual(db.execute("SELECT materiale_id FROM templates WHERE id=?", (t['id'],)).fetchone()[0], m['id'])
        self.j('put', f"/api/templates/{t['id']}", self.template(materiale_id=None))
        st, r = self.j('delete', f"/api/materialer/{m['id']}")
        self.assertEqual((st, r['ok']), (200, True))
        st, r = self.j('post', '/api/templates', self.template(materiale_id=99999))
        self.assertEqual(st, 400)

    def test_template_egne_vaerdier_valideres(self):
        st, r = self.j('post', '/api/templates', self.template(z_loeft_inde_mm=0.8))
        self.assertEqual(st, 400)
        self.assertIn('1.5', r['fejl'])

    def test_preview_viser_fraeserbredde_og_advarer_ved_lille_tekst(self):
        st, m = self.j('post', '/api/materialer', self.materiale(fraeser_bredde_mm=0.6))
        st, r = self.j('post', '/api/templates/preview', self.template(materiale_id=m['id'], system_hoejde_mm=3))
        self.assertEqual(r['stregbredde_mm'], 0.6)
        self.assertTrue(r['materiale'].startswith('Plast-'), r['materiale'])
        self.assertTrue(any('flyde sammen' in a for a in r['advarsler']), r['advarsler'])
        st, r = self.j('post', '/api/templates/preview', self.template(fraeser_bredde_mm=0.2))
        self.assertEqual(r['stregbredde_mm'], 0.2)
        self.assertFalse(any('flyde sammen' in a for a in r['advarsler']))

    def test_eksport_import_med_materiale_navn(self):
        navn = 'Akryl-' + os.urandom(3).hex()
        st, m = self.j('post', '/api/materialer', self.materiale(navn=navn))
        tnavn = 'TM-' + os.urandom(3).hex()
        st, t = self.j('post', '/api/templates', self.template(navn=tnavn, materiale_id=m['id']))
        st, eks = self.j('get', '/api/export')
        self.assertIn(navn, [x['navn'] for x in eks['materialer']])
        te = next(x for x in eks['templates'] if x['navn'] == tnavn)
        self.assertEqual(te['materiale'], navn)
        self.assertNotIn('materiale_id', te)
        # importér som ny template (andet navn) → kobles på materialet via navnet
        te2 = {**te, 'navn': tnavn + '-imp'}
        st, r = self.j('post', '/api/import', {'materialer': eks['materialer'], 'templates': [te2]})
        self.assertTrue(r['ok'], r)
        with sqlite3.connect(A.DB) as db:
            self.assertEqual(db.execute("SELECT materiale_id FROM templates WHERE navn=?", (tnavn + '-imp',)).fetchone()[0],
                             m['id'])


if __name__ == '__main__':
    unittest.main()
