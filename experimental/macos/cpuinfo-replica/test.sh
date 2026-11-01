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
# Build before checking pixels. Reusing an existing app would let a stale
# binary pass or fail the render checks against different source.
./build-app.sh >/dev/null
python3 Tests/verify_render.py
