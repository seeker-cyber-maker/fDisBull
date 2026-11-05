#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Explicit opt-in build. No download, shared installation or release publication.
set -euo pipefail
if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo 'Usage: build.sh <clean pinned ScummVM checkout> <new build directory> [jobs]' >&2
  exit 2
fi
source_tree=$(cd "$1" && pwd -P)
build=$2
jobs=${3:-2}
[[ $jobs =~ ^[1-9][0-9]*$ ]] && (( jobs <= 16 )) || { echo 'jobs must be 1..16' >&2; exit 2; }
[[ ! -e $build ]] || { echo 'Build directory must not already exist' >&2; exit 2; }
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# Preserve the project's external-storage target on the user's Mac. No automatic
# lowering of the reserve to make a large build fit on a nearly full SSD.
python3 - "$source_tree" "$build" <<'PY'
import os, pathlib, shutil, sys
source, build = map(pathlib.Path, sys.argv[1:])
parent = build.parent.resolve(strict=True)
reserve = int(os.environ.get('FDISBULL_DESTINATION_RESERVE_BYTES', '40000000000'))
if reserve < 20000000000:
    raise SystemExit('Reserve must be at least 20 GB')
if sys.platform == 'darwin' and any(not str(p).startswith(('/Volumes/CODEX/', '/Volumes/CACHE/'))
                                   for p in (source, parent)):
    raise SystemExit('Mac source/build paths must be on authorized CODEX or CACHE storage')
for path in (source, parent):
    if shutil.disk_usage(path).free < reserve + 3500000000:
        raise SystemExit(f'Insufficient storage: retain {reserve} bytes reserve plus 3.5 GB build allowance')
PY
python3 "$script_dir/apply.py" "$source_tree" --apply
mkdir -m 700 "$build"
build=$(cd "$build" && pwd -P)
(
  cd "$build"
  export CPPFLAGS="${CPPFLAGS:-} -DFDISBULL_ZCODE_AGENT=1"
  "$source_tree/configure" --backend=sdl --disable-all-engines --enable-engine=glk \
    --disable-detection-full --disable-readline --disable-cloud \
    --disable-system-dialogs --disable-taskbar --disable-translation \
    --disable-libcurl --disable-fluidsynth --disable-lua
  make -j"$jobs"
  python3 - "$source_tree" "$build/scummvm" <<'PY'
import hashlib, json, pathlib, subprocess, sys
source, binary = map(pathlib.Path, sys.argv[1:])
receipt = {'upstream': subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),
           'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
           'patch_sha256': hashlib.sha256(subprocess.check_output(['git','-C',str(source),'diff'])).hexdigest(),
           'header_sha256': hashlib.sha256((source/'engines/glk/zcode/fdisbull_agent.h').read_bytes()).hexdigest(),
           'real_game_validation': 'not_run', 'text_only': True,
           'source_directory': str(source), 'engine_data_directory': str(source/'dists/engine-data')}
path = binary.parent/'fdisbull-zcode-build.json'
path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
PY
)
