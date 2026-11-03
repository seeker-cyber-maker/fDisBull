#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl xz-utils git build-essential clang libx11-dev pkg-config libglib2.0-dev libpixman-1-dev ninja-build docker.io libsdl2-2.0-0 libsdl2-net-2.0-0 libncurses6 libpng16-16 zlib1g libfreetype6
bash scripts/ci/install-node.sh
mkdir -p .native/pe native-evidence/pe native-evidence/unified
if [ "${FDISBULL_LOCAL_DOCKER:-}" = 1 ]; then
  source scripts/ci/local-docker.sh
fi
# Admit runtime inputs before spending time compiling QEMU or building Wine.
timeout 30s docker info > native-evidence/pe/docker-info.txt
curl --fail --location --retry 3 \
  https://deb.debian.org/debian/dists/bookworm/main/installer-amd64/current/images/netboot/debian-installer/amd64/linux \
  --output "$FDISBULL_PE_KERNEL"
echo "d8808aa4ca188560da1e6d749dcb930c87a5fd8b11ebff1f3fa6d728af35203d  $FDISBULL_PE_KERNEL" | sha256sum --check
chmod +x "$FDISBULL_DOSBOX"
sha256sum "$FDISBULL_DOSBOX"
ldd "$FDISBULL_DOSBOX"
python - <<'PY'
import hashlib, json, os
from pathlib import Path
receipt=json.loads(Path('native-evidence/layers/backend-identity.json').read_text())
assert receipt['source_commit']==os.environ['CI_COMMIT_SHA']
assert receipt['backend_sha256']==hashlib.sha256(Path(os.environ['FDISBULL_DOSBOX']).read_bytes()).hexdigest()
PY

python -m pip install ".[test]" build
shopt -s nullglob
core_wheels=(dist/fdisbull-*.whl)
[[ ${#core_wheels[@]} -eq 1 ]]
mkdir -p .native/pe/packages
cp "${core_wheels[0]}" .native/pe/packages/
python scripts/check_dist.py .native/pe/packages/*.whl
python -m pip install --force-reinstall --no-deps .native/pe/packages/*.whl

# QEMU 9.2's mkvenv needs distlib when pip/setuptools are already
# present; do not rely on pip's private vendored dependencies.
python -m pip install distlib==0.4.0
python -c 'import distlib.scripts, distlib.version'
apt-get update
apt-get install -y build-essential clang pkg-config libglib2.0-dev libpixman-1-dev ninja-build
mkdir -p native-evidence/pe
curl --fail --location --retry 3 https://download.qemu.org/qemu-9.2.4.tar.xz \
  --output .native/pe/qemu-9.2.4.tar.xz
echo 'f3cc1c4eabfdb288218ac3e33763dbe9e276d8bc890b867a2335d58de2ddd39a  .native/pe/qemu-9.2.4.tar.xz' | sha256sum --check
tar -xJf .native/pe/qemu-9.2.4.tar.xz -C .native/pe
mkdir .native/pe/qemu-9.2.4/build
(
cd .native/pe/qemu-9.2.4/build
../configure --target-list=x86_64-softmmu --disable-docs --disable-user \
  --disable-gtk --disable-sdl --disable-vnc --disable-curses --disable-werror
ninja -j2 qemu-system-x86_64
./qemu-system-x86_64 --version
)

docker_build_network=()
if [ "${FDISBULL_EXECUTION_ORIGIN:-}" = local-linux ]; then
  test "${FDISBULL_LOCAL_DOCKER_BUILD_NETWORK:-}" = host
  docker_build_network=(--network host)
fi
docker build "${docker_build_network[@]}" --platform linux/amd64 -f experimental/wine/ci/Containerfile -t fdisbull-pe-ci .
docker create --name fdisbull-pe-libraries --network none fdisbull-pe-ci \
  sh -ec 'ldd /opt/dosbox-x > /tmp/dos-libraries; cat /tmp/dos-libraries; ! grep -q "not found" /tmp/dos-libraries'
docker cp "$FDISBULL_DOSBOX" fdisbull-pe-libraries:/opt/dosbox-x
docker start --attach fdisbull-pe-libraries
docker rm fdisbull-pe-libraries
docker create --name fdisbull-pe-export fdisbull-pe-ci /bin/true
docker cp fdisbull-pe-export:/opt/ci/oracle.exe .native/pe/oracle.exe
docker cp fdisbull-pe-export:/opt/ci/runtime-packages.txt native-evidence/pe/runtime-packages.txt
docker export --output .native/pe/rootfs.tar fdisbull-pe-export
docker rm fdisbull-pe-export
docker image inspect --format '{{.Id}}' fdisbull-pe-ci > native-evidence/pe/rootfs-image.txt

python experimental/wine/ci/build_runtime.py \
  --rootfs-tar .native/pe/rootfs.tar --base .native/pe/base.cpio.gz \
  --output "$FDISBULL_PE_INITRAMFS" > native-evidence/pe/runtime-preparation.json
python -m fdisbull.dos_runtime \
  --base-initramfs .native/pe/base.cpio.gz \
  --dosbox "$FDISBULL_DOSBOX" --output "$FDISBULL_DOS_INITRAMFS" \
  > native-evidence/pe/dos-runtime-preparation.json
rm .native/pe/rootfs.tar .native/pe/base.cpio.gz

python - <<'PY'
import hashlib, json, os
from pathlib import Path
import fdisbull
assert 'site-packages' in fdisbull.__file__, fdisbull.__file__
def identity(path):
    path=Path(path)
    with path.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'path':str(path),'sha256':digest,'size':path.stat().st_size}
receipt={'source_commit':os.environ['CI_COMMIT_SHA'],
         'version':fdisbull.__version__,'installed_module':fdisbull.__file__,
         'inputs':{key:identity(os.environ[key]) for key in (
             'FDISBULL_PE_QEMU','FDISBULL_PE_KERNEL','FDISBULL_PE_INITRAMFS','FDISBULL_PE_FIXTURE',
             'FDISBULL_DOSBOX','FDISBULL_DOS_INITRAMFS')},
         'wheel':identity(next(Path('.native/pe/packages').glob('*.whl')))}
Path('native-evidence/pe/backend-identity.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY

set -euo pipefail
python -m pytest -q -s tests/test_wine_debugger.py tests/test_wine_advanced.py tests/test_wine_doctor.py tests/test_wine_deltas.py tests/test_wine_deltas_native.py tests/test_udc_shell.py tests/test_udc_selected_shell.py -o pythonpath= \
  --junitxml=native-evidence/pe/tests.xml 2>&1 | tee native-evidence/pe/tests.log

set -euo pipefail
mkdir -p native-evidence/unified
python -m pytest -q -s tests/test_dos_qemu.py tests/test_qemu_machine.py -o pythonpath= \
  --junitxml=native-evidence/unified/tests.xml 2>&1 | tee native-evidence/unified/tests.log
