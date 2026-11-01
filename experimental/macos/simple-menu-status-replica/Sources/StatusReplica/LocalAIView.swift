import Foundation
import SwiftUI
import StatusCore

/// A host-wide system-stats view for local inference work. GPU memory is
/// unified system memory reported by the graphics driver, not model memory.
struct LocalAIView: View {
    @AppStorage("language", store: ReplicaPreferences.defaults) private var languageChoice = "System Default"
    let gpu: GPUSnapshot?
    let details: SystemDetails?
    let eCoreHistory: [Double]
    let pCoreHistory: [Double]
    let gpuHistory: [Double]
    private func tr(_ english: String) -> String { ReplicaLocalization.text(english, choice: languageChoice) }

    var body: some View {
        VStack(spacing: 0) {
            statsSection("cpu", "CPU & Thermal") {
                HStack(spacing: 12) {
                    clusterValue("E-cores", details?.eCorePercentage, color: .cyan)
                    clusterValue("P-cores", details?.pCorePercentage, color: .green)
                }
                if eCoreHistory.count > 1 || pCoreHistory.count > 1 {
                    ZStack {
                        HistoryTrace(samples: eCoreHistory, color: .cyan)
                        HistoryTrace(samples: pCoreHistory, color: .green)
                    }.frame(height: 19)
                }
                valueRow("Thermal", thermalLabel(details?.thermalState))
                valueRow("Load avg", loadLabel(details?.loadAverages))
                valueRow("Uptime", uptimeLabel(details?.uptimeSeconds))
            }

            statsSection("square.stack.3d.up", "GPU & Shared Memory") {
                valueRow("Device", gpu?.name ?? "Unavailable")
                HStack {
                    Text("Utilization")
                    Spacer()
                    Text(percent(gpu?.utilizationPercent)).fontWeight(.semibold).monospacedDigit()
                    ProgressView(value: fraction(gpu?.utilizationPercent)).tint(.green).frame(width: 58)
                }
                if gpuHistory.count > 1 {
                    HistoryTrace(samples: gpuHistory, color: .green).frame(height: 19)
                }
                HStack {
                    Text("GPU memory")
                    Spacer()
                    Text(gpu?.inUseSystemMemoryBytes.map { "\(byteLabel($0)) \(tr("in use"))" } ?? tr("Unavailable"))
                        .fontWeight(.semibold).monospacedDigit()
                }
                if let inUse = gpu?.inUseSystemMemoryBytes,
                   let physical = details?.memory.physicalBytes, physical > 0 {
                    ProgressView(value: min(1, Double(inUse) / Double(physical)))
                        .tint(.cyan)
                }
                if let allocated = gpu?.allocatedSystemMemoryBytes {
                    valueRow("Allocated by GPU", byteLabel(allocated))
                }
                Text("GPU memory shares system RAM; these are host counters, not per-model usage.")
                    .font(.system(size: 10)).foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            statsSection("memorychip", "Unified Memory") {
                let memory = details?.memory
                let usage = memory.flatMap(usedAndFree)
                HStack {
                    Text("Used / total")
                    Spacer()
                    Text(memory.map { "\(byteLabel(usage?.used)) / \(byteLabel($0.physicalBytes))" } ?? tr("Unavailable"))
                        .fontWeight(.semibold).monospacedDigit()
                }
                if let memory, !segments(for: memory).isEmpty {
                    segmentedBar(segments(for: memory))
                }
                memoryRow("Wired", memory?.wiredBytes, color: .orange)
                memoryRow("Active", memory?.activeBytes, color: .green)
                memoryRow("Compressed", memory?.compressedBytes, color: .purple)
                memoryRow("Free / reclaimable", usage?.free, color: .gray)
            }
        }
    }

    private func statsSection<Content: View>(_ symbol: String, _ title: String,
                                             @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Label { Text(LocalizedStringKey(title)) } icon: { Image(systemName: symbol) }
                .font(.system(size: 12, weight: .semibold))
            content()
        }
        .font(.system(size: 11))
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .overlay(alignment: .bottom) { Divider() }
    }

    private func clusterValue(_ name: String, _ value: Double?, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 4) {
                Circle().fill(color).frame(width: 5, height: 5)
                Text(LocalizedStringKey(name))
            }.foregroundColor(.secondary)
            Text(percent(value)).font(.system(size: 13, weight: .semibold)).monospacedDigit()
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private func valueRow(_ name: String, _ value: String) -> some View {
        HStack {
            Text(LocalizedStringKey(name)).foregroundColor(.secondary)
            Spacer(minLength: 5)
            Text(tr(value)).fontWeight(.medium).monospacedDigit().lineLimit(1)
        }
    }

