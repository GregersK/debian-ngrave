"""Testserver (NGRAVE_TESTSERVER=1): intet sendes til maskinerne, programmer gemmes
som filer, og maskiner kontaktes ikke — undtagen dem i NGRAVE_TEST_SEND_TIL."""
import base64, json, os, sqlite3, sys, tempfile, unittest
from contextlib import closing
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

_tmp0 = tempfile.mkdtemp()
os.environ.setdefault('NGRAVE_DB', os.path.join(_tmp0, 't.db'))
os.environ.setdefault('NGRAVE_AUTH_USER', 'u')
os.environ.setdefault('NGRAVE_AUTH_PASS', 'p')
os.environ.setdefault('NGRAVE_UPDATE_LOG', os.path.join(_tmp0, 'u.log'))
os.environ.setdefault('NGRAVE_HEARTBEAT', os.path.join(_tmp0, 'hb'))
import app as A  # noqa: E402
from workers import forbindelse  # noqa: E402

AUTH = {'Authorization': 'Basic ' + base64.b64encode(
    f"{os.environ['NGRAVE_AUTH_USER']}:{os.environ['NGRAVE_AUTH_PASS']}".encode()).decode()}


class Testserver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        A.init_db()
        cls.c = A.app.test_client()

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        with sqlite3.connect(A.DB) as db:
            self.m_test = db.execute("INSERT INTO maskiner (navn,model,ip,port,protokol) VALUES ('Prod','S5','127.0.0.1',9,'gcode')").lastrowid
            self.m_ok = db.execute("INSERT INTO maskiner (navn,model,ip,port,protokol) VALUES ('Lov','S5','127.0.0.1',9,'gcode')").lastrowid
            self.m_s3 = db.execute("INSERT INTO maskiner (navn,model,ip,port,protokol) VALUES ('S3','S3','127.0.0.1',9,'cipher')").lastrowid
            self.tid = db.execute("SELECT id FROM templates ORDER BY id LIMIT 1").fetchone()[0]
        self.p = mock.patch.multiple(A, TESTSERVER=True, TEST_SEND_TIL={self.m_ok}, TOERKOERSEL_DIR=self.dir, SERVERNAVN='LAASENGRAVE01-TEST')
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def batch(self, mid):
        with sqlite3.connect(A.DB) as db:
            b = db.execute("INSERT INTO job_batches (navn,template_id,maskine_id,loebe_til,status) VALUES ('b',?,?,1,'pending')",
                           (self.tid, mid)).lastrowid
            db.execute("INSERT INTO jobs (batch_id,slot_nr,slot_x_mm,slot_y_mm,system_nr) VALUES (?,1,0,0,'A1')", (b,))
        return b

    def koer(self, mid, gcode_send, cipher_send=None):
        with mock.patch('workers.gcode_worker.send', gcode_send), \
             mock.patch('workers.cipher_worker.send', cipher_send or mock.Mock(return_value=b'')), closing(A._db()) as db:
            A._koer_naeste_batch(db, mid)

    def test_sender_ikke_men_gemmer_programmet(self):
        b = self.batch(self.m_test)
        send = mock.Mock(return_value=b'')
        self.koer(self.m_test, send)
        self.assertEqual(send.call_count, 0)
        with sqlite3.connect(A.DB) as db:
            st, note = db.execute("SELECT status, fejl_besked FROM job_batches WHERE id=?", (b,)).fetchone()
        self.assertEqual(st, 'done')
        self.assertIn('TESTSERVER', note)
        filer = os.listdir(self.dir)
        self.assertEqual(len(filer), 1)
        self.assertRegex(filer[0], rf'_noegler-{b}_m{self.m_test}\.nc$')
        with open(os.path.join(self.dir, filer[0])) as f:
            prog = f.read()
        self.assertTrue(prog.startswith('M24') and prog.rstrip().endswith('M30'))
        # filen kan hentes via API'et, men kun med gyldigt navn
        with self.c.get(f'/api/toerkoersel/{filer[0]}', headers=AUTH) as r:
            self.assertEqual((r.status_code, r.data.decode()), (200, prog))
        self.assertEqual(self.c.get('/api/toerkoersel/..%2Fapp.py', headers=AUTH).status_code, 404)
        self.assertEqual(self.c.get('/api/toerkoersel/app.py', headers=AUTH).status_code, 400)
        liste = self.c.get('/api/toerkoersel', headers=AUTH).get_json()
        self.assertEqual([f['navn'] for f in liste['filer']], filer)

    def test_cipher_gemmes_som_cip(self):
        self.batch(self.m_s3)
        send = mock.Mock(return_value=b'')
        self.koer(self.m_s3, mock.Mock(), send)
        self.assertEqual(send.call_count, 0)
        self.assertTrue(os.listdir(self.dir)[0].endswith('.cip'))

    def test_tilladt_maskine_faar_rigtige_jobs(self):
        self.batch(self.m_ok)
        send = mock.Mock(return_value=b'')
        self.koer(self.m_ok, send)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(os.listdir(self.dir), [])

    def test_skilt_gemmes(self):
        with sqlite3.connect(A.DB) as db:
            s = db.execute("INSERT INTO skilte_jobs (navn,maskine_id,skilt_bredde_mm,skilt_hoejde_mm,linjer_json,status) "
                           "VALUES ('s',?,200,100,?,'pending')",
                           (self.m_test, json.dumps([{'tekst': 'Hej', 'hoejde_mm': 10, 'font': 'block', 'justering': 'center'}]))).lastrowid
        send = mock.Mock(return_value=b'')
        with mock.patch('workers.gcode_worker.send', send), closing(A._db()) as db:
            A._koer_naeste_skilt(db, self.m_test)
        self.assertEqual(send.call_count, 0)
        self.assertRegex(os.listdir(self.dir)[0], rf'_skilt-{s}_m{self.m_test}\.nc$')

    def test_maskiner_kontaktes_ikke(self):
        with mock.patch.object(forbindelse, 'probe_maskine', return_value={'status': 'online', 'ms': 1, 'fejl': None}) as probe:
            A._probe_alle(0)
            kaldt = {c.args[0] for c in probe.call_args_list}
            self.assertNotIn(self.m_test, kaldt)
            self.assertIn(self.m_ok, kaldt)
            r = self.c.post(f'/api/maskiner/{self.m_test}/ping', headers=AUTH).get_json()
            self.assertEqual(r['status'], 'test')
        self.assertEqual(self.c.post(f'/api/maskiner/{self.m_test}/test', headers=AUTH).status_code, 409)

    def test_status_viser_testserver(self):
        s = self.c.get('/api/status', headers=AUTH).get_json()
        self.assertEqual(s['server'], {'navn': 'LAASENGRAVE01-TEST', 'testserver': True, 'send_til': [self.m_ok]})
        self.assertEqual(s['maskiner'][str(self.m_test)], 'test')

    def test_normal_server_sender_som_altid(self):
        with mock.patch.object(A, 'TESTSERVER', False):
            self.batch(self.m_test)
            send = mock.Mock(return_value=b'')
            self.koer(self.m_test, send)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(os.listdir(self.dir), [])
            self.assertFalse(self.c.get('/api/status', headers=AUTH).get_json()['server']['testserver'])



