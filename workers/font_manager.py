"""Font Manager — enkeltstregs-skrifttyper til gravering.

Tre slags kilder:
- 'block':   nGraves egen blok-font (block_font.py) — til nøgler.
- 'hershey': Hershey-fontene fra HersheyFonts-biblioteket.
- 'svg':     medfølgende SVG-fonte i fonts/ (Relief SingleLine + EMS-serien, OFL).

Danske bogstaver: Hershey-fontene har ingen ÆØÅ. Med `dansk=True` (standard)
bygges ægte Æ Ø Å æ ø å af fontens egne bogstaver (workers/dansk.py).
`dansk=False` giver den gamle opførsel (AE/OE/AA) — bruges af nøgle-templates
der er lavet før v6.2, så de graverer præcis som de altid har gjort.

Alle funktioner returnerer (strokes, bredde_mm): strokes i mm, Y opad, baseline
i y=0, første tegns pen-position i x=0.
"""
import os
import threading

from .block_font import get_strokes as block_strokes
from . import dansk as _dansk

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts')

# ─── Register ────────────────────────────────────────────────────────────────
# Rækkefølgen er rækkefølgen i menuerne. 'vaegt' = antal parallelle linjer i
# fontens streger (bruges til ringen på Å og stregen i Ø). 'ae' = hvordan Æ
# bygges (se dansk.lav). Skjulte fonte vises ikke i menuen, men eksisterende
# templates der bruger dem graverer uændret.
_REGISTER = [
    # id            navn                     gruppe        kilde      ekstra
    ('block',       'Block',                 'Blok',       'block',   {}),
    ('relief',      'Relief',                'Sans',       'svg',     {'fil': 'relief/ReliefSingleLineSVG-Regular.svg'}),
    ('futural',     'Sans simpel',           'Sans',       'hershey', {}),
    ('futuram',     'Sans fed',              'Sans',       'hershey', {'vaegt': 2}),
    ('ems_readability',   'Readability',         'Sans',   'svg',     {'fil': 'ems/EMSReadability.svg'}),
    ('ems_readability_i', 'Readability kursiv',  'Sans',   'svg',     {'fil': 'ems/EMSReadabilityItalic.svg'}),
    ('ems_nixish',        'Nixish',              'Sans',   'svg',     {'fil': 'ems/EMSNixish.svg'}),
    ('ems_nixish_i',      'Nixish kursiv',       'Sans',   'svg',     {'fil': 'ems/EMSNixishItalic.svg'}),
    ('ems_osmotron',      'Osmotron (teknisk)',  'Sans',   'svg',     {'fil': 'ems/EMSOsmotron.svg'}),
    ('timesr',      'Times',                 'Serif',      'hershey', {}),
    ('timesrb',     'Times fed',             'Serif',      'hershey', {'vaegt': 3}),
    ('timesi',      'Times kursiv',          'Serif',      'hershey', {}),
    ('timesib',     'Times fed kursiv',      'Serif',      'hershey', {'vaegt': 3}),
    ('scripts',     'Script simpel',         'Håndskrift', 'hershey', {'ae': 'krog'}),
    ('scriptc',     'Script',                'Håndskrift', 'hershey', {'ae': 'krog', 'vaegt': 2, 'ae_lille': 'overlap', 'overlap_lille': 0.18}),
    ('cursive',     'Kursiv',                'Håndskrift', 'hershey', {'ae': 'krog'}),
    ('ems_allure',  'Allure',                'Håndskrift', 'svg',     {'fil': 'ems/EMSAllure.svg'}),
    ('ems_felix',   'Felix',                 'Håndskrift', 'svg',     {'fil': 'ems/EMSFelix.svg'}),
    ('ems_tech',    'Tech (tusch)',          'Håndskrift', 'svg',     {'fil': 'ems/EMSTech.svg'}),
    ('ems_elfin',   'Elfin',                 'Håndskrift', 'svg',     {'fil': 'ems/EMSElfin.svg'}),
    ('gothgrt',     'Gotisk (fraktur)',      'Gotisk',     'hershey', {'ae': 'flet', 'klip': 0.55, 'vaegt': 2}),
    ('gothgbt',     'Gotisk (engelsk)',      'Gotisk',     'hershey', {'ae': 'flet', 'klip': 0.62, 'vaegt': 2}),
    ('gothicita',   'Gotisk (italiensk)',    'Gotisk',     'hershey', {'ae': 'flet', 'klip': 0.85, 'vaegt': 2}),
    # Skjulte: bogstaver og tal er streg for streg de samme som en anden font.
    ('rowmans',     'Roman simpel',          'Sans',       'hershey', {'dublet_af': 'futural'}),
    ('rowmand',     'Roman',                 'Sans',       'hershey', {'dublet_af': 'futuram', 'vaegt': 2}),
    ('rowmant',     'Roman fed',             'Serif',      'hershey', {'dublet_af': 'timesrb', 'vaegt': 3}),
    ('gothiceng',   'Blackletter (engelsk)', 'Gotisk',     'hershey', {'dublet_af': 'gothgbt', 'ae': 'flet', 'klip': 0.62, 'vaegt': 2}),
    ('gothicger',   'Blackletter (tysk)',    'Gotisk',     'hershey', {'dublet_af': 'gothgrt', 'ae': 'flet', 'klip': 0.55, 'vaegt': 2}),
]

