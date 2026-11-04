#!/usr/bin/env bash
set -euo pipefail

# Build a playable, AGI-only ScummVM executable for Linux from the exact
# upstream source identity used by fDisBull's experimental AGI bridge.
# This is an oracle/scaffold build, NOT AGI->UIL compilation.

EXPECTED_COMMIT=750f2373fb100efe08c6444e36b68c01387fc307
if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "usage: $0 /path/to/clean/scummvm-v2.8.1 /absolute/output/prefix [jobs]" >&2
  exit 2
fi
SRC=$(realpath "$1")
OUT=$(realpath -m "$2")
JOBS=${3:-2}

[ -x "$SRC/configure" ] || { echo "missing ScummVM configure script" >&2; exit 2; }
[ "$(git -C "$SRC" rev-parse HEAD)" = "$EXPECTED_COMMIT" ] || {
  echo "ScummVM source commit mismatch" >&2; exit 2;
}
git -C "$SRC" diff --quiet -- . || { echo "ScummVM source tree is dirty" >&2; exit 2; }
git -C "$SRC" diff --cached --quiet -- . || { echo "ScummVM index is dirty" >&2; exit 2; }
case "$JOBS" in ''|*[!0-9]*) echo "jobs must be an integer" >&2; exit 2;; esac
[ "$JOBS" -ge 1 ] && [ "$JOBS" -le 64 ] || { echo "jobs must be 1..64" >&2; exit 2; }
mkdir -p "$OUT"

cd "$SRC"
./configure \
  --prefix="$OUT" \
  --disable-all-engines \
  --enable-engine=agi \
  --disable-cloud \
  --disable-system-dialogs \
  --disable-taskbar \
  --disable-translation \
  --disable-libcurl \
  --disable-fluidsynth \
  --disable-lua
make -j"$JOBS"
make install
[ -x "$OUT/bin/scummvm" ] || { echo "installed ScummVM binary missing" >&2; exit 1; }
cp "$OUT/bin/scummvm" "$OUT/bin/scummvm-agi"
sha256sum "$OUT/bin/scummvm-agi"
file "$OUT/bin/scummvm-agi"
echo "AGI-only ScummVM Linux scaffold built. It still interprets original AGI resources."