    private func memoryRow(_ name: String, _ value: UInt64?, color: Color) -> some View {
        HStack {
            RoundedRectangle(cornerRadius: 2).fill(color).frame(width: 7, height: 7)
            Text(LocalizedStringKey(name))
            Spacer()
            Text(byteLabel(value)).fontWeight(.medium).monospacedDigit()
        }
    }

    private struct Segment {
        let bytes: UInt64
        let color: Color
    }

    private func segments(for memory: MemoryDetails) -> [Segment] {
        let remaining = usedAndFree(memory)?.free
        return [(memory.wiredBytes, Color.orange), (memory.activeBytes, .green),
         (memory.compressedBytes, .purple), (remaining, .gray)]
            .compactMap { bytes, color in bytes.map { Segment(bytes: $0, color: color) } }
            .filter { $0.bytes > 0 }
    }

    /// Matches oMLX's host view: wired + active + compressed pages are in use;
    /// the remaining physical RAM is free or reclaimable. This is separate
    /// from the raw Mach free-page counter.
    private func usedAndFree(_ memory: MemoryDetails) -> (used: UInt64, free: UInt64)? {
        guard let wired = memory.wiredBytes, let active = memory.activeBytes,
              let compressed = memory.compressedBytes else { return nil }
        let sum = [wired, active, compressed].reduce(UInt64(0)) { partial, value in
            let (next, overflow) = partial.addingReportingOverflow(value)
            return overflow ? UInt64.max : next
        }
        let used = min(memory.physicalBytes, sum)
        return (used, memory.physicalBytes - used)
    }

    private func segmentedBar(_ parts: [Segment]) -> some View {
        let total = parts.reduce(UInt64(0)) { $0 &+ $1.bytes }
        return GeometryReader { geometry in
            HStack(spacing: 0) {
                ForEach(parts.indices, id: \.self) { index in
                    parts[index].color.frame(width: geometry.size.width * CGFloat(Double(parts[index].bytes) / Double(total)))
                }
            }
        }
        .frame(height: 6)
        .clipShape(Capsule())
        .help("Relative shares of raw wired, active, compressed, and free memory page counts")
    }

    private func percent(_ value: Double?) -> String {
        guard let value, value.isFinite, (0...100).contains(value) else { return tr("Unavailable") }
        return String(format: "%.1f%%", value)
    }

    private func fraction(_ value: Double?) -> Double {
        guard let value, value.isFinite else { return 0 }
        return min(1, max(0, value / 100))
    }

    private func byteLabel(_ value: UInt64?) -> String {
        guard let value else { return tr("Unavailable") }
        if value < 1_073_741_824 { return String(format: "%.0f MB", Double(value) / 1_048_576) }
        return String(format: "%.2f GB", Double(value) / 1_073_741_824)
    }

    private func thermalLabel(_ state: ProcessInfo.ThermalState?) -> String {
        guard let state else { return tr("Unavailable") }
        switch state {
        case .nominal: return "Nominal"
        case .fair: return "Fair"
        case .serious: return "Serious"
        case .critical: return "Critical"
        @unknown default: return "Unknown"
        }
    }

    private func loadLabel(_ values: [Double]?) -> String {
        guard let values, values.count == 3, values.allSatisfy({ $0.isFinite && $0 >= 0 }) else { return tr("Unavailable") }
        return values.map { String(format: "%.2f", $0) }.joined(separator: " · ")
    }

    private func uptimeLabel(_ seconds: TimeInterval?) -> String {
        guard let seconds, seconds.isFinite, seconds >= 0 else { return tr("Unavailable") }
        let minutes = Int(seconds / 60)
        if ReplicaLocalization.languageCode(languageChoice) == "ja" {
            if minutes >= 1440 { return "\(minutes / 1440)日 \((minutes % 1440) / 60)時間" }
            if minutes >= 60 { return "\(minutes / 60)時間 \(minutes % 60)分" }
            return "\(minutes)分"
        }
        if minutes >= 1440 { return "\(minutes / 1440)d \((minutes % 1440) / 60)h" }
        if minutes >= 60 { return "\(minutes / 60)h \(minutes % 60)m" }
        return "\(minutes)m"
    }
}

private struct HistoryTrace: View {
    let samples: [Double]
    let color: Color

    var body: some View {
        GeometryReader { geometry in
            if samples.count > 1 {
                Path { path in
                    for (index, sample) in samples.enumerated() {
                        let point = CGPoint(
                            x: geometry.size.width * CGFloat(index) / CGFloat(samples.count - 1),
                            y: geometry.size.height * (1 - CGFloat(min(1, max(0, sample))))
                        )
                        if index == 0 { path.move(to: point) }
                        else { path.addLine(to: point) }
                    }
                }.stroke(color, lineWidth: 1)
            }
        }
    }
}
