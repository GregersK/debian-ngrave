#!/bin/bash
# nGrave - Installation script for Debian 12
set -euo pipefail

REPO_URL="https://github.com/GregersK/debian-ngrave.git"
INSTALL_DIR=/opt/ngrave
ENV_DIR=/etc/ngrave
ENV_FILE="$ENV_DIR/ngrave.env"
SERVICE_USER=ngrave

echo "=== nGrave Installation ==="

if [ "$EUID" -ne 0 ]; then
  echo "Kør som root: sudo bash install.sh"
  exit 1
fi

echo "=== Opdaterer pakkelister ==="
apt update -q

echo "=== Installerer pakker ==="
apt install -y python3 python3-pip python3-venv git

echo "=== Opretter system-bruger '$SERVICE_USER' ==="
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

echo "=== Kloner repository ==="
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Eksisterende git-repo fundet — trækker seneste version"
    git -C "$INSTALL_DIR" pull origin main --quiet
else
    rm -rf "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR" --branch main --quiet
fi

echo "=== Opretter venv ==="
python3 -m venv "$INSTALL_DIR/venv"

echo "=== Installerer Python pakker ==="
"$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

echo "=== Opretter env-fil med auto-genereret password ==="
mkdir -p "$ENV_DIR"
chmod 750 "$ENV_DIR"
chown root:"$SERVICE_USER" "$ENV_DIR"

if [ ! -f "$ENV_FILE" ]; then
    GEN_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
    cat > "$ENV_FILE" <<ENV
# nGrave runtime config
NGRAVE_DB=/opt/ngrave/ngrave.db
NGRAVE_HOST=0.0.0.0
NGRAVE_PORT=80
NGRAVE_AUTH_USER=ngrave
NGRAVE_AUTH_PASS=$GEN_PASS
ENV
    chmod 640 "$ENV_FILE"
    chown root:"$SERVICE_USER" "$ENV_FILE"
    echo ""
    echo "  >> Auto-genereret login: ngrave / $GEN_PASS"
    echo "  >> Gemt i $ENV_FILE — opbevar sikkert."
    echo ""
else
    echo "  Eksisterende $ENV_FILE bevaret"
fi

echo "=== Sætter ejerskab ==="
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"

echo "=== Opretter systemd service ==="
cat > /etc/systemd/system/ngrave.service <<SERVICE
[Unit]
Description=nGrave Gravesystem
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$INSTALL_DIR/venv/bin/python app.py
Restart=always
RestartSec=5

# Tillad binding til port < 1024 uden at køre som root
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
SERVICE

echo "=== Opretter sudoers-regel for restart ==="
cat > /etc/sudoers.d/ngrave-restart <<SUDO
$SERVICE_USER ALL=(root) NOPASSWD: /bin/systemctl restart ngrave, /bin/systemctl start ngrave, /bin/systemctl reset-failed ngrave
SUDO
chmod 440 /etc/sudoers.d/ngrave-restart

echo "=== Opretter auto-opdatering (tag-baseret, dagligt) ==="
chmod +x "$INSTALL_DIR/ngrave-update.sh"

cat > /etc/systemd/system/ngrave-update.service <<SERVICE
[Unit]
Description=nGrave auto-opdatering fra GitHub (tag-baseret)

[Service]
Type=oneshot
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/ngrave-update.sh
SERVICE

cat > /etc/systemd/system/ngrave-update.timer <<TIMER
[Unit]
Description=nGrave auto-opdatering dagligt

[Timer]
OnBootSec=15min
OnUnitActiveSec=24h
RandomizedDelaySec=2h
Persistent=true

[Install]
WantedBy=timers.target
TIMER

echo "=== Opretter log-mappe ==="
mkdir -p /var/log
touch /var/log/ngrave-update.log
chown "$SERVICE_USER":"$SERVICE_USER" /var/log/ngrave-update.log

systemctl daemon-reload
systemctl enable ngrave
systemctl restart ngrave
systemctl enable ngrave-update.timer
systemctl restart ngrave-update.timer

echo ""
echo "=== nGrave installeret! ==="
echo "Web UI: http://$(hostname -I | awk '{print $1}')"
echo ""
echo "Auto-opdatering: dagligt fra GitHub (kun ved nye tags vXX.YY)"
echo "Log: tail -f /var/log/ngrave-update.log"
echo ""
echo "Næste skridt:"
echo "  1. Åbn http://$(hostname -I | awk '{print $1}') i browser"
echo "  2. Log ind med credentials fra $ENV_FILE"
echo "  3. Tilføj din(e) maskine(r) under fanen 'Maskiner'"
echo "  4. Test forbindelsen med 'Test position' knappen"
