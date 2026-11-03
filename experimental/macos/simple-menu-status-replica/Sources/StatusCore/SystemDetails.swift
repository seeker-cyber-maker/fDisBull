import Foundation
import Darwin
import IOKit
import IOKit.ps

public struct CPUCoreTimes: Equatable {
    public let user: UInt32
    public let system: UInt32
    public let idle: UInt32
    public let nice: UInt32
    public init(user: UInt32, system: UInt32, idle: UInt32, nice: UInt32) {
        self.user = user; self.system = system; self.idle = idle; self.nice = nice
    }
}

public enum CPUUsage {
    /// Tick counters can wrap; wrapping subtraction preserves the interval delta.
    public static func percentage(previous: CPUCoreTimes, current: CPUCoreTimes) -> Double? {
        let user = UInt64(current.user &- previous.user)
        let system = UInt64(current.system &- previous.system)
        let idle = UInt64(current.idle &- previous.idle)
        let nice = UInt64(current.nice &- previous.nice)
        let total = user + system + idle + nice
        guard total > 0 else { return nil }
        return 100 * Double(user + system + nice) / Double(total)
    }

    /// Aggregate tick deltas by cluster so a busy core contributes according
    /// to its measured interval, rather than averaging rounded percentages.
    public static func clusterPercentages(previous: [CPUCoreTimes], current: [CPUCoreTimes], eCoreCount: Int) -> (e: Double?, p: Double?)? {
        guard !current.isEmpty, previous.count == current.count,
              eCoreCount > 0, eCoreCount < current.count else { return nil }
        var eBusy: UInt64 = 0, eTotal: UInt64 = 0
        var pBusy: UInt64 = 0, pTotal: UInt64 = 0
        for (index, pair) in zip(previous, current).enumerated() {
            let prior = pair.0, now = pair.1
            let busy = UInt64(now.user &- prior.user)
                + UInt64(now.system &- prior.system)
                + UInt64(now.nice &- prior.nice)
            let total = busy + UInt64(now.idle &- prior.idle)
            guard total > 0 else { continue }
            if index < eCoreCount {
                eBusy += busy; eTotal += total
            } else {
                pBusy += busy; pTotal += total
            }
        }
        return (e: eTotal > 0 ? 100 * Double(eBusy) / Double(eTotal) : nil,
                p: pTotal > 0 ? 100 * Double(pBusy) / Double(pTotal) : nil)
    }
}

public struct MemoryDetails {
    public let physicalBytes: UInt64
    public let usedBytes: UInt64?
    public let appBytes: UInt64?
    /// Raw VM page categories for a segmented unified-memory display.
    public let activeBytes: UInt64?
    public let freeBytes: UInt64?
    public let wiredBytes: UInt64?
    public let compressedBytes: UInt64?
    public let cachedBytes: UInt64?
    public let swapUsedBytes: UInt64?
    public let swapTotalBytes: UInt64?
}

public enum BatteryPresence {
    /// A registry service may exist on a desktop with no installed battery.
    public static func isPresent(installed: Bool?, maximumCapacity: Int?) -> Bool {
        if let installed = installed { return installed }
        return (maximumCapacity ?? 0) > 0
    }
}

public struct BatteryDetails {
    public let isPresent: Bool
    public let percentage: Double?
    public let isCharging: Bool?
    public let cycleCount: Int?
    public let healthPercentage: Double?
    public let minutesRemaining: Int?
}

/// Values unavailable from macOS are nil. CPU values require two samples.
public struct SystemDetails {
    public let cpuPercentages: [Double?]
    /// Nil when the Apple Silicon performance-level split is unavailable.
    public let eCorePercentage: Double?
    public let pCorePercentage: Double?
    public let thermalState: ProcessInfo.ThermalState
    /// One-, five-, and fifteen-minute load averages; nil on read failure.
    public let loadAverages: [Double]?
    /// Wall-clock seconds since boot, including time spent asleep.
    public let uptimeSeconds: TimeInterval?
    public let memory: MemoryDetails
    public let battery: BatteryDetails
}

public final class SystemDetailsSampler {
    private var previousCPU: [CPUCoreTimes]?
    private let eCoreCount = SystemDetailsSampler.readECoreCount()
    public init() {}

    public func sample() -> SystemDetails {
        let current = readCPU()
        let percentages: [Double?]
        let clusters: (e: Double?, p: Double?)?
        if let current = current, let previous = previousCPU, current.count == previous.count {
            percentages = zip(previous, current).map { CPUUsage.percentage(previous: $0, current: $1) }
            clusters = eCoreCount.flatMap { CPUUsage.clusterPercentages(previous: previous, current: current, eCoreCount: $0) }
        } else {
            percentages = current.map { Array(repeating: nil, count: $0.count) } ?? []
            clusters = nil
        }
        previousCPU = current
        var loads = [Double](repeating: 0, count: 3)
        let loadAverages = getloadavg(&loads, 3) == 3 ? loads : nil
        return SystemDetails(cpuPercentages: percentages,
                             eCorePercentage: clusters?.e, pCorePercentage: clusters?.p,
                             thermalState: ProcessInfo.processInfo.thermalState,
                             loadAverages: loadAverages, uptimeSeconds: Self.readUptime(),
                             memory: readMemory(), battery: readBattery())
    }

    private static func readECoreCount() -> Int? {
        var levels: Int32 = 0
        var size = MemoryLayout<Int32>.size
        guard sysctlbyname("hw.nperflevels", &levels, &size, nil, 0) == 0, levels >= 2 else { return nil }
        var count: Int32 = 0
        size = MemoryLayout<Int32>.size
        guard sysctlbyname("hw.perflevel1.logicalcpu", &count, &size, nil, 0) == 0,
              count > 0 else { return nil }
        return Int(count)
    }

