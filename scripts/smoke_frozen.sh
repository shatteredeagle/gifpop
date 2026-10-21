#!/usr/bin/env bash
# Smoke test for the frozen bundle: start it with a throwaway profile, check it stays up and
# runs on the bundled Qt, then stop it with a second `gifpop --quit`.
#   scripts/smoke_frozen.sh path/to/app/gifpop
# QT_QPA_PLATFORM defaults to offscreen (headless CI); set it to wayland/xcb to try a real
# session. TMPDIR is private too, so this never talks to a GifPop you already have running
# (the single-instance socket lives in the temp dir).
set -euo pipefail
bin="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
tmp="$(mktemp -d)"
pid=""
cleanup() { [ -n "$pid" ] && kill "$pid" 2>/dev/null; rm -rf "$tmp"; }
trap cleanup EXIT
export TMPDIR="$tmp" HOME="$tmp/home" XDG_CONFIG_HOME="$tmp/config" \
       XDG_CACHE_HOME="$tmp/cache" XDG_DATA_HOME="$tmp/data"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
mkdir -p "$HOME"

"$bin" --background >"$tmp/log" 2>&1 &
pid=$!
sleep 3
if ! kill -0 "$pid" 2>/dev/null; then
  echo "frozen app exited early:" >&2; cat "$tmp/log" >&2; exit 1
fi
bundle="$(dirname "$bin")/_internal"
if ! grep -qF "$bundle/PyQt6/Qt6/lib/libQt6Core.so" "/proc/$pid/maps"; then
  echo "frozen app isn't using the bundled Qt:" >&2
  grep -i libqt6core "/proc/$pid/maps" >&2 || true
  exit 1
fi
platform="$(grep -o 'plugins/platforms/libq[a-z]*\.so' "/proc/$pid/maps" | sort -u | tr '\n' ' ')"
"$bin" --quit || { echo "gifpop --quit found no running instance" >&2; cat "$tmp/log" >&2; exit 1; }
for _ in $(seq 50); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
if kill -0 "$pid" 2>/dev/null; then echo "gifpop --quit didn't stop it" >&2; exit 1; fi
wait "$pid" || { echo "frozen app exited with an error:" >&2; cat "$tmp/log" >&2; exit 1; }
pid=""
[ -s "$tmp/log" ] && { echo "app output:"; cat "$tmp/log"; }
echo "frozen smoke ok ($QT_QPA_PLATFORM: ${platform:-?})"
