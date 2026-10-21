#!/usr/bin/env bash
# Builds the release tarball: dist/gifpop-<version>.tar.gz + SHA256SUMS.
# With KLIPY_API_KEY set, the KLIPY key is baked in (scrambled); without it the build
# works but users have to add their own key. Release CI always sets it.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
py="${PYTHON:-python3}"
version="$("$py" -c "import sys; sys.path.insert(0, '$root'); import gifpop; print(gifpop.__version__)")"
name="gifpop-$version"
dist="$root/dist"
stage="$dist/$name"

rm -rf "$stage" "$dist/$name.tar.gz"
mkdir -p "$stage"
cp -r "$root/gifpop" "$stage/"
cp "$root/install.sh" "$root/uninstall.sh" "$root/README.md" "$root/LICENSE" "$root/CHANGELOG.md" "$stage/"
find "$stage" \( -name __pycache__ -o -name _builtin.py \) -exec rm -rf {} +

check=()
if [ -n "${KLIPY_API_KEY:-}" ]; then
  "$py" "$root/scripts/embed_key.py" "$stage/gifpop/_builtin.py"
  check=(--expect-builtin)
fi

# Smoke-test the staged copy, then drop the test again.
mkdir -p "$stage/tests"
cp "$root/tests/smoke.py" "$stage/tests/"
"$py" "$stage/tests/smoke.py" "${check[@]}"
rm -rf "$stage/tests"
find "$stage" -name __pycache__ -prune -exec rm -rf {} +

tar -C "$dist" --owner=0 --group=0 --sort=name -czf "$dist/$name.tar.gz" "$name"
(cd "$dist" && sha256sum "$name.tar.gz" > SHA256SUMS)
rm -rf "$stage"
echo "Built $dist/$name.tar.gz"
