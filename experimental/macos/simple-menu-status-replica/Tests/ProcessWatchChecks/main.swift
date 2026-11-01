import Foundation

func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    guard condition() else { fatalError(message) }
}
let id = WatchedProcessIdentity(pid: 42, startSeconds: 100, startMicroseconds: 5)
func sample(_ watch: inout ProcessWatch, _ time: Double, _ cpu: Double) -> ProcessWatchState {
    watch.observe(.sample(identity: id, time: time, cpuPercent: cpu))
}
var watch = try ProcessWatch(identity: id, threshold: 10)
expect(sample(&watch, 0, 20) == .watching(averageCPU: 20, lowChecks: 0), "initial")
expect(sample(&watch, 30, 0) == .watching(averageCPU: 10, lowChecks: 0), "threshold equality")
expect(sample(&watch, 61, 2) == .watching(averageCPU: 1, lowChecks: 1), "rolling window")
expect(sample(&watch, 62, 2) == .watching(averageCPU: 4.0 / 3.0, lowChecks: 2), "low streak")
expect(sample(&watch, 63, 100) == .watching(averageCPU: 26, lowChecks: 0), "recovery")
watch = try ProcessWatch(identity: id, threshold: 10)
for i in 0..<4 { expect(sample(&watch, Double(i), 0) == .watching(averageCPU: 0, lowChecks: i + 1), "low check") }
expect(sample(&watch, 4, 0) == .stopped(.lowActivity), "fifth check")
expect(watch.observe(.unavailable) == .stopped(.lowActivity), "stop is terminal")
watch = try ProcessWatch(identity: id, threshold: 10)
_ = sample(&watch, 0, 0)
expect(watch.observe(.unavailable) == .watching(averageCPU: nil, lowChecks: 0), "missing is unknown")
expect(sample(&watch, 1, 0) == .watching(averageCPU: 0, lowChecks: 1), "unknown breaks streak")
expect(sample(&watch, 1, 0) == .watching(averageCPU: nil, lowChecks: 0), "invalid time is unknown")
_ = sample(&watch, 2, 0)
try watch.setThreshold(20)
expect(watch.state == .watching(averageCPU: 0, lowChecks: 0), "threshold resets streak")
let replacement = WatchedProcessIdentity(pid: 42, startSeconds: 101, startMicroseconds: 0)
expect(watch.observe(.sample(identity: replacement, time: 3, cpuPercent: 5)) == .stopped(.processExited), "PID reuse")
watch = try ProcessWatch(identity: id, threshold: 10)
expect(watch.observe(.exited) == .stopped(.processExited), "selected exit")
print("Process watch checks passed")
