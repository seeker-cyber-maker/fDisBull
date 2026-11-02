import Foundation
import Darwin
import IOKit.pwr_mgt

public struct ProcessCPU {
    public let pid: Int32
    public let name: String
    /// Percentage of one logical CPU. Multithreaded processes may exceed 100%.
    public let cpuPercent: Double
}

/// Stable identity for a single process lifetime.
public struct ProcessIdentity: Hashable {
    public let pid: Int32
    public let startSeconds: UInt64
    public let startMicroseconds: UInt64
    public init(pid: Int32, startSeconds: UInt64, startMicroseconds: UInt64) {
        self.pid = pid; self.startSeconds = startSeconds; self.startMicroseconds = startMicroseconds
    }
}

public struct ProcessCandidate {
    public let identity: ProcessIdentity
    public let name: String
}

public enum SelectedProcessSample {
    case sample(time: TimeInterval, cpuPercent: Double)
    case unavailable
    case exited
}

/// Samples real process CPU time. Call from one thread at a time. A first
/// sample establishes a baseline; processes without a baseline are omitted.
public final class ProcessSampler {
    private struct Identity: Hashable { let pid: Int32; let seconds: UInt64; let microseconds: UInt64 }
    private struct Reading { let name: String; let cpu: UInt64 }
    private var previous: [Identity: Reading] = [:]
    private var previousTime: TimeInterval?
    private var selectedPrevious: [ProcessIdentity: (time: TimeInterval, cpu: UInt64)] = [:]
    public init() {}

    /// Returns processes whose identity and CPU counter are currently readable.
    /// An empty result may also indicate enumeration failure.
    public func candidates() -> [ProcessCandidate] {
        let needed = proc_listpids(UInt32(PROC_ALL_PIDS), 0, nil, 0)
        guard needed > 0 else { return [] }
        var pids = [pid_t](repeating: 0, count: Int(needed) / MemoryLayout<pid_t>.size + 256)
        let bytes = pids.withUnsafeMutableBytes { proc_listpids(UInt32(PROC_ALL_PIDS), 0, $0.baseAddress, Int32($0.count)) }
        guard bytes > 0 else { return [] }
        return pids.prefix(Int(bytes) / MemoryLayout<pid_t>.size).compactMap { pid in
            guard pid > 0, let identity = readIdentity(pid) else { return nil }
            var task = proc_taskinfo()
            guard proc_pidinfo(pid, PROC_PIDTASKINFO, 0, &task, Int32(MemoryLayout<proc_taskinfo>.size)) == Int32(MemoryLayout<proc_taskinfo>.size),
                  readIdentity(pid) == identity else { return nil }
            var name = [CChar](repeating: 0, count: 1024)
            let display = proc_name(pid, &name, UInt32(name.count)) > 0 ? String(cString: name) : "PID \(pid)"
            return ProcessCandidate(identity: identity, name: display)
        }.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedSame ? $0.identity.pid < $1.identity.pid : $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    /// Samples one exact lifetime, independently of the top-process baseline.
    /// A baseline or temporary failure returns unavailable; ESRCH or a verified
    /// different lifetime at the same PID returns exited.
    public func sampleSelected(_ identity: ProcessIdentity) -> SelectedProcessSample {
        guard let observed = readIdentity(identity.pid) else {
            selectedPrevious.removeValue(forKey: identity)
            errno = 0
            if kill(identity.pid, 0) == -1 && errno == ESRCH { return .exited }
            return .unavailable
        }
        guard observed == identity else { selectedPrevious.removeValue(forKey: identity); return .exited }
        var task = proc_taskinfo()
        guard proc_pidinfo(identity.pid, PROC_PIDTASKINFO, 0, &task, Int32(MemoryLayout<proc_taskinfo>.size)) == Int32(MemoryLayout<proc_taskinfo>.size) else {
            selectedPrevious.removeValue(forKey: identity); return .unavailable
        }
        guard let after = readIdentity(identity.pid) else { selectedPrevious.removeValue(forKey: identity); return .unavailable }
        guard after == identity else { selectedPrevious.removeValue(forKey: identity); return .exited }
        let now = ProcessInfo.processInfo.systemUptime
        let cpu = task.pti_total_user &+ task.pti_total_system
        let old = selectedPrevious.updateValue((now, cpu), forKey: identity)
        guard let old, now > old.time, cpu >= old.cpu else { return .unavailable }
        return .sample(time: now, cpuPercent: Double(cpu - old.cpu) / 1_000_000_000 / (now - old.time) * 100)
    }

    private func readIdentity(_ pid: Int32) -> ProcessIdentity? {
        guard pid > 0 else { return nil }
        var info = proc_bsdinfo()
        guard proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &info, Int32(MemoryLayout<proc_bsdinfo>.size)) == Int32(MemoryLayout<proc_bsdinfo>.size) else { return nil }
        return ProcessIdentity(pid: pid, startSeconds: info.pbi_start_tvsec, startMicroseconds: info.pbi_start_tvusec)
    }

