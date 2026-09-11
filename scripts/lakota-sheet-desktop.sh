#!/usr/bin/env bash
# Desktop-shortcut wrapper for `lakota-grades print-sheet`.
#
#   lakota-sheet-desktop.sh pdf     refresh, build today's sheet, open the PDF in Evince (prints nothing)
#   lakota-sheet-desktop.sh print   refresh, build, send to the printer, even if today already printed
#
# Meant to run in a terminal window (Terminal=true in the .desktop file) so the 1-3 min
# refresh shows progress. Ends with a desktop notification and a key press so the window
# does not vanish before the result can be read.
set -u
MODE="${1:-pdf}"
BIN="${LAKOTA_GRADES_BIN:-$HOME/lakota-grades-mcp/.venv/bin/lakota-grades}"
HOME_DIR="${LAKOTA_GRADES_HOME:-$HOME/.lakota-grades}"
TODAY="$(date +%F)"
PDF="$HOME_DIR/sheets/$TODAY/sheet.pdf"

notify() { command -v notify-send >/dev/null && notify-send -a "Lakota sheet" "$1" "$2" || true; }
pause() { echo; read -r -n 1 -s -p "Press any key to close this window." || true; echo; }

case "$MODE" in
  pdf)
    echo "Building today's sheet (refreshing Canvas + HAC first, 1-3 min)..."
    # --force: the skip list should not stop a sheet someone asked for by hand.
    if "$BIN" print-sheet --dry-run --force; then
      notify "Sheet ready" "Opening $PDF"
      if command -v evince >/dev/null; then evince "$PDF" >/dev/null 2>&1 & else xdg-open "$PDF" >/dev/null 2>&1 & fi
      sleep 1
    else
      notify "Sheet not built" "See ~/.lakota-grades/print-sheet.log"
      pause
    fi
    ;;
  print)
    echo "Building and printing today's sheet (refreshing Canvas + HAC first, 1-3 min)..."
    # --reprint: a deliberate click after the 2 PM run still gets a fresh copy.
    if "$BIN" print-sheet --force --reprint; then
      notify "Sheet sent to printer" "$(tail -n 1 "$HOME_DIR/print-sheet.log")"
    else
      notify "Sheet NOT printed" "$(tail -n 1 "$HOME_DIR/print-sheet.log")"
    fi
    pause
    ;;
  *)
    echo "usage: $0 pdf|print" >&2
    exit 2
    ;;
esac
