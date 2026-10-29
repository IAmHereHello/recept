#!/usr/bin/env bash
# ReceptApp — printer setup for one-tap printing from the app.
# Run once on the Pi:   bash scripts/setup-printer.sh
# Printer not found automatically? Pass its IP address:
#                       bash scripts/setup-printer.sh 192.168.1.50
#
# Adds the Wi-Fi printer (built for the Epson XP-7100, but any AirPrint /
# IPP Everywhere printer works) as CUPS queue "recept-printer", driverless.
# Jobs sent while the printer is off wait in the queue and print as soon as
# it comes back on.

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}[✓]${NC} $*"; }
step() { echo -e "${YELLOW}[→]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$INSTALL_DIR/backend/.env"
QUEUE="recept-printer"
MODEL_MATCH="${PRINTER_MATCH:-XP-7100}"
PRINTER_IP="${1:-}"

# ── Packages: CUPS for the queue, avahi to find the printer, Chromium to make the PDF
step "Benodigde pakketten installeren (CUPS, Chromium)..."
sudo apt-get update -qq
sudo apt-get install -y -qq cups cups-client avahi-daemon
if ! command -v chromium >/dev/null && ! command -v chromium-browser >/dev/null; then
  sudo apt-get install -y -qq chromium || sudo apt-get install -y -qq chromium-browser
fi
sudo systemctl enable --now cups avahi-daemon
info "Pakketten OK"

# ── Find the printer ────────────────────────────────────────────────────────
if [ -n "$PRINTER_IP" ]; then
  URI="ipp://$PRINTER_IP/ipp/print"
else
  step "Printer zoeken op het netwerk ($MODEL_MATCH)..."
  URI=""
  for _ in 1 2 3; do
    URI="$(sudo lpinfo --include-schemes dnssd -v 2>/dev/null | awk '{print $2}' | grep -i "${MODEL_MATCH// /%20}" | grep -i "_ipp" | head -1 || true)"
    [ -n "$URI" ] && break
    sleep 3
  done
  [ -n "$URI" ] || die "Printer niet gevonden. Staat hij aan en op dezelfde wifi? Of geef het IP-adres mee: bash scripts/setup-printer.sh 192.168.1.50"
fi
info "Printer: $URI"

# ── Add the queue (driverless IPP Everywhere), A4, retry instead of pausing ──
step "Printer toevoegen als '$QUEUE'..."
sudo lpadmin -p "$QUEUE" -E -v "$URI" -m everywhere \
  -o media-default=iso_a4_210x297mm \
  -o printer-error-policy=retry-current-job \
  -D "ReceptApp printer"
sudo cupsenable "$QUEUE"
sudo cupsaccept "$QUEUE"
info "Printer toegevoegd"

# ── Tell the backend which queue to use ─────────────────────────────────────
touch "$ENV_FILE"
if grep -q '^PRINTER_NAME=' "$ENV_FILE"; then
  sed -i "s/^PRINTER_NAME=.*/PRINTER_NAME=$QUEUE/" "$ENV_FILE"
else
  echo "PRINTER_NAME=$QUEUE" >> "$ENV_FILE"
fi
info "PRINTER_NAME=$QUEUE opgeslagen in $ENV_FILE"

systemctl --user restart receptapp-backend 2>/dev/null && info "Backend herstart" \
  || echo "    Herstart de backend zelf: systemctl --user restart receptapp-backend"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  ${GREEN}Klaar!${NC} De printknop in de app print nu direct."
echo "  Testen: open een recept en tik op het printer-icoon."
echo "  Wachtrij bekijken: lpstat -o"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
