#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
/usr/bin/xcrun swiftc -target "$(uname -m)-apple-macosx14.0" -parse-as-library Sources/CPUCore.swift Tests/CoreTests.swift -o build/core-tests
build/core-tests
if [ -f 'build/Cpuinfo Replica.app/Contents/MacOS/CpuinfoReplica' ]; then
  python3 Tests/verify_render.py
fi
