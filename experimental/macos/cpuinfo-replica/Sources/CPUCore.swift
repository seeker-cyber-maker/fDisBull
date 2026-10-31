import Foundation

struct CPUTicks: Equatable {
    var user: UInt32
    var system: UInt32
    var idle: UInt32
    var nice: UInt32
}

enum UsageDelta {
    // Mach exposes unsigned 32-bit counters. A small modular wrap is valid;
    // a backwards reset giving an implausibly huge delta starts a new baseline.
    static func fraction(previous: CPUTicks?, current: CPUTicks) -> Double? {
        guard let previous else { return nil }
        let parts = [current.user &- previous.user, current.system &- previous.system,
                     current.idle &- previous.idle, current.nice &- previous.nice]
        guard parts.allSatisfy({ $0 <= UInt32.max / 2 }) else { return nil }
        let total = parts.reduce(UInt64(0)) { $0 + UInt64($1) }
        guard total > 0 else { return 0 }
        return Double(UInt64(parts[0]) + UInt64(parts[1]) + UInt64(parts[3])) / Double(total)
    }
}

struct CPUSample: Codable {
    let capturedAt: String
    let overall: Double?
    let cores: [Double?]
    let error: String?
    enum CodingKeys: String, CodingKey { case capturedAt, overall, cores, error }
    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(capturedAt, forKey: .capturedAt)
        try values.encode(overall, forKey: .overall)
        try values.encode(cores, forKey: .cores)
        try values.encode(error, forKey: .error)
    }
}

struct CPUHistory {
    private var host: CPUTicks?
    private var cores: [CPUTicks] = []

    mutating func update(host currentHost: CPUTicks, cores currentCores: [CPUTicks]) -> CPUSample {
        let hostUsage = UsageDelta.fraction(previous: host, current: currentHost)
        // A changed topology invalidates every per-core pairing, not merely the
        // new tail. CPU identity cannot be established by an array index alone.
        let sameTopology = cores.count == currentCores.count
        let values = currentCores.enumerated().map { index, ticks in
            UsageDelta.fraction(previous: sameTopology ? cores[index] : nil, current: ticks)
        }
        host = currentHost
        cores = currentCores
        return CPUSample(capturedAt: ISO8601DateFormatter().string(from: Date()),
                         overall: hostUsage, cores: values, error: nil)
    }
}

enum MeterColor: String, Codable { case green, orange, red, monochrome, unknown }
struct MeterBar: Codable {
    let x: Double
    let y: Double
    let width: Double
    let trackHeight: Double
    let fillHeight: Double?
    let color: MeterColor
}

enum MeterLayout {
    static let height = 24.0
    static let barWidth = 3.0
    static let gap = 2.0
    static let inset = 2.0
    static let trackHeight = 14.0
    static func clamped(_ usage: Double) -> Double { usage.isFinite ? min(1, max(0, usage)) : 0 }
    static func color(_ usage: Double?, monochrome: Bool = false) -> MeterColor {
        guard let usage, usage.isFinite else { return .unknown }
        if monochrome { return .monochrome }
        let u = clamped(usage)
        return u < 0.75 ? .green : u < 0.9 ? .orange : .red
    }
    static func width(coreCount: Int) -> Double {
        guard coreCount > 0 else { return 0 }
        return Double(coreCount) * barWidth + Double(coreCount - 1) * gap + inset * 2
    }
    static func bars(_ values: [Double?], monochrome: Bool = false) -> [MeterBar] {
        values.enumerated().map { index, value in
            MeterBar(x: inset + Double(index) * (barWidth + gap), y: (height - trackHeight) / 2,
                     width: barWidth, trackHeight: trackHeight,
                     fillHeight: value.flatMap { $0.isFinite ? max(barWidth, clamped($0) * trackHeight) : nil },
                     color: color(value, monochrome: monochrome))
        }
    }
}

struct DisplayOptions: Codable {
    var intervalMilliseconds = 500
    var showImage = true
    var showText = false
    var showCoresIndividually = true
    var theme = "Default"
    static let intervals = [100, 200, 500, 1000, 5000, 10000, 30000]
    var widthWithoutCores: Double { (showImage ? 24 : 0) + (showText ? 36 : 0) }
    mutating func setInterval(_ milliseconds: Int) {
        if Self.intervals.contains(milliseconds) { intervalMilliseconds = milliseconds }
    }
}
