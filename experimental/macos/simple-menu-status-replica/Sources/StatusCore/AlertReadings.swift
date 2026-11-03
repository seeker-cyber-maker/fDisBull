import Foundation

/// Valid percentages for the three locally measured alert sources. Unknown or
/// inconsistent readings remain nil and interrupt a pending alert hold.
public struct AlertReadings {
    public let cpuPercent: Double?
    public let memoryPercent: Double?
    public let storagePercent: Double?

    public init(cpuFraction: Double?, memoryUsed: UInt64?, memoryTotal: UInt64,
                storageAvailable: Int64?, storageTotal: Int64?) {
        if let cpuFraction, cpuFraction.isFinite, (0...1).contains(cpuFraction) {
            cpuPercent = cpuFraction * 100
        } else {
            cpuPercent = nil
        }
        if let memoryUsed, memoryTotal > 0, memoryUsed <= memoryTotal {
            memoryPercent = Double(memoryUsed) / Double(memoryTotal) * 100
        } else {
            memoryPercent = nil
        }
        if let storageAvailable, let storageTotal, storageTotal > 0,
           storageAvailable >= 0, storageAvailable <= storageTotal {
            storagePercent = (1 - Double(storageAvailable) / Double(storageTotal)) * 100
        } else {
            storagePercent = nil
        }
    }
}
