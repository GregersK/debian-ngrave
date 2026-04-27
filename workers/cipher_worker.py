"""S3 Worker — CIPHER CEF over RS232/Ethernet"""
import socket, time
from .font_manager import get_strokes

SPM = 40  # steps per mm

def s(v): return round(v * SPM)

def strokes_til_cipher(strokes, x_offset, y_offset, spejl_y=False):
    """Konverterer stroke-liste til CIPHER CEF kommandoer."""
    cmds = []
    pen = False
    for stroke in strokes:
        if not stroke: continue
        for i, (sx, sy) in enumerate(stroke):
            gx = s(x_offset + sx)
            gy = s(y_offset - sy) if spejl_y else s(y_offset + sy)
            if i == 0:
                if pen:
                    cmds.append("PU")
                    pen = False
                cmds.append(f"PA{gx},{gy}")
                cmds.append("PD")
                pen = True
            else:
                cmds.append(f"PA{gx},{gy}")
    if pen:
        cmds.append("PU")
    return cmds

def byg_job_cmds(job, tmpl):
    """Bygger CIPHER kommandoer for ét job (uden IN/FR og afslutning)."""
    zw      = tmpl['zone_bredde_mm']
    th      = tmpl['tekst_hoejde_mm']
    font    = tmpl.get('font', 'block') or 'block'
    spejl_y = bool(tmpl.get('spejl_y', False))
    sx  = job['slot_x_mm'] + float(tmpl.get('offset_x') or 0)
    sy  = job['slot_y_mm'] + float(tmpl.get('offset_y') or 0)

    def juster_x(base_x, tekst, justering, ffont, fth, fafstand):
        _, bredde = get_strokes(tekst, fth, ffont, fafstand)
        if justering == 'hoejre':   return base_x + zw - bredde
        elif justering == 'center': return base_x + (zw - bredde) / 2
        return base_x

    felter = []
    if tmpl.get('markering_aktiv', 1):
        felter.append(('type_felt', 'markering', tmpl.get('markering_x',0), tmpl.get('markering_y',0), tmpl.get('markering_justering','venstre'),
                       tmpl.get('markering_font') or font, float(tmpl.get('markering_hoejde_mm') or 0) or th,
                       float(tmpl.get('markering_bogstav_afstand_mm') or 0)))
    if tmpl.get('system_aktiv', 1):
        felter.append(('system_nr', 'system', tmpl.get('system_x',0), tmpl.get('system_y',5), tmpl.get('system_justering','venstre'),
                       tmpl.get('system_font') or font, float(tmpl.get('system_hoejde_mm') or 0) or th,
                       float(tmpl.get('system_bogstav_afstand_mm') or 0)))
    if tmpl.get('loebe_aktiv', 1):
        felter.append(('loebe_nr', 'loebe', tmpl.get('loebe_x',0), tmpl.get('loebe_y',0), tmpl.get('loebe_justering','hoejre'),
                       tmpl.get('loebe_font') or font, float(tmpl.get('loebe_hoejde_mm') or 0) or th,
                       float(tmpl.get('loebe_bogstav_afstand_mm') or 0)))
    if tmpl.get('ekstra_aktiv', 0):
        felter.append(('ekstra_tekst', 'ekstra', tmpl.get('ekstra_x',0), tmpl.get('ekstra_y',10), tmpl.get('ekstra_justering','venstre'),
                       tmpl.get('ekstra_font') or font, float(tmpl.get('ekstra_hoejde_mm') or 0) or th,
                       float(tmpl.get('ekstra_bogstav_afstand_mm') or 0)))

    cmds = []
    for felt_navn, felt_key, fx, fy, fjus, ffont, fth, fafstand in felter:
        tekst = job.get(felt_navn, '') or ''
        if not tekst.strip():
            continue
        strokes, bredde = get_strokes(tekst, fth, ffont, fafstand)
        dx = float(tmpl.get(f'felt_{felt_key}_dx') or 0)
        dy = float(tmpl.get(f'felt_{felt_key}_dy') or 0)
        x = juster_x(sx + float(fx) + dx, tekst, fjus, ffont, fth, fafstand)
        y = sy - (float(fy) + dy) if spejl_y else sy + float(fy) + dy
        cmds += strokes_til_cipher(strokes, x, y, spejl_y)

    return cmds

def byg_job(job, tmpl):
    """Bygger komplet CIPHER streng for ét enkelt job."""
    f   = tmpl['feed_xy']
    cmds = ["IN", "ZD0", f"FR{f}"]
    cmds += byg_job_cmds(job, tmpl)
    cmds.append("PA0,0")
    return ";".join(cmds) + ";|"

def byg_batch(jobs, tmpl):
    """Bygger ét samlet CIPHER program for alle jobs i batchen."""
    f   = tmpl['feed_xy']
    cmds = ["IN", "ZD0", f"FR{f}"]
    for job in jobs:
        cmds += byg_job_cmds(job, tmpl)
    cmds.append("PA0,0")
    return ";".join(cmds) + ";|"

def send(job_str, ip, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(30)
        s.connect((ip, port))
        s.sendall(job_str.encode("ascii"))
        time.sleep(1.0)
        try: return s.recv(4096)
        except socket.timeout: return b''
