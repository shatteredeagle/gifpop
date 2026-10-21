#!/usr/bin/env bash
# Removes GifPop. Keeps your settings and recents unless you pass --purge.
# install.sh puts a copy at ~/.local/lib/gifpop/uninstall.sh; it's safe to run from there.
set -uo pipefail

main() {
  local data="${XDG_DATA_HOME:-$HOME/.local/share}"
  local config="${XDG_CONFIG_HOME:-$HOME/.config}"
  local lib="$HOME/.local/lib/gifpop"
  local pat="^($lib/app/gifpop|[^ ]*python3[^ ]* -m gifpop)( |\$)"

  # Ask the running copy to quit, then make sure (bundled app or source install).
  "$HOME/.local/bin/gifpop" --quit >/dev/null 2>&1
  for _ in $(seq 20); do pgrep -u "$(id -u)" -f "$pat" >/dev/null || break; sleep 0.1; done
  pkill -u "$(id -u)" -f "$pat" 2>/dev/null

  if command -v gdbus >/dev/null; then
    gdbus call --session --dest org.kde.kglobalaccel --object-path /kglobalaccel \
      --method org.kde.KGlobalAccel.unregister gifpop.desktop _launch >/dev/null 2>&1
  fi
  cd / || true   # we may be running from inside $lib, which goes next
  rm -rf "$lib"
  rm -f "$HOME/.local/bin/gifpop" "$data/applications/gifpop.desktop" \
        "$config/autostart/gifpop.desktop" "$data/icons/hicolor/scalable/apps/gifpop.svg"
  local purged=""
  if [ "${1:-}" = --purge ]; then
    rm -rf "$config/gifpop" "$data/gifpop" "${XDG_CACHE_HOME:-$HOME/.cache}/gifpop"
    purged=" Settings and recents deleted too."
  fi
  command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 >/dev/null 2>&1
  echo "GifPop removed.$purged"
  echo "Win+. is free again: set Plasma's emoji picker back in System Settings > Keyboard > Shortcuts if you want it there."
}

# The whole script is read before main runs, so deleting this file mid-way is harmless.
main "$@"
exit
