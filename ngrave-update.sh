#!/bin/bash
# Auto-opdatering af nGrave fra GitHub main-branch
set -e

INSTALL_DIR=/opt/ngrave
LOG=/var/log/ngrave-update.log
BRANCH=main

cd "$INSTALL_DIR"

git fetch origin "$BRANCH" --quiet 2>/dev/null || {
    echo "$(date '+%Y-%m-%d %H:%M'): fetch fejlede (netværk?)" >> "$LOG"
    exit 0
}

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0
fi

CHANGED=$(git diff HEAD "origin/$BRANCH" --name-only)

git pull origin "$BRANCH" --quiet

if echo "$CHANGED" | grep -q "requirements.txt"; then
    "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"
fi

systemctl restart ngrave

echo "$(date '+%Y-%m-%d %H:%M'): Opdateret $(git rev-parse --short HEAD~1)→$(git rev-parse --short HEAD)" >> "$LOG"
