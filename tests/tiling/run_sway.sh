#!/usr/bin/env bash
# GifPop on sway (Wayland, headless): the popup must float (not tile) at 480x600, centred and
# focused; a second `gifpop` re-shows it; `gifpop --quit` stops it.
# Needs: sway, jq, dbus (dbus-run-session), Python with PyQt6. PYTHON overrides the interpreter.
set -euo pipefail

if [ -z "${GIFPOP_TILING_DBUS:-}" ] && command -v dbus-run-session >/dev/null; then
    exec env GIFPOP_TILING_DBUS=1 dbus-run-session -- bash "$0" "$@"
fi

# shellcheck source=tests/tiling/common.sh
. "$(dirname "$0")/common.sh"

for c in sway swaymsg jq "$PY"; do
    command -v "$c" >/dev/null || { echo "missing: $c"; exit 2; }
done

export XDG_RUNTIME_DIR="$TMP/run"
mkdir -m 700 -p "$XDG_RUNTIME_DIR"
unset DISPLAY WAYLAND_DISPLAY SWAYSOCK

cat >"$TMP/sway.conf" <<EOF
swaynag_command -
xwayland disable
output * scale 1
default_border none
default_floating_border none
focus_follows_mouse no
exec sh -c 'printf "%s %s\n" "\$SWAYSOCK" "\$WAYLAND_DISPLAY" >"$TMP/ready.tmp" && mv "$TMP/ready.tmp" "$TMP/ready"'
EOF

log "starting headless sway ($(sway --version 2>&1 | head -n1))"
WLR_BACKENDS=headless WLR_HEADLESS_OUTPUTS=1 WLR_LIBINPUT_NO_DEVICES=1 WLR_RENDERER=pixman \
    sway -c "$TMP/sway.conf" >"$TMP/sway.log" 2>&1 &
PIDS+=($!)

wm_log() { echo "$TMP/sway.log"; }
wm_tree() { timeout 5 swaymsg -s "$SWAYSOCK" -r -t get_tree; }
wm_focus() { timeout 5 swaymsg -s "$SWAYSOCK" "[app_id=\"$1\"] focus" >/dev/null; }
wm_describe() {
    local tree outs
    tree=$(wm_tree) && outs=$(timeout 5 swaymsg -s "$SWAYSOCK" -r -t get_outputs) || return 1
    jq -c --arg id "$1" --argjson outs "$outs" '
        [.. | objects | select(.app_id? == $id)] as $n
        | {count: ($n | length),
           floating: ($n[0].type == "floating_con"),
           rect: $n[0].rect,
           focused: ($n[0].focused == true),
           output: ($outs | map(select(.active)) | first | .rect)}' <<<"$tree"
}

SWAYSOCK=""
for _ in $(seq 1 80); do
    [ -s "$TMP/ready" ] && break
    kill -0 "${PIDS[0]}" 2>/dev/null || { cat "$TMP/sway.log"; echo "FAIL: sway exited"; exit 1; }
    sleep 0.25
done
[ -s "$TMP/ready" ] || { cat "$TMP/sway.log"; echo "FAIL: sway did not come up in 20 s"; exit 1; }
read -r SWAYSOCK WAYLAND_DISPLAY <"$TMP/ready"
export SWAYSOCK WAYLAND_DISPLAY
export QT_QPA_PLATFORM=wayland
log "sway up: WAYLAND_DISPLAY=$WAYLAND_DISPLAY"
timeout 5 swaymsg -s "$SWAYSOCK" -r -t get_outputs | jq -c '.[] | {name, rect, scale}'

scenario
