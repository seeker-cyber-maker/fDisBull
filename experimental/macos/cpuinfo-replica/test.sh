#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
/usr/bin/xcrun swiftc -target "$(uname -m)-apple-macosx14.0" -parse-as-library Sources/CPUCore.swift Tests/CoreTests.swift -o build/core-tests
build/core-tests
/usr/bin/xcrun swiftc -target "$(uname -m)-apple-macosx14.0" -parse-as-library Sources/CPUCore.swift Sources/MachSampler.swift Tests/SamplingTests.swift -o build/sampling-tests
build/sampling-tests
/usr/bin/xcrun swiftc -target "$(uname -m)-apple-macosx14.0" -D CPUINFO_TESTING -parse-as-library Sources/CPUCore.swift Sources/MachSampler.swift Sources/MeterRenderer.swift Sources/DisplayPreferences.swift Sources/main.swift Tests/MenuTests.swift -framework AppKit -framework ServiceManagement -o build/menu-tests
build/menu-tests
if [ -f 'build/Cpuinfo Replica.app/Contents/MacOS/CpuinfoReplica' ]; then
  python3 Tests/verify_render.py
fi
