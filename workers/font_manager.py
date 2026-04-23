"""Font Manager - Understøtter flere fonts"""
from .block_font import get_strokes as block_strokes

# Tilgængelige fonts — vises i UI
FONTS = {
    'block':    'Block (custom)',
    'futural':  'Sans-serif simpel',
    'romans':   'Roman simpel',
    'romanc':   'Roman',
    'romand':   'Roman duplex',
    'romant':   'Roman fed',
    'italics':  'Italic simpel',
    'italiccs': 'Italic',
    'italict':  'Italic fed',
    'scriptc':  'Script',
    'scripts':  'Script simpel',
    'gothgbt':  'Gothic fed',
    'gothgrt':  'Gothic',
}

def get_strokes(tekst, tekst_hoejde_mm, font='block', bogstav_afstand_mm=0.0):
    if font == 'block':
        return block_strokes(tekst, tekst_hoejde_mm, bogstav_afstand_mm)
    return hershey_strokes(tekst, tekst_hoejde_mm, font, bogstav_afstand_mm)

def hershey_strokes(tekst, tekst_hoejde_mm, font_name, bogstav_afstand_mm=0.0):
    try:
        from hershey_fonts import HersheyFonts
    except ImportError:
        return block_strokes(tekst, tekst_hoejde_mm, bogstav_afstand_mm)

    hf = HersheyFonts()
    try:
        hf.load_font(font_name)
    except:
        return block_strokes(tekst, tekst_hoejde_mm, bogstav_afstand_mm)

    hershey_height = 21.0
    scale = tekst_hoejde_mm / hershey_height

    all_strokes = []
    x_cursor = 0.0

    for ch in tekst:
        if ch == ' ':
            x_cursor += 8 * scale + bogstav_afstand_mm
            continue
        try:
            glyph = hf.get_glyph(ch)
            if not glyph or not glyph['paths']:
                x_cursor += 8 * scale + bogstav_afstand_mm
                continue
            for path in glyph['paths']:
                if path:
                    scaled = [(x_cursor + x * scale, y * scale) for (x, y) in path]
                    all_strokes.append(scaled)
            x_cursor += glyph.get('width', 16) * scale + bogstav_afstand_mm
        except:
            x_cursor += 8 * scale + bogstav_afstand_mm

    return all_strokes, x_cursor
