"""Skilt Worker - Genererer G-code til skiltegravering"""
import json
from .font_manager import get_strokes

MM = 1 / 25.4

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

def byg_skilt(skilt):
    bredde  = skilt['skilt_bredde_mm']
    hoejde  = skilt['skilt_hoejde_mm']
    linjer  = json.loads(skilt['linjer_json'])
    feed    = int(skilt.get('feed_xy')      or 12)
    feed_z  = int(skilt.get('feed_z')       or 40)
    rpm     = int(skilt.get('spindle_rpm')  or 16000)
    z_up    = float(skilt.get('z_op_mm')        or 5.0)
    prox    = float(skilt.get('prox_offset_mm') or 1.5)

    # Spacing parametre
    margin_top    = float(skilt.get('margin_top_mm')    or hoejde * 0.1)
    margin_bottom = float(skilt.get('margin_bottom_mm') or hoejde * 0.1)
    linje_afstand = skilt.get('linje_afstand_mm')  # None = auto

    antal = len(linjer)
    if antal == 0:
        return ""

    # Beregn Y-positioner
    tilg = hoejde - margin_top - margin_bottom

    if antal == 1:
        y_positions = [margin_top + tilg / 2]
    elif linje_afstand is not None:
        # Manuel afstand
        la = float(linje_afstand)
        y_positions = [margin_top + i * la for i in range(antal)]
    else:
        # Auto: fordel jævnt
        spacing = tilg / (antal - 1)
        y_positions = [margin_top + i * spacing for i in range(antal)]

    # ── Beregn og VALIDÉR alle linjer FØR vi udsender bevægelses-G-code ──────
    # Sikkerhed: hvis en linje ikke passer inden for skiltets bredde/højde,
    # ville maskinen ellers gravere ud over kanten — ind i emne-holder/bord.
    # Vi bygger derfor hele skiltet i hukommelsen, tjekker at alt er inden for
    # skiltets areal, og kaster en fejl (job -> 'fejl') før spindlen tændes.
    EPS = 0.05  # mm tolerance
    beregnet = []   # (strokes, x_start, y_pos)
    fejl = []
    for i, linje in enumerate(linjer):
        tekst     = linje.get('tekst', '')
        justering = linje.get('justering', 'venstre')
        th        = float(linje.get('hoejde_mm', 10.0) or 10.0)
        font      = linje.get('font', 'block') or 'block'

        strokes, tw = get_strokes(tekst, th, font)

        # Manuel X overskriver justering
        if linje.get('x_mm') is not None:
            x_start = float(linje['x_mm'])
        elif justering == 'center':
            x_start = (bredde - tw) / 2
        elif justering == 'hoejre':
            x_start = bredde - tw - bredde * 0.05
        else:
            x_start = bredde * 0.05

        # Manuel Y overskriver auto-fordeling
        y_pos = float(linje['y_mm']) if linje.get('y_mm') is not None else y_positions[i]

        # Bounds-check (spring tomme linjer over)
        if strokes:
            if x_start < -EPS:
                fejl.append(f"Linje {i+1} starter uden for venstre kant (x={x_start:.1f}mm)")
            if x_start + tw > bredde + EPS:
                fejl.append(f"Linje {i+1} er for bred: teksten fylder {tw:.1f}mm men skiltet er {bredde:.0f}mm "
                            f"(rager {x_start + tw - bredde:.1f}mm ud over højre kant)")
            if y_pos < -EPS or y_pos > hoejde + EPS:
                fejl.append(f"Linje {i+1} er placeret uden for skiltets højde ({hoejde:.0f}mm)")

        beregnet.append((strokes, x_start, y_pos))

    if fejl:
        raise ValueError("Skiltet kan ikke graveres — teksten passer ikke: " + "; ".join(fejl))

    # ── Alt valideret → udsend G-code ───────────────────────────────────────
    lines = ["M24","G28 Z0","G20","G90",f"M3 S{rpm}"]
    for strokes, x_start, y_pos in beregnet:
        if not strokes:
            continue
        lines += streger_til_gcode(strokes, x_start, y_pos, feed, feed_z, z_up, prox)

    lines += ["G4 P0","M5","M9","M11","M246","G28 Z0","G0 X0 Y0","M30"]
    return "\n".join(lines) + "\n"