INFO = {fid: {'id': fid, 'navn': navn, 'gruppe': gruppe, 'kilde': kilde,
              'skjult': 'dublet_af' in ekstra, **ekstra}
        for fid, navn, gruppe, kilde, ekstra in _REGISTER}

# Vist i menuerne (id -> navn), i rækkefølge.
FONTS = {fid: i['navn'] for fid, i in INFO.items() if not i['skjult']}
# Alle kendte navne (også skjulte og gamle id'er) — til at vise hvad en template bruger.
ALLE_NAVNE = {fid: i['navn'] for fid, i in INFO.items()}

# Bagudkompatibilitet: gamle font-nøgler gemt i eksisterende templates/skilte.
_ALIAS = {
    'romans': 'rowmans', 'romanc': 'rowmand', 'romand': 'rowmand',
    'romant': 'rowmant', 'italics': 'timesi', 'italiccs': 'timesi',
    'italict': 'timesib',
}
for _a, _m in _ALIAS.items():
    ALLE_NAVNE.setdefault(_a, ALLE_NAVNE[_m])

# ÆØÅ findes ikke i Hershey — den gamle erstatning (bevar versal/minuskel).
_TRANSLIT = {'Æ': 'AE', 'Ø': 'OE', 'Å': 'AA', 'æ': 'ae', 'ø': 'oe', 'å': 'aa'}

# Hershey: versalhøjde i font-enheder = base_line(9) - cap_line(-12).
_CAP_UNITS = 21.0

_CACHE = {}
_LAAS = threading.Lock()


def font_id(font):
    """Normaliseret id (gamle aliaser → rigtige navne). Ukendt → 'block'."""
    f = font or 'block'
    f = _ALIAS.get(f, f)
    return f if f in INFO else 'block'


def get_strokes(tekst, tekst_hoejde_mm, font='block', bogstav_afstand_mm=0.0, dansk=True):
    """Returnerer (liste af strokes i mm, samlet bredde i mm)."""
    afst = float(bogstav_afstand_mm or 0.0)
    if not font or font == 'block':
        return block_strokes(tekst, tekst_hoejde_mm, afst)
    fid = _ALIAS.get(font, font)
    info = INFO.get(fid)
    try:
        if info and info['kilde'] == 'svg':
            return _svg_strokes(tekst, tekst_hoejde_mm, info, afst)
        return _hershey_strokes(tekst, tekst_hoejde_mm, fid, afst, dansk)
    except Exception:
        # Bibliotek/fil mangler eller ukendt font → fald tilbage til block.
        return block_strokes(tekst, tekst_hoejde_mm, afst)


