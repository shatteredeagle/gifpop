#!/usr/bin/env bash
# One-line installer for GifPop's latest release:
#   curl -fsSL https://github.com/shatteredeagle/gifpop/releases/latest/download/get.sh | bash
# Downloads the release (a self-contained bundle: Python and Qt included), checks its
# SHA-256, then runs install.sh. No root needed. Re-run it any time to update.
set -euo pipefail
base="${GIFPOP_DOWNLOAD:-https://github.com/shatteredeagle/gifpop/releases/latest/download}"
tty=/dev/tty

if [ "$(uname -m)" != x86_64 ]; then
  echo "GifPop releases are built for x86_64 Linux only (this is $(uname -m))." >&2
  exit 1
fi
for tool in curl tar sha256sum; do
  command -v "$tool" >/dev/null || { echo "GifPop's installer needs $tool." >&2; exit 1; }
done

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
echo "Downloading GifPop…"
curl -fsSL -o "$work/gifpop.tar.gz" "$base/gifpop.tar.gz"
curl -fsSL -o "$work/SHA256SUMS" "$base/SHA256SUMS"
(cd "$work" && grep ' gifpop.tar.gz$' SHA256SUMS | sha256sum -c --quiet -) \
  || { echo "Download didn't match its checksum; not installing." >&2; exit 1; }
tar -xzf "$work/gifpop.tar.gz" -C "$work"
dir="$(find "$work" -maxdepth 1 -type d -name 'gifpop-*' | head -1)"
# Piped into bash, stdin is the script: give install.sh the terminal so it can ask about Win+.
if { : <"$tty"; } 2>/dev/null; then "$dir/install.sh" <"$tty"; else "$dir/install.sh" --no-hotkey; fi
