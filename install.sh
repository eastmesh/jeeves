#!/bin/bash
# ============================================================================
# meshcore-pathbot install script for Raspberry Pi 5 (Debian/Bookworm)
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/nasticmc/jeeves/main/install.sh | bash
#   -- or --
#   git clone https://github.com/nasticmc/jeeves.git && cd jeeves && bash install.sh
#
# What this does:
#   1. Installs system dependencies (Python 3.11+, Bluetooth, serial)
#   2. Creates a dedicated user and install directory
#   3. Clones the repo and creates a Python venv
#   4. Installs the package with all dependencies
#   5. Sets up config file
#   6. Installs and enables a systemd service
#   7. Opens the serial port permissions
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
INSTALL_DIR="/opt/meshcore-pathbot"
CONFIG_DIR="/etc/meshcore-pathbot"
DATA_DIR="/var/lib/meshcore-pathbot"
SERVICE_USER="meshcore"
REPO_URL="https://github.com/nasticmc/jeeves.git"
BRANCH="main"
WEB_PORT=8075

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No color

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ---------------------------------------------------------------------------
# Pre-checks
# ---------------------------------------------------------------------------
info "meshcore-pathbot installer for Raspberry Pi 5"
echo ""

# Must be root or sudo
if [[ $EUID -ne 0 ]]; then
    err "This script must be run as root. Try: sudo bash install.sh"
fi

# Check we're on a Debian-based system
if ! command -v apt-get &>/dev/null; then
    err "This script requires apt-get (Debian/Ubuntu). Exiting."
fi

# Check architecture
ARCH=$(uname -m)
info "Architecture: ${ARCH}"
if [[ "$ARCH" != "aarch64" && "$ARCH" != "armv7l" && "$ARCH" != "x86_64" ]]; then
    warn "Unexpected architecture: ${ARCH}. Continuing anyway..."
fi

# ---------------------------------------------------------------------------
# Step 1: System dependencies
# ---------------------------------------------------------------------------
info "Updating package list..."
apt-get update -qq

info "Installing system dependencies..."
apt-get install -y -qq \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    git \
    bluetooth \
    bluez \
    libbluetooth-dev \
    libffi-dev \
    libssl-dev \
    build-essential \
    > /dev/null 2>&1

# Verify Python version (need 3.10+)
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 10 ]]; then
    err "Python 3.10+ required, found ${PYTHON_VERSION}"
fi
ok "Python ${PYTHON_VERSION} found"

# ---------------------------------------------------------------------------
# Step 2: Create service user
# ---------------------------------------------------------------------------
if id "${SERVICE_USER}" &>/dev/null; then
    info "User '${SERVICE_USER}' already exists"
else
    info "Creating service user '${SERVICE_USER}'..."
    useradd --system --shell /usr/sbin/nologin --home-dir "${INSTALL_DIR}" "${SERVICE_USER}"
    ok "Created user '${SERVICE_USER}'"
fi

# Add to dialout group for serial access
usermod -aG dialout "${SERVICE_USER}" 2>/dev/null || true
# Add to bluetooth group for BLE access
usermod -aG bluetooth "${SERVICE_USER}" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Step 3: Clone or update repo
# ---------------------------------------------------------------------------
if [[ -d "${INSTALL_DIR}/.git" ]]; then
    info "Existing installation found, pulling latest..."
    cd "${INSTALL_DIR}"
    git fetch origin
    git reset --hard "origin/${BRANCH}"
    ok "Updated to latest"
else
    info "Cloning repository..."
    rm -rf "${INSTALL_DIR}"
    git clone --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
    ok "Cloned to ${INSTALL_DIR}"
fi

# ---------------------------------------------------------------------------
# Step 4: Python virtual environment and install
# ---------------------------------------------------------------------------
info "Setting up Python virtual environment..."
cd "${INSTALL_DIR}"

if [[ ! -d "venv" ]]; then
    python3 -m venv venv
