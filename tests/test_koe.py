"""Kø og online-kontrol: én tråd pr. maskine, retry kun ved forbindelsesfejl, probe-regler.

Der bruges rigtige sockets mod localhost (ingen rigtige maskiner) og en stub for
selve sendingen, så testene er hurtige og deterministiske."""
import base64, os, socket, sqlite3, sys, tempfile, threading, time, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

_tmp0 = tempfile.mkdtemp()
os.environ.setdefault('NGRAVE_DB', os.path.join(_tmp0, 'x.db'))
os.environ.setdefault('NGRAVE_AUTH_USER', 'u')
os.environ.setdefault('NGRAVE_AUTH_PASS', 'p')
os.environ.setdefault('NGRAVE_UPDATE_LOG', os.path.join(_tmp0, 'u.log'))
os.environ.setdefault('NGRAVE_HEARTBEAT', os.path.join(_tmp0, 'hb'))
import app as A  # noqa: E402
from workers import forbindelse as F  # noqa: E402

AUTH = {'Authorization': 'Basic ' + base64.b64encode(
    f"{os.environ['NGRAVE_AUTH_USER']}:{os.environ['NGRAVE_AUTH_PASS']}".encode()).decode()}
LINJER = '[{"tekst":"HEJ","font":"block","hoejde_mm":10,"justering":"center"}]'


class FakeMaskine:
    """Lytter på en port, gemmer det den modtager og lukker."""
    def __init__(self):
        self.srv = socket.socket()
        self.srv.bind(('127.0.0.1', 0))
        self.srv.listen(5)
        self.port = self.srv.getsockname()[1]
        self.modtaget = []
        self.forbindelser = 0
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            self.forbindelser += 1
            c.settimeout(0.3)
            data = b''
            try:
                while True:
                    d = c.recv(4096)
                    if not d:
                        break
                    data += d
            except OSError:
                pass
            self.modtaget.append(data)
            c.close()

    def luk(self):
        self.srv.close()


def lukket_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._gammel_db = A.DB
        A.DB = os.path.join(tempfile.mkdtemp(), 'koe.db')
        A.init_db()
        cls.c = A.app.test_client()

    @classmethod
    def tearDownClass(cls):
        A.DB = cls._gammel_db

    def setUp(self):
        A._nede_til.clear()
        self._patch = mock.patch.multiple(A, SEND_PAUSE=(0.01, 0.01), NEDE_VINDUE=30.0, SEND_FORSOEG=3)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        with sqlite3.connect(A.DB) as db:
            db.execute("DELETE FROM skilte_jobs")
            db.execute("DELETE FROM jobs")
            db.execute("DELETE FROM job_batches")
            db.commit()

    def maskine(self, port, protokol='gcode', navn='M'):
        with sqlite3.connect(A.DB) as db:
            cur = db.execute("INSERT INTO maskiner (navn,model,ip,port,protokol) VALUES (?,?,?,?,?)",
                             (navn, 'S5', '127.0.0.1', port, protokol))
            db.commit()
            mid = cur.lastrowid
        self.addCleanup(F.glem, mid)
        return mid

    def skilt(self, mid, status='pending'):
        with sqlite3.connect(A.DB) as db:
            cur = db.execute("INSERT INTO skilte_jobs (navn,maskine_id,skilt_bredde_mm,skilt_hoejde_mm,linjer_json,status) "
                             "VALUES ('s',?,200,100,?,?)", (mid, LINJER, status))
            db.commit()
            return cur.lastrowid

    def rk(self, tabel, id):
        with sqlite3.connect(A.DB) as db:
            db.row_factory = sqlite3.Row
            return dict(db.execute(f"SELECT * FROM {tabel} WHERE id=?", (id,)).fetchone())

    def koer(self, mid):
        with A.closing(A._db()) as db:
            return A._koer_naeste_skilt(db, mid)


