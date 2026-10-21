#!/usr/bin/env bash
# Removes GifPop. Keeps your settings and recents unless you pass --purge.
set -uo pipefail
data="${XDG_DATA_HOME:-$HOME/.local/share}"
config="${XDG_CONFIG_HOME:-$HOME/.config}"

"$HOME/.local/bin/gifpop" --quit >/dev/null 2>&1 || pkill -f "python3 -m gifpop" 2>/dev/null
if command -v gdbus >/dev/null; then
  gdbus call --session --dest org.kde.kglobalaccel --object-path /kglobalaccel \
    --method org.kde.KGlobalAccel.unregister gifpop.desktop _launch >/dev/null 2>&1
fi
rm -rf "$HOME/.local/lib/gifpop"
rm -f "$HOME/.local/bin/gifpop" "$data/applications/gifpop.desktop" \
      "$config/autostart/gifpop.desktop" "$data/icons/hicolor/scalable/apps/gifpop.svg"
if [ "${1:-}" = --purge ]; then
  rm -rf "$config/gifpop" "$data/gifpop" "${XDG_CACHE_HOME:-$HOME/.cache}/gifpop"
fi
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 >/dev/null 2>&1
echo "GifPop removed.${1:+ Settings and recents deleted too.}"
echo "Win+. is free again: set Plasma's emoji picker back in System Settings > Keyboard > Shortcuts if you want it there."
