#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p 'build/Cpuinfo Replica.app/Contents/MacOS'
mkdir -p 'build/Cpuinfo Replica.app/Contents/Resources'
cp NOTICE.md 'build/Cpuinfo Replica.app/Contents/Resources/NOTICE.md'
/usr/bin/xcrun swiftc -target "$(uname -m)-apple-macosx14.0" -parse-as-library Sources/CPUCore.swift Sources/MachSampler.swift Sources/MeterRenderer.swift Sources/main.swift \
  -framework AppKit -framework ServiceManagement -O -o 'build/Cpuinfo Replica.app/Contents/MacOS/CpuinfoReplica'
/usr/bin/python3 - <<'PY'
from pathlib import Path
import plistlib
info={"CFBundleIdentifier":"local.codex.cpuinfo-replica","CFBundleName":"Cpuinfo Replica",
      "CFBundleDisplayName":"Cpuinfo Replica","CFBundleExecutable":"CpuinfoReplica",
      "CFBundlePackageType":"APPL","CFBundleShortVersionString":"0.1.0","CFBundleVersion":"1",
      "LSUIElement":True,"LSMinimumSystemVersion":"14.0","NSHighResolutionCapable":True,
      "NSHumanReadableCopyright":"2026 Cpuinfo Replica contributors; behavior references Yusuke Shibata's MIT cpuinfo"}
Path('build/Cpuinfo Replica.app/Contents/Info.plist').write_bytes(plistlib.dumps(info))
PY
/usr/bin/codesign --force --sign - 'build/Cpuinfo Replica.app'
echo 'Built build/Cpuinfo Replica.app; no app was launched or installed.'