    private static func readUptime() -> TimeInterval? {
        var boottime = timeval()
        var size = MemoryLayout<timeval>.size
        guard sysctlbyname("kern.boottime", &boottime, &size, nil, 0) == 0,
              boottime.tv_sec > 0 else { return nil }
        return max(0, Date().timeIntervalSince1970 - TimeInterval(boottime.tv_sec))
    }

    private func readCPU() -> [CPUCoreTimes]? {
        var count: natural_t = 0
        var info: processor_info_array_t?
        var infoCount: mach_msg_type_number_t = 0
        let result = host_processor_info(mach_host_self(), PROCESSOR_CPU_LOAD_INFO, &count, &info, &infoCount)
        guard result == KERN_SUCCESS, let info = info else { return nil }
        defer {
            vm_deallocate(mach_task_self_, vm_address_t(UInt(bitPattern: info)), vm_size_t(infoCount) * vm_size_t(MemoryLayout<integer_t>.stride))
        }
        let stride = Int(CPU_STATE_MAX)
        guard Int(infoCount) >= Int(count) * stride else { return nil }
        return (0..<Int(count)).map { index in
            let base = index * stride
            return CPUCoreTimes(user: UInt32(bitPattern: info[base + Int(CPU_STATE_USER)]), system: UInt32(bitPattern: info[base + Int(CPU_STATE_SYSTEM)]), idle: UInt32(bitPattern: info[base + Int(CPU_STATE_IDLE)]), nice: UInt32(bitPattern: info[base + Int(CPU_STATE_NICE)]))
        }
    }

    private func readMemory() -> MemoryDetails {
        let physical = ProcessInfo.processInfo.physicalMemory
        var stats = vm_statistics64()
        var count = mach_msg_type_number_t(MemoryLayout<vm_statistics64>.size / MemoryLayout<integer_t>.size)
        let result = withUnsafeMutablePointer(to: &stats) { pointer in
            pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics64(mach_host_self(), HOST_VM_INFO64, $0, &count)
            }
        }
        var pageSize: vm_size_t = 0
        let pageResult = host_page_size(mach_host_self(), &pageSize)
        var used: UInt64?, app: UInt64?, active: UInt64?, free: UInt64?, wired: UInt64?, compressed: UInt64?, cached: UInt64?
        if result == KERN_SUCCESS && pageResult == KERN_SUCCESS {
            let page = UInt64(pageSize)
            active = UInt64(stats.active_count) * page
            free = UInt64(stats.free_count) * page
            wired = UInt64(stats.wire_count) * page
            compressed = UInt64(stats.compressor_page_count) * page
            // Purgeable pages can overlap inactive pages, so do not add both.
            cached = UInt64(stats.inactive_count) * page
            // Activity Monitor-style estimate: physical footprint excluding
            // reclaimable inactive pages, wired, and compressed.
            let reclaimable = min(physical, (cached ?? 0) + (free ?? 0))
            used = physical - reclaimable
            let nonApp = (wired ?? 0) + (compressed ?? 0)
            app = (used ?? 0) > nonApp ? (used ?? 0) - nonApp : 0
        }
        var swap = xsw_usage()
        var size = MemoryLayout<xsw_usage>.size
        let swapOK = sysctlbyname("vm.swapusage", &swap, &size, nil, 0) == 0
        return MemoryDetails(physicalBytes: physical, usedBytes: used, appBytes: app, activeBytes: active, freeBytes: free, wiredBytes: wired, compressedBytes: compressed, cachedBytes: cached, swapUsedBytes: swapOK ? swap.xsu_used : nil, swapTotalBytes: swapOK ? swap.xsu_total : nil)
    }

    private func readBattery() -> BatteryDetails {
        let service = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("AppleSmartBattery"))
        guard service != 0 else { return BatteryDetails(isPresent: false, percentage: nil, isCharging: nil, cycleCount: nil, healthPercentage: nil, minutesRemaining: nil) }
        defer { IOObjectRelease(service) }
        var properties: Unmanaged<CFMutableDictionary>?
        guard IORegistryEntryCreateCFProperties(service, &properties, kCFAllocatorDefault, 0) == KERN_SUCCESS,
              let values = properties?.takeRetainedValue() as? [String: Any] else {
            return BatteryDetails(isPresent: true, percentage: nil, isCharging: nil, cycleCount: nil, healthPercentage: nil, minutesRemaining: nil)
        }
        func number(_ key: String) -> Int? { (values[key] as? NSNumber)?.intValue }
        let current = number("CurrentCapacity"), maximum = number("MaxCapacity"), design = number("DesignCapacity")
        let installed = (values["BatteryInstalled"] as? NSNumber)?.boolValue
        guard BatteryPresence.isPresent(installed: installed, maximumCapacity: maximum) else {
            return BatteryDetails(isPresent: false, percentage: nil, isCharging: nil, cycleCount: nil, healthPercentage: nil, minutesRemaining: nil)
        }
        let percentage = current.flatMap { c in maximum.flatMap { $0 > 0 ? 100 * Double(c) / Double($0) : nil } }
        let health = maximum.flatMap { m in design.flatMap { $0 > 0 ? 100 * Double(m) / Double($0) : nil } }
        let minutes = number("TimeRemaining").flatMap { $0 >= 0 && $0 < 65535 ? $0 : nil }
        return BatteryDetails(isPresent: true, percentage: percentage, isCharging: (values["IsCharging"] as? NSNumber)?.boolValue, cycleCount: number("CycleCount"), healthPercentage: health, minutesRemaining: minutes)
    }
}