class SammenlignV611(unittest.TestCase):
    """tools/sammenlign_v611.py: et gemt program for en v6.1-template er identisk
    med det den RIGTIGE v6.1.1-kode (fra git-tagget) bygger."""
    def test_identisk_og_forklaret_forskel(self):
        import subprocess
        rod = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if subprocess.run(['git', '-C', rod, 'rev-parse', '-q', '--verify', 'v6.1.1^{commit}'], capture_output=True).returncode:
            self.skipTest('git-tagget v6.1.1 findes ikke i denne checkout')
        A.init_db()
        mappe = tempfile.mkdtemp()
        with sqlite3.connect(A.DB) as db:
            mid = db.execute("INSERT INTO maskiner (navn,model,ip,port,protokol,offset_x,optimering) VALUES ('Sml','S5','127.0.0.1',9,'gcode',0.7,'ingen')").lastrowid
            tid = db.execute("INSERT INTO templates (navn,noejle_type,zone_bredde_mm,zone_hoejde_mm,grid_json,system_font,kun_block) "
                             "VALUES ('Sml','X',18,8,'{}','romans',1)").lastrowid
            b = db.execute("INSERT INTO job_batches (navn,template_id,maskine_id,loebe_til,status) VALUES ('b',?,?,1,'pending')", (tid, mid)).lastrowid
            db.execute("INSERT INTO jobs (batch_id,slot_nr,slot_x_mm,slot_y_mm,system_nr,type_felt,loebe_nr) VALUES (?,1,24,11,'ÆA09','L1','7')", (b,))
        with mock.patch.multiple(A, TESTSERVER=True, TEST_SEND_TIL=set(), TOERKOERSEL_DIR=mappe), closing(A._db()) as db:
            A._koer_naeste_batch(db, mid)
        kør = lambda: subprocess.run([sys.executable, os.path.join(rod, 'tools', 'sammenlign_v611.py'), '--db', A.DB, '--mappe', mappe],
                                     capture_output=True, text=True, timeout=120)
        r = kør()
        self.assertIn('IDENTISK', r.stdout, r.stdout + r.stderr)
        self.assertIn('1 identiske med v6.1.1, 0 ændrede', r.stdout)
        # Slår man Block-låsen fra, er det forklaret
        with sqlite3.connect(A.DB) as db:
            db.execute("UPDATE templates SET kun_block=0 WHERE id=?", (tid,))
        for f in os.listdir(mappe):
            os.remove(os.path.join(mappe, f))
        with sqlite3.connect(A.DB) as db:
            db.execute("UPDATE job_batches SET status='pending' WHERE id=?", (b,))
        with mock.patch.multiple(A, TESTSERVER=True, TEST_SEND_TIL=set(), TOERKOERSEL_DIR=mappe), closing(A._db()) as db:
            A._koer_naeste_batch(db, mid)
        r = kør()
        self.assertIn('ÆNDRET', r.stdout)
        self.assertIn('Block (som i v6.1)', r.stdout)


