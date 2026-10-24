#!/bin/sh
set -eu
mkdir -p /work/evidence
uname -a > /work/evidence/linux.txt
wine --version > /work/evidence/wine-version.txt
dpkg-query -W wine wine64 gcc-mingw-w64-x86-64-win32 > /work/evidence/package-versions.txt
sha256sum /opt/dosbox-x/src/dosbox-x /opt/probes/target64.exe /opt/probes/controller64.exe /opt/packages/*.whl > /work/evidence/SHA256SUMS
python3 - <<'PY' > /work/counter-rva.txt
from pathlib import Path
symbols=Path('/opt/probes/target-symbols.txt').read_text().splitlines()
address=next(int(line.split()[0],16) for line in symbols if line.split()[-1]=='fdisbull_probe_counter')
base=next(int(line.split()[1],16) for line in Path('/opt/probes/target-headers.txt').read_text().splitlines() if line.split()[:1]==['ImageBase'])
print(hex(address-base))
PY
export WINEPREFIX=/work/wine-prefix
export WINEARCH=win64
export WINEDEBUG=-all
export XDG_RUNTIME_DIR=/work/runtime
export XDG_CACHE_HOME=/work/cache
mkdir -p -m700 "$XDG_RUNTIME_DIR" "$WINEPREFIX" "$XDG_CACHE_HOME"
set +e
xvfb-run -a sh -c 'timeout 180 wineboot -u && timeout 35 wine /opt/probes/controller64.exe Z:\\opt\\probes\\target64.exe "$(cat /work/counter-rva.txt)"' > /work/evidence/wine-probe.jsonl 2> /work/evidence/wine-probe.stderr
wine_status=$?
FDISBULL_DOSBOX=/opt/dosbox-x/src/dosbox-x /opt/venv/bin/python -m pytest -q --require-native \
  /opt/tests/test_debugger.py /opt/tests/test_code_layers.py /opt/tests/test_screenshot_grid.py \
  --junitxml=/work/evidence/dosbox-tests.xml > /work/evidence/dosbox-tests.log 2>&1
dosbox_status=$?
set -e
printf '{"wine_exit":%s,"dosbox_exit":%s}\n' "$wine_status" "$dosbox_status" > /work/evidence/exit-codes.json
cat /work/evidence/linux.txt /work/evidence/wine-version.txt /work/evidence/wine-probe.jsonl /work/evidence/exit-codes.json
# A caller may request a finite extraction window; failures still exit nonzero.
hold_seconds=${FDISBULL_HOLD_SECONDS:-0}
case "$hold_seconds" in ''|*[!0-9]*) exit 64;; esac
if [ "$hold_seconds" -gt 3600 ]; then exit 64; fi
if [ "$hold_seconds" -gt 0 ]; then sleep "$hold_seconds"; fi
if [ "$wine_status" -ne 0 ] || [ "$dosbox_status" -ne 0 ]; then exit 1; fi
