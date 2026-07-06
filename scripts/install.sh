#!/usr/bin/env bash
# ReceptApp — Raspberry Pi install script
# Run once after cloning: bash scripts/install.sh

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
die()     { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Derive install dir from this script's location ──────────────────────────
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$INSTALL_DIR/backend"
FRONTEND_DIR="$INSTALL_DIR/frontend"
SCRIPTS_DIR="$INSTALL_DIR/scripts"
SERVICE_DIR="$HOME/.config/systemd/user"
DESKTOP_DIR="$HOME/Desktop"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ReceptApp — Pi installer"
echo "  Install dir: $INSTALL_DIR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Prerequisites ────────────────────────────────────────────────────────────
command -v python3 >/dev/null || die "python3 not found. Run: sudo apt install python3 python3-pip python3-venv"
command -v node    >/dev/null || die "node not found. Run: sudo apt install nodejs npm"
command -v npm     >/dev/null || die "npm not found."
command -v git     >/dev/null || die "git not found."
info "Prerequisites OK"

# ── Python venv ──────────────────────────────────────────────────────────────
if [ ! -d "$BACKEND_DIR/venv" ]; then
  info "Creating Python virtual environment..."
  python3 -m venv "$BACKEND_DIR/venv"
fi
info "Installing Python dependencies..."
"$BACKEND_DIR/venv/bin/pip" install -q --upgrade pip
"$BACKEND_DIR/venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

# ── API key ──────────────────────────────────────────────────────────────────
if [ ! -f "$BACKEND_DIR/.env" ]; then
  echo ""
  warn "Anthropic API key required for AI recipe import."
  warn "Get one at: https://console.anthropic.com"
  read -rp "  Enter your ANTHROPIC_API_KEY (or press Enter to skip): " API_KEY
  if [ -n "$API_KEY" ]; then
    echo "ANTHROPIC_API_KEY=$API_KEY" > "$BACKEND_DIR/.env"
    info "Saved to $BACKEND_DIR/.env"
  else
    echo "ANTHROPIC_API_KEY=" > "$BACKEND_DIR/.env"
    warn "No key set — AI import will not work until you edit $BACKEND_DIR/.env"
  fi
else
  info ".env already exists, skipping"
fi

# ── Node / frontend ──────────────────────────────────────────────────────────
info "Installing Node dependencies..."
npm --prefix "$FRONTEND_DIR" install --silent

info "Building frontend..."
npm --prefix "$FRONTEND_DIR" run build

# ── Systemd user services ────────────────────────────────────────────────────
mkdir -p "$SERVICE_DIR"

info "Writing systemd service: receptapp-backend"
cat > "$SERVICE_DIR/receptapp-backend.service" <<EOF
[Unit]
Description=ReceptApp Backend
After=network.target

[Service]
WorkingDirectory=$BACKEND_DIR
EnvironmentFile=$BACKEND_DIR/.env
ExecStart=$BACKEND_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

info "Writing systemd service: receptapp-frontend"
NODE_BIN_DIR="$(dirname "$(command -v node)")"
cat > "$SERVICE_DIR/receptapp-frontend.service" <<EOF
[Unit]
Description=ReceptApp Frontend
After=receptapp-backend.service

[Service]
WorkingDirectory=$FRONTEND_DIR
Environment=PATH=$NODE_BIN_DIR:/usr/local/bin:/usr/bin:/bin
ExecStart=$(command -v npm) run preview
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable receptapp-backend receptapp-frontend
systemctl --user start  receptapp-backend receptapp-frontend

# Enable linger so services start at boot without needing to log in first
loginctl enable-linger "$(whoami)"
info "Services enabled and started (boot-persistent)"

# ── Desktop update shortcut ──────────────────────────────────────────────────
mkdir -p "$DESKTOP_DIR"
DESKTOP_FILE="$DESKTOP_DIR/receptapp-update.desktop"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Update ReceptApp
Comment=Pull latest version from GitHub and restart the app
Exec=x-terminal-emulator -e bash -c "$SCRIPTS_DIR/update.sh && echo '' && echo 'Klaar! Druk Enter om te sluiten.' || echo 'Mislukt — zie foutmelding hierboven.'; read"
Icon=system-software-update
Terminal=false
Categories=Utility;
EOF

chmod +x "$DESKTOP_FILE"
chmod +x "$SCRIPTS_DIR/update.sh"
# Trust the desktop file on Raspberry Pi OS (LXDE/Wayfire)
[ -f /usr/bin/gio ] && gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true

info "Desktop shortcut created: $DESKTOP_FILE"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  ${GREEN}ReceptApp installed!${NC}"
echo ""
echo "  Frontend:  http://localhost:3001"
echo "  Backend:   http://localhost:8001"
echo ""
echo "  Service status:"
echo "    systemctl --user status receptapp-backend"
echo "    systemctl --user status receptapp-frontend"
echo ""
echo "  Update button added to desktop."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
