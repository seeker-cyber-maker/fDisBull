#!/usr/bin/env bash
set -euo pipefail
if [ "${FDISBULL_UNIFIED_PREPARED:-}" = 1 ]; then
  test "${FDISBULL_EXECUTION_ORIGIN:-}" = local-linux
  python scripts/ci/unified-runtime-inputs.py verify --install-firmware /usr/local/share/qemu
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends ca-certificates curl xz-utils git build-essential clang libx11-dev libglib2.0-0 libpixman-1-0 libsdl2-2.0-0 libsdl2-net-2.0-0 libncurses6 libncursesw6 libgl1 libpng16-16 zlib1g libfreetype6
  bash scripts/ci/install-node.sh
  mkdir -p native-evidence/pe native-evidence/unified
  ldd "$FDISBULL_PE_QEMU" | tee native-evidence/pe/acceptance-qemu-libraries.txt
  ! grep -q 'not found' native-evidence/pe/acceptance-qemu-libraries.txt
  ldd "$FDISBULL_DOSBOX" | tee native-evidence/pe/acceptance-dos-libraries.txt
  ! grep -q 'not found' native-evidence/pe/acceptance-dos-libraries.txt
  python -m pip install ".[test]"
  shopt -s nullglob
  core_wheels=(dist/fdisbull-*.whl)
  [[ ${#core_wheels[@]} -eq 1 ]]
  python scripts/check_dist.py .native/pe/packages/*.whl
  python -m pip install --force-reinstall --no-deps .native/pe/packages/*.whl
fi

set -euo pipefail
python -m pytest -q -s tests/test_wine_debugger.py tests/test_wine_advanced.py tests/test_wine_doctor.py tests/test_wine_deltas.py tests/test_wine_deltas_native.py tests/test_udc_shell.py tests/test_udc_selected_shell.py -o pythonpath= \
  --junitxml=native-evidence/pe/tests.xml 2>&1 | tee native-evidence/pe/tests.log

set -euo pipefail
mkdir -p native-evidence/unified
python -m pytest -q -s tests/test_dos_qemu.py tests/test_qemu_machine.py -o pythonpath= \
  --junitxml=native-evidence/unified/tests.xml 2>&1 | tee native-evidence/unified/tests.log

if [ "${FDISBULL_UNIFIED_PREPARED:-}" = 1 ]; then
  python scripts/ci/native-receipt.py unified
fi
