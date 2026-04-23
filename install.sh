#!/bin/bash
# nGrave - Installation script for Debian 12
set -e

REPO_URL="https://github.com/GregersK/debian-ngrave.git"
INSTALL_DIR=/opt/ngrave

echo "=== nGrave Installation ==="

if [ "$EUID" -ne 0 ]; then
  echo "Kør som root: sudo bash install.sh"
  exit 1
fi

echo "=== Opdaterer system ==="
apt update -q && apt upgrade -y -q

echo "=== Installerer pakker ==="
apt install -y python3 python3-pip python3-venv git

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
"$INSTALL_DIR/venv/bin/pip" install -q flask hershey-fonts

echo "=== Opretter systemd service ==="
cat > /etc/systemd/system/ngrave.service << 'SERVICE'
[Unit]
Description=nGrave Gravesystem
After=network.target

[Service]
User=root
WorkingDirectory=/opt/ngrave
ExecStart=/opt/ngrave/venv/bin/python app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

echo "=== Opretter auto-opdatering ==="
chmod +x "$INSTALL_DIR/ngrave-update.sh"

cat > /etc/systemd/system/ngrave-update.service << 'SERVICE'
[Unit]
Description=nGrave auto-opdatering fra GitHub

[Service]
Type=oneshot
ExecStart=/opt/ngrave/ngrave-update.sh
SERVICE

cat > /etc/systemd/system/ngrave-update.timer << 'TIMER'
[Unit]
Description=nGrave auto-opdatering hver 5. minut

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
TIMER

systemctl daemon-reload
systemctl enable ngrave
systemctl start ngrave
systemctl enable ngrave-update.timer
systemctl start ngrave-update.timer

echo ""
echo "=== nGrave installeret! ==="
echo "Web UI: http://$(hostname -I | awk '{print $1}')"
echo ""
echo "Auto-opdatering: aktiv (hvert 5. minut fra GitHub main)"
echo "Log: tail -f /var/log/ngrave-update.log"
echo ""
echo "Næste skridt:"
echo "  1. Åbn http://$(hostname -I | awk '{print $1}') i browser"
echo "  2. Gå til Maskiner og konfigurer IP/port"
echo "  3. Opret nøgle-templates med grid-koordinater"
echo "  4. Test forbindelsen med 'Test position' knappen"
