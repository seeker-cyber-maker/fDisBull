import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}
let a = CPUCoreTimes(user: 10, system: 10, idle: 30, nice: 0)
let b = CPUCoreTimes(user: 20, system: 15, idle: 45, nice: 0)
check(CPUUsage.percentage(previous: a, current: b) == 50, "CPU percentage")
check(CPUUsage.percentage(previous: a, current: a) == nil, "zero interval")
let wrap = CPUCoreTimes(user: UInt32.max - 4, system: 0, idle: 0, nice: 0)
let wrapped = CPUCoreTimes(user: 5, system: 0, idle: 10, nice: 0)
check(CPUUsage.percentage(previous: wrap, current: wrapped) == 50, "counter wrap")
let previousCluster = Array(repeating: CPUCoreTimes(user: 0, system: 0, idle: 0, nice: 0), count: 4)
let currentCluster = [
    CPUCoreTimes(user: 10, system: 0, idle: 90, nice: 0),
    CPUCoreTimes(user: 40, system: 0, idle: 60, nice: 0),
    CPUCoreTimes(user: 100, system: 0, idle: 100, nice: 0),
    CPUCoreTimes(user: 20, system: 0, idle: 80, nice: 0),
]
let cluster = CPUUsage.clusterPercentages(previous: previousCluster, current: currentCluster, eCoreCount: 2)
check(cluster?.e == 25 && cluster?.p == 40, "weighted E/P cluster percentages")
check(CPUUsage.clusterPercentages(previous: previousCluster, current: currentCluster, eCoreCount: 0) == nil, "unknown split")
check(CPUUsage.clusterPercentages(previous: previousCluster, current: previousCluster, eCoreCount: 2)?.e == nil, "no E interval")
check(!BatteryPresence.isPresent(installed: false, maximumCapacity: 0), "desktop registry service")
check(!BatteryPresence.isPresent(installed: nil, maximumCapacity: 0), "unknown battery with zero capacity")
check(BatteryPresence.isPresent(installed: true, maximumCapacity: nil), "installed battery")
check(BatteryPresence.isPresent(installed: nil, maximumCapacity: 5000), "capacity fallback")
let sampler = SystemDetailsSampler()
let first = sampler.sample()
Thread.sleep(forTimeInterval: 0.2)
let second = sampler.sample()
check(first.memory.physicalBytes > 0, "physical memory")
check((second.memory.activeBytes == nil) == (second.memory.freeBytes == nil), "VM page categories have one availability state")
if let active = second.memory.activeBytes, let free = second.memory.freeBytes {
    check(active <= second.memory.physicalBytes && free <= second.memory.physicalBytes, "VM page categories fit physical memory")
}
check(!second.cpuPercentages.isEmpty, "CPU cores")
check(second.cpuPercentages.contains { $0 != nil }, "sampled CPU")
check(second.cpuPercentages.allSatisfy { $0 == nil || (0...100).contains($0!) }, "CPU range")
check(second.loadAverages == nil || (second.loadAverages!.count == 3 && second.loadAverages!.allSatisfy { $0.isFinite && $0 >= 0 }), "load averages")
check(second.uptimeSeconds == nil || (second.uptimeSeconds!.isFinite && second.uptimeSeconds! >= 0), "wall-clock uptime")
var modelLength = 0
if sysctlbyname("hw.model", nil, &modelLength, nil, 0) == 0 {
    var model = [CChar](repeating: 0, count: modelLength)
    if sysctlbyname("hw.model", &model, &modelLength, nil, 0) == 0 && String(cString: model) == "Mac13,1" {
        check(!second.battery.isPresent, "Mac13,1 without installed battery")
        check(second.eCorePercentage != nil && second.pCorePercentage != nil, "Mac13,1 E/P split")
        check((0...100).contains(second.eCorePercentage!) && (0...100).contains(second.pCorePercentage!), "Mac13,1 cluster ranges")
    }
}
print("System details checks passed (\(second.cpuPercentages.count) cores; battery present: \(second.battery.isPresent))")
