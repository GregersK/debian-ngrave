#!/bin/bash
# Auto-opdatering af nGrave fra GitHub — tag-baseret rollout
# Pull'er kun nye release-tags (vX.Y[.Z]), ikke arbitrære main-commits.
set -euo pipefail

INSTALL_DIR=/opt/ngrave
LOG=/var/log/ngrave-update.log

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S')  $*" >> "$LOG"
}

cd "$INSTALL_DIR"

if ! git fetch --tags --prune --quiet origin 2>/dev/null; then
    log "WARN: fetch fejlede (netværk?)"
    exit 0
fi

# ── Kanal: stable (standard) eller beta ──────────────────────────────────────
# Skriv 'beta' i /etc/ngrave/channel (eller /opt/ngrave/channel) for at lade
# DENNE maskine hente pre-release-versioner (fx v6.3-beta1). Alt andet = stable.
CHANNEL=stable
for cf in /etc/ngrave/channel "$INSTALL_DIR/channel"; do
    if [ -r "$cf" ]; then
        CHANNEL=$(head -n1 "$cf" | tr -d '[:space:]' | tr 'A-Z' 'a-z')
        break
    fi
done
[ "$CHANNEL" = "beta" ] || CHANNEL=stable

# Lær git at -alpha/-beta/-rc er pre-release-suffikser (sorterer UNDER final),
# så en beta-maskine automatisk rykker op til den endelige version når den kommer.
git config --unset-all versionsort.suffix 2>/dev/null || true
git config --add versionsort.suffix -alpha
git config --add versionsort.suffix -beta
git config --add versionsort.suffix -rc

if [ "$CHANNEL" = "beta" ]; then
    # beta: nyeste tag overhovedet (inkl. pre-releases)
    LATEST_TAG=$(git tag -l 'v[0-9]*' --sort=-version:refname | head -n 1 || true)
else
    # stable: nyeste tag UDEN pre-release-suffiks (ingen bindestreg)
    LATEST_TAG=$(git tag -l 'v[0-9]*' --sort=-version:refname | grep -v -- '-' | head -n 1 || true)
fi

if [ -z "$LATEST_TAG" ]; then
    log "INFO: ingen tags for kanal '$CHANNEL' — ingen handling"
    exit 0
fi

CURRENT_TAG=$(git describe --tags --exact-match 2>/dev/null || echo "")

if [ "$CURRENT_TAG" = "$LATEST_TAG" ]; then
    exit 0
fi

log "INFO: [kanal:$CHANNEL] opgraderer fra '${CURRENT_TAG:-<ingen tag>}' til '$LATEST_TAG'"

git checkout --quiet "$LATEST_TAG"

if [ -f requirements.txt ]; then
    "$INSTALL_DIR/venv/bin/pip" install -q --upgrade -r requirements.txt || {
        log "WARN: pip install fejlede — fortsætter alligevel"
    }
fi

# Ryd evt. 'failed'-tilstand FØR genstart. Hvis systemd's start-rate-limit
# er blevet ramt (flere hurtige genstarts-fejl), sidder servicen ellers fast
# i 'failed' og starter først igen ved reboot — det er den typiske årsag til
# "servicen kom ikke op efter opdatering".
sudo -n /bin/systemctl reset-failed ngrave 2>/dev/null || true

if sudo -n /bin/systemctl restart ngrave 2>/dev/null; then
    sleep 3
    if systemctl is-active --quiet ngrave 2>/dev/null; then
        log "INFO: opgraderet til $LATEST_TAG — service kører"
    else
        # Kom ikke op → ryd failed-tilstand, prøv én gang til, gem diagnostik.
        log "WARN: service kom ikke op efter restart til $LATEST_TAG — forsøger igen"
        sudo -n /bin/systemctl reset-failed ngrave 2>/dev/null || true
        sudo -n /bin/systemctl start ngrave 2>/dev/null || true
        sleep 3
        {
            echo "----- DIAGNOSTIK $(date '+%F %T') efter fejlet start til $LATEST_TAG -----"
            systemctl status ngrave --no-pager -l 2>&1 | tail -25
            journalctl -u ngrave -n 30 --no-pager 2>&1 | tail -30
            echo "----- diagnostik slut -----"
        } >> "$LOG" 2>&1 || true
        if systemctl is-active --quiet ngrave 2>/dev/null; then
            log "INFO: service kom op efter andet forsøg (til $LATEST_TAG)"
        else
            log "FEJL: service er STADIG nede efter opdatering til $LATEST_TAG — se diagnostik ovenfor i denne log"
        fi
    fi
else
    log "WARN: kunne ikke genstarte via sudo (mangler sudoers-regel?)"
fi