class NeutraliserKopi(unittest.TestCase):
    """tools/neutraliser_kopi.py på en kopi af en v6.1.1-database."""
    def test_ventende_jobs_saettes_ud_af_spil_og_data_bevares(self):
        import subprocess
        rod = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_sti = os.path.join(tempfile.mkdtemp(), 'kopi.db')
        with sqlite3.connect(db_sti) as db, open(os.path.join(rod, 'tests', 'fixtures', 'schema_v611.sql'), encoding='utf-8') as f:
            db.executescript(f.read())
            db.execute("INSERT INTO maskiner (navn,model,ip,port,protokol,offset_x) VALUES ('M','S5','1.2.3.4',1,'gcode',1.25)")
            db.execute("INSERT INTO templates (navn,noejle_type,zone_bredde_mm,zone_hoejde_mm,grid_json,system_font) "
                       "VALUES ('T','X',18,8,'{}','romans')")
            for st in ('pending', 'on-hold', 'running', 'done', 'fejl'):
                db.execute("INSERT INTO job_batches (navn,template_id,maskine_id,loebe_til,status) VALUES (?,1,1,1,?)", (st, st))
            db.execute("INSERT INTO skilte_jobs (navn,maskine_id,skilt_bredde_mm,skilt_hoejde_mm,linjer_json,status) "
                       "VALUES ('s',1,100,50,'[]','pending')")
        r = subprocess.run([sys.executable, os.path.join(rod, 'tools', 'neutraliser_kopi.py'), db_sti, '--fra', 'LAASENGRAVE01'],
                           capture_output=True, text=True, timeout=60, env={**os.environ, 'NGRAVE_DB': db_sti})
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        with sqlite3.connect(db_sti) as db:
            st = dict(db.execute("SELECT navn, status FROM job_batches"))
            self.assertEqual(st, {'pending': 'fejl', 'on-hold': 'fejl', 'running': 'fejl', 'done': 'done', 'fejl': 'fejl'})
            self.assertEqual(db.execute("SELECT COUNT(*) FROM job_batches WHERE fejl_kode='kopi'").fetchone()[0], 3)
            self.assertIn('LAASENGRAVE01', db.execute("SELECT fejl_besked FROM job_batches WHERE navn='pending'").fetchone()[0])
            self.assertEqual(db.execute("SELECT status, fejl_kode FROM skilte_jobs").fetchone(), ('fejl', 'kopi'))
            self.assertEqual(db.execute("SELECT offset_x FROM maskiner").fetchone()[0], 1.25)
            self.assertEqual(db.execute("SELECT kun_block FROM templates WHERE navn='T'").fetchone()[0], 1)
        self.assertIn('Ventende jobs', r.stdout)


if __name__ == '__main__':
    unittest.main()
