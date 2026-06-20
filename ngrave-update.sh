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

if ! git fetch --tags --quiet origin 2>/dev/null; then
    log "WARN: fetch fejlede (netværk?)"
    exit 0
fi

LATEST_TAG=$(git tag -l 'v[0-9]*' --sort=-v:refname | head -n 1 || true)
if [ -z "$LATEST_TAG" ]; then
    log "INFO: ingen release-tags fundet — ingen handling"
    exit 0
fi

CURRENT_TAG=$(git describe --tags --exact-match 2>/dev/null || echo "")

if [ "$CURRENT_TAG" = "$LATEST_TAG" ]; then
    exit 0
fi

log "INFO: opgraderer fra '${CURRENT_TAG:-<ingen tag>}' til '$LATEST_TAG'"

git checkout --quiet "$LATEST_TAG"

if [ -f requirements.txt ]; then
    "$INSTALL_DIR/venv/bin/pip" install -q --upgrade -r requirements.txt || {
        log "WARN: pip install fejlede — fortsætter alligevel"
    }
fi

if sudo -n /bin/systemctl restart ngrave 2>/dev/null; then
    log "INFO: opgraderet til $LATEST_TAG og service restartet"
else
    log "WARN: kunne ikke restarte service via sudo — opgradering deployet, men kører stadig gammel version indtil næste manuel restart"
fi