def manglende_tegn(tekst, font='block'):
    """Tegn (ikke mellemrum) som skrifttypen ikke kan gravere — i rækkefølge, unikke."""
    ud = []
    for ch in dict.fromkeys(tekst or ''):
        if ch.isspace():
            continue
        s, _ = get_strokes(ch, 10.0, font)
        if not s:
            ud.append(ch)
    return ud


# ─── Hershey ─────────────────────────────────────────────────────────────────
class _Hershey:
    """En indlæst Hershey-font med glyffer omregnet til (adv, strokes) i
    font-enheder (Y opad, baseline 0) + cache af konstruerede danske tegn."""

    def __init__(self, navn):
        from HersheyFonts import HersheyFonts
        hf = HersheyFonts()
        hf.load_default_font(navn)
        self.glyffer = {}
        for ch, g in hf.all_glyphs.items():
            if len(ch) != 1:
                continue
            base, left = g.base_line, g.left_offset
            # Præcis samme regnestykke som før v6.2 (heltal), så output er bit-identisk.
            st = [[(hx - left, base - hy) for (hx, hy) in s] for s in g.strokes if s]
            self.glyffer[ch] = (g.char_width, st)
        self.opskrift = INFO.get(navn, {})
        self._dansk = {}

    def glyf(self, ch):
        return self.glyffer.get(ch)

    def dansk(self, ch):
        if ch not in self._dansk:
            self._dansk[ch] = _dansk.lav(ch, self.glyf, _CAP_UNITS, self.opskrift)
        return self._dansk[ch]


def _hent(navn):
    f = _CACHE.get(navn)
    if f is None:
        with _LAAS:
            f = _CACHE.get(navn)
            if f is None:
                f = _Hershey(navn) if INFO.get(navn, {}).get('kilde') != 'svg' else _svg_font(navn)
                _CACHE[navn] = f
    return f


def _hershey_strokes(tekst, tekst_hoejde_mm, navn, afst, dansk):
    f = _hent(navn)
    if not dansk:
        tekst = ''.join(_TRANSLIT.get(c, c) for c in tekst)
    scale = tekst_hoejde_mm / _CAP_UNITS
    ekstra = afst / scale if scale else 0
    alle = []
    x_cursor = 0.0  # i font-enheder
    for ch in tekst:
        g = f.glyf(ch)
        if g is None and ch in _dansk.DANSKE:
            g = f.dansk(ch)
        if g is None:
            continue                     # tegnet findes ikke i fonten (som før: ingen plads)
        adv, sts = g
        for s in sts:
            alle.append([((x_cursor + x) * scale, y * scale) for (x, y) in s])
        x_cursor += adv + ekstra
    return alle, x_cursor * scale


# ─── SVG-fonte ───────────────────────────────────────────────────────────────
def _svg_font(fid):
    from .svg_font import SvgFont
    return SvgFont(os.path.join(FONT_DIR, INFO[fid]['fil']))


def _svg_strokes(tekst, tekst_hoejde_mm, info, afst):
    f = _hent(info['id'])
    scale = tekst_hoejde_mm / f.cap
    # Kurver flades ud så afvigelsen er under ca. 0,4 % af teksthøjden (min. 0,02
    # mm): glat på store skilte uden tusindvis af små G-code-linjer på små.
    tol_mm = min(0.1, max(0.02, 0.004 * tekst_hoejde_mm))
    tol = tol_mm / scale
    ekstra = afst / scale if scale else 0
    alle = []
    x = 0.0
    forrige = None
    sidste_ekstra = 0.0
    for ch in tekst:
        g = f.glyf(ch, tol)
        if g is None and ch in _dansk.DANSKE:
            g = _dansk.lav(ch, lambda c: f.glyf(c, tol), f.cap, info)
        if g is None:
            forrige = None
            continue
        if forrige is not None:
            x -= f.kerning(forrige, ch)
        adv, sts = g
        for s in sts:
            alle.append([((x + px) * scale, py * scale) for (px, py) in s])
        x += adv + ekstra
        sidste_ekstra = ekstra
        forrige = ch
    return alle, (x - sidste_ekstra) * scale if alle or x else 0.0
