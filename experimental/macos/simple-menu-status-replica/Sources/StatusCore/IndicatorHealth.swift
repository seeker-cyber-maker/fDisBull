import Foundation

/// A summary of the available measurements, not a diagnosis of overall system health.
/// Thresholds are replica design choices, not claims about the original app.
public enum IndicatorHealth {
    public static let highCPU = 0.90
    public static let highGPU = 0.90
    public static let lowStorageFraction = 0.10

    public enum Status: Equatable {
        case unknown
        case normal
        case memoryCritical
        case memoryWarning
        case highCPU
        case highGPU
        case lowStorage

        public var label: String {
            switch self {
            case .unknown: return "Waiting for CPU sample"
            case .normal: return "No issues in measured indicators"
            case .memoryCritical: return "Critical memory pressure"
            case .memoryWarning: return "Elevated memory pressure"
            case .highCPU: return "High CPU usage"
            case .highGPU: return "High GPU usage"
            case .lowStorage: return "Low available storage"
            }
        }
    }

    /// CPU and GPU are fractions from zero through one. Invalid samples are
    /// unknown. Storage is considered only when both values form a valid pair.
    /// A warning can be shown before the first CPU sample; a normal result
    /// requires a valid CPU sample and describes only measured indicators.
    public static func evaluate(cpu: Double?, gpu: Double?, memory: MemoryMood,
                                storageAvailable: UInt64?, storageTotal: UInt64?) -> Status {
        func valid(_ sample: Double?) -> Double? {
            guard let value = sample, value.isFinite, (0...1).contains(value) else { return nil }
            return value
        }
        let cpu = valid(cpu)
        let gpu = valid(gpu)
        if memory == .stressed { return .memoryCritical }
        if memory == .concerned { return .memoryWarning }
        if let cpu = cpu, cpu >= highCPU { return .highCPU }
        if let gpu = gpu, gpu >= highGPU { return .highGPU }
        if let available = storageAvailable, let total = storageTotal,
           total > 0, available <= total,
           Double(available) / Double(total) <= lowStorageFraction { return .lowStorage }
        return cpu == nil ? .unknown : .normal
    }
}
