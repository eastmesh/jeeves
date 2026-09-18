#!/bin/bash
# ============================================================================
# meshcore-pathbot update script
#
# Usage:
#   sudo bash update.sh            # Update systemd installation
#   bash update.sh                 # Update local dev setup
#   bash update.sh --branch main   # Update to a specific branch
#
# What this does:
#   1. Detects the installation type (systemd or local dev)
#   2. Stops the service if it is running
#   3. Pulls the latest code from git
#   4. Reinstalls the Python package and dependencies
#   5. Restarts the service (if it was running before)
#   6. Reports the new version
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
INSTALL_DIR="/opt/meshcore-pathbot"
CONFIG_DIR="/etc/meshcore-pathbot"
DATA_DIR="/var/lib/meshcore-pathbot"
SERVICE_NAME="meshcore-pathbot"
BRANCH="main"

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
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --branch|-b)
            BRANCH="${2:?--branch requires a value}"
            shift 2
            ;;
        --help|-h)
            echo "Usage: sudo bash update.sh [--branch BRANCH]"
            echo ""
            echo "Options:"
            echo "  --branch, -b BRANCH   Git branch to update to (default: main)"
            echo "  --help,   -h          Show this help message"
            exit 0
            ;;
        *)
            err "Unknown option: $1"
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Detect installation mode
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -d "${INSTALL_DIR}/.git" ]]; then
    MODE="systemd"
    REPO_DIR="${INSTALL_DIR}"
    VENV="${INSTALL_DIR}/venv"
    info "Detected systemd installation at ${INSTALL_DIR}"
elif [[ -d "${SCRIPT_DIR}/.git" ]]; then
    MODE="dev"
    REPO_DIR="${SCRIPT_DIR}"
    VENV="${SCRIPT_DIR}/venv"
    info "Detected local dev setup at ${SCRIPT_DIR}"
else
    err "No meshcore-pathbot installation found. Run install.sh first."
fi

# Systemd updates require root
if [[ "${MODE}" == "systemd" && $EUID -ne 0 ]]; then
    err "Updating a systemd installation requires root. Try: sudo bash update.sh"
fi

# ---------------------------------------------------------------------------
# Step 1: Stop service if running
# ---------------------------------------------------------------------------
SERVICE_WAS_RUNNING=false

if [[ "${MODE}" == "systemd" ]] && systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
    info "Stopping ${SERVICE_NAME} service..."
    systemctl stop "${SERVICE_NAME}"
    SERVICE_WAS_RUNNING=true
    ok "Service stopped"
fi

# ---------------------------------------------------------------------------
# Step 2: Pull latest code
# ---------------------------------------------------------------------------
info "Fetching latest code (branch: ${BRANCH})..."

cd "${REPO_DIR}"

OLD_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")

git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git reset --hard "origin/${BRANCH}"

NEW_COMMIT=$(git rev-parse HEAD)

if [[ "${OLD_COMMIT}" == "${NEW_COMMIT}" ]]; then
    ok "Already up to date (${NEW_COMMIT:0:8})"
else
    ok "Updated ${OLD_COMMIT:0:8} → ${NEW_COMMIT:0:8}"
    # Show a brief summary of what changed
    echo ""
    git log --oneline "${OLD_COMMIT}..${NEW_COMMIT}" | head -10 | while read -r line; do
        echo "    ${line}"
    done
    echo ""
fi

# ---------------------------------------------------------------------------
# Step 3: Update Python package
# ---------------------------------------------------------------------------
info "Updating Python package and dependencies..."

if [[ ! -d "${VENV}" ]]; then
    info "Virtual environment not found, creating..."
    python3 -m venv "${VENV}"
fi

"${VENV}/bin/pip" install --upgrade pip setuptools wheel > /dev/null 2>&1
"${VENV}/bin/pip" install --upgrade -e "${REPO_DIR}[ble]" > /dev/null 2>&1

ok "Package updated"

# Verify the installation
if "${VENV}/bin/python" -m meshcore_pathbot --help > /dev/null 2>&1; then
    ok "meshcore-pathbot CLI verified"
else
    err "Post-update verification failed. Check the logs."
fi

# ---------------------------------------------------------------------------
# Step 4: Fix permissions (systemd only)
# ---------------------------------------------------------------------------
if [[ "${MODE}" == "systemd" ]]; then
    chown -R meshcore:meshcore "${INSTALL_DIR}"
fi

# ---------------------------------------------------------------------------
# Step 5: Restart service
# ---------------------------------------------------------------------------
if [[ "${MODE}" == "systemd" ]]; then
    if "${SERVICE_WAS_RUNNING}"; then
        info "Restarting ${SERVICE_NAME} service..."
        systemctl start "${SERVICE_NAME}"
        # Give it a moment to confirm it came up
        sleep 2
        if systemctl is-active --quiet "${SERVICE_NAME}"; then
            ok "Service restarted successfully"
        else
            err "Service failed to start. Check: sudo journalctl -u ${SERVICE_NAME} -n 50"
        fi
    else
        warn "Service was not running before the update — not starting it automatically."
        echo "  To start: sudo systemctl start ${SERVICE_NAME}"
    fi
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "============================================================================"
echo -e "${GREEN}Update complete!${NC}"
echo "============================================================================"
echo ""
echo "  Commit:   ${NEW_COMMIT:0:8} (${BRANCH})"
if [[ "${MODE}" == "systemd" ]]; then
    echo "  Service:  $(systemctl is-active ${SERVICE_NAME} 2>/dev/null || echo 'inactive')"
    echo ""
    echo "  To view logs:"
    echo "    sudo journalctl -u ${SERVICE_NAME} -f"
fi
echo ""
echo "============================================================================"
