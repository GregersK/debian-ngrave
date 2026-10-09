"""API-tests mod en midlertidig database (ingen netværk, ingen maskiner)."""
import base64, json, os, sqlite3, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

_tmp = tempfile.mkdtemp()
os.environ['NGRAVE_DB'] = os.path.join(_tmp, 'test.db')
os.environ['NGRAVE_AUTH_USER'] = 'u'
os.environ['NGRAVE_AUTH_PASS'] = 'p'
os.environ['NGRAVE_UPDATE_LOG'] = os.path.join(_tmp, 'u.log')
os.environ['NGRAVE_HEARTBEAT'] = os.path.join(_tmp, 'hb')
import app as A  # noqa: E402

AUTH = {'Authorization': 'Basic ' + base64.b64encode(b'u:p').decode()}


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        A.init_db()
        with sqlite3.connect(A.DB) as db:
            db.execute("INSERT INTO maskiner (navn,model,ip,port,protokol) VALUES ('S5','S5','10.255.255.1',22000,'gcode')")
            db.commit()
        cls.c = A.app.test_client()

    def j(self, method, url, body=None, auth=True):
        r = getattr(self.c, method)(url, json=body, headers=AUTH if auth else {})
        return r.status_code, (r.get_json(silent=True) if r.data else None)

    def skilt(self, linjer, **kw):
        d = {'maskine_id': 1, 'skilt_bredde_mm': 200, 'skilt_hoejde_mm': 100, 'linjer': linjer}
        d.update(kw)
        return d

    # --- auth -------------------------------------------------------------
    def test_auth_kraeves(self):
        for m, u in [('get', '/api/maskiner'), ('get', '/api/export'), ('post', '/api/import'),
                     ('post', '/api/skilt/preview'), ('get', '/api/systeminfo'), ('get', '/api/status')]:
            self.assertEqual(self.j(m, u, {} if m == 'post' else None, auth=False)[0], 401, u)

    # --- skilt: forhåndsvisning + afvisning ---------------------------------
    def test_preview_returnerer_paths_og_fejl(self):
        st, d = self.j('post', '/api/skilt/preview', self.skilt([{'tekst': 'Køkken', 'hoejde_mm': 15, 'font': 'timesr', 'justering': 'center'}]))
        self.assertEqual(st, 200)
        self.assertTrue(d['ok'])
        self.assertTrue(d['linjer'][0]['paths'])
        self.assertNotIn('strokes', d['linjer'][0])

    def test_preview_viser_overflow(self):
        st, d = self.j('post', '/api/skilt/preview', self.skilt([{'tekst': 'ALT FOR LANG TEKST HER', 'hoejde_mm': 40, 'font': 'block'}]))
        self.assertEqual(st, 200)
        self.assertFalse(d['ok'])
        self.assertTrue(d['fejl'])

    def test_bestilling_der_ikke_passer_afvises_med_400(self):
        st, d = self.j('post', '/api/skilte', self.skilt([{'tekst': 'ALT FOR LANG TEKST HER', 'hoejde_mm': 40, 'font': 'block'}]))
        self.assertEqual(st, 400)
        self.assertIn('Passer ikke', d['fejl'])

    def test_bestilling_uden_tekst_afvises(self):
        self.assertEqual(self.j('post', '/api/skilte', self.skilt([{'tekst': '  ', 'hoejde_mm': 10}]))[0], 400)

    def test_bestilling_uden_maskine_afvises(self):
        self.assertEqual(self.j('post', '/api/skilte', {'skilt_bredde_mm': 100, 'skilt_hoejde_mm': 50, 'linjer': [{'tekst': 'A'}]})[0], 400)

    def test_gyldig_bestilling_oprettes(self):
        st, d = self.j('post', '/api/skilte', self.skilt([{'tekst': 'HEJ', 'hoejde_mm': 12, 'font': 'block', 'justering': 'center'}]))
        self.assertEqual((st, d['ok']), (200, True))

    # --- skilt-templates: feed/rpm + maskine gemmes -------------------------
    def test_skilt_template_gemmer_feed_og_maskine(self):
        body = {'navn': 'T-feed', 'skilt_bredde_mm': 100, 'skilt_hoejde_mm': 50, 'antal_linjer': 1,
                'linjer_config': [{'justering': 'center', 'hoejde_mm': 10, 'font': 'block'}],
                'feed_xy': '20', 'feed_z': '', 'spindle_rpm': 18000, 'maskine_id': ''}
        st, d = self.j('post', '/api/skilt-templates', body)
        self.assertEqual(st, 200)
        body.update(feed_xy=25, maskine_id='1')
        self.assertEqual(self.j('put', f"/api/skilt-templates/{d['id']}", body)[0], 200)
        row = next(t for t in self.j('get', '/api/skilt-templates')[1] if t['id'] == d['id'])
        self.assertEqual((row['feed_xy'], row['feed_z'], row['spindle_rpm'], row['maskine_id']), (25, None, 18000, 1))

    # --- nøgle-ordre: validering -------------------------------------------
    def test_noegle_ordre_uden_template_giver_400_ikke_500(self):
        self.assertEqual(self.j('post', '/api/batches', {'maskine_id': 1})[0], 400)

    def test_noegle_ordre_for_stor_afvises(self):
        st, d = self.j('post', '/api/batches', {'template_id': 1, 'maskine_id': 1, 'loebe_fra': 1, 'loebe_til': 99999})
        self.assertEqual(st, 400)

    def test_noegle_ordre_med_tekst_i_tal_felt_giver_400(self):
        self.assertEqual(self.j('post', '/api/batches', {'template_id': 1, 'maskine_id': 1, 'loebe_fra': 'abc'})[0], 400)

    # --- gentag + fejl-besked ----------------------------------------------
    def test_gentag_batch_og_skilt(self):
        with sqlite3.connect(A.DB) as db:
            db.execute("INSERT INTO job_batches (navn,template_id,maskine_id,loebe_til,status,fejl_besked) VALUES ('x',1,1,5,'fejl','Maskinen svarede ikke')")
            bid = db.execute("SELECT max(id) FROM job_batches").fetchone()[0]
            db.execute("INSERT INTO skilte_jobs (navn,maskine_id,skilt_bredde_mm,skilt_hoejde_mm,linjer_json,status,fejl_besked) VALUES ('s',1,100,50,'[]','fejl','x')")
            sid = db.execute("SELECT max(id) FROM skilte_jobs").fetchone()[0]
            db.commit()
        self.assertTrue(self.j('post', f'/api/batches/{bid}/gentag')[1]['ok'])
        self.assertTrue(self.j('post', f'/api/skilte/{sid}/gentag')[1]['ok'])
        self.assertFalse(self.j('post', f'/api/batches/{bid}/gentag')[1]['ok'])   # ikke længere 'fejl'
        row = next(b for b in self.j('get', '/api/batches')[1] if b['id'] == bid)
        self.assertEqual((row['status'], row['fejl_besked']), ('pending', None))

    def test_status_taeller_batches_og_skilte(self):
        st, d = self.j('get', '/api/status')
        self.assertEqual(st, 200)
        for k in ('noegler_pending', 'noegler_running', 'noegler_hold', 'skilte_pending', 'skilte_running'):
            self.assertIn(k, d)

    def test_kort_fejl_er_menneskelig(self):
        self.assertIn('timeout', A._kort_fejl(TimeoutError()))
        self.assertIn('afviste', A._kort_fejl(ConnectionRefusedError()))
        self.assertIn('Netværksfejl', A._kort_fejl(OSError(113, 'No route to host')))

    # --- backup round-trip -------------------------------------------------
    def test_backup_round_trip_og_whitelist(self):
        exp = self.j('get', '/api/export')[1]
        self.assertNotIn('id', exp['templates'][0])
        exp['templates'][0]['__evil__;DROP TABLE templates;--'] = 'x'
        st, r = self.j('post', '/api/import', exp)
        self.assertEqual(st, 200)
        self.assertEqual(r['templates']['created'], 0)       # opdaterer, dublerer ikke
        self.assertEqual(self.j('post', '/api/import', {'templates': [{'navn': 'Mangler'}]})[0], 400)  # NOT NULL → rollback


if __name__ == '__main__':
    unittest.main()
