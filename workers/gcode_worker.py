"""S5 Worker - G-code over TCP (nøgler) med prox og relativ Z-løft"""
import socket, time
from .font_manager import get_strokes
from .forbindelse import aabn
from .optimering import optimer

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

def send(gcode, ip, port):
    # aabn() kaster ForbindelsesFejl hvis vi ikke kommer igennem — dvs. intet er sendt.
    with aabn(ip, port) as s:
        s.settimeout(15)
        s.sendall(gcode.encode("ascii", errors="ignore"))
        time.sleep(1.0)
        try: return s.recv(4096)
        except socket.timeout: return b''

# Felterne på en nøgle: (job-felt, template-præfiks, std. x, std. y, std. justering, std. aktiv)
FELTER = (
    ('type_felt',    'markering', 0, 0,  'venstre', 1),
    ('system_nr',    'system',    0, 5,  'venstre', 1),
    ('loebe_nr',     'loebe',     0, 0,  'hoejre',  1),
    ('ekstra_tekst', 'ekstra',    0, 10, 'venstre', 0),
)


def felt_def(tmpl):
    """Aktive felter: (job-felt, præfiks, x, y, justering, font, højde, bogstavafstand)."""
    th = tmpl['tekst_hoejde_mm']
    font = tmpl.get('font', 'block') or 'block'
    ud = []
    for felt_navn, p, dx, dy, djus, daktiv in FELTER:
        if not tmpl.get(f'{p}_aktiv', daktiv):
            continue
        ud.append((felt_navn, p, tmpl.get(f'{p}_x', dx), tmpl.get(f'{p}_y', dy),
                   tmpl.get(f'{p}_justering', djus), tmpl.get(f'{p}_font') or font,
                   float(tmpl.get(f'{p}_hoejde_mm') or 0) or th,
                   float(tmpl.get(f'{p}_bogstav_afstand_mm') or 0)))
    return ud


def felt_layout(job, tmpl, sx=0.0, sy=0.0):
    """Placering af hvert felt på én nøgle — bruges af BÅDE gravering og
    forhåndsvisning (så det man ser er det der graveres).

    x er stregernes pen-start (justeret i zonen), y er baseline; begge i mm med
    (sx, sy) som nøglens hjørne. Stregerne er i mm med Y opad fra baseline."""
    zw = tmpl['zone_bredde_mm']
    dansk = bool(tmpl.get('dansk_tegn', 0))
    ud = []
    for felt_navn, p, fx, fy, fjus, ffont, fth, fafstand in felt_def(tmpl):
        tekst = job.get(felt_navn, '') or ''
        if not tekst.strip():
            continue
        strokes, bredde = get_strokes(tekst, fth, ffont, fafstand, dansk)
        base_x = sx + float(fx)
        if fjus == 'hoejre':
            x = base_x + zw - bredde
        elif fjus == 'center':
            x = base_x + (zw - bredde) / 2
        else:
            x = base_x
        ud.append({'felt': p, 'tekst': tekst, 'font': ffont, 'hoejde_mm': fth,
                   'strokes': strokes, 'bredde_mm': bredde, 'x': x, 'y': sy + float(fy)})
    return ud


def byg_batch(jobs, tmpl):
    """Bygger ét samlet G-code program for alle jobs i batchen."""
    zo  = tmpl['z_op_mm']
    po  = tmpl.get('prox_offset_mm', 1.5)
    f   = tmpl['feed_xy']
    fz  = tmpl['feed_z']
    rpm = tmpl['spindle_rpm']
    ox  = float(tmpl.get('offset_x') or 0)
    oy  = float(tmpl.get('offset_y') or 0)
    oz  = float(tmpl.get('offset_z') or 0)
    zo  += oz
    niveau = tmpl.get('optimering', 'ingen')

    lines = ["M24","G28 Z0","G20","G90",f"M3 S{rpm}"]

    for job in jobs:
        sx = job['slot_x_mm'] + ox
        sy = job['slot_y_mm'] + oy
        for felt in felt_layout(job, tmpl, sx, sy):
            lines += streger_til_gcode(optimer(felt['strokes'], niveau), felt['x'], felt['y'],
                                       f, fz, zo, po)

    lines += ["G4 P0","M5","M9","M11","M246","G28 Z0","G0 X0 Y0","M30"]
    return "\n".join(lines) + "\n"
