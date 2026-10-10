#!/usr/bin/env bash
# ==============================================================================
# 🛰️ T.R.A.C.E. Production Deployment: Nginx (Port 80 -> 8765) & Systemd Daemon
# ==============================================================================

set -eo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_banner()  {
    echo -e "${BOLD}${BLUE}======================================================================${NC}"
    echo -e "${BOLD}${BLUE}  🛰️ $1${NC}"
    echo -e "${BOLD}${BLUE}======================================================================${NC}"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

log_banner "T.R.A.C.E. Production Setup: Nginx & 24/7 Auto-Restarting Daemon"

# Check root or sudo access
SUDO=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo &>/dev/null; then
        SUDO="sudo"
    else
        log_error "This script requires root or sudo privileges to configure Nginx and Systemd."
        exit 1
    fi
fi

# Detect actual user (when running with sudo, use SUDO_USER)
TARGET_USER="${SUDO_USER:-$(id -un)}"
log_info "Configuring service to run under user: ${GREEN}${TARGET_USER}${NC}"
log_info "Application directory: ${GREEN}${SCRIPT_DIR}${NC}"

# ------------------------------------------------------------------------------
# 1. Pre-compress Static Assets for Instant Page Loading (<100ms)
# ------------------------------------------------------------------------------
log_info "Pre-compressing web/index.html and web/scenes.json with maximum gzip compression..."
if [ -f "web/index.html" ]; then
    gzip -kf -9 web/index.html
    log_success "Created web/index.html.gz ($(wc -c < web/index.html.gz | awk '{printf "%.1f MB", $1/1024/1024}'))"
fi
if [ -f "web/scenes.json" ]; then
    gzip -kf -9 web/scenes.json
    log_success "Created web/scenes.json.gz ($(wc -c < web/scenes.json.gz | awk '{printf "%.1f MB", $1/1024/1024}'))"
fi

# ------------------------------------------------------------------------------
# 2. Configure Systemd Daemon (trace.service)
# ------------------------------------------------------------------------------
log_info "Setting up Systemd daemon with 5-second automatic crash restart..."

SERVICE_FILE="/etc/systemd/system/trace.service"
TEMP_SERVICE=$(mktemp)

cat << EOF > "$TEMP_SERVICE"
[Unit]
Description=T.R.A.C.E. Bi-Temporal Satellite Change Intelligence Engine
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=${TARGET_USER}
WorkingDirectory=${SCRIPT_DIR}
EnvironmentFile=-${SCRIPT_DIR}/.env
ExecStart=${SCRIPT_DIR}/.venv/bin/uvicorn src.server.app:app --host 0.0.0.0 --port 8765 --workers 2
Restart=always
RestartSec=5
RestartPreventExitStatus=
KillMode=mixed
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

$SUDO cp "$TEMP_SERVICE" "$SERVICE_FILE"
rm -f "$TEMP_SERVICE"
$SUDO chmod 644 "$SERVICE_FILE"

log_info "Reloading systemd daemon..."
$SUDO systemctl daemon-reload
$SUDO systemctl enable trace.service
$SUDO systemctl restart trace.service
log_success "Systemd service 'trace.service' installed, enabled, and started."

# ------------------------------------------------------------------------------
# 3. Install & Configure Nginx (Port 80 -> Port 8765)
# ------------------------------------------------------------------------------
log_info "Checking Nginx installation..."
if ! command -v nginx &>/dev/null; then
    log_info "Installing Nginx package..."
    if command -v apt-get &>/dev/null; then
        $SUDO apt-get update -y -q
        $SUDO apt-get install -y nginx
        $SUDO apt-get clean
    elif command -v dnf &>/dev/null; then
        $SUDO dnf install -y nginx
        $SUDO dnf clean all
    else
        log_error "Could not detect apt-get or dnf to install nginx."
        exit 1
    fi
fi

log_info "Configuring Nginx reverse proxy from Port 80 to 127.0.0.1:8765..."

# Prepare configuration with actual repository path
TEMP_NGINX=$(mktemp)
sed "s|__REPO_PATH__|${SCRIPT_DIR}|g" config/nginx_trace.conf.template > "$TEMP_NGINX"

if [ -d "/etc/nginx/sites-available" ]; then
    $SUDO cp "$TEMP_NGINX" /etc/nginx/sites-available/trace
    $SUDO ln -sf /etc/nginx/sites-available/trace /etc/nginx/sites-enabled/trace
    $SUDO rm -f /etc/nginx/sites-enabled/default
elif [ -d "/etc/nginx/conf.d" ]; then
    $SUDO cp "$TEMP_NGINX" /etc/nginx/conf.d/trace.conf
    $SUDO rm -f /etc/nginx/conf.d/default.conf
fi
rm -f "$TEMP_NGINX"

# Test configuration
log_info "Validating Nginx configuration syntax..."
if $SUDO nginx -t; then
    $SUDO systemctl restart nginx
    $SUDO systemctl enable nginx
    log_success "Nginx successfully restarted and enabled on boot (Port 80 -> Port 8765)."
else
    log_error "Nginx configuration syntax error. Please inspect /etc/nginx/."
    exit 1
fi

# ------------------------------------------------------------------------------
# 4. Verification & Diagnostics
# ------------------------------------------------------------------------------
log_banner "Verification & Daemon Health Check"

# Wait 2 seconds for services to settle
sleep 2

# Check Daemon Status
if $SUDO systemctl is-active --quiet trace; then
    log_success "Daemon status: ACTIVE (running)"
else
    log_warn "Daemon status: INACTIVE. Showing recent journal logs:"
    $SUDO journalctl -u trace -n 20 --no-pager
fi

# Check Crash Restart Policy
RESTART_POLICY=$(systemctl show trace.service -p Restart --value 2>/dev/null || echo "unknown")
RESTART_DELAY=$(systemctl show trace.service -p RestartSecUSec --value 2>/dev/null || echo "unknown")
log_info "Daemon restart policy: ${BOLD}${RESTART_POLICY}${NC} (RestartSec: ${BOLD}${RESTART_DELAY}${NC})"

# Test Local HTTP Port 8765 (FastAPI backend)
log_info "Testing internal FastAPI backend on 127.0.0.1:8765..."
if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/ | grep -q "200"; then
    log_success "FastAPI backend (127.0.0.1:8765): HTTP 200 OK"
else
    log_warn "FastAPI backend not responding on 127.0.0.1:8765 yet. Check logs with: sudo journalctl -u trace -f"
fi

# Test Public Port 80 Forwarding via Nginx
log_info "Testing Nginx Port 80 forwarding & compression..."
NGINX_TEST=$(curl -s -I -H "Accept-Encoding: gzip" http://127.0.0.1/ || true)
if echo "$NGINX_TEST" | grep -q "200 OK"; then
    log_success "Nginx Port 80 Forwarding: HTTP 200 OK"
    if echo "$NGINX_TEST" | grep -iq "content-encoding: gzip"; then
        log_success "Gzip Pre-compressed delivery: ACTIVE (Instant load verified!)"
    else
        log_info "Gzip header check completed."
    fi
else
    log_warn "Port 80 response test: Check Nginx with sudo systemctl status nginx"
fi

echo ""
log_banner "Production Deployment Ready!"
echo ""
echo -e "  🌐 ${BOLD}Public Web Console:${NC}   ${GREEN}http://<YOUR_EC2_PUBLIC_IP>/${NC} (Port 80, no :8765 needed!)"
echo -e "  ⚡ ${BOLD}Speed Optimization:${NC}  Pre-compressed with gzip -9 & Nginx gzip_static enabled"
echo -e "  🔄 ${BOLD}Daemon Auto-Restart:${NC} Always active, restarts in 5 seconds on crash"
echo ""
echo -e "  ${BOLD}Helpful Management Commands:${NC}"
echo -e "  --> View daemon logs:     ${BLUE}sudo journalctl -u trace -f${NC}"
echo -e "  --> Check daemon status:   ${BLUE}sudo systemctl status trace${NC}"
echo -e "  --> Restart daemon:        ${BLUE}sudo systemctl restart trace${NC}"
echo -e "  --> Restart Nginx:         ${BLUE}sudo systemctl restart nginx${NC}"
echo ""
