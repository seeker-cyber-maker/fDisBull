import Foundation
import IOKit
import Metal

/// A best-effort sample of the system's default Metal device. Missing values
/// indicate that its driver did not expose a valid reading.
public struct GPUSnapshot {
    public let name: String?
    public let utilizationPercent: Double?
    public let rendererUtilizationPercent: Double?
    public let tilerUtilizationPercent: Double?
    public let coreCount: Int?
    /// IOAccelerator's system-wide GPU memory counters on supported drivers.
    /// On Apple Silicon this is unified memory, not dedicated VRAM.
    public let inUseSystemMemoryBytes: UInt64?
    public let allocatedSystemMemoryBytes: UInt64?
    public let driverInUseSystemMemoryBytes: UInt64?
    /// Metal's advisory per-process working-set limit; not installed GPU RAM.
    public let recommendedMaxWorkingSetBytes: UInt64?
}

public enum GPUMetrics {
    public static func sample() -> GPUSnapshot {
        guard let device = MTLCreateSystemDefaultDevice() else {
            return unavailable(name: nil, recommended: nil)
        }
        let recommended = device.recommendedMaxWorkingSetSize > 0 ? device.recommendedMaxWorkingSetSize : nil
        var iterator: io_iterator_t = 0
        guard let matching = IOServiceMatching("IOAccelerator"),
              IOServiceGetMatchingServices(kIOMainPortDefault, matching, &iterator) == KERN_SUCCESS else {
            return unavailable(name: device.name, recommended: recommended)
        }
        defer { IOObjectRelease(iterator) }
        while true {
            let service = IOIteratorNext(iterator)
            if service == IO_OBJECT_NULL { break }
            defer { IOObjectRelease(service) }
            var registryID: UInt64 = 0
            guard IORegistryEntryGetRegistryEntryID(service, &registryID) == KERN_SUCCESS,
                  registryID == device.registryID else { continue }
            let property = IORegistryEntryCreateCFProperty(service, "PerformanceStatistics" as CFString, kCFAllocatorDefault, 0)?.takeRetainedValue()
            let stats = property as? [String: Any]
            let cores = IORegistryEntryCreateCFProperty(service, "gpu-core-count" as CFString, kCFAllocatorDefault, 0)?.takeRetainedValue()
            let coreValue = numeric(cores)
            let coreCount: Int?
            if let value = coreValue, value.isFinite, value > 0, value <= Double(Int32.max), value.rounded() == value {
                coreCount = Int(value)
            } else {
                coreCount = nil
            }
            return GPUSnapshot(name: device.name,
                               utilizationPercent: percent(stats?["Device Utilization %"]),
                               rendererUtilizationPercent: percent(stats?["Renderer Utilization %"]),
                               tilerUtilizationPercent: percent(stats?["Tiler Utilization %"]),
                               coreCount: coreCount,
                               inUseSystemMemoryBytes: GPUCounterParsing.bytes(stats?["In use system memory"]),
                               allocatedSystemMemoryBytes: GPUCounterParsing.bytes(stats?["Alloc system memory"]),
                               driverInUseSystemMemoryBytes: GPUCounterParsing.bytes(stats?["In use system memory (driver)"]),
                               recommendedMaxWorkingSetBytes: recommended)
        }
        return unavailable(name: device.name, recommended: recommended)
    }

    private static func unavailable(name: String?, recommended: UInt64?) -> GPUSnapshot {
        GPUSnapshot(name: name, utilizationPercent: nil, rendererUtilizationPercent: nil,
                    tilerUtilizationPercent: nil, coreCount: nil,
                    inUseSystemMemoryBytes: nil, allocatedSystemMemoryBytes: nil,
                    driverInUseSystemMemoryBytes: nil, recommendedMaxWorkingSetBytes: recommended)
    }

    private static func numeric(_ value: Any?) -> Double? {
        guard let number = value as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID() else { return nil }
        return number.doubleValue
    }

    private static func percent(_ value: Any?) -> Double? {
        guard let number = numeric(value), number.isFinite, (0...100).contains(number) else { return nil }
        return number
    }
}

enum GPUCounterParsing {
    /// These registry counters are integral byte counts. Reject booleans,
    /// negatives, fractions, and wrapped values instead of displaying a lie.
    static func bytes(_ value: Any?) -> UInt64? {
        guard let number = value as? NSNumber,
              CFGetTypeID(number) != CFBooleanGetTypeID() else { return nil }
        return UInt64(number.stringValue)
    }
}
