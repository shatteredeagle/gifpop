#!/usr/bin/env bash
# Installs GifPop for the current user: app files, launcher, app menu entry, autostart,
# and (on KDE Plasma) the Win+. hotkey. Run ~/.local/lib/gifpop/uninstall.sh to remove.
# From a release download it installs the bundled app (Python and Qt included, nothing else
# needed). From a git checkout (no app/ bundle) it runs the source with the system
# /usr/bin/python3 and your distro's PyQt6.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
lib="$HOME/.local/lib/gifpop"
bin="$HOME/.local/bin"
data="${XDG_DATA_HOME:-$HOME/.local/share}"
apps="$data/applications"
icons="$data/icons/hicolor/scalable/apps"
autostart="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
py=/usr/bin/python3
hotkey=ask
for arg in "$@"; do
  case "$arg" in
    --hotkey) hotkey=yes ;;
    --no-hotkey) hotkey=no ;;
    *) echo "Usage: $0 [--hotkey|--no-hotkey]" >&2; exit 2 ;;
  esac
done
if [ "$here" = "$lib" ]; then
  echo "Run install.sh from the downloaded folder or a checkout, not from $lib." >&2
  exit 2
fi

if [ -x "$here/app/gifpop" ]; then
  mode=bundle
  icon_src="$here/app/_internal/gifpop/assets/gifpop.svg"
elif [ -d "$here/gifpop" ]; then
  mode=source
  icon_src="$here/gifpop/assets/gifpop.svg"
  if ! "$py" -c "import PyQt6.QtWidgets, PyQt6.QtNetwork" 2>/dev/null; then
    echo "Running from source needs PyQt6 from your distro. Install it, then run this again:" >&2
    if command -v pacman >/dev/null; then echo "  sudo pacman -S --needed python-pyqt6 qt6-imageformats" >&2
    elif command -v apt >/dev/null; then echo "  sudo apt install python3-pyqt6 qt6-image-formats-plugins" >&2
    elif command -v dnf >/dev/null; then echo "  sudo dnf install python3-pyqt6 qt6-qtimageformats" >&2
    elif command -v zypper >/dev/null; then echo "  sudo zypper install python3-PyQt6 qt6-imageformats" >&2
    else echo "  (package is usually called python3-pyqt6 or python-pyqt6)" >&2
    fi
    echo "Or install a release instead, which needs nothing extra." >&2
    exit 1
  fi
else
  echo "No GifPop app next to install.sh (expected app/ or gifpop/ in $here)." >&2
  exit 1
fi

# Stop a running copy (bundled or source) before replacing it: ask it to quit, then make sure.
if [ -x "$bin/gifpop" ]; then "$bin/gifpop" --quit >/dev/null 2>&1 || true; fi
pat="^($lib/app/gifpop|[^ ]*python3[^ ]* -m gifpop)( |\$)"
for _ in $(seq 20); do pgrep -u "$(id -u)" -f "$pat" >/dev/null || break; sleep 0.1; done
pkill -u "$(id -u)" -f "$pat" 2>/dev/null || true

# Fresh copy of the app (leaves your settings, recents and templates alone).
rm -rf "$lib"
mkdir -p "$lib" "$bin" "$apps" "$icons" "$autostart"
if [ "$mode" = bundle ]; then
  cp -a "$here/app" "$lib/app"
  run="exec \"$lib/app/gifpop\" \"\$@\""
else
  cp -r "$here/gifpop" "$lib/"
  find "$lib" -name __pycache__ -prune -exec rm -rf {} +
  run="PYTHONPATH=\"$lib\${PYTHONPATH:+:\$PYTHONPATH}\" exec $py -m gifpop \"\$@\""
fi
cp "$here/uninstall.sh" "$lib/uninstall.sh"
chmod +x "$lib/uninstall.sh"
cp "$icon_src" "$icons/gifpop.svg"

cat > "$bin/gifpop" <<EOF
#!/bin/sh
$run
EOF
chmod +x "$bin/gifpop"

cat > "$apps/gifpop.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=GifPop
GenericName=GIF search and meme maker
Comment=Win+. style GIF picker and meme maker
Exec=$bin/gifpop
Icon=gifpop
Categories=Utility;
Keywords=gif;meme;emoji;clipboard;
StartupNotify=false
Actions=meme;

[Desktop Action meme]
Name=Make a meme
Exec=$bin/gifpop --meme
EOF

cat > "$autostart/gifpop.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=GifPop
Exec=$bin/gifpop --background
Icon=gifpop
X-KDE-autostart-phase=2
NoDisplay=true
EOF

command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 >/dev/null 2>&1 || true
echo "Installed GifPop to $lib"

# Win+. on KDE Plasma: move Plasma's emoji picker off Meta+. and give it to GifPop.
kga() { gdbus call --session --dest org.kde.kglobalaccel --object-path /kglobalaccel \
          --method "org.kde.KGlobalAccel.$1" "${@:2}"; }
meta_period=268435502                 # Qt::META | Qt::Key_Period
emojier_alt=503316512                 # Meta+Ctrl+Alt+Shift+Space, Plasma's other default
gifpop_id="['gifpop.desktop','_launch','GifPop','Launch GifPop']"
emojier_id="['org.kde.plasma.emojier.desktop','_launch','Emoji Selector','Emoji Selector']"
if command -v gdbus >/dev/null && kga allMainComponents >/dev/null 2>&1; then
  if [ "$hotkey" = ask ] && [ ! -t 0 ]; then
    echo "No terminal to ask about Win+.; skipping. Re-run with --hotkey to bind it."
    hotkey=no
  elif [ "$hotkey" = ask ]; then
    read -r -p "Open GifPop with Win+. (replaces Plasma's emoji picker shortcut)? [Y/n] " a || a=n
    case "$a" in [nN]*) hotkey=no ;; *) hotkey=yes ;; esac
  fi
  if [ "$hotkey" = yes ]; then
    kga setForeignShortcut "$emojier_id" "[$emojier_alt]" >/dev/null 2>&1 || true
    kga doRegister "$gifpop_id" >/dev/null 2>&1 || true
    kga setForeignShortcut "$gifpop_id" "[$meta_period]" >/dev/null 2>&1 || true
    # setForeignShortcut only stores the key: until the next login KDE ignores real key
    # presses for it. setShortcut with SetPresent (2) makes it live right away.
    kga setShortcut "$gifpop_id" "[$meta_period]" 2 >/dev/null 2>&1 || true
    if kga shortcutKeys "$gifpop_id" 2>/dev/null | grep -q "$meta_period"; then
      echo "Win+. now opens GifPop. (Emoji picker: Meta+Ctrl+Alt+Shift+Space, or the 😀 button.)"
    else
      echo "Couldn't take Win+.: another app holds it. Set it by hand:"
      echo "  System Settings > Keyboard > Shortcuts > GifPop"
    fi
  fi
else
  echo "Not on KDE Plasma: bind your desktop's shortcut to: $bin/gifpop"
fi

setsid -f "$bin/gifpop" --background >/dev/null 2>&1 || true
echo "Running in the tray. Open it with the hotkey or: gifpop"
echo "Remove it any time with: $lib/uninstall.sh"