fi

# Activate and install
source venv/bin/activate

info "Installing meshcore-pathbot and dependencies..."
pip install --upgrade pip setuptools wheel > /dev/null 2>&1
pip install -e ".[ble]" > /dev/null 2>&1
ok "Package installed"

# Verify
if venv/bin/python -m meshcore_pathbot --help > /dev/null 2>&1; then
    ok "meshcore-pathbot CLI verified"
else
    err "Installation verification failed"
fi

deactivate

# ---------------------------------------------------------------------------
# Step 5: Configuration
# ---------------------------------------------------------------------------
mkdir -p "${CONFIG_DIR}"
mkdir -p "${DATA_DIR}"

if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then
    info "Creating default config..."
    cp "${INSTALL_DIR}/config.example.toml" "${CONFIG_DIR}/config.toml"

    # Patch the repeaters_file path to use the data directory
    sed -i "s|repeaters_file = \"repeaters.json\"|repeaters_file = \"${DATA_DIR}/repeaters.json\"|" "${CONFIG_DIR}/config.toml"

    ok "Config created at ${CONFIG_DIR}/config.toml"
    warn "You MUST edit ${CONFIG_DIR}/config.toml to set your connection type and serial port!"
else
    info "Config already exists at ${CONFIG_DIR}/config.toml (not overwriting)"
fi

# Set ownership
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${CONFIG_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${DATA_DIR}"

# ---------------------------------------------------------------------------
# Step 6: Systemd service
# ---------------------------------------------------------------------------
info "Installing systemd service..."

cat > /etc/systemd/system/meshcore-pathbot.service <<SVCEOF
[Unit]
Description=MeshCore PathBot - Path Resolver with Web Dashboard
After=network.target bluetooth.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${DATA_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python -m meshcore_pathbot --config ${CONFIG_DIR}/config.toml
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=${DATA_DIR} ${CONFIG_DIR}
ProtectHome=yes

# Allow serial and bluetooth device access
SupplementaryGroups=dialout bluetooth

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable meshcore-pathbot
ok "Systemd service installed and enabled"

# ---------------------------------------------------------------------------
# Step 7: Detect serial devices
# ---------------------------------------------------------------------------
echo ""
info "Detecting serial devices..."
SERIAL_DEVICES=$(ls /dev/ttyUSB* /dev/ttyACM* /dev/serial/by-id/* 2>/dev/null || true)
if [[ -n "$SERIAL_DEVICES" ]]; then
    ok "Found serial devices:"
    echo "$SERIAL_DEVICES" | while read -r dev; do
        echo "    $dev"
    done
else
    warn "No serial devices found. Plug in your MeshCore radio and check again."
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "============================================================================"
echo -e "${GREEN}Installation complete!${NC}"
echo "============================================================================"
echo ""
echo "  Install dir:  ${INSTALL_DIR}"
echo "  Config file:  ${CONFIG_DIR}/config.toml"
echo "  Data dir:     ${DATA_DIR}"
echo "  Service:      meshcore-pathbot.service"
echo "  Web UI:       http://$(hostname -I | awk '{print $1}'):${WEB_PORT}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Edit your config:"
echo "     sudo nano ${CONFIG_DIR}/config.toml"
echo ""
echo "  2. Set your connection type and serial port, e.g.:"
echo "     [connection]"
echo "     type = \"serial\""
echo "     serial_port = \"/dev/ttyUSB0\""
echo ""
echo "  3. Start the service:"
echo "     sudo systemctl start meshcore-pathbot"
echo ""
echo "  4. Check status:"
echo "     sudo systemctl status meshcore-pathbot"
echo "     sudo journalctl -u meshcore-pathbot -f"
echo ""
echo "  5. Open the dashboard:"
echo "     http://$(hostname -I | awk '{print $1}'):${WEB_PORT}"
echo ""
echo "============================================================================"
