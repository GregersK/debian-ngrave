"""S5 Worker - G-code over TCP med block font og prox"""
import socket, time
from .font_manager import get_strokes

MM = 1 / 25.4

def xi(v): return round(v * MM, 4)
def yi(v): return round(-v * MM, 4)
def zi(v): return round(-v * MM, 4)

def streger_til_gcode(strokes, x_offset, y, feed, feed_z, z_up, prox_offset):
    """Genererer G-code med prox og relativ Z-løft."""
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

def byg_job(job, tmpl):
    zo  = tmpl['z_op_mm']
    po  = tmpl.get('prox_offset_mm', 1.5)
    f   = tmpl['feed_xy']
    fz  = tmpl['feed_z']
    rpm = tmpl['spindle_rpm']
    zw  = tmpl['zone_bredde_mm']
    th  = tmpl['tekst_hoejde_mm']
    sx  = job['slot_x_mm']
    sy  = job['slot_y_mm']

    # Maskin-kalibrering offset
    ox  = tmpl.get('offset_x', 0.0)
    oy  = tmpl.get('offset_y', 0.0)
    oz  = tmpl.get('offset_z', 0.0)
    sx  += ox
    sy  += oy
    zo  += oz
    
    def juster_x(base_x, tekst, justering):
        """Beregn X-position baseret på justering."""
        _, bredde = get_strokes(tekst, th, 'block')
        if justering == 'hoejre':
            return base_x + zw - bredde
        elif justering == 'center':
            return base_x + (zw - bredde) / 2
        else:  # venstre
            return base_x
    
    lines = ["M24","G28 Z0","G20","G90",f"M3 S{rpm}"]
    
    # Markering
    mark_jus = tmpl.get('markering_justering', 'venstre')
    mark_x = juster_x(sx + tmpl.get('markering_x', 0.0), job['type_felt'], mark_jus)
    mark_y = sy + tmpl.get('markering_y', 0.0)
    strokes, _ = get_strokes(job['type_felt'], th, 'block')
    lines += streger_til_gcode(strokes, mark_x, mark_y, f, fz, zo, po)
    
    # Løbenr
    loebe_jus = tmpl.get('loebe_justering', 'hoejre')
    loebe_x = juster_x(sx + tmpl.get('loebe_x', 0.0), job['loebe_nr'], loebe_jus)
    loebe_y = sy + tmpl.get('loebe_y', 0.0)
    strokes, _ = get_strokes(job['loebe_nr'], th, 'block')
    lines += streger_til_gcode(strokes, loebe_x, loebe_y, f, fz, zo, po)
    
    # Systemnr
    sys_jus = tmpl.get('system_justering', 'venstre')
    sys_x = juster_x(sx + tmpl.get('system_x', 0.0), job['system_nr'], sys_jus)
    sys_y = sy + tmpl.get('system_y', 5.0)
    strokes, _ = get_strokes(job['system_nr'], th, 'block')
    lines += streger_til_gcode(strokes, sys_x, sys_y, f, fz, zo, po)
    
    lines += ["G4 P0","M5","M9","M11","M246","G28 Z0","G0 X0 Y0","M30"]
    return "\n".join(lines) + "\n"

def send(gcode, ip, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(15)
        s.connect((ip, port))
        s.sendall(gcode.encode("ascii", errors="ignore"))
        time.sleep(1.0)
        try: return s.recv(4096)
        except socket.timeout: return b''

def byg_batch(jobs, tmpl):
    """Bygger ét samlet G-code program for alle jobs i batchen."""
    zo  = tmpl['z_op_mm']
    po  = tmpl.get('prox_offset_mm', 1.5)
    f   = tmpl['feed_xy']
    fz  = tmpl['feed_z']
    rpm = tmpl['spindle_rpm']
    zw  = tmpl['zone_bredde_mm']
    th  = tmpl['tekst_hoejde_mm']
    font = tmpl.get('font', 'block') or 'block'
    ox  = float(tmpl.get('offset_x') or 0)
    oy  = float(tmpl.get('offset_y') or 0)
    oz  = float(tmpl.get('offset_z') or 0)
    zo  += oz

    def juster_x(base_x, tekst, justering):
        _, bredde = get_strokes(tekst, th, font)
        if justering == 'hoejre':   return base_x + zw - bredde
        elif justering == 'center': return base_x + (zw - bredde) / 2
        return base_x

    # Saml aktive felter med per-felt font og hoejde
    felter = []
    if tmpl.get('markering_aktiv', 1):
        felter.append(('type_felt', tmpl.get('markering_x',0), tmpl.get('markering_y',0), tmpl.get('markering_justering','venstre'),
                       tmpl.get('markering_font') or font, float(tmpl.get('markering_hoejde_mm') or 0) or th))
    if tmpl.get('system_aktiv', 1):
        felter.append(('system_nr', tmpl.get('system_x',0), tmpl.get('system_y',5), tmpl.get('system_justering','venstre'),
                       tmpl.get('system_font') or font, float(tmpl.get('system_hoejde_mm') or 0) or th))
    if tmpl.get('loebe_aktiv', 1):
        felter.append(('loebe_nr', tmpl.get('loebe_x',0), tmpl.get('loebe_y',0), tmpl.get('loebe_justering','hoejre'),
                       tmpl.get('loebe_font') or font, float(tmpl.get('loebe_hoejde_mm') or 0) or th))
    if tmpl.get('ekstra_aktiv', 0):
        felter.append(('ekstra_tekst', tmpl.get('ekstra_x',0), tmpl.get('ekstra_y',10), tmpl.get('ekstra_justering','venstre'),
                       tmpl.get('ekstra_font') or font, float(tmpl.get('ekstra_hoejde_mm') or 0) or th))

    lines = ["M24","G28 Z0","G20","G90",f"M3 S{rpm}"]

    for job in jobs:
        sx = job['slot_x_mm'] + ox
        sy = job['slot_y_mm'] + oy

        for felt_navn, fx, fy, fjus, ffont, fth in felter:
            tekst = job.get(felt_navn, '') or ''
            if not tekst.strip():
                continue
            strokes, _ = get_strokes(tekst, fth, ffont)
            _, bredde = get_strokes(tekst, fth, ffont)
            if fjus == 'hoejre':   x = sx + float(fx) + zw - bredde
            elif fjus == 'center': x = sx + float(fx) + (zw - bredde) / 2
            else:                  x = sx + float(fx)
            y = sy + float(fy)
            lines += streger_til_gcode(strokes, x, y, f, fz, zo, po)

    lines += ["G4 P0","M5","M9","M11","M246","G28 Z0","G0 X0 Y0","M30"]
    return "\n".join(lines) + "\n"
