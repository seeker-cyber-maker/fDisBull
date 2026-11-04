#!/usr/bin/env bash
# Build the pinned, GPL ScummVM Gob sidecar in an external workspace.
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo 'Usage: gob-build-headless.sh <clean ScummVM v2026.4.0 checkout> <existing external workspace> [jobs]' >&2
  exit 2
fi
source_tree=$(cd "$1" && pwd -P)
workspace=$(cd "$2" && pwd -P)
jobs=${3:-6}
case "$workspace" in
  /Volumes/CODEX/*|/Volumes/CACHE/*) ;;
  *) echo 'Workspace must be on an authorized external CODEX or CACHE volume.' >&2; exit 2 ;;
esac
case "$source_tree" in
  /Volumes/CODEX/*|/Volumes/CACHE/*) ;;
  *) echo 'The source and in-tree build outputs must be on CODEX or CACHE.' >&2; exit 2 ;;
esac
if ! [[ "$jobs" =~ ^[1-9][0-9]*$ ]]; then
  echo 'jobs must be a positive integer.' >&2
  exit 2
fi
expected_commit=7d2709da5136866589f7602f5f5a7b17de03420e
actual_commit=$(git -C "$source_tree" rev-parse HEAD)
if [[ "$actual_commit" != "$expected_commit" ]]; then
  echo "Expected ScummVM v2026.4.0 commit $expected_commit; got $actual_commit" >&2
  exit 2
fi
if [[ -n $(git -C "$source_tree" status --porcelain) ]]; then
  echo 'ScummVM checkout must be clean before applying the experimental patch.' >&2
  exit 2
fi
admit_tool=/Users/tiga/.codex/bin/storage_admit.py
if [[ ! -f "$admit_tool" ]]; then
  echo "Storage admission tool is missing: $admit_tool" >&2
  exit 2
fi
reserve_bytes=${FDISBULL_DESTINATION_RESERVE_BYTES:-40000000000}
if ! [[ "$reserve_bytes" =~ ^[0-9]+$ ]] || (( reserve_bytes < 20000000000 )); then
  echo 'Destination reserve must be at least 20 GB; default target is 40 GB.' >&2
  exit 2
fi
python3 "$admit_tool" --path "$source_tree" --expected-bytes 3500000000 --destination-reserve-bytes "$reserve_bytes"
if [[ "$workspace" != "$source_tree" ]]; then
  python3 "$admit_tool" --path "$workspace" --expected-bytes 3500000000 --destination-reserve-bytes "$reserve_bytes"
fi
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
patch="$script_dir/gob-headless-bridge.patch"
git -C "$source_tree" apply --check "$patch"
git -C "$source_tree" apply "$patch"
mkdir -p "$workspace/tmp"
(
  cd "$source_tree"
  export TMPDIR="$workspace/tmp"
  ./configure --backend=null --disable-all-engines --enable-engine=gob \
    --disable-detection-full --disable-readline --disable-cloud \
    --disable-system-dialogs --disable-taskbar --disable-translation \
    --disable-libcurl --disable-fluidsynth --disable-lua
  if [[ -f scummvm ]]; then
    prior_hash=$(shasum -a 256 scummvm | cut -d ' ' -f 1)
    receipt_time=$(date -u +%Y%m%dT%H%M%SZ)
    mkdir -p "$workspace/prior-binaries"
    cp -p scummvm "$workspace/prior-binaries/scummvm-$receipt_time-$prior_hash"
    printf '%s\n' "$prior_hash" > "$workspace/prior-binaries/scummvm-$receipt_time-$prior_hash.sha256"
  fi
  make -j"$jobs"
  shasum -a 256 scummvm
)
