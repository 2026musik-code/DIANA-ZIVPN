#!/bin/bash

# DIANA ZIVPN Auto Installer
# Repo: https://github.com/2026musik-code/DIANA-ZIVPN

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check Root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root${NC}"
  exit
fi

echo -e "${GREEN}Starting DIANA ZIVPN Panel Installation...${NC}"

# 1. Install System Dependencies
echo -e "${YELLOW}[1/6] Installing System Dependencies...${NC}"
apt-get update
apt-get install -y python3 python3-pip python3-venv git curl wget

# 2. Check/Install Zivpn Binary
if [ ! -f "/usr/local/bin/zivpn" ]; then
    echo -e "${YELLOW}[2/6] Zivpn Binary not found. Installing Zivpn...${NC}"
    wget -O zi.sh https://raw.githubusercontent.com/zahidbd2/udp-zivpn/main/zi.sh
    chmod +x zi.sh
    ./zi.sh
    # clean up
    rm zi.sh
else
    echo -e "${GREEN}[2/6] Zivpn Binary already installed.${NC}"
fi

# 3. Setup Panel Directory
INSTALL_DIR="/opt/diana-zivpn"
REPO_URL="https://github.com/2026musik-code/DIANA-ZIVPN"

echo -e "${YELLOW}[3/6] Setting up Panel at $INSTALL_DIR...${NC}"

if [ -d "$INSTALL_DIR" ]; then
    echo "Directory exists. Updating..."
    cd "$INSTALL_DIR" || exit
    git pull origin main || git pull
else
    echo "Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR" || exit
fi

# 4. Setup Python Environment
echo -e "${YELLOW}[4/6] Setting up Python Environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# Initialize Database
echo "Initializing Database..."
./venv/bin/python3 init_project.py

# Configure Production Mode
echo "Configuring Production Mode..."
sed -i 's/MOCK_MODE = True/MOCK_MODE = False/g' utils/system.py
sed -i 's/MOCK_MODE = True/MOCK_MODE = False/g' utils/zivpn_config.py
# Also ensure Zivpn config util points to right path if needed, but default is /etc/zivpn/config.json which matches Zivpn installer.

# 5. Setup Systemd Service
echo -e "${YELLOW}[5/6] Creating Systemd Service...${NC}"
cat <<EOF > /etc/systemd/system/diana-zivpn.service
[Unit]
Description=Diana Zivpn Web Panel
After=network.target

[Service]
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/gunicorn -w 4 -b 0.0.0.0:80 app:app
Restart=always
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable diana-zivpn
systemctl restart diana-zivpn

# 6. Setup Cron Job
echo -e "${YELLOW}[6/6] Setting up Auto-Delete Cron Job...${NC}"
# Remove existing cron job for this script to avoid duplicates
crontab -l | grep -v "cron_cleanup.py" | crontab -
# Add new one
(crontab -l 2>/dev/null; echo "0 0 * * * cd $INSTALL_DIR && ./venv/bin/python3 cron_cleanup.py >> cron.log 2>&1") | crontab -

echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}   INSTALLATION COMPLETE SUCCESSFULL      ${NC}"
echo -e "${GREEN}==========================================${NC}"
echo -e "Access your panel at: http://$(hostname -I | awk '{print $1}')/"
echo -e "Default Admin: admin / admin123"
echo -e "${YELLOW}Please change your admin password immediately!${NC}"
