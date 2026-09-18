#!/bin/bash
# ============================================================================
# meshcore-pathbot run script
#
# Quick way to run the bot manually (outside of systemd).
# Useful for testing and debugging.
#
# Usage:
#   ./run.sh                          # Uses default config
#   ./run.sh --serial /dev/ttyUSB0    # Override connection
#   ./run.sh --debug                  # Enable debug logging
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/meshcore-pathbot"
CONFIG_DIR="/etc/meshcore-pathbot"
DATA_DIR="/var/lib/meshcore-pathbot"

# Determine where we're running from
if [[ -f "${SCRIPT_DIR}/venv/bin/python" ]]; then
    # Running from the install directory
    VENV="${SCRIPT_DIR}/venv"
    CONFIG="${SCRIPT_DIR}/config.toml"
elif [[ -f "${INSTALL_DIR}/venv/bin/python" ]]; then
    # Running from anywhere, use installed version
    VENV="${INSTALL_DIR}/venv"
    CONFIG="${CONFIG_DIR}/config.toml"
else
    # Not installed yet, try local dev setup
    if [[ -f "${SCRIPT_DIR}/pyproject.toml" ]]; then
        echo "[INFO] No venv found. Creating one for local development..."
        python3 -m venv "${SCRIPT_DIR}/venv"
        source "${SCRIPT_DIR}/venv/bin/activate"
        pip install -e "${SCRIPT_DIR}" > /dev/null 2>&1
        VENV="${SCRIPT_DIR}/venv"
        CONFIG="${SCRIPT_DIR}/config.toml"
    else
        echo "[ERROR] Cannot find meshcore-pathbot installation."
        echo "Run install.sh first, or run from the project directory."
        exit 1
    fi
fi

# Use config file if it exists
EXTRA_ARGS=()
if [[ -f "$CONFIG" ]]; then
    EXTRA_ARGS+=("--config" "$CONFIG")
fi

echo "[INFO] Using venv: ${VENV}"
echo "[INFO] Config: ${CONFIG:-none}"
echo "[INFO] Extra args: $*"
echo ""

# Run the bot
exec "${VENV}/bin/python" -m meshcore_pathbot "${EXTRA_ARGS[@]}" "$@"
