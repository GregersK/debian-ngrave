"""Fonte, ægte ÆØÅ, bogstavafstand, sti-optimering og nøgle-preview/-kontrol.

Det vigtigste: test_kompatibel_med_v61 — eksisterende nøgle-templates (uden
ægte ÆØÅ, uden optimering) skal give BYTE-IDENTISK G-code/CIPHER som før."""
import base64, json, math, os, sqlite3, sys, tempfile, unittest
from contextlib import closing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

_tmp0 = tempfile.mkdtemp()
os.environ.setdefault('NGRAVE_DB', os.path.join(_tmp0, 'f.db'))
os.environ.setdefault('NGRAVE_AUTH_USER', 'u')
os.environ.setdefault('NGRAVE_AUTH_PASS', 'p')
os.environ.setdefault('NGRAVE_UPDATE_LOG', os.path.join(_tmp0, 'u.log'))
os.environ.setdefault('NGRAVE_HEARTBEAT', os.path.join(_tmp0, 'hb'))
import app as A  # noqa: E402
from tests import golden_cases  # noqa: E402
from workers import gcode_worker, cipher_worker, skilt_worker  # noqa: E402
from workers.font_manager import FONTS, INFO, ALLE_NAVNE, get_strokes, manglende_tegn  # noqa: E402
from workers.optimering import optimer, statistik  # noqa: E402

AUTH = {'Authorization': 'Basic ' + base64.b64encode(
    f"{os.environ['NGRAVE_AUTH_USER']}:{os.environ['NGRAVE_AUTH_PASS']}".encode()).decode()}
DANSK = 'ÆØÅæøå'


def _laengde(strokes):
    return sum(math.dist(p, q) for s in strokes for p, q in zip(s, s[1:]))


class Kompatibilitet(unittest.TestCase):
    def test_kompatibel_med_v61(self):
        """Uden dansk_tegn og optimering: præcis samme output som før omskrivningen."""
        with open(golden_cases.GOLDEN, encoding='utf-8') as fh:
            golden = json.load(fh)
        ny = golden_cases.beregn(gcode_worker.byg_batch, cipher_worker.byg_batch, skilt_worker.byg_skilt)
        self.assertEqual(set(golden), set(ny))
        for k in golden:
            self.assertEqual(golden[k], ny[k], f'{k} graverer anderledes end v6.1')

    def test_gamle_aliaser_virker_stadig(self):
        for gammel in ('romans', 'romanc', 'romand', 'romant', 'italics', 'italiccs', 'italict'):
            s, w = get_strokes('ABC', 5, gammel)
            self.assertTrue(s and w > 0, gammel)
            self.assertIn(gammel, ALLE_NAVNE)


class Dansk(unittest.TestCase):
    def test_alle_fonte_kan_aeoeaa(self):
        for fid in INFO:
            self.assertEqual(manglende_tegn(DANSK, fid), [], fid)
            for ch in DANSK:
                s, w = get_strokes(ch, 10, fid)
                self.assertTrue(s, f'{fid} {ch}')
                self.assertGreater(w, 0, f'{fid} {ch}')

    def test_konstrueret_bogstav_aldrig_bredere_end_gammel_erstatning(self):
        for fid, i in INFO.items():
            if i['kilde'] != 'hershey':
                continue
            for ch, gl in zip(DANSK, ('AE', 'OE', 'AA', 'ae', 'oe', 'aa')):
                _, ny = get_strokes(ch, 10, fid)
                _, gammel = get_strokes(gl, 10, fid, dansk=False)
                self.assertLessEqual(ny, gammel + 1e-9, f'{fid} {ch}')

    def test_dansk_false_giver_gammel_erstatning(self):
        a, _ = get_strokes('Ø', 10, 'futural', dansk=False)
        b, _ = get_strokes('OE', 10, 'futural', dansk=False)
        self.assertEqual(a, b)
        c, _ = get_strokes('Ø', 10, 'futural')
        self.assertNotEqual(a, c)

    def test_ring_og_streg_holder_sig_taet_paa_bogstavet(self):
        for fid, i in INFO.items():
            if i['kilde'] != 'hershey':
                continue
            s, _ = get_strokes('Å', 10, fid)
            top = max(p[1] for st in s for p in st)
            self.assertLess(top, 14.5, f'{fid}: ringen på Å rager for højt op ({top:.1f} mm)')

    def test_tekst_uden_aeoeaa_er_uaendret_af_dansk_flag(self):
        for fid in INFO:
            self.assertEqual(get_strokes('Kontor 12-B', 7, fid, 0.3, True),
                             get_strokes('Kontor 12-B', 7, fid, 0.3, False), fid)


