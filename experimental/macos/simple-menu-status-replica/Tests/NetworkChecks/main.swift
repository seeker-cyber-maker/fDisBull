import Foundation

precondition(NetworkRate.bytesPerSecond(previous: 1_000, current: 1_500, elapsed: 2) == 250)
precondition(NetworkRate.bytesPerSecond(previous: 1_000, current: 900, elapsed: 2) == nil) // reset
precondition(NetworkRate.bytesPerSecond(previous: 1, current: 2, elapsed: 0) == nil)
precondition(NetworkRate.counterDelta(previous: UInt64.max - 2, current: 3) == 6) // wrap
precondition(NetworkRate.counterDelta(previous: 8_000, current: 20) == nil) // reset, not wrap
print("Network rate checks passed")
