#!/usr/bin/env bash
# Installs GifPop for the current user: launcher, app menu entry, autostart.
# Needs: python-pyqt6, qt6-imageformats (pacman). No pip packages.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
bin="$HOME/.local/bin"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
autostart="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
mkdir -p "$bin" "$apps" "$autostart"

/usr/bin/python3 -c "import PyQt6.QtWidgets" 2>/dev/null || {
  echo "Missing PyQt6. Run: pkexec pacman -S --needed python-pyqt6 qt6-imageformats" >&2; exit 1; }

cat > "$bin/gifpop" <<EOF
#!/bin/sh
PYTHONPATH="$here\${PYTHONPATH:+:\$PYTHONPATH}" exec /usr/bin/python3 -m gifpop "\$@"
EOF
chmod +x "$bin/gifpop"

cat > "$apps/gifpop.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=GifPop
GenericName=GIF search and meme maker
Comment=Win+. style GIF picker and meme maker
Exec=$bin/gifpop
Icon=$here/gifpop/assets/gifpop.svg
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
Icon=$here/gifpop/assets/gifpop.svg
X-KDE-autostart-phase=2
NoDisplay=true
EOF

command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 >/dev/null 2>&1 || true
echo "Installed. Launcher: $bin/gifpop"
echo "Set the hotkey: System Settings > Keyboard > Shortcuts > Add New > Application > GifPop."
