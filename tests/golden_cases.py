"""Faste test-tilfælde til regressions-tjek af gravér-output.

`tests/golden_v61.json` indeholder SHA-256 af det output v6.1/v6.2-koden lavede
FØR font-motoren blev skrevet om. Testene i test_fonts.py genberegner outputtet
med *kompatibilitets-indstillingerne* (ingen sti-optimering, AE/OE/AA som før)
og kræver at det er byte-for-byte identisk — så eksisterende templates på
flåden graverer præcis som de altid har gjort.

Kør `python3 -m tests.golden_cases --skriv` for at (gen)skabe filen. Det må
KUN gøres mod en kode-version man stoler på (dvs. aldrig bare for at få en
fejlende test til at gå igennem).
"""
import hashlib
import json
import os
import sys

HER = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HER, 'golden_v61.json')

FONTE = ['block', 'futural', 'futuram', 'rowmans', 'rowmand', 'rowmant', 'timesr', 'timesrb',
         'timesi', 'timesib', 'scripts', 'scriptc', 'cursive', 'gothgrt', 'gothgbt',
         'gothiceng', 'gothicger', 'gothicita', 'romans', 'italict', 'ukendt_font']

JOBS = [
    {'slot_x_mm': 24, 'slot_y_mm': 11, 'type_felt': 'L1', 'system_nr': 'A0938E', 'loebe_nr': '17', 'ekstra_tekst': ''},
    {'slot_x_mm': 74, 'slot_y_mm': 11, 'type_felt': 'HOVEDDØR', 'system_nr': 'Æble-Øst/Å 12', 'loebe_nr': '018', 'ekstra_tekst': 'Kælder 3.'},
    {'slot_x_mm': 124, 'slot_y_mm': 77, 'type_felt': 'X', 'system_nr': 'abc xyz 0O', 'loebe_nr': 'P-0019-S', 'ekstra_tekst': 'Ægte æøå'},
]


def tmpl(font, **kw):
    t = {
        'z_op_mm': 5.0, 'prox_offset_mm': 1.5, 'feed_xy': 12, 'feed_z': 40, 'spindle_rpm': 16000,
        'zone_bredde_mm': 18.0, 'tekst_hoejde_mm': 3.5, 'font': 'block',
        'markering_aktiv': 1, 'markering_x': 0, 'markering_y': 0, 'markering_justering': 'venstre',
        'markering_font': font, 'markering_hoejde_mm': 0, 'markering_bogstav_afstand_mm': 0,
        'system_aktiv': 1, 'system_x': 0, 'system_y': 5, 'system_justering': 'center',
        'system_font': font, 'system_hoejde_mm': 2.5, 'system_bogstav_afstand_mm': 0.3,
        'loebe_aktiv': 1, 'loebe_x': 0, 'loebe_y': 0, 'loebe_justering': 'hoejre',
        'loebe_font': None, 'loebe_hoejde_mm': 0, 'loebe_bogstav_afstand_mm': 0,
        'ekstra_aktiv': 1, 'ekstra_x': 1, 'ekstra_y': 10, 'ekstra_justering': 'venstre',
        'ekstra_font': font, 'ekstra_hoejde_mm': 3, 'ekstra_bogstav_afstand_mm': -0.2,
        'offset_x': 1.5, 'offset_y': -2.0, 'offset_z': 0.5,
        'spejl_y': False,
        'felt_markering_dx': 0.0, 'felt_markering_dy': 0.0, 'felt_system_dx': 0.2,
        'felt_system_dy': -0.1, 'felt_loebe_dx': 0.0, 'felt_loebe_dy': 0.0,
        'felt_ekstra_dx': 0.0, 'felt_ekstra_dy': 0.3,
    }
    t.update(kw)
    return t


SKILTE = [
    {'skilt_bredde_mm': 200, 'skilt_hoejde_mm': 100, 'linjer_json': [
        {'tekst': 'Reception', 'justering': 'center', 'hoejde_mm': 14, 'font': 'futural'},
        {'tekst': 'Kontor 2 - 1. sal', 'justering': 'center', 'hoejde_mm': 8, 'font': 'rowmant'}]},
    {'skilt_bredde_mm': 300, 'skilt_hoejde_mm': 120, 'margin_top_mm': 12, 'margin_bottom_mm': 15,
     'linjer_json': [
        {'tekst': 'Dr. Hansen', 'justering': 'venstre', 'hoejde_mm': 18, 'font': 'scriptc'},
        {'tekst': 'Tandlaege', 'justering': 'hoejre', 'hoejde_mm': 10, 'font': 'gothgrt'},
        {'tekst': 'ABC 123', 'justering': 'center', 'hoejde_mm': 9, 'font': 'block'}]},
    {'skilt_bredde_mm': 150, 'skilt_hoejde_mm': 60, 'linje_afstand_mm': 20, 'feed_xy': 20, 'spindle_rpm': 18000,
     'linjer_json': [
        {'tekst': 'Gang A', 'justering': 'center', 'hoejde_mm': 12, 'font': 'timesi', 'x_mm': 10, 'y_mm': 30},
        {'tekst': 'Exit', 'justering': 'center', 'hoejde_mm': 8, 'font': 'cursive'}]},
]


def _h(s):
    return {'sha256': hashlib.sha256(s.encode('utf-8')).hexdigest(), 'linjer': s.count('\n')}


def beregn(gcode_byg, cipher_byg, skilt_byg):
    """gcode_byg(jobs, tmpl), cipher_byg(jobs, tmpl), skilt_byg(skilt) -> str."""
    ud = {}
    for f in FONTE:
        ud[f'gcode/{f}'] = _h(gcode_byg(JOBS, tmpl(f)))
        ud[f'cipher/{f}'] = _h(cipher_byg(JOBS, tmpl(f)))
        ud[f'cipher-spejl/{f}'] = _h(cipher_byg(JOBS, tmpl(f, spejl_y=True)))
    for i, s in enumerate(SKILTE):
        ud[f'skilt/{i}'] = _h(skilt_byg(json.loads(json.dumps(s))))
    return ud


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(HER))
    from workers import gcode_worker, cipher_worker, skilt_worker
    ud = beregn(gcode_worker.byg_batch, cipher_worker.byg_batch, skilt_worker.byg_skilt)
    if '--skriv' in sys.argv:
        with open(GOLDEN, 'w', encoding='utf-8') as fh:
            json.dump(ud, fh, indent=1, sort_keys=True)
        print(f'Skrev {len(ud)} tilfælde til {GOLDEN}')
    else:
        print(json.dumps(ud, indent=1, sort_keys=True)[:2000])
