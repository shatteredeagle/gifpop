#!/usr/bin/env bash
# Builds the self-contained release: a PyInstaller bundle (Python + PyQt6 + Qt) in
#   dist/gifpop-<version>.tar.gz, dist/gifpop.tar.gz (same file, unversioned) + dist/SHA256SUMS
# Needs a Python with the pinned toolchain:  pip install -r packaging/requirements-build.txt
# ($PYTHON picks the interpreter, default python3). With KLIPY_API_KEY set the KLIPY key is
# baked in (scrambled) and the build fails if the plain key shows up anywhere in the bundle.
# Without it the build works but users have to add their own key. Release CI always sets it.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
py="${PYTHON:-python3}"
version="$("$py" -c "import sys; sys.path.insert(0, '$root'); import gifpop; print(gifpop.__version__)")"
name="gifpop-$version"
dist="$root/dist"
build="$dist/.build"
stage="$dist/$name"

"$py" -m PyInstaller --version >/dev/null 2>&1 || {
  echo "PyInstaller missing for $py. Run: $py -m pip install -r packaging/requirements-build.txt" >&2
  exit 1
}

rm -rf "$build" "$stage" "$dist/$name.tar.gz" "$dist/gifpop.tar.gz" "$dist/SHA256SUMS"
mkdir -p "$build/src" "$stage"

# 1. Staged copy of the source: the key module is generated here, never in the checkout.
cp -r "$root/gifpop" "$build/src/"
find "$build/src" \( -name __pycache__ -o -name _builtin.py \) -prune -exec rm -rf {} +
check=()
if [ -n "${KLIPY_API_KEY:-}" ]; then
  "$py" "$root/scripts/embed_key.py" "$build/src/gifpop/_builtin.py"
  check=(--expect-builtin)
fi

# 2. Source smoke test against the staged copy (same code that gets frozen).
mkdir -p "$build/src/tests"
cp "$root/tests/smoke.py" "$build/src/tests/"
"$py" "$build/src/tests/smoke.py" "${check[@]}"
rm -rf "$build/src/tests"
find "$build/src" -name __pycache__ -prune -exec rm -rf {} +

# 3. Freeze.
GIFPOP_SRC="$build/src" "$py" -m PyInstaller --noconfirm --log-level WARN \
  --distpath "$build/dist" --workpath "$build/work" "$root/packaging/gifpop.spec"
app="$build/dist/app"
test -x "$app/gifpop"
ls "$app/_internal/PyQt6/Qt6/plugins/platforms/libqwayland.so" \
   "$app/_internal/PyQt6/Qt6/plugins/platforms/libqxcb.so" \
   "$app/_internal/PyQt6/Qt6/plugins/imageformats/libqgif.so" \
   "$app/_internal/PyQt6/Qt6/plugins/imageformats/libqwebp.so" \
   "$app/_internal/PyQt6/Qt6/plugins/imageformats/libqjpeg.so" \
   "$app/_internal/PyQt6/Qt6/plugins/tls/libqopensslbackend.so" \
   "$app/_internal/gifpop/assets/gifpop.svg" >/dev/null
if [ -n "${KLIPY_API_KEY:-}" ]; then
  # The key module must be inside the frozen archive, or release users get no key.
  "$py" -c 'import sys; from PyInstaller.archive.readers import pkg_archive_contents as c
assert "gifpop._builtin" in c(sys.argv[1]), "gifpop._builtin is not in the frozen app"' "$app/gifpop"
fi

# 4. Smoke test the frozen app: starts headless, stays up, `--quit` stops it.
"$root/scripts/smoke_frozen.sh" "$app/gifpop"

# 5. Release folder + tarballs.
cp -a "$app" "$stage/app"
cp "$root/install.sh" "$root/uninstall.sh" "$root/README.md" "$root/LICENSE" "$root/CHANGELOG.md" "$stage/"
if [ -n "${KLIPY_API_KEY:-}" ] && grep -rqaF -- "$KLIPY_API_KEY" "$stage"; then
  echo "plain KLIPY key found in the bundle" >&2
  exit 1
fi
tar -C "$dist" --owner=0 --group=0 --sort=name -czf "$dist/$name.tar.gz" "$name"
cp "$dist/$name.tar.gz" "$dist/gifpop.tar.gz"
(cd "$dist" && sha256sum "$name.tar.gz" gifpop.tar.gz > SHA256SUMS)
rm -rf "$stage" "$build"
echo "Built $dist/$name.tar.gz ($(du -h "$dist/$name.tar.gz" | cut -f1))"
