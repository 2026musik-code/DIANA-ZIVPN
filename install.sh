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

# Ask for Domain
echo -e "${YELLOW}Do you want to use a Domain with SSL? (y/n)${NC}"
read -r USE_DOMAIN
DOMAIN=""
if [[ "$USE_DOMAIN" =~ ^[Yy]$ ]]; then
    echo -e "Enter your domain name (e.g., vpn.example.com): "
    read -r DOMAIN
fi

# 1. Install System Dependencies
echo -e "${YELLOW}[1/7] Installing System Dependencies...${NC}"
# lsof is needed for checking ports
apt-get update
apt-get install -y python3 python3-pip python3-venv git curl wget lsof ufw

if [[ -n "$DOMAIN" ]]; then
    echo -e "${YELLOW}Installing Nginx and Certbot...${NC}"
    apt-get install -y nginx certbot python3-certbot-nginx
fi

# 2. Check/Install Zivpn Binary
if [ ! -f "/usr/local/bin/zivpn" ]; then
    echo -e "${YELLOW}[2/7] Zivpn Binary not found. Installing Zivpn...${NC}"
    wget -O zi.sh https://raw.githubusercontent.com/zahidbd2/udp-zivpn/main/zi.sh
    chmod +x zi.sh
    ./zi.sh
    # clean up
    rm zi.sh
else
    echo -e "${GREEN}[2/7] Zivpn Binary already installed.${NC}"
fi

# 3. Setup Panel Directory
INSTALL_DIR="/opt/diana-zivpn"
REPO_URL="https://github.com/2026musik-code/DIANA-ZIVPN"

echo -e "${YELLOW}[3/7] Setting up Panel at $INSTALL_DIR...${NC}"

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
echo -e "${YELLOW}[4/7] Setting up Python Environment...${NC}"
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

# 5. Firewall & Port Handling
echo -e "${YELLOW}[5/7] Configuring Firewall & Ports...${NC}"

# Stop common conflicting services on port 80 if NOT using Domain (Nginx needs port 80)
# If using Domain, we need Nginx, so we shouldn't kill it blindly, but we might need to restart it later.
if [[ -z "$DOMAIN" ]]; then
    if lsof -Pi :80 -sTCP:LISTEN -t >/dev/null ; then
        echo -e "${RED}Port 80 is busy. Attempting to free it...${NC}"
        systemctl stop apache2 2>/dev/null
        systemctl disable apache2 2>/dev/null
        systemctl stop nginx 2>/dev/null
        systemctl disable nginx 2>/dev/null
    fi
fi

# Open Ports
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 5667/udp
ufw allow 6000:19999/udp

# 6. Setup Systemd Service
echo -e "${YELLOW}[6/7] Creating Systemd Service...${NC}"

# If using domain + nginx, Gunicorn binds to localhost:8000
# If using IP only, Gunicorn binds to 0.0.0.0:80
BIND_ADDR="0.0.0.0:80"
if [[ -n "$DOMAIN" ]]; then
    BIND_ADDR="127.0.0.1:8000"
fi

cat <<EOF > /etc/systemd/system/diana-zivpn.service
[Unit]
Description=Diana Zivpn Web Panel
After=network.target

[Service]
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/gunicorn -w 4 -b $BIND_ADDR app:app
Restart=always
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable diana-zivpn
systemctl restart diana-zivpn

# 6b. Setup Nginx & SSL if Domain provided
if [[ -n "$DOMAIN" ]]; then
    echo -e "${YELLOW}Configuring Nginx for $DOMAIN...${NC}"

    cat <<EOF > /etc/nginx/sites-available/diana-zivpn
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF
    ln -s /etc/nginx/sites-available/diana-zivpn /etc/nginx/sites-enabled/ 2>/dev/null
    rm /etc/nginx/sites-enabled/default 2>/dev/null

    systemctl restart nginx

    echo -e "${YELLOW}Obtaining SSL Certificate...${NC}"
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m admin@$DOMAIN --redirect
fi

# 7. Setup Cron Job
echo -e "${YELLOW}[7/7] Setting up Auto-Delete Cron Job...${NC}"
crontab -l 2>/dev/null | grep -v "cron_cleanup.py" | crontab -
(crontab -l 2>/dev/null; echo "0 0 * * * cd $INSTALL_DIR && ./venv/bin/python3 cron_cleanup.py >> cron.log 2>&1") | crontab -

echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}   INSTALLATION COMPLETE SUCCESSFULL      ${NC}"
echo -e "${GREEN}==========================================${NC}"

# Service Check
if systemctl is-active --quiet diana-zivpn; then
    echo -e "${GREEN}Service is RUNNING.${NC}"
else
    echo -e "${RED}Service failed to start! Check logs: journalctl -u diana-zivpn -n 20${NC}"
fi

if [[ -n "$DOMAIN" ]]; then
    echo -e "Access your panel at: https://$DOMAIN/"
else
    IP=$(hostname -I | awk '{print $1}')
    echo -e "Access your panel at: http://$IP/"
fi

echo -e "Default Admin: admin / admin123"
echo -e "${YELLOW}Please change your admin password immediately!${NC}"
