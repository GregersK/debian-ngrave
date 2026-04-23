#!/bin/bash
# nGrave - Installation script for Debian 12
set -e

echo "=== nGrave Installation ==="

# Tjek root
if [ "$EUID" -ne 0 ]; then
  echo "Kør som root: sudo bash install.sh"
  exit 1
fi

echo "=== Opdaterer system ==="
apt update -q && apt upgrade -y -q

echo "=== Installerer Python ==="
apt install -y python3 python3-pip python3-venv unzip

echo "=== Opretter venv ==="
mkdir -p /opt/ngrave
python3 -m venv /opt/ngrave/venv
source /opt/ngrave/venv/bin/activate

echo "=== Installerer Python pakker ==="
pip install -q flask hershey-fonts

echo "=== Kopierer filer ==="
cp -r . /opt/ngrave/
cp -r workers /opt/ngrave/
cp -r templates /opt/ngrave/
cp -r static /opt/ngrave/

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

systemctl daemon-reload
systemctl enable ngrave
systemctl start ngrave

echo ""
echo "=== nGrave installeret! ==="
echo "Web UI: http://$(hostname -I | awk '{print $1}')"
echo ""
echo "Næste skridt:"
echo "  1. Åbn http://$(hostname -I | awk '{print $1}') i browser"
echo "  2. Gå til Maskiner og konfigurer IP/port"
echo "  3. Opret nøgle-templates med grid-koordinater"
echo "  4. Test forbindelsen med 'Test position' knappen"
