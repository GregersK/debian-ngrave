"""Enkeltstregs SVG-fonts (Inkscape "Hershey Text"-formatet: <font>/<glyph d=...>).

Bruges til de medfølgende fonte i fonts/ (Relief SingleLine, EMS-serien). Læser
glyffer, fontens egen kerning (<hkern>) og flader Bézier-kurver ud til linjer.

Koordinater ud: font-enheder, Y opad, baseline 0, pen-position i x=0 — samme
form som workers/dansk.py og font_manager forventer.
"""
import math
import re
import threading
import xml.etree.ElementTree as ET

NS = '{http://www.w3.org/2000/svg}'
_TOKEN = re.compile(r'[MmLlHhVvCcSsQqTtZzAa]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?')


def _flad_kubisk(p0, p1, p2, p3, tol, ud, dybde=0):
    """Rekursiv udfladning af en kubisk Bézier: stop når kontrolpunkterne ligger
    inden for `tol` fra korden (så antal linjestykker følger kurvens krumning)."""
    dx, dy = p3[0] - p0[0], p3[1] - p0[1]
    d2 = abs((p1[0] - p3[0]) * dy - (p1[1] - p3[1]) * dx)
    d3 = abs((p2[0] - p3[0]) * dy - (p2[1] - p3[1]) * dx)
    if dybde >= 10 or (d2 + d3) ** 2 <= tol * tol * (dx * dx + dy * dy):
        ud.append(p3)
        return
    p01 = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
    p12 = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    p23 = ((p2[0] + p3[0]) / 2, (p2[1] + p3[1]) / 2)
    p012 = ((p01[0] + p12[0]) / 2, (p01[1] + p12[1]) / 2)
    p123 = ((p12[0] + p23[0]) / 2, (p12[1] + p23[1]) / 2)
    c = ((p012[0] + p123[0]) / 2, (p012[1] + p123[1]) / 2)
    _flad_kubisk(p0, p01, p012, c, tol, ud, dybde + 1)
    _flad_kubisk(c, p123, p23, p3, tol, ud, dybde + 1)


def parse_path(d, tol=1.0):
    """SVG path-data → liste af polylinjer. `tol` = max afvigelse (samme enhed som d)."""
    tok = _TOKEN.findall(d or '')
    i, cmd = 0, None
    cur = start = (0.0, 0.0)
    last_ctrl = None
    strokes, s = [], []

    def num():
        nonlocal i
        v = float(tok[i])
        i += 1
        return v

    def flush():
        nonlocal s
        if len(s) >= 2:
            strokes.append(s)
        s = []

    try:
        while i < len(tok):
            if tok[i].isalpha():
                cmd = tok[i]
                i += 1
                if cmd in 'Zz':
                    if s and s[-1] != start:
                        s.append(start)
                    cur = start
                    flush()
                    last_ctrl = None
                    continue
            if cmd is None:
                break
            rel = cmd.islower()
            C = cmd.upper()
            ox, oy = cur if rel else (0.0, 0.0)
            if C == 'M':
                flush()
                cur = (ox + num(), oy + num())
                start = cur
                s = [cur]
                cmd = 'l' if rel else 'L'      # efterfølgende talpar er linjer
                last_ctrl = None
            elif C == 'L':
                cur = (ox + num(), oy + num())
                s.append(cur)
                last_ctrl = None
            elif C == 'H':
                cur = ((cur[0] if rel else 0.0) + num(), cur[1])
                s.append(cur)
                last_ctrl = None
            elif C == 'V':
                cur = (cur[0], (cur[1] if rel else 0.0) + num())
                s.append(cur)
                last_ctrl = None
            elif C in 'CS':
                if C == 'C':
                    p1 = (ox + num(), oy + num())
                else:
                    p1 = (2 * cur[0] - last_ctrl[0], 2 * cur[1] - last_ctrl[1]) if last_ctrl else cur
                p2 = (ox + num(), oy + num())
                p3 = (ox + num(), oy + num())
                if not s:
                    s = [cur]
                _flad_kubisk(cur, p1, p2, p3, tol, s)
                last_ctrl, cur = p2, p3
            elif C in 'QT':
                if C == 'Q':
                    q = (ox + num(), oy + num())
                else:
                    q = (2 * cur[0] - last_ctrl[0], 2 * cur[1] - last_ctrl[1]) if last_ctrl else cur
                p3 = (ox + num(), oy + num())
                p1 = (cur[0] + 2 / 3 * (q[0] - cur[0]), cur[1] + 2 / 3 * (q[1] - cur[1]))
                p2 = (p3[0] + 2 / 3 * (q[0] - p3[0]), p3[1] + 2 / 3 * (q[1] - p3[1]))
                if not s:
                    s = [cur]
                _flad_kubisk(cur, p1, p2, p3, tol, s)
                last_ctrl, cur = q, p3
            elif C == 'A':
                # Elliptiske buer bruges ikke af de medfølgende fonte — tegnes som linje.
                for _ in range(5):
                    num()
                cur = (ox + num(), oy + num())
                s.append(cur)
                last_ctrl = None
            else:
                i += 1
    except (IndexError, ValueError):
        pass                                   # afkortet/ugyldig data: brug det vi har
    flush()
    return strokes


class SvgFont:
    def __init__(self, path):
        root = ET.parse(path).getroot()
        font = root.find(f'.//{NS}font')
        if font is None:
            raise ValueError(f'Ingen <font> i {path}')
        face = font.find(f'{NS}font-face')
        self.navn = face.get('font-family') if face is not None else path
        self.default_adv = float(font.get('horiz-adv-x') or 500)
        self._d = {}          # tegn -> (adv, d)
        navne = {}            # glyph-name -> tegn
        for g in font.findall(f'{NS}glyph'):
            u = g.get('unicode')
            if not u or len(u) != 1:
                continue
            self._d[u] = (float(g.get('horiz-adv-x') or self.default_adv), g.get('d') or '')
            if g.get('glyph-name'):
                navne[g.get('glyph-name')] = u
        self.kern = {}
        for k in font.findall(f'{NS}hkern'):
            a = self._klasse(k.get('u1'), k.get('g1'), navne)
            b = self._klasse(k.get('u2'), k.get('g2'), navne)
            v = float(k.get('k') or 0)
            for x in a:
                for y in b:
                    self.kern[(x, y)] = v
        # Versalhøjde målt på 'H' (font-face cap-height passer ikke altid)
        ys = [p[1] for st in parse_path(self._d['H'][1]) for p in st] if 'H' in self._d else []
        self.cap = (max(ys) - min(ys)) if ys else float((face.get('cap-height') if face is not None else 0) or 700)
        self._cache = {}
        self._laas = threading.Lock()

    @staticmethod
    def _klasse(u, g, navne):
        ud = set()
        for x in (u or '').split(','):
            if len(x) == 1:
                ud.add(x)
        for x in (g or '').split(','):
            if x in navne:
                ud.add(navne[x])
        return ud

    def har(self, ch):
        return ch in self._d

    def glyf(self, ch, tol):
        """(advance, strokes) i font-enheder; None hvis tegnet ikke findes."""
        if ch not in self._d:
            return None
        key = (ch, round(tol, 3))
        g = self._cache.get(key)
        if g is None:
            adv, d = self._d[ch]
            g = (adv, [list(s) for s in parse_path(d, tol)])
            with self._laas:
                if len(self._cache) > 4000:
                    self._cache.clear()
                self._cache[key] = g
        return g

    def kerning(self, a, b):
        return self.kern.get((a, b), 0.0)
