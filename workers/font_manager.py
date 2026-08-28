"""Font Manager — single-stroke fonts til gravering.

To font-kilder:
- 'block': custom single-stroke font (block_font.py) med ægte ÆØÅ-glyffer.
- Hershey single-stroke fonts via HersheyFonts-biblioteket (mange skrifttyper).

VIGTIGT om dansk: Hershey-fonts indeholder IKKE ÆØÅ. De substitueres til
AE/OE/AA (samme princip som block-fonten) så danske skilte stadig kan graveres
i den valgte skrifttype uden at tabe bogstaver.
"""
from .block_font import get_strokes as block_strokes

# Vist i UI-dropdown. Nøgle = font-id gemt i databasen, værdi = visningsnavn.
# Kun single-stroke skrifttyper egnet til gravering/skilte er med — de rene
# symbol-/matematik-/alfabet-fonts (greek, cyrillic, music, …) er udeladt.
FONTS = {
    'block':     'Block (single-stroke, ÆØÅ)',
    'futural':   'Sans simpel',
    'futuram':   'Sans fed',
    'rowmans':   'Roman simpel',
    'rowmand':   'Roman',
    'rowmant':   'Roman fed',
    'timesr':    'Times',
    'timesrb':   'Times fed',
    'timesi':    'Times kursiv',
    'timesib':   'Times fed kursiv',
    'scripts':   'Script simpel',
    'scriptc':   'Script',
    'cursive':   'Kursiv',
    'gothgrt':   'Gotisk',
    'gothgbt':   'Gotisk fed',
    'gothiceng': 'Blackletter (engelsk)',
    'gothicger': 'Blackletter (tysk)',
    'gothicita': 'Blackletter (italiensk)',
}

# Bagudkompatibilitet: gamle font-nøgler gemt i eksisterende templates/skilte
# (som før faldt stille tilbage til block pga. en API-fejl) mappes nu til den
# nærmeste faktiske Hershey-font, så gamle jobs renderer i en rigtig skrifttype.
_ALIAS = {
    'romans': 'rowmans', 'romanc': 'rowmand', 'romand': 'rowmand',
    'romant': 'rowmant', 'italics': 'timesi', 'italiccs': 'timesi',
    'italict': 'timesib',
}

# ÆØÅ findes ikke i Hershey — substituér (bevar versal/minuskel).
_DANSK = {'Æ': 'AE', 'Ø': 'OE', 'Å': 'AA', 'æ': 'ae', 'ø': 'oe', 'å': 'aa'}

# Hershey caps-højde i font-enheder: base_line(9) - cap_line(-12) = 21.
_CAP_UNITS = 21.0

_CACHE = {}


def get_strokes(tekst, tekst_hoejde_mm, font='block', bogstav_afstand_mm=0.0):
    """Returnerer (liste af strokes, samlet bredde i mm).

    Strokes er i mm med Y opad og baseline i y=0 — samme konvention som
    block_font, så gcode/cipher/skilt-workers kan bruge outputtet direkte.
    """
    if not font or font == 'block':
        return block_strokes(tekst, tekst_hoejde_mm, bogstav_afstand_mm)
    return hershey_strokes(tekst, tekst_hoejde_mm, font, bogstav_afstand_mm)


def _load(name):
    if name not in _CACHE:
        from HersheyFonts import HersheyFonts
        hf = HersheyFonts()
        hf.load_default_font(name)
        _CACHE[name] = hf
    return _CACHE[name]


def _dansk_translit(tekst):
    return ''.join(_DANSK.get(c, c) for c in tekst)


def hershey_strokes(tekst, tekst_hoejde_mm, font_name, bogstav_afstand_mm=0.0):
    real = _ALIAS.get(font_name, font_name)
    try:
        hf = _load(real)
    except Exception:
        # Bibliotek mangler eller ukendt font → fald tilbage til block.
        return block_strokes(tekst, tekst_hoejde_mm, bogstav_afstand_mm)

    tekst = _dansk_translit(tekst)
    scale = tekst_hoejde_mm / _CAP_UNITS
    all_strokes = []
    x_cursor = 0.0  # i font-enheder
    try:
        for g in hf.glyphs_for_text(tekst):
            base = g.base_line
            left = g.left_offset
            for stroke in g.strokes:
                if not stroke:
                    continue
                # x: læg glyffens venstrekant på x_cursor. y: flip (Hershey er
                # Y-nedad) så baseline=0 og opad er positiv.
                pts = [((x_cursor + (hx - left)) * scale, (base - hy) * scale)
                       for (hx, hy) in stroke]
                all_strokes.append(pts)
            x_cursor += g.char_width + (bogstav_afstand_mm / scale if scale else 0)
    except Exception:
        return block_strokes(tekst, tekst_hoejde_mm, bogstav_afstand_mm)

    return all_strokes, x_cursor * scale
