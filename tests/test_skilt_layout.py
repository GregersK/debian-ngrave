"""Tests af skilt-layoutmotoren (bounds, centrering, forhåndsvisning == G-code)."""
import json, os, re, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from workers.skilt_worker import layout_skilt, byg_skilt, MM


def mk(linjer, b=200, h=100, **kw):
    d = {'skilt_bredde_mm': b, 'skilt_hoejde_mm': h, 'linjer_json': json.dumps(linjer)}
    d.update(kw)
    return d


class Bounds(unittest.TestCase):
    def test_tekst_over_toppen_afvises(self):
        sk = mk([{'tekst': 'HEJ', 'hoejde_mm': 20, 'font': 'block', 'y_mm': 5}])
        self.assertFalse(layout_skilt(sk)['ok'])
        with self.assertRaises(ValueError):
            byg_skilt(sk)

    def test_for_bred_tekst_afvises(self):
        sk = mk([{'tekst': 'DETTE ER EN MEGET LANG TEKST', 'hoejde_mm': 30, 'font': 'timesr'}], b=100)
        r = layout_skilt(sk)
        self.assertFalse(r['ok'])
        self.assertIn('højre kant', ' '.join(r['fejl']))

    def test_manuel_x_uden_for_venstre_kant(self):
        self.assertFalse(layout_skilt(mk([{'tekst': 'TEST', 'hoejde_mm': 15, 'x_mm': -20}]))['ok'])

    def test_nedstrygere_taelles_med(self):
        # script-font har nedstrygere: baseline tæt på bunden → rager under
        sk = mk([{'tekst': 'gjy', 'hoejde_mm': 30, 'font': 'scriptc', 'y_mm': 98}])
        self.assertFalse(layout_skilt(sk)['ok'])

    def test_tom_linje_ignoreres(self):
        r = layout_skilt(mk([{'tekst': '', 'hoejde_mm': 10}, {'tekst': 'HEJ', 'hoejde_mm': 10}]))
        self.assertTrue(r['ok'])

    def test_max_linjer(self):
        self.assertFalse(layout_skilt(mk([{'tekst': 'A', 'hoejde_mm': 3}] * 11))['ok'])


class Placering(unittest.TestCase):
    def test_enkelt_linje_er_lodret_og_vandret_centreret(self):
        r = layout_skilt(mk([{'tekst': 'HEJ', 'hoejde_mm': 20, 'font': 'block', 'justering': 'center'}]))
        x0, y0, x1, y1 = r['linjer'][0]['bbox']
        self.assertAlmostEqual((y0 + y1) / 2, 50, delta=0.6)
        self.assertAlmostEqual((x0 + x1) / 2, 100, delta=0.6)

    def test_margen_er_afstand_til_teksten(self):
        r = layout_skilt(mk([{'tekst': 'Direktør', 'hoejde_mm': 12, 'font': 'timesr', 'justering': 'center'},
                             {'tekst': 'Møde', 'hoejde_mm': 8, 'font': 'timesr', 'justering': 'center'}]))
        self.assertTrue(r['ok'])
        self.assertAlmostEqual(r['linjer'][0]['bbox'][1], 10, delta=0.6)   # 10 mm top-margen

    def test_fem_linjer_fordeles(self):
        r = layout_skilt(mk([{'tekst': t, 'hoejde_mm': 8, 'font': 'rowmans'} for t in ('A', 'B', 'C', 'D', 'E')]))
        self.assertTrue(r['ok'])
        ys = [l['y'] for l in r['linjer']]
        self.assertEqual(ys, sorted(ys))

    def test_overlap_giver_advarsel(self):
        r = layout_skilt(mk([{'tekst': 'AAA', 'hoejde_mm': 30, 'font': 'block'}] * 3))
        self.assertTrue(any('overlapper' in a for a in r['advarsler']))

    def test_ugyldigt_tegn_giver_advarsel(self):
        r = layout_skilt(mk([{'tekst': 'Pris 5€', 'hoejde_mm': 10, 'font': 'block'}]))
        self.assertTrue(any('€' in a for a in r['advarsler']))


class Paritet(unittest.TestCase):
    def test_preview_og_gcode_bruger_samme_koordinater(self):
        sk = mk([{'tekst': 'Køkken', 'hoejde_mm': 15, 'font': 'timesr', 'justering': 'center'}])
        lay, g = layout_skilt(sk), byg_skilt(sk)
        m = re.search(r'G0 X(-?[\d.]+) Y(-?[\d.]+)', g)
        gx, gy = float(m[1]) / MM, float(m[2]) / MM
        px, py = lay['linjer'][0]['paths'][0][0]
        self.assertAlmostEqual(gx, px, delta=0.02)
        self.assertAlmostEqual(-gy, py, delta=0.02)

    def test_gcode_har_spindel_og_afslutning(self):
        g = byg_skilt(mk([{'tekst': 'HEJ', 'hoejde_mm': 10, 'font': 'block'}], feed_xy=99, spindle_rpm=12345))
        self.assertIn('M3 S12345', g)
        self.assertIn('F99', g)
        self.assertTrue(g.rstrip().endswith('M30'))


if __name__ == '__main__':
    unittest.main()
