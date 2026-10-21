# shellcheck shell=bash
# Shared scenario for run_sway.sh / run_i3.sh. The caller defines:
#   wm_tree             full layout tree as JSON (for failure dumps)
#   wm_describe NAME    normalised JSON for the window with app_id / WM_CLASS NAME:
#                       {count, floating, rect:{x,y,width,height}, focused, output:{x,y,width,height}}
#   wm_focus NAME       give keyboard focus to that window
#   wm_log              path of the WM's log file
# and exports the display variables (WAYLAND_DISPLAY or DISPLAY) plus QT_QPA_PLATFORM.

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
HERE="$ROOT/tests/tiling"
PY=${PYTHON:-python3}
TMP=$(mktemp -d "${TMPDIR:-/tmp}/gifpop-tiling.XXXXXX")
PIDS=()
GIFPOP_PID=""
WANT_W=480
WANT_H=600

# Throwaway profile: no key, default settings (auto_hide on), nothing touches the real home.
export XDG_CONFIG_HOME="$TMP/config" XDG_CACHE_HOME="$TMP/cache" XDG_DATA_HOME="$TMP/data"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"
export QT_SCALE_FACTOR=1 QT_FONT_DPI=96
unset QT_QPA_PLATFORMTHEME QT_STYLE_OVERRIDE QT_AUTO_SCREEN_SCALE_FACTOR QT_SCREEN_SCALE_FACTORS

log() { printf '[%s] %s\n' "$(date +%T)" "$*"; }

cleanup() {
    local p
    for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
    sleep 0.5
    for p in "${PIDS[@]}"; do kill -9 "$p" 2>/dev/null || true; done
    rm -rf "$TMP"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

dump() {
    echo "----- layout tree -----"
    wm_tree 2>&1 | jq . 2>/dev/null || wm_tree 2>&1 || true
    local f
    for f in "$TMP/gifpop.log" "$TMP/filler.log" "$(wm_log)"; do
        [ -s "$f" ] || continue
        echo "----- $(basename "$f") (last 60 lines) -----"
        tail -n 60 "$f"
    done
}

fail() {
    echo "FAIL: $*"
    dump
    exit 1
}

# wait_until SECONDS CMD...: poll CMD until it exits 0 and prints nothing. Its last output
# (the list of unmet expectations) is kept in $LAST.
LAST=""
wait_until() {
    local secs=$1 out
    shift
    local deadline=$((SECONDS + secs))
    while :; do
        if out=$("$@" 2>&1) && [ -z "$out" ]; then
            LAST=""
            return 0
        fi
        LAST=$out
        [ "$SECONDS" -ge "$deadline" ] && return 1
        sleep 0.25
    done
}

alive() { [ -n "$GIFPOP_PID" ] && kill -0 "$GIFPOP_PID" 2>/dev/null; }

# Prints one line per unmet expectation for the GifPop window; nothing when all hold.
# $1 = 1 to also require keyboard focus.
check_popup() {
    local want_focus=${1:-1} desc
    alive || { echo "the gifpop process has exited"; return 0; }
    desc=$(wm_describe gifpop) || { echo "WM IPC query failed"; return 0; }
    jq -r --argjson wf "$want_focus" --argjson W "$WANT_W" --argjson H "$WANT_H" '
        def abs: if . < 0 then -. else . end;
        if .count != 1 then "expected exactly 1 gifpop window, found \(.count)"
        else
            ((.rect.x + .rect.width / 2) - (.output.x + .output.width / 2)) as $dx
            | ((.rect.y + .rect.height / 2) - (.output.y + .output.height / 2)) as $dy
            | (if .floating then empty else "not floating (got tiled)" end),
              (if .rect.width == $W and .rect.height == $H then empty
               else "size \(.rect.width)x\(.rect.height), want \($W)x\($H)" end),
              (if ($dx | abs) <= .output.width * 0.1 and ($dy | abs) <= .output.height * 0.1 then empty
               else "not centred: window centre is off the output centre by (\($dx), \($dy)), output \(.output)" end),
              (if $wf == 1 and (.focused | not) then "not focused" else empty end)
        end' <<<"$desc"
}

check_popup_gone() {
    local desc
    alive || { echo "the gifpop process has exited"; return 0; }
    desc=$(wm_describe gifpop) || { echo "WM IPC query failed"; return 0; }
    jq -r 'if .count == 0 then empty else "gifpop window still mapped" end' <<<"$desc"
}

check_filler_tiled() {
    local desc
    desc=$(wm_describe filler) || { echo "WM IPC query failed"; return 0; }
    jq -r 'if .count != 1 then "expected 1 filler window, found \(.count)"
           elif .floating then "filler window is floating; the WM is not tiling"
           else empty end' <<<"$desc"
}

run_gifpop() {  # extra args...; runs a short-lived second instance / control command
    (cd "$ROOT" && PYTHONPATH="$ROOT" timeout 20 "$PY" -m gifpop "$@") >>"$TMP/gifpop-cli.log" 2>&1
}

scenario() {
    log "starting a tiled filler window"
    (cd "$ROOT" && exec "$PY" "$HERE/filler.py") >"$TMP/filler.log" 2>&1 &
    PIDS+=($!)
    wait_until 30 check_filler_tiled || fail "filler window never tiled: $LAST"
    log "ok: filler is tiled"

    log "starting gifpop"
    (cd "$ROOT" && PYTHONPATH="$ROOT" exec "$PY" -m gifpop) >"$TMP/gifpop.log" 2>&1 &
    GIFPOP_PID=$!
    PIDS+=("$GIFPOP_PID")
    wait_until 30 check_popup 1 || fail "gifpop window on first show: $LAST"
    log "ok: gifpop floats, ${WANT_W}x${WANT_H}, centred, focused"
    wait_until 5 check_filler_tiled || fail "filler after gifpop opened: $LAST"
    log "ok: filler still tiled next to it"

    # On tiling WMs focus follows the mouse, so GifPop must NOT hide on focus loss.
    log "focusing the filler (gifpop must stay open on a tiling WM)"
    wm_focus filler
    if wait_until 3 check_popup_gone; then
        fail "gifpop hid itself on focus loss (it shouldn't on tiling WMs)"
    fi
    wait_until 5 check_popup 0 || fail "gifpop after focus moved away: $LAST"
    log "ok: still open, floating and sized after focus moved away"
    log "running a second instance"
    run_gifpop || fail "second instance exited with $?"
    wait_until 20 check_popup 0 || fail "gifpop after second instance: $LAST"
    if wait_until 5 check_popup 1; then
        log "ok: second instance re-focused it"
    else
        log "WARN: still floating and sized but not re-focused ($LAST)"
    fi

    log "gifpop --quit"
    run_gifpop --quit || fail "gifpop --quit exited with $? (no running instance found?)"
    local deadline=$((SECONDS + 15))
    while alive; do
        [ "$SECONDS" -ge "$deadline" ] && fail "gifpop still running 15 s after --quit"
        sleep 0.25
    done
    wait "$GIFPOP_PID" 2>/dev/null || true
    log "ok: --quit stopped it"
    log "PASS"
}
