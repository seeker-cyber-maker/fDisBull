import Foundation

/// Pure, in-memory threshold policy. Thresholds and hold times are supplied by
/// the caller; they are replica settings, not claims about the original app.
/// Values must use the same units as the configured threshold, with larger
/// values representing more pressure (e.g. percent used, not percent free).
public struct AlertPolicy {
    public enum Metric: Hashable { case cpu, memoryUsage, storage }
    public struct Rule {
        public let threshold: Double
        public let holdDuration: TimeInterval
        public let recoveryNotice: Bool
        public init(threshold: Double, holdDuration: TimeInterval, recoveryNotice: Bool = false) {
            precondition(threshold.isFinite && holdDuration.isFinite && holdDuration >= 0)
            self.threshold = threshold
            self.holdDuration = holdDuration
            self.recoveryNotice = recoveryNotice
        }
    }
    public enum Event: Equatable {
        case triggered(Metric)
        case recovered(Metric)
    }
    private struct State {
        var since: Date?
        var lastSample: Date?
        var lastTrigger: Date?
        var active = false
    }
    private let rules: [Metric: Rule]
    private let cooldown: TimeInterval
    private var states: [Metric: State] = [:]

    /// The default cooldown is five minutes, measured independently per metric.
    public init(rules: [Metric: Rule], cooldown: TimeInterval = 300) {
        precondition(cooldown.isFinite && cooldown >= 0)
        self.rules = rules
        self.cooldown = cooldown
    }

    /// An absent or non-finite sample interrupts a pending hold, but cannot
    /// establish recovery. Out-of-order samples are ignored entirely.
    @discardableResult
    public mutating func sample(_ metric: Metric, value: Double?, at time: Date) -> Event? {
        guard let rule = rules[metric] else { return nil }
        var state = states[metric] ?? State()
        if let last = state.lastSample, time < last { return nil }
        state.lastSample = time
        guard let value = value, value.isFinite else {
            state.since = nil
            states[metric] = state
            return nil
        }
        if value < rule.threshold {
            state.since = nil
            let recovered = state.active
            state.active = false
            states[metric] = state
            return recovered && rule.recoveryNotice ? .recovered(metric) : nil
        }
        if !state.active {
            if state.since == nil { state.since = time }
            let held = time.timeIntervalSince(state.since!) >= rule.holdDuration
            let cooled = state.lastTrigger.map { time.timeIntervalSince($0) >= cooldown } ?? true
            if held && cooled {
                state.active = true
                state.since = nil
                state.lastTrigger = time
                states[metric] = state
                return .triggered(metric)
            }
        }
        states[metric] = state
        return nil
    }
}
