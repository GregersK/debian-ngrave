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
    feed    = 12
    feed_z  = 40
    rpm     = 16000
    z_up    = 5.0
    prox    = 1.5

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

    lines = ["M24","G28 Z0","G20","G90",f"M3 S{rpm}"]

    for i, linje in enumerate(linjer):
        tekst     = linje['tekst']
        justering = linje.get('justering', 'venstre')
        th        = linje.get('hoejde_mm', 10.0)
        font      = linje.get('font', 'block')

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
        if linje.get('y_mm') is not None:
            y_pos = float(linje['y_mm'])
        else:
            y_pos = y_positions[i]

        lines += streger_til_gcode(strokes, x_start, y_pos, feed, feed_z, z_up, prox)

    lines += ["G4 P0","M5","M9","M11","M246","G28 Z0","G0 X0 Y0","M30"]
    return "\n".join(lines) + "\n"