class Probe(Base):
    def test_online_sender_aldrig_data(self):
        fm = FakeMaskine(); self.addCleanup(fm.luk)
        r = F.probe('127.0.0.1', fm.port)
        self.assertEqual(r['status'], 'online')
        time.sleep(0.5)
        self.assertEqual(fm.modtaget, [b''])      # forbindelse åbnet og lukket — ingen bytes

    def test_lukket_port_er_afviser(self):
        r = F.probe('127.0.0.1', lukket_port())
        self.assertEqual(r['status'], 'afviser')
        self.assertIn('afviste', r['fejl'])

    def test_probe_springes_over_mens_der_sendes(self):
        fm = FakeMaskine(); self.addCleanup(fm.luk)
        mid = self.maskine(fm.port)
        with F.send_laas(mid):
            self.assertIsNone(F.probe_maskine(mid, '127.0.0.1', fm.port))
        self.assertEqual(fm.forbindelser, 0)

    def test_probe_venter_efter_sending_men_manuel_gaar_igennem(self):
        fm = FakeMaskine(); self.addCleanup(fm.luk)
        mid = self.maskine(fm.port)
        F.noter(mid, 'online', 'job', sendt=True)
        self.assertIsNone(F.probe_maskine(mid, '127.0.0.1', fm.port, kun_hvis_rolig_sek=120))   # baggrund: lad den være
        self.assertEqual(F.probe_maskine(mid, '127.0.0.1', fm.port)['status'], 'online')         # knap: spørg alligevel

    def test_ping_api_og_status(self):
        fm = FakeMaskine(); self.addCleanup(fm.luk)
        mid = self.maskine(fm.port)
        r = self.c.post(f'/api/maskiner/{mid}/ping', headers=AUTH).get_json()
        self.assertEqual(r['status'], 'online')
        st = {m['id']: m for m in self.c.get('/api/maskiner/status', headers=AUTH).get_json()}
        self.assertEqual(st[mid]['status'], 'online')
        self.assertEqual(st[mid]['kilde'], 'probe')
        self.assertEqual(self.c.get('/api/status', headers=AUTH).get_json()['maskiner'][str(mid)], 'online')
        self.assertEqual(self.c.post('/api/maskiner/9999/ping', headers=AUTH).status_code, 404)

    def test_offline_taeller_i_status(self):
        mid = self.maskine(lukket_port())
        self.c.post(f'/api/maskiner/{mid}/ping', headers=AUTH)
        self.assertGreaterEqual(self.c.get('/api/status', headers=AUTH).get_json()['maskiner_offline'], 1)


class TestPosition(Base):
    def test_kraever_bekraeftelse_naar_maskinen_lige_har_faaet_et_program(self):
        mid = self.maskine(1)
        F.noter(mid, 'online', 'job', sendt=True)
        send = mock.Mock(return_value=b'')
        with mock.patch('workers.gcode_worker.send', send):
            r = self.c.post(f'/api/maskiner/{mid}/test', headers=AUTH)
            self.assertEqual(r.status_code, 409)
            self.assertTrue(r.get_json()['kraever_bekraeftelse'])
            self.assertEqual(send.call_count, 0)
            r = self.c.post(f'/api/maskiner/{mid}/test', json={'tving': True}, headers=AUTH)
            self.assertEqual((r.status_code, send.call_count), (200, 1))

    def test_dobbelt_test_kraever_ikke_bekraeftelse(self):
        mid = self.maskine(1)
        with mock.patch('workers.gcode_worker.send', return_value=b''):
            self.assertEqual(self.c.post(f'/api/maskiner/{mid}/test', headers=AUTH).status_code, 200)
            self.assertEqual(self.c.post(f'/api/maskiner/{mid}/test', headers=AUTH).status_code, 200)   # test-pos graverer ikke

    def test_doed_maskine_giver_klar_fejl(self):
        mid = self.maskine(lukket_port())
        r = self.c.post(f'/api/maskiner/{mid}/test', headers=AUTH)
        self.assertEqual(r.status_code, 502)
        self.assertIn('afviste', r.get_json()['fejl'])
        self.assertEqual(F.hent(mid)['status'], 'afviser')


