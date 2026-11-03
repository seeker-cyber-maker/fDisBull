import Foundation

/// Identifies one process lifetime, not just a reusable PID.
public struct WatchedProcessIdentity: Equatable {
    public let pid: Int32
    public let startSeconds: UInt64
    public let startMicroseconds: UInt64
    public init(pid: Int32, startSeconds: UInt64, startMicroseconds: UInt64) {
        self.pid = pid
        self.startSeconds = startSeconds
        self.startMicroseconds = startMicroseconds
    }
}

public enum ProcessWatchObservation {
    /// CPU percent of one logical CPU, sampled at a monotonic time in seconds.
    case sample(identity: WatchedProcessIdentity, time: TimeInterval, cpuPercent: Double)
    /// The selected process was definitively observed to have exited.
    case exited
    /// No reliable conclusion about the process or its CPU can be made.
    case unavailable
}

public enum ProcessWatchState: Equatable {
    case watching(averageCPU: Double?, lowChecks: Int)
    case stopped(ProcessWatchStopReason)
}

public enum ProcessWatchStopReason: Equatable {
    case lowActivity
    case processExited
}

public enum ProcessWatchError: Error { case invalidThreshold }

/// Caller supplies observations and decides when to sample. This type does not
/// inspect processes, manage sleep assertions, or take action on the process.
/// The average is the arithmetic mean of valid readings in the last 60 seconds;
/// it is available immediately and is not a time-weighted CPU measurement.
public struct ProcessWatch {
    public let identity: WatchedProcessIdentity
    public private(set) var threshold: Double
    public private(set) var state: ProcessWatchState = .watching(averageCPU: nil, lowChecks: 0)
    private var readings: [(time: TimeInterval, cpu: Double)] = []
    private var lastTime: TimeInterval?

    public init(identity: WatchedProcessIdentity, threshold: Double) throws {
        guard threshold.isFinite, threshold >= 0 else { throw ProcessWatchError.invalidThreshold }
        self.identity = identity
        self.threshold = threshold
    }

    /// Changing the threshold starts a fresh sequence of low checks.
    public mutating func setThreshold(_ value: Double) throws {
        guard value.isFinite, value >= 0 else { throw ProcessWatchError.invalidThreshold }
        threshold = value
        if case let .watching(average, _) = state {
            state = .watching(averageCPU: average, lowChecks: 0)
        }
    }

    @discardableResult
    public mutating func observe(_ observation: ProcessWatchObservation) -> ProcessWatchState {
        guard case let .watching(_, previousLow) = state else { return state }
        switch observation {
        case .exited:
            state = .stopped(.processExited)
        case .unavailable:
            clearUncertainHistory()
        case let .sample(observed, time, cpu):
            guard observed == identity else {
                if observed.pid == identity.pid { state = .stopped(.processExited) }
                else { clearUncertainHistory() }
                return state
            }
            guard time.isFinite, cpu.isFinite, cpu >= 0,
                  lastTime.map({ time > $0 }) ?? true else {
                clearUncertainHistory()
                return state
            }
            lastTime = time
            readings.removeAll { $0.time < time - 60 }
            readings.append((time, cpu))
            let average = readings.reduce(0.0) { $0 + $1.cpu } / Double(readings.count)
            let low = average < threshold ? previousLow + 1 : 0
            state = low >= 5 ? .stopped(.lowActivity) : .watching(averageCPU: average, lowChecks: low)
        }
        return state
    }

    private mutating func clearUncertainHistory() {
        readings.removeAll()
        lastTime = nil
        state = .watching(averageCPU: nil, lowChecks: 0)
    }
}
