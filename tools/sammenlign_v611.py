#!/usr/bin/env python3
"""Sammenlign testserverens gemte nøgle-programmer med dem v6.1.1 ville have sendt.

    /opt/ngrave/venv/bin/python /opt/ngrave/tools/sammenlign_v611.py

For hver gemt fil i toerkoersel/ (nøgle-batches) bygges programmet igen med den
RIGTIGE v6.1.1-kode (hentet fra git-tagget v6.1.1 i dette repo) ud fra samme
batch, template og maskine i databasen. Resultatet:

  IDENTISK  — maskinen ville få præcis det samme som fra den gamle server.
  ÆNDRET    — med forklaring: de nye funktioner der er slået til for templaten
              eller maskinen (materiale, ægte ÆØÅ, Block-lås slået fra,
              optimering, lavt løft …). Ingen af dem er slået til af sig selv.

Skilte sammenlignes ikke: v6.2 har en ny layout-motor til skilte (rettede
margener og kant-tjek), så de er bevidst anderledes.

OBS: sammenligningen bruger templaten som den ser ud NU — er den rettet efter
jobbet blev oprettet, vil det også give forskelle.
"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import io

ROD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAVN = re.compile(r'^\d{8}-\d{6}_noegler-(\d+)_m(\d+)\.(nc|cip)$')
DANSK = set('ÆØÅæøå')

V611_BYG = r"""
import json, sys, os
sys.path.insert(0, os.getcwd())
d = json.load(sys.stdin)
if d['protokol'] == 'gcode':
    from workers.gcode_worker import byg_batch
else:
    from workers.cipher_worker import byg_batch
sys.stdout.write(byg_batch(d['jobs'], d['tmpl']))
"""


def hent_v611(tag='v6.1.1'):
    """Pak v6.1.1's workers ud i en midlertidig mappe (ændrer ikke repoet)."""
    try:
        data = subprocess.run(['git', '-C', ROD, 'archive', tag, 'workers'], capture_output=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise SystemExit(f"Kunne ikke hente {tag} fra git ({e}). Kør: git -C {ROD} fetch --tags")
    mappe = tempfile.mkdtemp(prefix='ngrave-v611-')
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        t.extractall(mappe, filter='data') if hasattr(tarfile, 'data_filter') else t.extractall(mappe)
    return mappe


def forklar(tmpl, maskine, jobs):
    grunde = []
    if tmpl.get('materiale_id'):
        grunde.append('templaten bruger et materiale (feed/rpm/løft fra materialet)')
    if (tmpl.get('z_loeft_inde_mm') or 0) > 0:
        grunde.append('lavt løft mellem bogstaver')
    if (maskine.get('optimering') or 'ingen') != 'ingen':
        grunde.append(f"maskinens optimering er «{maskine['optimering']}»")
    fonte = {tmpl.get(f'{p}_font') or tmpl.get('font') or 'block' for p in ('markering', 'system', 'loebe', 'ekstra')}
    if not tmpl.get('kun_block') and fonte - {'block', ''}:
        grunde.append('«Gravér alt i Block (som i v6.1)» er slået fra — de valgte skrifttyper bruges nu')
    tekster = ''.join((j.get(k) or '') for j in jobs for k in ('type_felt', 'system_nr', 'loebe_nr', 'ekstra_tekst'))
    if tmpl.get('dansk_tegn') and DANSK & set(tekster) and not tmpl.get('kun_block') and fonte - {'block', ''}:
        grunde.append('ægte ÆØÅ i Hershey-skrifttype')
    if set(tekster) & set(",:;+#&()'!?*=_@%"):
        grunde.append("teksten har tegn som Block nu kan gravere (før sprunget over): , : ; + # & ( ) ' ! ? * = _ @ %")
    return grunde or ['ingen af de nye funktioner er slået til — se forskellen med: diff <(v6.1.1) <(fil)']


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', default=os.environ.get('NGRAVE_DB') or os.path.join(ROD, 'ngrave.db'))
    ap.add_argument('--mappe', default=os.environ.get('NGRAVE_TOERKOERSEL_DIR') or os.path.join(ROD, 'toerkoersel'))
    ap.add_argument('--tag', default='v6.1.1')
    a = ap.parse_args()

    try:
        filer = sorted(f for f in os.listdir(a.mappe) if NAVN.match(f))
    except FileNotFoundError:
        filer = []
    if not filer:
        print(f"Ingen gemte nøgle-programmer i {a.mappe} endnu — opret et nøglejob på testserveren først.")
        return 0
    v611 = hent_v611(a.tag)
    db = sqlite3.connect(a.db)
    db.row_factory = sqlite3.Row
    ens = andre = mangler = 0
    for f in filer:
        bid, mid, _ = NAVN.match(f).groups()
        b = db.execute("SELECT * FROM job_batches WHERE id=?", (int(bid),)).fetchone()
        m = db.execute("SELECT * FROM maskiner WHERE id=?", (int(mid),)).fetchone()
        t = db.execute("SELECT * FROM templates WHERE id=?", (b['template_id'],)).fetchone() if b else None
        if not (b and m and t):
            print(f"  ?  {f}: batch/maskine/template findes ikke længere i databasen")
            mangler += 1
            continue
        jobs = [dict(j) for j in db.execute("SELECT * FROM jobs WHERE batch_id=? ORDER BY slot_nr ASC", (b['id'],))]
        tmpl, maskine = dict(t), dict(m)
        tmpl.update(offset_x=maskine.get('offset_x') or 0.0, offset_y=maskine.get('offset_y') or 0.0,
                    offset_z=maskine.get('offset_z') or 0.0, spejl_y=bool(maskine.get('spejl_y')))
        for felt in ('markering', 'system', 'loebe', 'ekstra'):
            tmpl[f'felt_{felt}_dx'] = float(maskine.get(f'felt_{felt}_dx') or 0.0)
            tmpl[f'felt_{felt}_dy'] = float(maskine.get(f'felt_{felt}_dy') or 0.0)
        r = subprocess.run([sys.executable, '-I', '-c', V611_BYG], cwd=v611, capture_output=True, text=True,
                           input=json.dumps({'protokol': maskine['protokol'], 'jobs': jobs, 'tmpl': tmpl}, default=str))
        if r.returncode:
            print(f"  ?  {f}: v6.1.1-koden fejlede: {r.stderr.strip().splitlines()[-1] if r.stderr else r.returncode}")
            mangler += 1
            continue
        with open(os.path.join(a.mappe, f), encoding='ascii', errors='replace') as fh:
            ny = fh.read()
        navn = f"{t['navn']} → {m['navn']}"
        if ny == r.stdout:
            ens += 1
            stoerrelse = f"{ny.count(';')} kommandoer" if f.endswith('.cip') else f"{len(ny.splitlines())} linjer"
            print(f"  ✓  IDENTISK  {f}  ({navn}, {stoerrelse})")
        else:
            andre += 1
            print(f"  ≠  ÆNDRET    {f}  ({navn})")
            for g in forklar(tmpl, maskine, jobs):
                print(f"        – {g}")
    print(f"\n{ens} identiske med v6.1.1, {andre} ændrede, {mangler} kunne ikke sammenlignes.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
