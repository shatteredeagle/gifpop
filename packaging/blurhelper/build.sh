#!/usr/bin/env bash
# Build libgifpopblur.so against a Qt install that matches the bundled PyQt6-Qt6.
# Usage: packaging/blurhelper/build.sh <QT_PREFIX> <OUT_SO>
#   QT_PREFIX  e.g. .../qt/6.11.2/gcc_64 (aqtinstall layout, has include/<Module>/<ver>/<Module>/private)
#   OUT_SO     output path, e.g. build/libgifpopblur.so
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <QT_PREFIX> <OUT_SO>" >&2
    exit 2
fi

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
qt="$(cd "$1" && pwd)"
out="$2"
CXX="${CXX:-g++}"
CC="${CC:-gcc}"

# Qt version from the install's Qt6Core headers dir (include/QtCore/<ver>/).
qtver="$(basename "$(find "$qt/include/QtCore" -mindepth 1 -maxdepth 1 -type d -name '6.*' | head -n1)")"
if [[ -z "$qtver" ]]; then
    echo "error: no private headers under $qt/include/QtCore/6.*" >&2
    exit 1
fi

gen="$(mktemp -d)"
trap 'rm -rf "$gen"' EXIT

scanner="$(pkg-config --variable=wayland_scanner wayland-scanner 2>/dev/null || command -v wayland-scanner)"
for proto in ext-background-effect-v1 blur; do
    "$scanner" client-header "$here/protocols/$proto.xml" "$gen/$proto-client-protocol.h"
    "$scanner" private-code "$here/protocols/$proto.xml" "$gen/$proto-protocol.c"
done

mkdir -p "$(dirname "$out")"
for proto in ext-background-effect-v1 blur; do
    "$CC" -O2 -fPIC -fvisibility=hidden $(pkg-config --cflags wayland-client) \
        -c "$gen/$proto-protocol.c" -o "$gen/$proto-protocol.o"
done
"$CXX" -std=c++17 -O2 -fPIC -shared -fvisibility=hidden -fvisibility-inlines-hidden \
    -Wall -Wextra -Wno-unused-parameter \
    -DQT_NO_KEYWORDS -DQT_NO_DEBUG \
    -I"$gen" \
    -I"$qt/include" \
    -I"$qt/include/QtCore" -I"$qt/include/QtCore/$qtver" -I"$qt/include/QtCore/$qtver/QtCore" \
    -I"$qt/include/QtGui" -I"$qt/include/QtGui/$qtver" -I"$qt/include/QtGui/$qtver/QtGui" \
    $(pkg-config --cflags wayland-client) \
    "$here/gifpopblur.cpp" "$gen/ext-background-effect-v1-protocol.o" "$gen/blur-protocol.o" \
    -L"$qt/lib" -lQt6Gui -lQt6Core \
    $(pkg-config --libs wayland-client) \
    -Wl,--no-undefined -Wl,--as-needed \
    -o "$out"

echo "built $out (Qt $qtver)"
