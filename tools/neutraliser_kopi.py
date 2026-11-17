#!/usr/bin/env python3
"""Gør en kopieret database klar til en TESTSERVER.

    python3 tools/neutraliser_kopi.py /opt/ngrave/ngrave.db --fra LAASENGRAVE01

1. Opgraderer kopien til denne version (samme migrering som ved opstart).
2. Ventende / på-hold / igangværende jobs sættes til «fejl» med en tydelig
   besked, så testserveren ALDRIG sender dem — heller ikke til en maskine den
   har lov at teste på. (Den rigtige server har dem stadig og kører dem som altid.)
3. Tjekker databasens integritet.

Templates, skilt-templates, maskiner, kalibrering og historik bevares uændret.
Den gamle server røres ikke — kun kopien ændres.
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime

ROD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def neutraliser(db_sti, fra='den gamle server'):
    os.environ['NGRAVE_DB'] = db_sti
    sys.path.insert(0, ROD)
    import app as A                       # noqa: E402 — læser NGRAVE_DB ved import
    A.DB = db_sti
    A.init_db()                           # migrering + seed + 'running' → 'fejl'

    besked = (f"Kopieret fra {fra} {datetime.now():%d-%m-%Y %H:%M} — ikke sendt fra testserveren "
              "(den rigtige server har jobbet)")
    with sqlite3.connect(db_sti) as db:
        ok = db.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != 'ok':
            raise SystemExit(f"FEJL: kopien er beskadiget ({ok}) — kopiér igen")
        b = db.execute("UPDATE job_batches SET status='fejl', fejl_besked=?, fejl_kode='kopi' "
                       "WHERE status IN ('pending','on-hold','running') OR "
                       "(status='fejl' AND fejl_besked='Afbrudt ved restart')", (besked,)).rowcount
        db.execute("UPDATE jobs SET status='fejl' WHERE status IN ('pending','running') AND batch_id IN "
                   "(SELECT id FROM job_batches WHERE fejl_kode='kopi')")
        s = db.execute("UPDATE skilte_jobs SET status='fejl', fejl_besked=?, fejl_kode='kopi' "
                       "WHERE status IN ('pending','running') OR "
                       "(status='fejl' AND fejl_besked='Afbrudt ved restart')", (besked,)).rowcount
        tael = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ('maskiner', 'templates', 'skilt_templates', 'materialer', 'job_batches', 'skilte_jobs')}
        laast = db.execute("SELECT COUNT(*) FROM templates WHERE kun_block=1 AND aktiv=1").fetchone()[0]
    return {'neutraliseret_batches': b, 'neutraliseret_skilte': s, 'antal': tael, 'block_som_v61': laast}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('db')
    ap.add_argument('--fra', default='den gamle server', help='navnet på serveren kopien kommer fra')
    a = ap.parse_args()
    r = neutraliser(os.path.abspath(a.db), a.fra)
    print(f"  Kopien er opgraderet og tjekket (integritet ok).")
    print(f"  Ventende jobs sat til «fejl» så de ikke sendes herfra: {r['neutraliseret_batches']} nøgle-batches, "
          f"{r['neutraliseret_skilte']} skilte")
    print("  Indhold: " + ", ".join(f"{v} {k}" for k, v in r['antal'].items()))
    if r['block_som_v61']:
        print(f"  {r['block_som_v61']} nøgle-template(s) graverer i Block som i v6.1 (de havde valgt en anden skrifttype)")


if __name__ == '__main__':
    main()
