import Foundation

/// Thresholds are replica design choices, not claims about the original app.
public enum MemoryMood: Equatable {
    case relaxed, concerned, stressed, unknown
    public static func from(pressure: Pressure?) -> Self {
        switch pressure { case .normal: return .relaxed; case .warning: return .concerned; case .critical: return .stressed; case nil: return .unknown }
    }
    public enum Pressure { case normal, warning, critical }
    /// Startup estimate until the system delivers a pressure event. Cached and
    /// inactive pages are reclaimable and therefore are not treated as used.
    public static func estimated(total: UInt64, free: UInt64, inactive: UInt64, purgeable: UInt64) -> Self {
        guard total > 0 else { return .unknown }
        let available = min(total, free &+ min(inactive, total) &+ min(purgeable, total))
        let fraction = Double(available) / Double(total)
        if fraction >= 0.30 { return .relaxed }
        if fraction >= 0.15 { return .concerned }
        return .stressed
    }
    public var emoji: String {
        switch self { case .relaxed: return "😊"; case .concerned: return "😐"; case .stressed: return "😰"; case .unknown: return "❔" }
    }
}
