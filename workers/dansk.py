"""Ægte Æ Ø Å æ ø å til skrifttyper der ikke har dem (Hershey-fontene).

Bogstaverne bygges ud af fontens EGNE glyffer, så de får samme stil og vægt:
  Ø/ø  = O/o + en skråstreg
  Å/å  = A/a + en ring (dobbelt/tredobbelt i fede fonte)
  Æ    = A'ets venstre halvdel + E (E'ets stamme sat i A'ets spids)
  æ    = a + e (e'ets bue starter i a'ets stamme)

Fordi skrifttyperne er meget forskellige (opret, kursiv, script, gotisk), har
hver font en OPSKRIFT (se font_manager). Alle mål er i font-enheder med Y opad,
baseline 0 og glyffens pen-position i x=0.

Et konstrueret bogstav er aldrig bredere end den gamle erstatning (AE/OE/AA),
så tekst der passede før, passer også nu.
"""
import math

DANSKE = 'ÆØÅæøå'


def _punkter(strokes):
    return [p for s in strokes for p in s]


def bbox(strokes):
    pts = _punkter(strokes)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _flyt(strokes, dx, dy=0.0):
    return [[(x + dx, y + dy) for x, y in s] for s in strokes]


def _skaev(strokes, k):
    """Skævvrid: x' = x - k*y (k>0 retter en højre-hældende kursiv op)."""
    if not k:
        return [list(s) for s in strokes]
    return [[(x - k * y, y) for x, y in s] for s in strokes]


def _laengde(strokes):
    return sum(math.dist(p, q) for s in strokes for p, q in zip(s, s[1:]))


def _klip(strokes, c, behold='venstre'):
    """Behold kun de dele af stregerne der ligger til venstre (eller højre) for x=c."""
    def inde(p):
        return p[0] <= c + 1e-9 if behold == 'venstre' else p[0] >= c - 1e-9
    ud = []
    for s in strokes:
        cur = []
        for a, b in zip(s, s[1:]):
            ia, ib = inde(a), inde(b)
            if ia and not cur:
                cur = [a]
            if ia and ib:
                cur.append(b)
            elif ia != ib:
                t = (c - a[0]) / (b[0] - a[0])
                m = (c, a[1] + t * (b[1] - a[1]))
                if ia:
                    cur.append(m)
                    ud.append(cur)
                    cur = []
                else:
                    cur = [m, b]
        if len(cur) >= 2:
            ud.append(cur)
    return [s for s in ud if _laengde([s]) > 1e-6]


