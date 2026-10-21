#!/usr/bin/env bash
# GifPop on i3 (X11 under Xvfb): the popup must float (not tile) at 480x600, centred and
# focused; a second `gifpop` re-shows it; `gifpop --quit` stops it.
# Needs: i3, Xvfb, xdpyinfo (x11-utils), jq, dbus (dbus-run-session), Python with PyQt6.
set -euo pipefail

if [ -z "${GIFPOP_TILING_DBUS:-}" ] && command -v dbus-run-session >/dev/null; then
    exec env GIFPOP_TILING_DBUS=1 dbus-run-session -- bash "$0" "$@"
fi

# shellcheck source=tests/tiling/common.sh
. "$(dirname "$0")/common.sh"

for c in i3 i3-msg Xvfb xdpyinfo jq "$PY"; do
    command -v "$c" >/dev/null || { echo "missing: $c"; exit 2; }
done

unset WAYLAND_DISPLAY I3SOCK
n=99
while [ -e "/tmp/.X11-unix/X$n" ] || [ -e "/tmp/.X$n-lock" ]; do n=$((n + 1)); done
export DISPLAY=":$n"
export QT_QPA_PLATFORM=xcb

log "starting Xvfb on $DISPLAY"
Xvfb "$DISPLAY" -screen 0 1280x720x24 -nolisten tcp >"$TMP/xvfb.log" 2>&1 &
PIDS+=($!)
for _ in $(seq 1 80); do
    xdpyinfo >/dev/null 2>&1 && break
    sleep 0.25
done
xdpyinfo >/dev/null 2>&1 || { cat "$TMP/xvfb.log"; echo "FAIL: Xvfb did not come up"; exit 1; }

cat >"$TMP/i3.conf" <<'EOF'
default_border none
default_floating_border none
focus_follows_mouse no
EOF

log "starting i3 ($(i3 --version 2>&1 | head -n1))"
i3 -c "$TMP/i3.conf" >"$TMP/i3.log" 2>&1 &
PIDS+=($!)

for _ in $(seq 1 40); do
    I3SOCK=$(i3 --get-socketpath 2>/dev/null) && [ -S "$I3SOCK" ] && break
    sleep 0.25
done
export I3SOCK   # GifPop reads it to know it's on a tiling WM

wm_log() { echo "$TMP/i3.log"; }
wm_tree() { timeout 5 i3-msg -t get_tree; }
# Match by title: under xcb Qt takes WM_CLASS instance from argv[0] ("python"), not the app name.
wm_focus() { timeout 5 i3-msg "[title=\"^$1\$\"] focus" >/dev/null; }
wm_describe() {
    local tree outs
    tree=$(wm_tree) && outs=$(timeout 5 i3-msg -t get_outputs) || return 1
    # Qt sets WM_CLASS to (applicationName, Capitalised applicationName): ("gifpop", "Gifpop").
    jq -c --arg id "$1" --argjson outs "$outs" '
        . as $t
        | [.. | objects | select(.window != null and (
              ((.window_properties.class // "") | ascii_downcase) == $id or
              ((.window_properties.instance // "") | ascii_downcase) == $id))] as $n
        | [$t | .. | objects | (.floating_nodes? // [])[] | .. | objects | .id] as $fl
        | {count: ($n | length),
           floating: ($n[0] != null and ($fl | index($n[0].id)) != null
                      and (($n[0].floating // "") | endswith("_on"))),
           rect: $n[0].rect,
           focused: ($n[0].focused == true),
           output: ($outs | map(select(.active)) | first | .rect)}' <<<"$tree"
}

for _ in $(seq 1 80); do
    timeout 2 i3-msg -t get_version >/dev/null 2>&1 && break
    sleep 0.25
done
timeout 2 i3-msg -t get_version >/dev/null 2>&1 || { cat "$TMP/i3.log"; echo "FAIL: i3 did not come up"; exit 1; }
log "i3 up"
timeout 5 i3-msg -t get_outputs | jq -c '.[] | select(.active) | {name, rect}'

scenario
