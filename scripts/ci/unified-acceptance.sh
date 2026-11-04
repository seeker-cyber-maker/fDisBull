#!/usr/bin/env bash
set -euo pipefail
if [ "${FDISBULL_UNIFIED_PREPARED:-}" = 1 ]; then
  [[ "${FDISBULL_EXECUTION_ORIGIN:-}" = local-linux || "${FDISBULL_EXECUTION_ORIGIN:-}" = boat-linux ]]
  qemu_firmware_dir="$(dirname "$(dirname "$FDISBULL_PE_QEMU")")/share/qemu"
  python scripts/ci/unified-runtime-inputs.py verify --install-firmware "$qemu_firmware_dir"
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
  # The verified QEMU is relocatable. Check its real default data search and
  # require a default-BIOS Q35 launch to reach QMP before running the suite.
  python -I - <<'PYCODE'
import json, os, subprocess, tempfile, time
from pathlib import Path
from fdisbull.qemu_control import QemuControl

qemu = Path(os.environ['FDISBULL_PE_QEMU']).resolve(strict=True)
firmware = qemu.parent.parent / 'share/qemu'
evidence = Path('native-evidence/pe')
search = subprocess.run([str(qemu), '-L', 'help'], capture_output=True, text=True, timeout=20, check=True)
(evidence / 'qemu-data-directories.txt').write_text(search.stdout)
if firmware.resolve() not in [Path(line).resolve() for line in search.stdout.splitlines() if line.strip()]:
    raise RuntimeError('Verified firmware directory is absent from QEMU data search')
if not (firmware / 'bios-256k.bin').is_file():
    raise RuntimeError('Verified default PC BIOS is missing')
with tempfile.TemporaryDirectory(prefix='fdisbull-qmp-preflight-') as directory:
    socket = Path(directory) / 'qmp.sock'
    command = [str(qemu), '-accel', 'tcg,thread=multi', '-machine', 'q35',
               '-m', '64M', '-smp', '1', '-nic', 'none', '-display', 'none',
               '-monitor', 'none', '-serial', 'none', '-S', '-no-reboot',
               '-qmp', f'unix:{socket},server=on,wait=off']
    qmp = None
    with (evidence / 'qemu-bios-preflight.log').open('wb') as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        try:
            qmp = QemuControl(socket, process, time.monotonic() + 20)
            status = qmp.call('query-status', timeout_ms=10000)
            if status.get('running') is not False:
                raise RuntimeError('QEMU preflight did not remain paused')
        finally:
            if qmp is not None:
                qmp.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
    (evidence / 'qemu-bios-preflight.json').write_text(json.dumps({
        'firmware_directory': str(firmware), 'qmp_status': status,
        'scope': 'default BIOS and paused QMP preflight; not guest acceptance'
    }, indent=2) + '\n')
PYCODE
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
