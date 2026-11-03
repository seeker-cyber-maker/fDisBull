#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p .build/checks
swiftc Sources/StatusCore/MemoryMood.swift Tests/PressureChecks/main.swift -o .build/checks/pressure-checks
.build/checks/pressure-checks
swiftc Sources/StatusCore/NetworkMetrics.swift Tests/NetworkChecks/main.swift -o .build/checks/network-checks
.build/checks/network-checks
swiftc Sources/StatusCore/ProcessCaffeine.swift Tests/ProcessCaffeineChecks/main.swift -o .build/checks/process-caffeine-checks
.build/checks/process-caffeine-checks
swiftc Sources/StatusCore/GPUMetrics.swift Tests/GPUChecks/main.swift -o .build/checks/gpu-checks
.build/checks/gpu-checks
swiftc Sources/StatusCore/SystemDetails.swift Tests/SystemDetailsChecks/main.swift -o .build/checks/system-details-checks
.build/checks/system-details-checks
swiftc Sources/StatusCore/AlertPolicy.swift Sources/StatusCore/AlertReadings.swift Tests/AlertChecks/main.swift -o .build/checks/alert-checks
.build/checks/alert-checks
swiftc Sources/StatusCore/AppCacheCleanup.swift Tests/CacheChecks/main.swift -o .build/checks/cache-checks
.build/checks/cache-checks
swiftc Sources/StatusCore/VPNStatus.swift Tests/VPNChecks/main.swift -o .build/checks/vpn-checks
.build/checks/vpn-checks
swiftc Sources/StatusCore/PublicIP.swift Tests/PublicIPChecks/main.swift -o .build/checks/public-ip-checks
.build/checks/public-ip-checks
swiftc Sources/StatusReplica/ReplicaLocalization.swift Sources/StatusReplica/ShareImage.swift Tests/ShareChecks/main.swift -o .build/checks/share-checks
.build/checks/share-checks
swiftc Sources/StatusCore/LoginItem.swift Tests/LoginItemChecks/main.swift -o .build/checks/login-item-checks
.build/checks/login-item-checks
swiftc Sources/StatusCore/MemoryMood.swift Sources/StatusCore/IndicatorHealth.swift Tests/IndicatorHealthChecks/main.swift -o .build/checks/indicator-health-checks
.build/checks/indicator-health-checks
swiftc Sources/StatusCore/ProcessWatch.swift Tests/ProcessWatchChecks/main.swift -o .build/checks/process-watch-checks
.build/checks/process-watch-checks
swiftc Sources/StatusCore/ReplicaPreferences.swift Tests/PreferencesChecks/main.swift -o .build/checks/preferences-checks
.build/checks/preferences-checks
swiftc Sources/StatusCore/StorageMetrics.swift Tests/StorageChecks/main.swift -o .build/checks/storage-checks
.build/checks/storage-checks
swiftc Sources/StatusCore/StorageMetrics.swift Sources/StatusCore/StorageCategoryScan.swift Tests/StorageCategoryChecks/main.swift -o .build/checks/storage-category-checks
.build/checks/storage-category-checks

swiftc -target "$(uname -m)-apple-macosx12.0" Sources/StatusReplica/CPUBarGraph.swift Tests/CPUBarGraphChecks/main.swift -framework AppKit -o .build/checks/cpu-bar-graph-checks
.build/checks/cpu-bar-graph-checks

swiftc -target "$(uname -m)-apple-macosx12.0" Sources/StatusCore/MemoryMood.swift Sources/StatusReplica/CPUBarGraph.swift Tests/CombinedIconChecks/main.swift -framework AppKit -o .build/checks/combined-icon-checks
.build/checks/combined-icon-checks
