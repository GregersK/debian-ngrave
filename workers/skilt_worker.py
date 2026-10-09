"""Skilt Worker - layout, validering og G-code til skiltegravering.

Alt layout sker i `layout_skilt()`, som bruges af BÅDE gravering (`byg_skilt`)
og forhåndsvisningen i GUI'en (`/api/skilt/preview`). Så det man ser er det der
graveres, og validering (bounds) bruger de faktiske streger — ikke et gæt.

Koordinater: skiltets origin er øverste venstre hjørne, X mod højre, Y NEDAD
(mm). En linjes `y` er dens baseline (bunden af versaler); glyffer rager opad
fra baseline (mod mindre y), og nedstrygere (g, j, y, script) rager under den.
"""
import json
from .font_manager import get_strokes

MM = 1 / 25.4
EPS = 0.05            # mm tolerance ved bounds-check
MAX_LINJER = 10
MAX_TEKST = 200       # tegn pr. linje


def xi(v): return round(v * MM, 4)
def yi(v): return round(-v * MM, 4)


def streger_til_gcode(strokes, x_offset, y, feed, feed_z, z_up, prox_offset):
    lines = []
    z_up_rel = round(z_up * MM, 4)
    z_prox_off = round(prox_offset * MM, 4)
    for stroke in strokes:
        if not stroke: continue
        for i, (sx, sy) in enumerate(stroke):
            gx = round(xi(x_offset + sx), 4)
            gy = round(yi(y) + sy * MM, 4)
            if i == 0:
                lines.append(f"G0 X{gx} Y{gy}")
                lines.append(f"G4 P25")
                lines.append(f"G30 F{feed_z}")
                if prox_offset != 0:
                    lines.append(f"G91")
                    lines.append(f"G0 Z{z_prox_off}")
                    lines.append(f"G90")
            else:
                lines.append(f"G1 X{gx} Y{gy} F{feed}")
        lines.append(f"G91")
        lines.append(f"G0 Z{z_up_rel}")
        lines.append(f"G90")
    return lines


def _num(v, default=None):
    try:
        if v is None or v == '':
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _ugyldige_tegn(tekst, th, font):
    """Tegn (ikke mellemrum) som skrifttypen ikke kan gravere."""
    out = []
    for ch in dict.fromkeys(tekst):  # unikke, bevarer rækkefølge
        if ch.isspace():
            continue
        s, _ = get_strokes(ch, th, font)
        if not s:
            out.append(ch)
    return out


