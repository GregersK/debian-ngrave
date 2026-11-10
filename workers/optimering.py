"""Hurtigere gravering: færre penneløft og færre G-code-linjer.

Hvert penneløft koster tid på maskinen (løft, kør, dwell, prox-nedkørsel), og
mange små linjestykker får maskinen til at bremse ned. Tre niveauer pr. maskine:

  ingen   Stregerne sendes præcis som fonten tegner dem (som før v6.2).
  let     Samme rækkefølge og retning som fonten:
          - to streger hvor den ene slutter præcis hvor den næste starter,
            køres uden at løfte (fræseren ville alligevel ned samme sted),
          - punkter der ligger på en lige linje (< 1 µm) og dubletter fjernes.
  fuld    Standard. Som let, men streger der rører hinanden kædes sammen også
          når den ene skal køres BAGLÆNS, og næste streg er den nærmeste. Præcis
          de samme streger graveres (fontene tegner i forvejen deres streger i
          tilfældige retninger) — typisk 20-50 % færre penneløft.

Hvis en maskine mod forventning graverer anderledes, sættes den til "ingen"
under Maskiner.
"""
import math

NIVEAUER = ('ingen', 'let', 'fuld')
STANDARD = 'fuld'
_TOL = 1e-6          # mm: endepunkter regnes som samme punkt
_LIGE = 0.001        # mm: max afvigelse for at et punkt regnes som "på linjen"


def niveau(v):
    return v if v in NIVEAUER else STANDARD


def _rens(s):
    """Fjern dubletter og punkter der ligger på en lige linje mellem naboerne.
    En streg med ét punkt (en prik) bevares som den er."""
    ud = [s[0]]
    for p in s[1:]:
        if abs(p[0] - ud[-1][0]) > 1e-9 or abs(p[1] - ud[-1][1]) > 1e-9:
            ud.append(p)
    if len(ud) < 3:
        return ud
    res = [ud[0]]
    for i in range(1, len(ud) - 1):
        a, b, c = res[-1], ud[i], ud[i + 1]
        abx, aby = b[0] - a[0], b[1] - a[1]
        bcx, bcy = c[0] - b[0], c[1] - b[1]
        acx, acy = c[0] - a[0], c[1] - a[1]
        L = math.hypot(acx, acy)
        # samme retning (ikke en vending) og tæt på linjen a-c
        if L > 0 and abx * bcx + aby * bcy > 0 and abs(acx * aby - acy * abx) / L < _LIGE:
            continue
        res.append(b)
    res.append(ud[-1])
    return res


def _samme(p, q):
    return abs(p[0] - q[0]) <= _TOL and abs(p[1] - q[1]) <= _TOL


def optimer(strokes, niveau_='ingen'):
    """Returnerer nye streger (input ændres ikke)."""
    if niveau_ not in ('let', 'fuld'):
        return strokes
    ss = [list(s) for s in strokes if s]
    if niveau_ == 'let':
        ud = []
        for s in ss:
            if ud and len(ud[-1]) > 1 and len(s) > 1 and _samme(ud[-1][-1], s[0]):
                ud[-1].extend(s[1:])
            else:
                ud.append(s)
        return [_rens(s) for s in ud]

    # fuld: grådig sammenkædning (også baglæns) + nærmeste næste streg
    if not ss:
        return []
    rest = ss
    ud = []
    cur = rest.pop(0)
    while True:
        fundet = True
        while fundet and len(cur) > 1:
            fundet = False
            for i, s in enumerate(rest):
                if len(s) < 2:
                    continue
                if _samme(cur[-1], s[0]):
                    cur = cur + s[1:]
                elif _samme(cur[-1], s[-1]):
                    cur = cur + s[-2::-1]
                elif _samme(cur[0], s[-1]):
                    cur = s[:-1] + cur
                elif _samme(cur[0], s[0]):
                    cur = s[:0:-1] + cur
                else:
                    continue
                rest.pop(i)
                fundet = True
                break
        ud.append(_rens(cur))
        if not rest:
            break
        px, py = cur[-1]
        bedst, bi, vend = None, 0, False
        for i, s in enumerate(rest):
            d0 = (s[0][0] - px) ** 2 + (s[0][1] - py) ** 2
            d1 = (s[-1][0] - px) ** 2 + (s[-1][1] - py) ** 2
            if bedst is None or d0 < bedst:
                bedst, bi, vend = d0, i, False
            if d1 < bedst:
                bedst, bi, vend = d1, i, True
        cur = rest.pop(bi)
        if vend:
            cur = cur[::-1]
    return ud


def statistik(strokes):
    """Penneløft (= antal streger), fræsevej og luftvej i mm."""
    ss = [s for s in strokes if s]
    fraes = sum(math.dist(p, q) for s in ss for p, q in zip(s, s[1:]))
    luft = sum(math.dist(a[-1], b[0]) for a, b in zip(ss, ss[1:]))
    return {'loeft': len(ss), 'fraesevej_mm': round(fraes, 1), 'luftvej_mm': round(luft, 1)}
