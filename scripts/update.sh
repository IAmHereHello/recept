#!/usr/bin/env bash
# ReceptApp — update script
# Called by the desktop button. Pulls latest code and restarts services.

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}[✓]${NC} $*"; }
step() { echo -e "${YELLOW}[→]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$INSTALL_DIR/backend"
FRONTEND_DIR="$INSTALL_DIR/frontend"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ReceptApp updater"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

step "Ophalen van GitHub..."
cd "$INSTALL_DIR"
git pull origin main

step "Python afhankelijkheden bijwerken..."
"$BACKEND_DIR/venv/bin/pip" install -q --upgrade pip
"$BACKEND_DIR/venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

step "Node afhankelijkheden bijwerken..."
npm --prefix "$FRONTEND_DIR" install --silent

step "Frontend bouwen..."
npm --prefix "$FRONTEND_DIR" run build

step "Services herstarten..."
systemctl --user restart receptapp-backend
systemctl --user restart receptapp-frontend

echo ""
info "Backend:  $(systemctl --user is-active receptapp-backend)"
info "Frontend: $(systemctl --user is-active receptapp-frontend)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  ${GREEN}Update voltooid!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
