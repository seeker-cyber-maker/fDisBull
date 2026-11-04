#!/usr/bin/env bash
set -Eeuo pipefail
test "${FDISBULL_EXECUTION_ORIGIN:-}" = local-linux
test "${FDISBULL_UNIFIED_PREPARE_ONLY:-}" = 1
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates git build-essential clang libx11-dev libsdl2-2.0-0 libsdl2-net-2.0-0 libncurses6 libncursesw6 libgl1 libpng16-16 zlib1g libfreetype6
python - <<'PY'
import hashlib,json,os
from pathlib import Path
receipt=json.loads(Path('native-evidence/layers/backend-identity.json').read_text())
assert receipt['source_commit']==os.environ['CI_COMMIT_SHA']
with Path(os.environ['FDISBULL_DOSBOX']).open('rb') as stream:
    assert receipt['backend_sha256']==hashlib.file_digest(stream,'sha256').hexdigest()
PY
python -m pip install '.[test]' build
mkdir -p .native/pe/packages .native/pe/qemu-9.2.4/build .native/pe/qemu-9.2.4/pc-bios native-evidence/pe
cp dist/fdisbull-*.whl .native/pe/packages/
python scripts/check_dist.py .native/pe/packages/*.whl
python -m pip install --force-reinstall --no-deps .native/pe/packages/*.whl
cp .native/reuse-unified/qemu "$FDISBULL_PE_QEMU"
cp .native/reuse-unified/kernel "$FDISBULL_PE_KERNEL"
cp .native/reuse-unified/oracle "$FDISBULL_PE_FIXTURE"
cp -a .native/reuse-unified/firmware/. .native/pe/qemu-9.2.4/pc-bios/
cp -a .native/reuse-unified native-evidence/pe/reuse
cp .native/reuse-unified/wine-packages.txt native-evidence/pe/runtime-packages.txt
python -m fdisbull.wine_runtime --base-initramfs .native/reuse-unified/wine-base --output "$FDISBULL_PE_INITRAMFS" > native-evidence/pe/runtime-preparation.json
python -m fdisbull.dos_runtime --base-initramfs .native/reuse-unified/wine-base --dosbox "$FDISBULL_DOSBOX" --output "$FDISBULL_DOS_INITRAMFS" > native-evidence/pe/dos-runtime-preparation.json
python - <<'PY'
import hashlib,json,os
from pathlib import Path
import fdisbull
assert 'site-packages' in fdisbull.__file__
def identity(path):
    path=Path(path)
    with path.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'path':str(path),'sha256':digest,'size':path.stat().st_size}
receipt={'source_commit':os.environ['CI_COMMIT_SHA'], 'version':fdisbull.__version__,
         'installed_module':fdisbull.__file__,
         'inputs':{key:identity(os.environ[key]) for key in ('FDISBULL_PE_QEMU','FDISBULL_PE_KERNEL',
             'FDISBULL_PE_INITRAMFS','FDISBULL_PE_FIXTURE','FDISBULL_DOSBOX','FDISBULL_DOS_INITRAMFS')},
         'wheel':identity(next(Path('.native/pe/packages').glob('*.whl'))),
         'reuse_origin':'native-evidence/pe/reuse/origin.json'}
Path('native-evidence/pe/backend-identity.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY
python scripts/ci/unified-runtime-inputs.py prepare
