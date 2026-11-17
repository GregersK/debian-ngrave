#!/bin/bash
# Kopiér data fra en kørende nGrave-server til DENNE (test)server.
#
#   bash /opt/ngrave/tools/kopier-fra-server.sh root@LAASENGRAVE01
#
# Uden SSH som root (Debian tillader det ikke med password som standard):
# lav kopien på den gamle server (se TESTSERVER.md), flyt filen hertil og kør
#   bash /opt/ngrave/tools/kopier-fra-server.sh --fil /root/ngrave-kopi.db LAASENGRAVE01
#
# Den gamle server ændres IKKE: databasen læses med SQLite's backup-funktion
# (sikker mens tjenesten kører); kopien hentes over SSH. Her på testserveren:
#   - den nuværende database gemmes som ngrave.db.foer-kopi-<tid>
#   - kopien opgraderes, og ventende jobs i den sættes til «fejl», så de aldrig
#     sendes herfra (den gamle server har dem stadig og kører dem som altid)
#
# Kræver: SSH-adgang som root til den gamle server (password eller nøgle) og at
# denne server er installeret som testserver (NGRAVE_TESTSERVER=1).
set -euo pipefail

FIL=""
if [ "${1:-}" = "--fil" ]; then
    FIL="${2:-}"
    KILDE="${3:-den gamle server}"
    if [ -z "$FIL" ] || [ ! -f "$FIL" ]; then
        echo "Filen findes ikke: ${FIL:-<ingen>}"
        exit 1
    fi
else
    KILDE="${1:-}"
fi
if [ -z "$KILDE" ]; then
    echo "Brug: bash $0 root@<gammel-server> [sti-til-database-på-gammel-server]"
    echo "  eller: bash $0 --fil <kopi.db> [navn-på-gammel-server]"
    exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
    echo "Kør som root."
    exit 1
fi

INSTALL_DIR=${NGRAVE_INSTALL_DIR:-/opt/ngrave}
ENV_FILE=${NGRAVE_ENV_FILE:-/etc/ngrave/ngrave.env}

# Sikkerhed: kun på en testserver (ellers kunne ventende jobs fra kopien graveres her)
if ! grep -qiE '^NGRAVE_TESTSERVER=(1|ja|true|yes|on)\s*$' "$ENV_FILE" 2>/dev/null; then
    echo "STOP: $ENV_FILE har ikke NGRAVE_TESTSERVER=1."
    echo "Denne server skal være installeret som testserver, før der kopieres data hertil."
    exit 1
fi

LOKAL_DB=$(grep -E '^NGRAVE_DB=' "$ENV_FILE" | tail -1 | cut -d= -f2- || true)
LOKAL_DB=${LOKAL_DB:-$INSTALL_DIR/ngrave.db}

NY="$LOKAL_DB.ny-kopi"
rm -f "$NY"
if [ -n "$FIL" ]; then
    echo "=== Bruger kopien $FIL ==="
    cp "$FIL" "$NY"
else
echo "=== Finder databasen på $KILDE ==="
FJERN_DB="${2:-}"
if [ -z "$FJERN_DB" ]; then
    FJERN_DB=$(ssh -o ConnectTimeout=10 "$KILDE" "grep -E '^NGRAVE_DB=' /etc/ngrave/ngrave.env 2>/dev/null | tail -1 | cut -d= -f2-" || true)
    FJERN_DB=${FJERN_DB:-/opt/ngrave/ngrave.db}
fi
echo "  $KILDE:$FJERN_DB"

echo "=== Laver en sikker kopi (SQLite backup — den gamle server kører videre) ==="
# Backup til en midlertidig fil på den gamle server, send den hertil, slet den igen.
ssh -o ConnectTimeout=10 "$KILDE" "python3 - '$FJERN_DB'" > "$NY" <<'PY'
import os, sqlite3, sys, tempfile
kilde = sys.argv[1]
if not os.path.exists(kilde):
    sys.stderr.write(f"Databasen findes ikke: {kilde}\n"); sys.exit(2)
fd, tmp = tempfile.mkstemp(suffix='.db'); os.close(fd)
try:
    s = sqlite3.connect(kilde, timeout=30)
    s.execute("PRAGMA query_only=1")
    d = sqlite3.connect(tmp)
    s.backup(d)
    d.close(); s.close()
    with open(tmp, 'rb') as f:
        sys.stdout.buffer.write(f.read())
finally:
    os.unlink(tmp)
PY
fi
STR=$(stat -c %s "$NY")
if [ "$STR" -lt 4096 ]; then
    echo "FEJL: kopien er tom eller for lille ($STR bytes) — intet er ændret her."
    rm -f "$NY"
    exit 1
fi
echo "  Hentet $((STR / 1024)) kB"

echo "=== Stopper nGrave her (testserveren) ==="
systemctl stop ngrave

if [ -f "$LOKAL_DB" ]; then
    GEM="$LOKAL_DB.foer-kopi-$(date +%Y%m%d-%H%M%S)"
    mv "$LOKAL_DB" "$GEM"
    rm -f "$LOKAL_DB-wal" "$LOKAL_DB-shm"
    echo "  Testserverens tidligere database gemt som $GEM"
fi
mv "$NY" "$LOKAL_DB"

echo "=== Opgraderer kopien og sætter ventende jobs ud af spil ==="
"$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/tools/neutraliser_kopi.py" "$LOKAL_DB" --fra "${KILDE#*@}"
chown ngrave:ngrave "$LOKAL_DB" "$LOKAL_DB"-* 2>/dev/null || chown ngrave:ngrave "$LOKAL_DB"

echo "=== Starter nGrave igen ==="
systemctl start ngrave
sleep 2
systemctl is-active --quiet ngrave && echo "  nGrave kører." || { echo "FEJL: nGrave startede ikke — se: journalctl -u ngrave -n 40"; exit 1; }
echo ""
echo "Færdig. Åbn http://$(hostname -I | awk '{print $1}') — banneret øverst skal sige TESTSERVER."