class Koe(Base):
    def test_forbindelsesfejl_proever_igen_og_lykkes(self):
        mid = self.maskine(1); sid = self.skilt(mid)
        kald = []
        def send(payload, ip, port):
            kald.append(1)
            if len(kald) < 3:
                raise F.ForbindelsesFejl('timeout', 'Maskinen svarede ikke (timeout)')
        with mock.patch('workers.gcode_worker.send', send):
            self.assertTrue(self.koer(mid))
        r = self.rk('skilte_jobs', sid)
        self.assertEqual((len(kald), r['status'], r['fejl_besked'], r['fejl_kode']), (3, 'done', None, None))

    def test_opgivet_forbindelse_giver_fejl_kode_og_fail_fast(self):
        mid = self.maskine(1); s1, s2 = self.skilt(mid), self.skilt(mid)
        kald = []
        def send(payload, ip, port):
            kald.append(1)
            raise F.ForbindelsesFejl('timeout', 'Maskinen svarede ikke (timeout)')
        with mock.patch('workers.gcode_worker.send', send):
            self.koer(mid)
            self.assertEqual(len(kald), 3)                  # alle forsøg brugt på første job
            self.koer(mid)
            self.assertEqual(len(kald), 3)                  # job 2 fejler straks — ingen nye forsøg
        for sid in (s1, s2):
            r = self.rk('skilte_jobs', sid)
            self.assertEqual((r['status'], r['fejl_kode']), ('fejl', 'forbindelse'))
            self.assertIn('svarede ikke', r['fejl_besked'])

    def test_gentag_fejlede_saetter_kun_forbindelsesfejl_tilbage(self):
        mid = self.maskine(1); s1, s2 = self.skilt(mid), self.skilt(mid)
        with mock.patch('workers.gcode_worker.send', side_effect=F.ForbindelsesFejl('afvist', 'Maskinen afviste')):
            self.koer(mid); self.koer(mid)
        with sqlite3.connect(A.DB) as db:      # s2 fejlede af en anden grund
            db.execute("UPDATE skilte_jobs SET fejl_kode='data' WHERE id=?", (s2,)); db.commit()
        d = self.c.post('/api/jobkoe/gentag-fejlede', json={}, headers=AUTH).get_json()
        self.assertEqual((d['skilte'], d['noegler']), (1, 0))
        self.assertEqual(self.rk('skilte_jobs', s1)['status'], 'pending')
        self.assertEqual(self.rk('skilte_jobs', s2)['status'], 'fejl')
        self.assertNotIn(mid, A._nede_til)         # ellers ville gentagelsen straks fejle igen
        with mock.patch('workers.gcode_worker.send', return_value=b''):
            self.koer(mid)
        self.assertEqual(self.rk('skilte_jobs', s1)['status'], 'done')

    def test_fejl_midt_i_sending_proeves_aldrig_igen(self):
        mid = self.maskine(1); sid = self.skilt(mid)
        send = mock.Mock(side_effect=ConnectionResetError('reset'))
        with mock.patch('workers.gcode_worker.send', send):
            self.koer(mid)
        r = self.rk('skilte_jobs', sid)
        self.assertEqual((send.call_count, r['status'], r['fejl_kode']), (1, 'fejl', 'sending'))
        self.assertIn('tjek maskinen', r['fejl_besked'])

    def test_skilt_paa_cipher_maskine_afvises(self):
        mid = self.maskine(1, protokol='cipher'); sid = self.skilt(mid)
        send = mock.Mock()
        with mock.patch('workers.gcode_worker.send', send):
            self.koer(mid)
        r = self.rk('skilte_jobs', sid)
        self.assertEqual((send.call_count, r['status'], r['fejl_kode']), (0, 'fejl', 'data'))
        d = self.c.post('/api/skilte', headers=AUTH, json={'maskine_id': mid, 'skilt_bredde_mm': 200, 'skilt_hoejde_mm': 100,
                                                          'linjer': [{'tekst': 'X', 'hoejde_mm': 10}]})
        self.assertEqual(d.status_code, 400)

    def test_noegle_batch_sendes_med_rigtigt_program(self):
        fm = FakeMaskine(); self.addCleanup(fm.luk)
        mid = self.maskine(fm.port)
        with sqlite3.connect(A.DB) as db:
            tid = db.execute("SELECT id FROM templates ORDER BY id LIMIT 1").fetchone()[0]
            bid = db.execute("INSERT INTO job_batches (navn,template_id,maskine_id,loebe_til) VALUES ('b',?,?,2)", (tid, mid)).lastrowid
            for i in (1, 2):
                db.execute("INSERT INTO jobs (batch_id,slot_nr,slot_x_mm,slot_y_mm,loebe_nr,type_felt,system_nr) VALUES (?,?,?,?,?,?,?)",
                           (bid, i, 10 * i, 10, str(i), 'A', '1'))
            db.commit()
        with A.closing(A._db()) as db:
            self.assertTrue(A._koer_naeste_batch(db, mid))
        self.assertEqual(self.rk('job_batches', bid)['status'], 'done')
        time.sleep(0.3)
        self.assertEqual(len(fm.modtaget), 1)
        self.assertIn(b'M3', fm.modtaget[0])
        self.assertEqual(F.hent(mid)['status'], 'online')
        self.assertIsNotNone(F.hent(mid)['sidst_sendt'])

    def test_en_doed_maskine_blokerer_ikke_de_andre(self):
        """A hænger i sin sending; B's job skal alligevel blive sendt (parallelle maskin-tråde)."""
        a, b = self.maskine(1, navn='A'), self.maskine(2, navn='B')
        sa, sb = self.skilt(a), self.skilt(b)
        slip = threading.Event()
        def send(payload, ip, port):
            if port == 1:
                slip.wait(10)
        A.stop_event.clear()
        t = threading.Thread(target=A.queue_worker, daemon=True)
        with mock.patch('workers.gcode_worker.send', send):
            t.start()
            try:
                for _ in range(60):
                    if self.rk('skilte_jobs', sb)['status'] == 'done':
                        break
                    time.sleep(0.1)
                self.assertEqual(self.rk('skilte_jobs', sb)['status'], 'done')
                self.assertEqual(self.rk('skilte_jobs', sa)['status'], 'running')   # A hænger stadig
            finally:
                slip.set()
                for _ in range(60):
                    if self.rk('skilte_jobs', sa)['status'] == 'done':
                        break
                    time.sleep(0.1)
                A.stop_event.set()
                t.join(5)
                A.stop_event.clear()
        self.assertEqual(self.rk('skilte_jobs', sa)['status'], 'done')

    def test_samme_maskine_koeres_serielt_i_id_raekkefoelge(self):
        mid = self.maskine(1)
        ids = [self.skilt(mid) for _ in range(3)]
        raekkefoelge, samtidige, maks = [], [0], [0]
        lock = threading.Lock()
        def send(payload, ip, port):
            with lock:
                samtidige[0] += 1; maks[0] = max(maks[0], samtidige[0])
            time.sleep(0.05)
            with lock:
                samtidige[0] -= 1
                raekkefoelge.append(1)
        A.stop_event.clear()
        t = threading.Thread(target=A.queue_worker, daemon=True)
        with mock.patch('workers.gcode_worker.send', send):
            t.start()
            for _ in range(80):
                if all(self.rk('skilte_jobs', i)['status'] == 'done' for i in ids):
                    break
                time.sleep(0.1)
            A.stop_event.set(); t.join(5); A.stop_event.clear()
        self.assertEqual(maks[0], 1)
        self.assertEqual(len(raekkefoelge), 3)


if __name__ == '__main__':
    unittest.main()
