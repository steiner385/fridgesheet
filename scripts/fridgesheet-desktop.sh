#!/usr/bin/env bash
# Desktop-shortcut wrapper for `fridgesheet print-sheet`.
#
#   fridgesheet-desktop.sh pdf     refresh, build today's sheet, open the PDF in Evince (prints nothing)
#   fridgesheet-desktop.sh print   refresh, build, send to the printer, even if today already printed
#
# Meant to run in a terminal window (Terminal=true in the .desktop file) so the 1-3 min
# refresh shows progress. The viewer is started detached (setsid) so it outlives the
# terminal window, which closes as soon as this script exits.
set -u
MODE="${1:-pdf}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The venv beside this checkout, whatever the checkout is called; FRIDGESHEET_BIN overrides.
BIN="${FRIDGESHEET_BIN:-$HERE/../.venv/bin/fridgesheet}"
HOME_DIR="${FRIDGESHEET_HOME:-$HOME/.fridgesheet}"
LOG="$HOME_DIR/print-sheet.log"
TODAY="$(date +%F)"
LOCAL_PDF="$HOME_DIR/sheets/$TODAY/sheet.pdf"

notify() { command -v notify-send >/dev/null && notify-send -a "Fridge Sheet" "$1" "$2" 2>/dev/null || true; }
pause() { echo; read -r -n 1 -s -p "Press any key to close this window." || true; echo; }
last_log() { tail -n 1 "$LOG" 2>/dev/null || true; }
# The archive copy (Google Drive) if the run made one, else the local file.
saved_pdf() { local p; p="$(last_log | sed -n 's/.* saved=\(.*\.pdf\).*/\1/p')"; [ -n "$p" ] && [ -f "$p" ] && echo "$p" || echo "$LOCAL_PDF"; }
open_pdf() {
  if command -v evince >/dev/null; then
    setsid -f evince "$1" </dev/null >/dev/null 2>&1
  else
    setsid -f xdg-open "$1" </dev/null >/dev/null 2>&1
  fi
}

case "$MODE" in
  pdf)
    echo "Building today's sheet (refreshing Canvas + HAC first, 1-3 min)..."
    # --force: the skip list should not stop a sheet someone asked for by hand.
    if "$BIN" print-sheet --dry-run --force; then
      PDF="$(saved_pdf)"
      echo; echo "Saved: $PDF"
      notify "Sheet ready" "$PDF"
      open_pdf "$PDF"
      sleep 2   # give the viewer a moment to start before the terminal goes away
    else
      notify "Sheet not built" "$(last_log)"
      pause
    fi
    ;;
  print)
    echo "Building and printing today's sheet (refreshing Canvas + HAC first, 1-3 min)..."
    # --reprint: a deliberate click after the 2 PM run still gets a fresh copy.
    if "$BIN" print-sheet --force --reprint; then
      echo; echo "Saved: $(saved_pdf)"
      notify "Sheet sent to printer" "$(last_log)"
    else
      notify "Sheet NOT printed" "$(last_log)"
    fi
    pause
    ;;
  *)
    echo "usage: $0 pdf|print" >&2
    exit 2
    ;;
esac