def layout_skilt(skilt):
    """Beregner placering af alle linjer og validerer at alt er inden for skiltet.

    `skilt` er en dict med skilt_bredde_mm, skilt_hoejde_mm, linjer_json (str el.
    liste) og valgfrit margin_top_mm, margin_bottom_mm, linje_afstand_mm.
    Returnerer en dict med `ok`, `fejl`, `advarsler` og pr. linje `paths` (i
    skilt-koordinater, klar til SVG) samt de interne `strokes` til G-code.
    """
    bredde = float(skilt['skilt_bredde_mm'])
    hoejde = float(skilt['skilt_hoejde_mm'])
    linjer = skilt['linjer_json']
    if isinstance(linjer, str):
        linjer = json.loads(linjer)

    fejl, advarsler = [], []
    if bredde <= 0 or hoejde <= 0:
        fejl.append("Skiltets bredde og højde skal være større end 0")
    if len(linjer) > MAX_LINJER:
        fejl.append(f"Max {MAX_LINJER} linjer pr. skilt")
        linjer = linjer[:MAX_LINJER]

    margin_top = _num(skilt.get('margin_top_mm'))
    margin_bot = _num(skilt.get('margin_bottom_mm'))
    if margin_top is None: margin_top = hoejde * 0.1
    if margin_bot is None: margin_bot = hoejde * 0.1
    la = _num(skilt.get('linje_afstand_mm'))      # None = fordel jævnt

    # Tekst-højder (bruges til automatisk lodret placering)
    ths = [(_num(l.get('hoejde_mm'), 10.0) or 10.0) for l in linjer]
    n = len(linjer)

    # Automatisk baseline-placering. Margen = afstand fra skiltets kant til
    # TEKSTEN (øverste linjes versalhøjde / nederste linjes baseline).
    y_auto = []
    if n:
        foerste = margin_top + ths[0]
        sidste = hoejde - margin_bot
        if n == 1:
            tilg = hoejde - margin_top - margin_bot
            y_auto = [margin_top + (tilg + ths[0]) / 2]   # centreret
        elif la is not None:
            y_auto = [foerste + i * la for i in range(n)]
        else:
            step = (sidste - foerste) / (n - 1)
            y_auto = [foerste + i * step for i in range(n)]

    out = []
    for i, linje in enumerate(linjer):
        tekst = str(linje.get('tekst', '') or '')
        justering = linje.get('justering', 'venstre') or 'venstre'
        th = ths[i]
        font = linje.get('font', 'block') or 'block'
        lf, la_ = [], []   # linje-fejl / -advarsler
        if len(tekst) > MAX_TEKST:
            lf.append(f"Teksten er for lang (max {MAX_TEKST} tegn)")
            tekst = tekst[:MAX_TEKST]
        if th <= 0 or th > max(bredde, hoejde) * 2:
            lf.append(f"Ugyldig teksthøjde ({th:g} mm)")
            th = 10.0

        strokes, tw = get_strokes(tekst, th, font) if tekst.strip() else ([], 0.0)

        x_man, y_man = _num(linje.get('x_mm')), _num(linje.get('y_mm'))
        if x_man is not None:
            x_start = x_man
        elif justering == 'center':
            x_start = (bredde - tw) / 2
        elif justering == 'hoejre':
            x_start = bredde - tw - bredde * 0.05
        else:
            x_start = bredde * 0.05
        y_pos = y_man if y_man is not None else (y_auto[i] if i < len(y_auto) else 0.0)

        paths, bbox = [], None
        for s in strokes:
            if not s:
                continue
            p = [[round(x_start + sx, 2), round(y_pos - sy, 2)] for (sx, sy) in s]
            paths.append(p)
        if paths:
            xs = [pt[0] for p in paths for pt in p]
            ys = [pt[1] for p in paths for pt in p]
            bbox = [min(xs), min(ys), max(xs), max(ys)]
            x0, y0, x1, y1 = bbox
            if x0 < -EPS:
                lf.append(f"rager {-x0:.1f} mm ud over venstre kant")
            if x1 > bredde + EPS:
                lf.append(f"rager {x1 - bredde:.1f} mm ud over højre kant "
                          f"(teksten er {tw:.0f} mm bred, skiltet {bredde:g} mm)")
            if y0 < -EPS:
                lf.append(f"rager {-y0:.1f} mm ud over toppen")
            if y1 > hoejde + EPS:
                lf.append(f"rager {y1 - hoejde:.1f} mm ud under bunden")
        if tekst.strip():
            ugyldige = _ugyldige_tegn(tekst, th, font)
            if ugyldige:
                la_.append("Tegn der springes over (findes ikke i skrifttypen): "
                           + " ".join(ugyldige))
            if not paths:
                lf.append("Ingen tegn kan graveres i denne skrifttype")

        out.append({
            'i': i, 'tekst': tekst, 'font': font, 'hoejde_mm': th,
            'justering': justering, 'x': round(x_start, 2), 'y': round(y_pos, 2),
            'bredde_mm': round(tw, 2), 'paths': paths, 'bbox': bbox,
            'fejl': lf, 'advarsler': la_, 'strokes': strokes,
        })

    # Overlap mellem linjer (kun advarsel — kan være tilsigtet)
    synlige = [l for l in out if l['bbox']]
    for a, b in zip(synlige, synlige[1:]):
        if a['bbox'][3] > b['bbox'][1] + EPS and a['bbox'][0] < b['bbox'][2] and b['bbox'][0] < a['bbox'][2]:
            advarsler.append(f"Linje {a['i']+1} og {b['i']+1} overlapper hinanden")

    for l in out:
        for m in l['fejl']:
            fejl.append(f"Linje {l['i']+1}: {m}")
        for m in l['advarsler']:
            advarsler.append(f"Linje {l['i']+1}: {m}")

    return {'ok': not fejl, 'bredde': bredde, 'hoejde': hoejde,
            'fejl': fejl, 'advarsler': advarsler, 'linjer': out}


def byg_skilt(skilt):
    """Bygger G-code. Kaster ValueError (→ job 'fejl') FØR spindlen tændes hvis
    noget ikke passer inden for skiltet."""
    feed   = int(_num(skilt.get('feed_xy'), 0)     or 12)
    feed_z = int(_num(skilt.get('feed_z'), 0)      or 40)
    rpm    = int(_num(skilt.get('spindle_rpm'), 0) or 16000)
    z_up   = float(_num(skilt.get('z_op_mm'), 0)        or 5.0)
    prox   = float(_num(skilt.get('prox_offset_mm'), 0) or 1.5)

    lay = layout_skilt(skilt)
    if not lay['linjer']:
        return ""
    if not lay['ok']:
        raise ValueError("Skiltet kan ikke graveres — " + "; ".join(lay['fejl']))

    lines = ["M24", "G28 Z0", "G20", "G90", f"M3 S{rpm}"]
    for l in lay['linjer']:
        if not l['strokes']:
            continue
        lines += streger_til_gcode(l['strokes'], l['x'], l['y'], feed, feed_z, z_up, prox)
    lines += ["G4 P0", "M5", "M9", "M11", "M246", "G28 Z0", "G0 X0 Y0", "M30"]
    return "\n".join(lines) + "\n"
