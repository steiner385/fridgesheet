#!/usr/bin/env bash
# The old name of scripts/fridgesheet-desktop.sh, kept for one release so a desktop shortcut
# made before the rename to Fridge Sheet keeps working. Point new shortcuts at the new name.
exec "$(dirname "${BASH_SOURCE[0]}")/fridgesheet-desktop.sh" "$@"