class Fonte(unittest.TestCase):
    def test_skjulte_dubletter_ikke_i_menu_men_virker(self):
        for fid in ('rowmans', 'rowmand', 'rowmant', 'gothiceng', 'gothicger'):
            self.assertNotIn(fid, FONTS)
            self.assertTrue(get_strokes('Abc', 5, fid)[0])
        for fid in ('relief', 'ems_readability', 'ems_allure', 'futural', 'block'):
            self.assertIn(fid, FONTS)

    def test_nye_fonte_indlaeses(self):
        for fid, i in INFO.items():
            if i['kilde'] == 'svg':
                s, w = get_strokes('Hamburg 2024', 10, fid)
                self.assertGreater(len(s), 10, fid)
                h = max(p[1] for st in s for p in st if True) - min(p[1] for st in s for p in st)
                self.assertGreater(h, 9, fid)          # versalhøjde ≈ 10 mm + nedstreg

    def test_relief_bruger_kerning(self):
        _, av = get_strokes('AV', 10, 'relief')
        _, a = get_strokes('A', 10, 'relief')
        _, v = get_strokes('V', 10, 'relief')
        self.assertLess(av, a + v - 0.5)

    def test_bogstavafstand_virker_i_alle_fonte(self):
        for fid in INFO:
            _, w0 = get_strokes('ABCD', 8, fid)
            _, w1 = get_strokes('ABCD', 8, fid, 1.0)
            _, wm = get_strokes('ABCD', 8, fid, -0.5)
            self.assertGreater(w1 - w0, 2.9, fid)       # 3-4 mellemrum à 1 mm
            self.assertLess(w1 - w0, 4.1, fid)
            self.assertLess(wm, w0, fid)

    def test_block_nye_tegn_flytter_ikke_resten(self):
        """Før blev et ukendt tegn til et tomrum af samme bredde — det nye tegn
        skal stå præcis dér, så alt efter det står hvor det plejer."""
        s_ny, w_ny = get_strokes('A#B', 5, 'block')
        s_ukendt, w_ukendt = get_strokes('A€B', 5, 'block')
        self.assertEqual(w_ny, w_ukendt)
        self.assertEqual(s_ny[-2:], s_ukendt[-2:])      # B'ets to streger er identiske
        self.assertEqual(manglende_tegn(",:;+#&()'!?*=_@%", 'block'), [])


class Optimering(unittest.TestCase):
    def tekster(self):
        for fid in ('block', 'futuram', 'timesrb', 'gothgbt', 'scriptc', 'relief'):
            yield fid, get_strokes('HOVEDDØR 12 Søndergade', 6, fid)[0]

    def test_samme_fraesevej_og_aldrig_flere_loeft(self):
        for fid, s in self.tekster():
            for niv in ('let', 'fuld'):
                o = optimer(s, niv)
                self.assertAlmostEqual(_laengde(o), _laengde(s), places=6, msg=f'{fid} {niv}')
                self.assertLessEqual(len(o), len(s), f'{fid} {niv}')

    def test_fuld_sparer_loeft_i_fede_fonte(self):
        s = get_strokes('HOVEDDØR 12', 6, 'futuram')[0]
        self.assertLess(len(optimer(s, 'fuld')), len(s) * 0.7)

    def test_let_bevarer_raekkefoelge_og_retning(self):
        for fid, s in self.tekster():
            o = optimer(s, 'let')
            # første og sidste punkt i hele programmet er de samme, og alle punkter
            # i output findes i input i samme rækkefølge
            self.assertEqual(o[0][0], s[0][0])
            self.assertEqual(o[-1][-1], s[-1][-1])
            alle_in = [p for st in s for p in st]
            it = iter(alle_in)
            self.assertTrue(all(any(p == q for q in it) for st in o for p in st), fid)

    def test_ingen_aendrer_intet_og_prikker_bevares(self):
        s = [[(1.0, 1.0)], [(0, 0), (1, 0), (2, 0)], [(2, 0), (2, 2)]]
        self.assertEqual(optimer(s, 'ingen'), s)
        for niv in ('let', 'fuld'):
            o = optimer(s, niv)
            self.assertIn([(1.0, 1.0)], o)                 # prikken (ét punkt) er der stadig
        self.assertEqual(optimer([], 'fuld'), [])

    def test_statistik(self):
        st = statistik([[(0, 0), (3, 4)], [(3, 4), (3, 5)]])
        self.assertEqual(st['loeft'], 2)
        self.assertAlmostEqual(st['fraesevej_mm'], 6.0)
        self.assertAlmostEqual(st['luftvej_mm'], 0.0)


