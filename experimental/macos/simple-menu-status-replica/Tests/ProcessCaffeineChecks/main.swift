import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fputs("FAIL: \(message)\n", stderr); exit(1) }
}
let now = Date(timeIntervalSince1970: 1_000)
let indefinite = try CaffeineTiming(now: now, duration: nil)
check(indefinite.deadline == nil && !indefinite.isExpired(at: now.addingTimeInterval(1_000_000)), "indefinite session")
let timed = try CaffeineTiming(now: now, duration: 60)
check(!timed.isExpired(at: now.addingTimeInterval(59.99)), "not expired early")
check(timed.isExpired(at: now.addingTimeInterval(60)), "expires at deadline")
for duration in [0.0, -1.0, Double.infinity, Double.nan] {
    do { _ = try CaffeineTiming(now: now, duration: duration); check(false, "reject invalid duration") }
    catch CaffeineError.invalidDuration { }
}
let controller = CaffeineController()
check(!controller.isActive && controller.mode == nil && controller.deadline == nil, "initial state")
controller.stop()
check(!controller.isActive, "stopping an inactive controller")
let sampler = ProcessSampler()
check(sampler.sample().isEmpty, "first sample establishes baseline")
Thread.sleep(forTimeInterval: 0.1)
let processes = sampler.sample(limit: 10)
check(!processes.isEmpty, "real process samples available")
check(processes.count <= 10 && processes.allSatisfy { $0.pid > 0 && !$0.name.isEmpty && $0.cpuPercent >= 0 }, "process sample fields")
check(zip(processes, processes.dropFirst()).allSatisfy { $0.cpuPercent >= $1.cpuPercent }, "processes sorted by CPU")
print("Process and caffeine checks passed (\(processes.count) real processes).")
let candidates = sampler.candidates()
let ownPID = getpid()
guard let own = candidates.first(where: { $0.identity.pid == ownPID }) else { fatalError("current process must be selectable") }
check(!own.name.isEmpty, "candidate name")
if case .unavailable = sampler.sampleSelected(own.identity) {} else { check(false, "selected baseline is unavailable") }
Thread.sleep(forTimeInterval: 0.1)
if case let .sample(time, cpu) = sampler.sampleSelected(own.identity) {
    check(time > 0 && cpu >= 0 && cpu.isFinite, "selected sample fields")
} else { check(false, "selected process sampled regardless of top list") }
let reused = ProcessIdentity(pid: ownPID, startSeconds: own.identity.startSeconds &+ 1, startMicroseconds: own.identity.startMicroseconds)
if case .exited = sampler.sampleSelected(reused) {} else { check(false, "different lifetime is exited") }
let invalid = ProcessIdentity(pid: 0, startSeconds: 0, startMicroseconds: 0)
if case .unavailable = sampler.sampleSelected(invalid) {} else { check(false, "invalid identity is unknown") }
print("Selected process checks passed.")
