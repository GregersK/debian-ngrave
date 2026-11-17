"""Netværk mod gravemaskiner: forbindelse, online-probe og status.

Den vigtigste regel her: *intet er sendt* når vi ikke kunne oprette forbindelse.
Det gør en forbindelsesfejl sikker at prøve igen automatisk — i modsætning til en
fejl midt i en sending, hvor vi ikke ved hvor meget maskinen nåede at modtage
(og et automatisk retry derfor kunne gravere to gange).
"""
import socket
import threading
import time

CONNECT_TIMEOUT = 5.0   # LAN: en tændt maskine svarer på millisekunder


class ForbindelsesFejl(OSError):
    """Kunne ikke oprette forbindelse til maskinen — intet er sendt."""
    def __init__(self, aarsag, besked):
        super().__init__(besked)
        self.aarsag = aarsag      # 'timeout' | 'afvist' | 'ingen_rute'
        self.besked = besked

    def __str__(self):
        return self.besked


def _forklar(e, ip, port):
    if isinstance(e, (socket.timeout, TimeoutError)):
        return 'timeout', "Maskinen svarede ikke (timeout) — er den tændt og på netværket?"
    if isinstance(e, ConnectionRefusedError):
        return 'afvist', ("Maskinen afviste forbindelsen — kører den, og er port/IP rigtig? "
                          "(Måske er en anden forbindelse åben mod den.)")
    return 'ingen_rute', f"Kan ikke nå maskinen på {ip}:{port} — tjek netværk, kabel og IP-adresse."


def aabn(ip, port, timeout=None):
    """Åbner en TCP-forbindelse. Kaster ForbindelsesFejl hvis det ikke lykkes."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(CONNECT_TIMEOUT if timeout is None else timeout)
    try:
        s.connect((ip, port))
    except OSError as e:
        s.close()
        aarsag, besked = _forklar(e, ip, port)
        raise ForbindelsesFejl(aarsag, besked) from e
    return s


def probe(ip, port, timeout=2.0):
    """Er der nogen der svarer på ip:port? Kun connect + luk — der sendes aldrig data.

    Returnerer {'status': 'online'|'offline'|'afviser', 'ms': int|None, 'fejl': str|None}
      online   forbindelsen blev oprettet
      afviser  værten svarer, men porten er lukket eller optaget (RST)
      offline  intet svar (timeout / ingen rute)
    """
    t0 = time.monotonic()
    try:
        s = aabn(ip, port, timeout)
    except ForbindelsesFejl as e:
        status = 'afviser' if e.aarsag == 'afvist' else 'offline'
        return {'status': status, 'ms': None, 'fejl': e.besked}
    ms = int((time.monotonic() - t0) * 1000)
    try:
        s.close()
    except OSError:
        pass
    return {'status': 'online', 'ms': ms, 'fejl': None}


# ─── Status-register (i hukommelsen — nulstilles ved genstart) ────────────────
_status = {}
_status_laas = threading.Lock()
_send_laas = {}                 # maskine_id -> Lock: én sending ad gangen pr. maskine
_send_laas_laas = threading.Lock()


def send_laas(mid):
    """Lås der sikrer at vi kun har én forbindelse åben mod en maskine ad gangen
    (en sending og en probe må aldrig overlappe)."""
    with _send_laas_laas:
        return _send_laas.setdefault(mid, threading.Lock())


def noter(mid, status, kilde, fejl=None, ms=None, sendt=False):
    """Gem hvad vi sidst ved om en maskine. kilde: 'probe' | 'job'."""
    nu = time.time()
    with _status_laas:
        s = _status.setdefault(mid, {'status': 'ukendt', 'sidst_set': None,
                                     'sidst_tjekket': None, 'sidst_sendt': None,
                                     'kilde': None, 'fejl': None, 'ms': None})
        s['status'] = status
        s['sidst_tjekket'] = nu
        s['kilde'] = kilde
        s['fejl'] = fejl
        s['ms'] = ms
        if status == 'online':
            s['sidst_set'] = nu
        if sendt:
            s['sidst_sendt'] = nu


def hent(mid):
    with _status_laas:
        return dict(_status.get(mid) or {'status': 'ukendt', 'sidst_set': None,
                                         'sidst_tjekket': None, 'sidst_sendt': None,
                                         'kilde': None, 'fejl': None, 'ms': None})


def kendte_ids():
    with _status_laas:
        return list(_status)


def sendt_for_nylig(mid, inden_for_sek):
    """Sekunder siden vi sendte et program til maskinen, hvis det er sket inden for
    `inden_for_sek` (maskinen graverer så formentlig stadig) — ellers None."""
    sendt = hent(mid)['sidst_sendt']
    if sendt is None:
        return None
    siden = time.time() - sendt
    return int(siden) if siden < inden_for_sek else None


def glem(mid):
    with _status_laas:
        _status.pop(mid, None)


def probe_maskine(mid, ip, port, kun_hvis_rolig_sek=0, timeout=2.0):
    """Probe med de sikkerhedsregler der gælder for en kørende produktion.

    - Springes over (returnerer None) hvis maskinen lige nu modtager et program.
    - Springes over hvis der er sendt et program inden for `kun_hvis_rolig_sek`
      sekunder: maskinen graverer formentlig stadig, og vi vil ikke røre ved den.
      (En manuel probe fra knappen sender 0 og ignorerer derfor ventetiden.)
    """
    laas = send_laas(mid)
    if not laas.acquire(blocking=False):
        return None
    try:
        if kun_hvis_rolig_sek and sendt_for_nylig(mid, kun_hvis_rolig_sek) is not None:
            return None
        r = probe(ip, port, timeout)
        noter(mid, r['status'], 'probe', fejl=r['fejl'], ms=r['ms'])
        return r
    finally:
        laas.release()