class Hastighed(unittest.TestCase):
    """Optimeringen i den G-code der rent faktisk sendes."""
    def test_fuld_giver_faerre_penneloeft_samme_slutpunkter(self):
        tmpl = golden_cases.tmpl('futuram')
        ingen = gcode_worker.byg_batch(golden_cases.JOBS, {**tmpl, 'optimering': 'ingen'})
        fuld = gcode_worker.byg_batch(golden_cases.JOBS, {**tmpl, 'optimering': 'fuld'})
        self.assertLess(fuld.count('G30'), ingen.count('G30') * 0.75)
        # Ingen nye koordinater: hvert XY i det optimerede program findes i det oprindelige
        # (en vendt streg tegner bare mod sit gamle startpunkt i stedet for fra det).
        def xy(prog):
            return {l.split(' ', 1)[1].split(' F')[0] for l in prog.splitlines() if l.startswith(('G0 X', 'G1 X'))}
        self.assertTrue(xy(fuld) <= xy(ingen))
        self.assertLess(fuld.count('G0 X'), ingen.count('G0 X'))
        self.assertEqual(fuld.splitlines()[:5], ingen.splitlines()[:5])        # samme opstart (spindel osv.)
        self.assertEqual(fuld.splitlines()[-8:], ingen.splitlines()[-8:])      # samme afslutning

    def test_cipher_bruger_ogsaa_optimering(self):
        tmpl = golden_cases.tmpl('futuram')
        ingen = cipher_worker.byg_batch(golden_cases.JOBS, {**tmpl, 'optimering': 'ingen'})
        fuld = cipher_worker.byg_batch(golden_cases.JOBS, {**tmpl, 'optimering': 'fuld'})
        self.assertLess(fuld.count(';PD'), ingen.count(';PD'))

    def test_ordre_bruger_maskinens_niveau(self):
        from unittest import mock
        A.init_db()
        with sqlite3.connect(A.DB) as db:
            mid = db.execute("INSERT INTO maskiner (navn,model,ip,port,protokol,optimering) "
                             "VALUES ('H','S5','127.0.0.1',1,'gcode','ingen')").lastrowid
            tid = db.execute("SELECT id FROM templates ORDER BY id LIMIT 1").fetchone()[0]
            db.execute("UPDATE templates SET system_font='futuram' WHERE id=?", (tid,))
            db.commit()
        programmer = []
        def send(prog, ip, port):
            programmer.append(prog)
            return b''
        for niv in ('ingen', 'fuld'):
            with sqlite3.connect(A.DB) as db:
                db.execute("UPDATE maskiner SET optimering=? WHERE id=?", (niv, mid))
                b = db.execute("INSERT INTO job_batches (navn,template_id,maskine_id,loebe_til,status) "
                               "VALUES ('h',?,?,1,'pending')", (tid, mid)).lastrowid
                db.execute("INSERT INTO jobs (batch_id,slot_nr,slot_x_mm,slot_y_mm,system_nr) VALUES (?,1,0,0,'HOVEDDØR')", (b,))
                db.commit()
            with mock.patch('workers.gcode_worker.send', send), closing(A._db()) as db:
                A._koer_naeste_batch(db, mid)
        self.assertEqual(len(programmer), 2)
        self.assertLess(programmer[1].count('G30'), programmer[0].count('G30'))


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        A.init_db()
        cls.c = A.app.test_client()

    def j(self, method, url, body=None):
        r = getattr(self.c, method)(url, json=body, headers=AUTH)
        return r.status_code, r.get_json(silent=True)

    def template(self, **kw):
        d = {'navn': 'T-' + os.urandom(4).hex(), 'noejle_type': 'X', 'zone_bredde_mm': 18, 'zone_hoejde_mm': 8,
             'tekst_hoejde_mm': 3.5, 'linje_afstand': 1.5, 'feed_xy': 12, 'feed_z': 40, 'spindle_rpm': 16000,
             'z_op_mm': 5, 'prox_offset_mm': 1.5, 'grid': {'kolonner': 1, 'raekker': 1, 'slots': [{'nr': 1, 'x': 0, 'y': 0}]}}
        d.update(kw)
        return d

    def test_fonts_endpoints(self):
        st, f = self.j('get', '/api/fonts')
        self.assertEqual(st, 200)
        self.assertIn('relief', f)
        self.assertNotIn('rowmans', f)
        st, info = self.j('get', '/api/fonts/info')
        ids = {x['id'] for x in info['fonte']}
        self.assertIn('rowmans', ids)
        self.assertIn('romans', info['navne'])            # gammelt id kan stadig vises
        st, prove = self.j('get', '/api/fonts/prove?tekst=Æble')
        self.assertEqual(set(prove), set(f))
        self.assertGreater(prove['relief']['loeft'], 0)

    def test_ny_template_faar_aegte_aeoeaa_og_afstand_gemmes(self):
        st, r = self.j('post', '/api/templates', self.template(system_bogstav_afstand_mm=0.4))
        self.assertTrue(r['ok'])
        with sqlite3.connect(A.DB) as db:
            row = db.execute("SELECT dansk_tegn, system_bogstav_afstand_mm FROM templates WHERE id=?", (r['id'],)).fetchone()
        self.assertEqual(row, (1, 0.4))
        # En ældre klient der ikke sender felterne må ikke nulstille dem
        d = self.template(navn='opdateret')
        st, r2 = self.j('put', f"/api/templates/{r['id']}", d)
        self.assertTrue(r2['ok'])
        with sqlite3.connect(A.DB) as db:
            row = db.execute("SELECT dansk_tegn, system_bogstav_afstand_mm FROM templates WHERE id=?", (r['id'],)).fetchone()
        self.assertEqual(row, (1, 0.4))
        st, r3 = self.j('put', f"/api/templates/{r['id']}", self.template(dansk_tegn=0, system_bogstav_afstand_mm=0))
        with sqlite3.connect(A.DB) as db:
            row = db.execute("SELECT dansk_tegn, system_bogstav_afstand_mm FROM templates WHERE id=?", (r['id'],)).fetchone()
        self.assertEqual(row, (0, 0.0))

    def test_eksisterende_templates_beholder_ae_oe_aa(self):
        """Migrering af en v6.1-database: gamle templates får dansk_tegn=0, maskiner 'fuld'."""
        tmp = tempfile.mkdtemp()
        gl = os.path.join(tmp, 'v61.db')
        with sqlite3.connect(gl) as db:
            db.executescript("""
                CREATE TABLE maskiner (id INTEGER PRIMARY KEY AUTOINCREMENT, navn TEXT NOT NULL, model TEXT NOT NULL,
                    ip TEXT NOT NULL, port INTEGER NOT NULL, protokol TEXT NOT NULL, aktiv INTEGER DEFAULT 1);
                CREATE TABLE templates (id INTEGER PRIMARY KEY AUTOINCREMENT, navn TEXT NOT NULL, noejle_type TEXT NOT NULL,
                    zone_bredde_mm REAL NOT NULL, zone_hoejde_mm REAL NOT NULL, grid_json TEXT NOT NULL, aktiv INTEGER DEFAULT 1);
                INSERT INTO maskiner (navn,model,ip,port,protokol) VALUES ('M','S5','1.2.3.4',1,'gcode');
                INSERT INTO templates (navn,noejle_type,zone_bredde_mm,zone_hoejde_mm,grid_json) VALUES ('Gammel','X',18,8,'{}');
            """)
        gammel_db = A.DB
        try:
            A.DB = gl
            A.migrate_db()
            with sqlite3.connect(gl) as db:
                self.assertEqual(db.execute("SELECT dansk_tegn FROM templates").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT optimering FROM maskiner").fetchone()[0], 'fuld')
                self.assertEqual(db.execute("SELECT navn FROM templates").fetchone()[0], 'Gammel')
        finally:
            A.DB = gammel_db

    def test_template_preview_bruger_rigtige_streger_og_finder_overflow(self):
        d = self.template(system_font='futural', system_hoejde_mm=2.5, eksempel={'system_nr': 'A0938E', 'type_felt': 'L1', 'loebe_nr': '17'})
        st, r = self.j('post', '/api/templates/preview', d)
        self.assertEqual(st, 200)
        self.assertTrue(r['ok'], r['fejl'])
        felter = {f['felt']: f for f in r['felter']}
        self.assertTrue(felter['system']['paths'])
        self.assertGreater(r['statistik']['loeft'], 0)
        d['eksempel']['system_nr'] = 'MEGET LANG TEKST'
        st, r = self.j('post', '/api/templates/preview', d)
        self.assertFalse(r['ok'])
        self.assertTrue(any('højre' in f for f in r['fejl']))

    def test_batch_tjek_finder_for_brede_loebenumre(self):
        st, r = self.j('post', '/api/templates', self.template(loebe_hoejde_mm=5))
        tid = r['id']
        st, ok = self.j('post', '/api/batches/tjek', {'template_id': tid, 'system_nr': 'AB', 'loebe_fra': 1, 'loebe_til': 9})
        self.assertTrue(ok['ok'], ok)
        st, nej = self.j('post', '/api/batches/tjek', {'template_id': tid, 'system_nr': 'AB', 'loebe_fra': 123400, 'loebe_til': 123456})
        self.assertFalse(nej['ok'])
        self.assertEqual(sum('Løbenr' in f for f in nej['fejl']), 1, nej['fejl'])   # én besked, det værste nummer
        st, x = self.j('post', '/api/batches/tjek', {'template_id': 'x'})
        self.assertEqual(st, 400)

    def test_maskine_optimering_gemmes_og_bevares(self):
        st, r = self.j('post', '/api/maskiner', {'navn': 'O', 'model': 'S5', 'ip': '10.0.0.9', 'port': 1, 'protokol': 'gcode'})
        mid = r['id']
        with sqlite3.connect(A.DB) as db:
            self.assertEqual(db.execute("SELECT optimering FROM maskiner WHERE id=?", (mid,)).fetchone()[0], 'fuld')
        self.j('put', f'/api/maskiner/{mid}', {'navn': 'O', 'model': 'S5', 'ip': '10.0.0.9', 'port': 1,
                                               'protokol': 'gcode', 'optimering': 'ingen'})
        self.j('put', f'/api/maskiner/{mid}', {'navn': 'O2', 'model': 'S5', 'ip': '10.0.0.9', 'port': 1, 'protokol': 'gcode'})
        with sqlite3.connect(A.DB) as db:
            self.assertEqual(db.execute("SELECT optimering FROM maskiner WHERE id=?", (mid,)).fetchone()[0], 'ingen')

    def test_skilt_med_bogstavafstand_og_statistik(self):
        base = {'skilt_bredde_mm': 300, 'skilt_hoejde_mm': 100}
        st, a = self.j('post', '/api/skilt/preview', {**base, 'linjer': [{'tekst': 'Ærø', 'hoejde_mm': 20, 'font': 'futural'}]})
        st, b = self.j('post', '/api/skilt/preview', {**base, 'linjer': [{'tekst': 'Ærø', 'hoejde_mm': 20, 'font': 'futural', 'afstand_mm': 3}]})
        self.assertGreater(b['linjer'][0]['bredde_mm'], a['linjer'][0]['bredde_mm'] + 5)
        self.assertGreater(a['statistik']['loeft'], 0)
        st, c = self.j('post', '/api/skilt/preview', {**base, 'linjer': [{'tekst': 'X', 'hoejde_mm': 20, 'afstand_mm': 999}]})
        self.assertFalse(c['ok'])


if __name__ == '__main__':
    unittest.main()
