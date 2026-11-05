#!/usr/bin/env bash
# Builds dist/NeonMinutes-<version>-linux-x86_64.run (run on Linux, see .github/workflows/linux.yml).
#
#   bash installer/build_linux.sh <python of the build venv> <pyannote model .tar.gz>
#
# The build venv must already contain the program's dependencies (CPU torch is enough): their
# exact versions become the installer's lock file.
set -euo pipefail
PY="$1"
MODEL_TGZ="$2"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build/linux"
STAGE="$BUILD/payload"
CACHE="$BUILD/cache"
DIST="$ROOT/dist"

# Portable CPython (python-build-standalone, same release as the Windows build), checked by SHA-256.
RUNTIME_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.12.15%2B20261003-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
RUNTIME_SHA256="731af898886c5f821890dc901eca3c651cca8e51fa7308c159d12a1194aeac91"

VERSION="$("$PY" -c "import sys; sys.path.insert(0, '$ROOT'); import meeting_transcriber; print(meeting_transcriber.__version__)")"
echo "== Neon Minutes $VERSION per Linux"
rm -rf "$STAGE"
mkdir -p "$STAGE" "$CACHE" "$DIST"

echo "== Python portatile"
TGZ="$CACHE/python-linux.tar.gz"
[ -f "$TGZ" ] || curl -fsSL "$RUNTIME_URL" -o "$TGZ"
echo "$RUNTIME_SHA256  $TGZ" | sha256sum -c -
tar -xzf "$TGZ" -C "$STAGE"
mv "$STAGE/python" "$STAGE/runtime"

echo "== Programma, documentazione, licenze"
mkdir -p "$STAGE/meeting_transcriber" "$STAGE/assets" "$STAGE/docs" "$STAGE/installer" "$STAGE/models"
cp "$ROOT"/meeting_transcriber/*.py "$STAGE/meeting_transcriber/"
cp "$ROOT"/assets/piuma.png "$ROOT"/assets/banner.png "$STAGE/assets/"
cp -r "$ROOT"/docs/* "$STAGE/docs/"
cp "$ROOT"/installer/postinstall.py "$ROOT"/installer/linux_setup.py "$STAGE/installer/"
cp "$ROOT/LICENSE.txt" "$STAGE/"
cp "$ROOT/installer/glossary-template.txt" "$STAGE/glossary.txt"

echo "== Modello pyannote"
tar -xzf "$MODEL_TGZ" -C "$STAGE/models"
test -f "$STAGE/models/pyannote-community-1/config.yaml"

echo "== Versioni delle dipendenze, avvisi di terze parti, dimensioni"
"$PY" "$ROOT/installer/linux_prepare.py" "$STAGE"

echo "== Pacchetto autoestraente"
OUT="$DIST/NeonMinutes-$VERSION-linux-x86_64.run"
tar -czf "$BUILD/payload.tar.gz" -C "$BUILD" payload
cat "$ROOT/installer/linux_header.sh" "$BUILD/payload.tar.gz" > "$OUT"
chmod +x "$OUT"
echo "== Fatto: $OUT ($(du -h "$OUT" | cut -f1))"
