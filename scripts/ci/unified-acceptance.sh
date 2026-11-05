#!/usr/bin/env bash
set -euo pipefail
if [ "${FDISBULL_UNIFIED_PREPARED:-}" = 1 ]; then
  [[ "${FDISBULL_EXECUTION_ORIGIN:-}" = local-linux || "${FDISBULL_EXECUTION_ORIGIN:-}" = boat-linux ]]
  # The stripped retained executable resolves firmware relative to build/.
  python scripts/ci/unified-runtime-inputs.py verify --install-firmware .native/pe/qemu-9.2.4/share/qemu
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends ca-certificates curl xz-utils git build-essential clang libx11-dev libglib2.0-0 libpixman-1-0 libsdl2-2.0-0 libsdl2-net-2.0-0 libncurses6 libncursesw6 libgl1 libpng16-16 zlib1g libfreetype6 libzstd1
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

windows_tests=()
windows_selection=()
if [ "${FDISBULL_REQUIRE_WINDOWS:-}" = 1 ]; then
  export FDISBULL_PE32_FIXTURE="$CI_PROJECT_DIR/native-evidence/pe/selftest32.exe"
  windows_tests=(tests/test_windows_native.py tests/test_wine_pe32.py tests/test_wine_pe32_state.py tests/test_win16_debugger.py tests/test_win16_native.py)
  # The arbitrary NE client and declared Snake movie require independent private
  # fixtures. This lane runs every bounded NE guard and the real authored PE32
  # process; it does not relabel those guards as full Win16 compatibility.
  windows_selection=(-k 'not test_real_original_ne_entry_registers_memory_and_completed_instructions and not test_real_win16_original_ne_gui_keyboard_named_scene_and_dot_mode')
  if [ "${FDISBULL_REQUIRE_NE:-}" = 1 ]; then
    test "${FDISBULL_REQUIRE_NE_GUI:-}" = 1
    test "${FDISBULL_REQUIRE_NE_CAMPAIGN:-}" = 1
    test "${FDISBULL_NE_CAMPAIGN_CASES:-}" = 3
    mkdir "$FDISBULL_NE_CAMPAIGN_OUTPUT"
    windows_tests+=(tests/test_windows_sequence_campaign.py)
    windows_selection=()
  fi
fi

set -euo pipefail
python -m pytest -q -s tests/test_wine_debugger.py tests/test_wine_advanced.py tests/test_wine_doctor.py tests/test_wine_deltas.py tests/test_wine_deltas_native.py tests/test_udc_shell.py tests/test_udc_selected_shell.py -o pythonpath= \
  --junitxml=native-evidence/pe/core-tests.xml 2>&1 | tee native-evidence/pe/tests.log
if [ "${FDISBULL_REQUIRE_WINDOWS:-}" = 1 ]; then
  # The large Wine11 OS is reserved for the explicit 8GiB Windows tests. Existing
  # Wine64 and DOS acceptance retain their verified smaller OS base.
  export FDISBULL_PE_INITRAMFS="$CI_PROJECT_DIR/native-evidence/pe/windows-runtime.cpio.gz"
  export FDISBULL_NE_INITRAMFS="$FDISBULL_PE_INITRAMFS"
  python -m pytest -q -s "${windows_tests[@]}" "${windows_selection[@]}" -o pythonpath= \
    --junitxml=native-evidence/pe/windows-tests.xml 2>&1 | tee -a native-evidence/pe/tests.log
  export FDISBULL_PE_INITRAMFS="$CI_PROJECT_DIR/.native/pe/runtime.cpio.gz"
fi
python - <<'PY_JUNIT'
from pathlib import Path
from xml.etree import ElementTree as ET
combined=ET.Element('testsuites')
for name in ('core-tests.xml','windows-tests.xml'):
    path=Path('native-evidence/pe')/name
    if path.exists():
        document=ET.parse(path).getroot()
        suites=[document] if document.tag=='testsuite' else list(document)
        for suite in suites:combined.append(suite)
ET.ElementTree(combined).write('native-evidence/pe/tests.xml',encoding='utf-8',xml_declaration=True)
PY_JUNIT

set -euo pipefail
mkdir -p native-evidence/unified
python -m pytest -q -s tests/test_dos_qemu.py tests/test_qemu_machine.py -o pythonpath= \
  --junitxml=native-evidence/unified/tests.xml 2>&1 | tee native-evidence/unified/tests.log

if [ "${FDISBULL_UNIFIED_PREPARED:-}" = 1 ]; then
  python scripts/ci/native-receipt.py unified
fi
