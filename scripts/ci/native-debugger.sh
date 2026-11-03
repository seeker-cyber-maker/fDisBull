#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl xz-utils git build-essential clang rustc libx11-dev autoconf automake pkg-config nasm llvm ffmpeg libsdl2-dev libsdl2-net-dev libncurses-dev libpng-dev zlib1g-dev libfreetype6-dev
bash scripts/ci/install-node.sh
python -m pip install ".[test]" build
export NATIVE_EVIDENCE="native-evidence/$FDISBULL_PROFILE"
export FDISBULL_FRAME_EVIDENCE="$CI_PROJECT_DIR/$NATIVE_EVIDENCE/frame-capture"
mkdir -p .native "$NATIVE_EVIDENCE"
git clone --no-checkout https://github.com/joncampbell123/dosbox-x.git .native/dosbox-x
git -C .native/dosbox-x checkout 029bd65c5dcc7cdc7f2e14e35278620d9707d969
python - <<'PY'
import hashlib, json, os, subprocess
from pathlib import Path
checkout=Path('.native/dosbox-x').resolve()
directory=Path(os.environ['FDISBULL_PATCH_DIRECTORY']).resolve()
manifest=json.loads((directory/'source-manifest.json').read_text())
head=subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip()
assert head==manifest['baseline_commit'], 'Wrong upstream baseline'
patch=directory/'headless-agent.patch'
assert hashlib.sha256(patch.read_bytes()).hexdigest()==manifest['patch_sha256'], 'Patch hash mismatch'
subprocess.run(['git','-C',str(checkout),'apply','--check',str(patch)],check=True)
subprocess.run(['git','-C',str(checkout),'apply',str(patch)],check=True)
for item in manifest['source_files']:
    path=checkout/item['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'], item['path']
print(f"Verified {len(manifest['source_files'])} patched source files against the declared manifest")
PY

(
  cd .native/dosbox-x
  ./autogen.sh
  ./configure --enable-sdl2 --enable-debug=heavy --enable-dosbox_agent \
    --disable-avcodec --disable-libslirp --disable-libfluidsynth
  make -j2
)
mkdir -p "$(dirname "$FDISBULL_DOSBOX")"
cp .native/dosbox-x/src/dosbox-x "$FDISBULL_DOSBOX"
cp .native/dosbox-x/config.log "$NATIVE_EVIDENCE/config.log"
python - <<'PY'
import hashlib, json, os
from pathlib import Path
executable=Path(os.environ['FDISBULL_DOSBOX'])
patch=Path(os.environ['FDISBULL_PATCH_DIRECTORY'])/'headless-agent.patch'
receipt={'source_commit':os.environ['CI_COMMIT_SHA'],
         'upstream_commit':'029bd65c5dcc7cdc7f2e14e35278620d9707d969',
         'backend_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
         'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),
         'profile':os.environ['FDISBULL_PATCH_DIRECTORY'],
         'python_version':os.sys.version, 'configure_flags':['--enable-sdl2','--enable-debug=heavy','--enable-dosbox_agent','--disable-avcodec','--disable-libslirp','--disable-libfluidsynth'], 'acceptance_tests':(Path('scripts/ci/native-'+os.environ['FDISBULL_PROFILE']+'-tests.txt').read_text()+' '+Path('scripts/ci/native-shared-tests.txt').read_text()).split()}
(Path(os.environ['NATIVE_EVIDENCE'])/'backend-identity.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY

python -m pytest -q --require-native $(cat scripts/ci/native-"$FDISBULL_PROFILE"-tests.txt scripts/ci/native-shared-tests.txt) --junitxml="$NATIVE_EVIDENCE/tests.xml" 2>&1 | tee "$NATIVE_EVIDENCE/tests.log"
if [ "$FDISBULL_PROFILE" = layers ]; then bash scripts/ci/native-offline.sh; fi
