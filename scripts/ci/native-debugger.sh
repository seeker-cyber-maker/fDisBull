#!/usr/bin/env bash
set -euo pipefail

# Kept as one finite source-transport seam so it can be checked without builds.
prepare_dosbox_source() {
  local pinned_commit="$1" upstream
  if [ -n "${FDISBULL_DOSBOX_UPSTREAM_ARCHIVE:-}" ]; then
    python - "$FDISBULL_DOSBOX_UPSTREAM_ARCHIVE" "${FDISBULL_DOSBOX_UPSTREAM_SHA256:-}" "$pinned_commit" <<'PY'
import importlib.util, sys, tarfile
from pathlib import Path
path, expected, pinned = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location('local_upstream_check', 'scripts/ci/local-linux.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
checker.upstream_archive_identity(path, expected, expected_commit=pinned)
destination = Path('.native/upstream/unpacked')
destination.mkdir(parents=True, exist_ok=False)
with tarfile.open(path, 'r:') as archive:
    archive.extractall(destination, filter='data')
PY
    upstream="$PWD/.native/upstream/unpacked/dosbox-x.git"
    test "$(git --git-dir="$upstream" rev-parse --is-bare-repository)" = true
    test ! -e "$upstream/objects/info/alternates"
    test "$(git --git-dir="$upstream" rev-parse refs/heads/upstream)" = "$pinned_commit"
    git --git-dir="$upstream" fsck --connectivity-only --no-reflogs
  elif [ "${FDISBULL_EXECUTION_ORIGIN:-}" = local-linux ]; then
    echo 'Local native CI requires an explicit verified offline upstream archive' >&2
    return 1
  else
    upstream=https://github.com/joncampbell123/dosbox-x.git
  fi
  git init -q .native/dosbox-x
  git -C .native/dosbox-x remote add origin "$upstream"
  git -C .native/dosbox-x fetch --depth 1 --no-recurse-submodules origin "$pinned_commit"
  git -c core.hooksPath=/dev/null -C .native/dosbox-x checkout --detach FETCH_HEAD
}
# End finite source-transport seam.

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl xz-utils git build-essential clang rustc libx11-dev autoconf automake pkg-config nasm llvm ffmpeg libsdl2-dev libsdl2-net-dev libncurses-dev libpng-dev zlib1g-dev libfreetype6-dev
bash scripts/ci/install-node.sh
python -m pip install ".[test]" build
export NATIVE_EVIDENCE="native-evidence/$FDISBULL_PROFILE"
export FDISBULL_FRAME_EVIDENCE="$CI_PROJECT_DIR/$NATIVE_EVIDENCE/frame-capture"
mkdir -p .native "$NATIVE_EVIDENCE"
prepare_dosbox_source 029bd65c5dcc7cdc7f2e14e35278620d9707d969
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

if [ "${FDISBULL_REUSE_BACKEND:-${FDISBULL_REUSE_STABLE:-}}" = 1 ]; then
  python scripts/ci/native_backend_reuse.py ".native/reuse-$FDISBULL_PROFILE" \
    "$FDISBULL_PATCH_DIRECTORY/source-manifest.json" "$FDISBULL_REUSE_IMAGE_DIGEST" \
    "$NATIVE_EVIDENCE" "$FDISBULL_DOSBOX" --profile "$FDISBULL_PROFILE"
else
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
fi
python - <<'PY'
import hashlib, json, os, subprocess
from pathlib import Path
executable=Path(os.environ['FDISBULL_DOSBOX'])
patch=Path(os.environ['FDISBULL_PATCH_DIRECTORY'])/'headless-agent.patch'
receipt={'source_commit':os.environ['CI_COMMIT_SHA'],
         'upstream_commit':'029bd65c5dcc7cdc7f2e14e35278620d9707d969',
         'backend_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
         'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),
         'profile':os.environ['FDISBULL_PATCH_DIRECTORY'],
         'python_version':os.sys.version, 'configure_flags':['--enable-sdl2','--enable-debug=heavy','--enable-dosbox_agent','--disable-avcodec','--disable-libslirp','--disable-libfluidsynth'], 'acceptance_tests':(Path('scripts/ci/native-'+os.environ['FDISBULL_PROFILE']+'-tests.txt').read_text()+' '+Path('scripts/ci/native-shared-tests.txt').read_text()).split()}
if os.environ.get('FDISBULL_DOSBOX_UPSTREAM_ARCHIVE'):
    receipt['upstream_source']={'transport':'local-bare-git-archive',
        'archive_sha256':os.environ['FDISBULL_DOSBOX_UPSTREAM_SHA256'],
        'tree':subprocess.check_output(['git','-C','.native/dosbox-x','rev-parse','HEAD^{tree}'],text=True).strip()}
reuse=Path(os.environ['NATIVE_EVIDENCE'])/'reuse-provenance.json'
if reuse.exists():
    receipt.update(json.loads(reuse.read_text()))
(Path(os.environ['NATIVE_EVIDENCE'])/'backend-identity.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY

python -m pytest -q --require-native $(cat scripts/ci/native-"$FDISBULL_PROFILE"-tests.txt scripts/ci/native-shared-tests.txt) --junitxml="$NATIVE_EVIDENCE/tests.xml" 2>&1 | tee "$NATIVE_EVIDENCE/tests.log"
if [ "$FDISBULL_PROFILE" = layers ]; then bash scripts/ci/native-offline.sh; fi