def haeldning(strokes, cap):
    """Kursiv-hældning (dx pr. dy) målt på glyffens længste næsten-lodrette streg."""
    bedst, k = 0.0, 0.0
    for s in strokes:
        for a, b in zip(s, s[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            if abs(dy) > 0.4 * cap and abs(dx) < 0.6 * abs(dy) and abs(dy) > bedst:
                bedst, k = abs(dy), dx / dy
    return k


def _lodret_x(strokes, cap, min_andel=0.35, hvilken='venstre'):
    """x for en lang, næsten lodret streg (stamme). None hvis ingen findes."""
    kand = []
    for s in strokes:
        for a, b in zip(s, s[1:]):
            dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
            if dy > min_andel * cap and dx < 0.25 * dy:
                kand.append((a[0] + b[0]) / 2)
    if not kand:
        return None
    return min(kand) if hvilken == 'venstre' else max(kand)


def _top_x(strokes, andel=0.12):
    """Midten af glyffens øverste del (spidsen på et A, toppen af et a)."""
    x0, y0, x1, y1 = bbox(strokes)
    graense = y1 - andel * (y1 - y0)
    xs = [p[0] for p in _punkter(strokes) if p[1] >= graense]
    return (min(xs) + max(xs)) / 2 if xs else (x0 + x1) / 2


def _gentag(stroke_fn, vaegt, afstand):
    """Tegn en streg/ring 1-3 gange (fede Hershey-fonte er bygget af parallelle linjer)."""
    ud = []
    for i in range(vaegt):
        ud += stroke_fn((i - (vaegt - 1) / 2) * afstand)
    return ud


def _ring(cx, cy, r, vaegt, afstand, n=16):
    def en(d):
        rr = r + d
        return [[(cx + rr * math.cos(2 * math.pi * j / n), cy + rr * math.sin(2 * math.pi * j / n))
                 for j in range(n + 1)]]
    return _gentag(en, vaegt, afstand)


def _skraastreg(x0, y0, x1, y1, vaegt, afstand):
    L = math.hypot(x1 - x0, y1 - y0) or 1.0
    nx, ny = -(y1 - y0) / L, (x1 - x0) / L
    return _gentag(lambda d: [[(x0 + nx * d, y0 + ny * d), (x1 + nx * d, y1 + ny * d)]], vaegt, afstand)


def _par(glyf, a, b):
    """Fallback: to bogstaver sat efter hinanden (som AE i dag)."""
    ga, gb = glyf(a), glyf(b)
    if not ga or not gb:
        return None
    return ga[1] + _flyt(gb[1], ga[0]), ga[0] + gb[0]


def lav(ch, glyf, cap, opskrift=None):
    """Byg tegnet `ch` (et af ÆØÅæøå). glyf(c) -> (adv, strokes) | None.
    Returnerer (adv, strokes) eller None hvis basisbogstaverne mangler."""
    o = opskrift or {}
    vaegt = int(o.get('vaegt', 1))
    afst = o.get('linjeafstand', 0.045) * cap

    if ch in 'Øø':
        g = glyf('O' if ch == 'Ø' else 'o')
        if not g:
            return None
        adv, s = g
        x0, y0, x1, y1 = bbox(s)
        w, h = x1 - x0, y1 - y0
        return adv, s + _skraastreg(x0 - 0.06 * w, y0 - 0.06 * h, x1 + 0.06 * w, y1 + 0.06 * h, vaegt, afst)

    if ch in 'Åå':
        g = glyf('A' if ch == 'Å' else 'a')
        if not g:
            return None
        adv, s = g
        _, _, _, y1 = bbox(s)
        r = o.get('ring', 0.1) * cap
        cx = _top_x(s) + o.get('ring_dx', 0.0) * cap
        return adv, s + _ring(cx, y1 + 0.06 * cap + r + (vaegt - 1) * afst / 2, r, vaegt, afst)

    if ch == 'Æ':
        ga, ge = glyf('A'), glyf('E')
        if not ga or not ge:
            return None
        (aadv, a), (eadv, e) = ga, ge
        metode = o.get('ae', 'spids')
        if metode == 'spids':
            # Ret evt. kursiv op, klip A ved spidsen og sæt E'ets stamme dér.
            k = o.get('haeldning')
            if k is None:
                k = haeldning(e, cap)
            a2, e2 = _skaev(a, k), _skaev(e, k)
            spids = max(_punkter(a2), key=lambda p: p[1])
            x0, _, x1, _ = bbox(a2)
            rel = (spids[0] - x0) / ((x1 - x0) or 1)
            venstre = _klip(a2, spids[0])
            stamme = _lodret_x(e2, cap)
            if stamme is None or not (0.25 <= rel <= 0.75) or _laengde(venstre) < 0.3 * _laengde(a2):
                return _par(glyf, 'A', 'E')
            dx = spids[0] - stamme
            ud = venstre + _flyt(e2, dx)
            return dx + eadv, _skaev(ud, -k)
        if metode == 'krog':
            # Script: A'ets op-streg og løkke bevares, ned-stregen fjernes, og E
            # hægtes på i spidsen (sådan skrives Æ i hånden).
            spids = max(_punkter(a), key=lambda p: p[1])
            venstre = _klip(a, spids[0] + o.get('klip_dx', 0.0) * cap)
            ex0 = bbox(e)[0]
            dx = spids[0] - ex0 - o.get('overlap', 0.15) * cap
            return dx + eadv, venstre + _flyt(e, dx)
        if metode == 'flet':
            # Gotisk: E'et skubbes ind over A'ets højre side, der klippes bort.
            x0, _, x1, _ = bbox(a)
            c = x0 + o.get('klip', 0.62) * (x1 - x0)
            venstre = _klip(a, c)
            ex0 = bbox(e)[0]
            dx = c - ex0 - o.get('overlap', 0.0) * cap
            return dx + eadv, venstre + _flyt(e, dx)
        return _par(glyf, 'A', 'E')

    if ch == 'æ':
        ga, ge = glyf('a'), glyf('e')
        if not ga or not ge:
            return None
        (aadv, a), (eadv, e) = ga, ge
        k = o.get('haeldning')
        if k is None:
            k = haeldning(glyf('E')[1], cap) if glyf('E') else 0.0
        a2, e2 = _skaev(a, k), _skaev(e, k)
        if o.get('ae_lille', 'stamme') == 'stamme':
            st = _lodret_x(a2, cap, 0.22, 'hoejre')
            anker = st if st is not None else bbox(a2)[2] - 0.04 * cap
        else:
            anker = bbox(a2)[2] - o.get('overlap_lille', 0.08) * cap
        dx = anker - bbox(e2)[0]
        return dx + eadv, _skaev(a2 + _flyt(e2, dx), -k)

    return None