    public func sample(limit: Int = 10) -> [ProcessCPU] {
        let now = ProcessInfo.processInfo.systemUptime
        let needed = proc_listpids(UInt32(PROC_ALL_PIDS), 0, nil, 0)
        guard needed > 0 else { return [] }
        // Leave room for processes created between the size and data calls.
        var pids = [pid_t](repeating: 0, count: Int(needed) / MemoryLayout<pid_t>.size + 256)
        let bytes = pids.withUnsafeMutableBytes { proc_listpids(UInt32(PROC_ALL_PIDS), 0, $0.baseAddress, Int32($0.count)) }
        guard bytes > 0 else { return [] }
        var current: [Identity: Reading] = [:]
        for pid in pids.prefix(Int(bytes) / MemoryLayout<pid_t>.size) where pid > 0 {
            var info = proc_bsdinfo()
            let infoSize = Int32(MemoryLayout<proc_bsdinfo>.size)
            guard proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &info, infoSize) == infoSize else { continue }
            var task = proc_taskinfo()
            let taskSize = Int32(MemoryLayout<proc_taskinfo>.size)
            guard proc_pidinfo(pid, PROC_PIDTASKINFO, 0, &task, taskSize) == taskSize else { continue }
            var buffer = [CChar](repeating: 0, count: 1024)
            let name: String
            if proc_name(pid, &buffer, UInt32(buffer.count)) > 0 {
                name = String(cString: buffer)
            } else { name = "PID \(pid)" }
            let identity = Identity(pid: pid, seconds: info.pbi_start_tvsec, microseconds: info.pbi_start_tvusec)
            current[identity] = Reading(name: name, cpu: task.pti_total_user &+ task.pti_total_system)
        }
        defer { previous = current; previousTime = now }
        guard let earlier = previousTime, now > earlier else { return [] }
        let elapsed = now - earlier
        return current.compactMap { identity, reading -> ProcessCPU? in
            guard let old = previous[identity], reading.cpu >= old.cpu else { return nil }
            let percent = Double(reading.cpu - old.cpu) / 1_000_000_000 / elapsed * 100
            return ProcessCPU(pid: identity.pid, name: reading.name, cpuPercent: percent)
        }.sorted { $0.cpuPercent == $1.cpuPercent ? $0.pid < $1.pid : $0.cpuPercent > $1.cpuPercent }
            .prefix(max(0, limit)).map { $0 }
    }
}

/// Pure timing state, separated from IOKit so expiry can be checked safely.
public struct CaffeineTiming {
    public let deadline: Date?
    public init(now: Date, duration: TimeInterval?) throws {
        if let duration {
            guard duration.isFinite, duration > 0 else { throw CaffeineError.invalidDuration }
            deadline = now.addingTimeInterval(duration)
        } else { deadline = nil }
    }
    public func isExpired(at now: Date) -> Bool { deadline.map { now >= $0 } ?? false }
}

public enum CaffeineError: Error {
    case invalidDuration
    case assertionFailed(Int32)
}

/// Owns its IOKit assertions and releases them on stop, expiry, or deinit.
/// Use on the main thread; expiry callbacks are delivered on the main queue.
public final class CaffeineController {
    public enum Mode { case systemOnly, systemAndDisplay }
    public private(set) var mode: Mode?
    public private(set) var deadline: Date?
    public var isActive: Bool { !assertions.isEmpty }
    private var assertions: [IOPMAssertionID] = []
    private var timer: DispatchSourceTimer?
    public init() {}

    public func start(mode: Mode, duration: TimeInterval? = nil) throws {
        let timing = try CaffeineTiming(now: Date(), duration: duration)
        // Acquire the new assertions first so a failed replacement preserves
        // the existing session. Release partial acquisitions on failure.
        var acquired: [IOPMAssertionID] = []
        let types = mode == .systemOnly ? [kIOPMAssertionTypePreventUserIdleSystemSleep] : [kIOPMAssertionTypePreventUserIdleSystemSleep, kIOPMAssertionTypePreventUserIdleDisplaySleep]
        for type in types {
            var id = IOPMAssertionID(0)
            let result = IOPMAssertionCreateWithName(type as CFString, IOPMAssertionLevel(kIOPMAssertionLevelOn), "Simple Menu Status Replica" as CFString, &id)
            guard result == kIOReturnSuccess else {
                acquired.forEach { IOPMAssertionRelease($0) }
                throw CaffeineError.assertionFailed(result)
            }
            acquired.append(id)
        }
        stop()
        assertions = acquired
        self.mode = mode
        deadline = timing.deadline
        if let duration {
            let source = DispatchSource.makeTimerSource(queue: .main)
            source.schedule(deadline: .now() + duration)
            source.setEventHandler { [weak self] in self?.stop() }
            timer = source
            source.resume()
        }
    }
    public func stop() {
        timer?.cancel(); timer = nil
        assertions.forEach { IOPMAssertionRelease($0) }
        assertions.removeAll()
        mode = nil; deadline = nil
    }
    deinit { stop() }
}
