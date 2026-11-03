import Foundation
import Darwin

/// A sampled view of the currently selected non-loopback IPv4 interface.
/// Rates are nil until two valid samples have been collected.
public struct NetworkMetrics: Equatable {
    public let interfaceName: String?
    public let localIPv4: String?
    public let uploadBytesPerSecond: Double?
    public let downloadBytesPerSecond: Double?

    public init(interfaceName: String?, localIPv4: String?, uploadBytesPerSecond: Double?, downloadBytesPerSecond: Double?) {
        self.interfaceName = interfaceName
        self.localIPv4 = localIPv4
        self.uploadBytesPerSecond = uploadBytesPerSecond
        self.downloadBytesPerSecond = downloadBytesPerSecond
    }

    public static let unavailable = NetworkMetrics(interfaceName: nil, localIPv4: nil, uploadBytesPerSecond: nil, downloadBytesPerSecond: nil)
}

/// Computes a byte rate from cumulative interface counters. A decrease is
/// treated as a counter reset, except for a clear UInt64 wrap near the limits.
public enum NetworkRate {
    public static func bytesPerSecond(previous: UInt64, current: UInt64, elapsed: TimeInterval) -> Double? {
        guard elapsed.isFinite, elapsed > 0, let delta = counterDelta(previous: previous, current: current) else { return nil }
        return Double(delta) / elapsed
    }

    public static func counterDelta(previous: UInt64, current: UInt64) -> UInt64? {
        if current >= previous { return current - previous }
        let wrapWindow = UInt64(1) << 32
        guard previous >= UInt64.max - wrapWindow, current < wrapWindow else { return nil }
        return current &- previous
    }
}

/// Samples macOS interface counters through getifaddrs. It performs no network
/// requests and keeps only the previous cumulative counters for rate estimates.
public final class NetworkMetricsSampler {
    private struct Sample {
        let name: String
        let address: String
        let received: UInt64
        let sent: UInt64
        let time: TimeInterval
    }

    private var previous: Sample?
    private let clock: () -> TimeInterval

    public init(clock: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }) {
        self.clock = clock
    }

    public func sample() -> NetworkMetrics {
        guard let current = readInterface() else {
            previous = nil
            return .unavailable
        }

        let rates: (Double?, Double?)
        if let old = previous, old.name == current.name {
            let elapsed = current.time - old.time
            rates = (
                NetworkRate.bytesPerSecond(previous: old.sent, current: current.sent, elapsed: elapsed),
                NetworkRate.bytesPerSecond(previous: old.received, current: current.received, elapsed: elapsed)
            )
        } else {
            rates = (nil, nil)
        }
        previous = current
        return NetworkMetrics(interfaceName: current.name, localIPv4: current.address, uploadBytesPerSecond: rates.0, downloadBytesPerSecond: rates.1)
    }

    private func readInterface() -> Sample? {
        var head: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&head) == 0, let first = head else { return nil }
        defer { freeifaddrs(head) }

        var candidates: [(priority: Int, sample: Sample)] = []
        var cursor: UnsafeMutablePointer<ifaddrs>? = first
        while let node = cursor {
            let item = node.pointee
            cursor = item.ifa_next
            guard let address = item.ifa_addr,
                  address.pointee.sa_family == UInt8(AF_INET),
                  item.ifa_flags & UInt32(IFF_UP) != 0,
                  item.ifa_flags & UInt32(IFF_LOOPBACK) == 0,
                  let data = item.ifa_data?.assumingMemoryBound(to: if_data.self).pointee else { continue }

            let name = String(cString: item.ifa_name)
            let ipv4 = address.withMemoryRebound(to: sockaddr_in.self, capacity: 1) { sockaddr in
                String(cString: inet_ntoa(sockaddr.pointee.sin_addr))
            }
            let priority = interfacePriority(name)
            candidates.append((priority, Sample(name: name, address: ipv4, received: UInt64(data.ifi_ibytes), sent: UInt64(data.ifi_obytes), time: clock())))
        }
        return candidates.sorted { lhs, rhs in
            lhs.priority == rhs.priority ? lhs.sample.name < rhs.sample.name : lhs.priority < rhs.priority
        }.first?.sample
    }

    private func interfacePriority(_ name: String) -> Int {
        // Prefer physical Ethernet/Wi-Fi interfaces over virtual and peer links.
        if name.hasPrefix("en") { return 0 }
        if name.hasPrefix("bridge") { return 1 }
        if name.hasPrefix("utun") || name.hasPrefix("awdl") || name.hasPrefix("llw") || name.hasPrefix("p2p") { return 3 }
        return 2
    }
}
