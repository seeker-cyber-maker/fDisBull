import Foundation

let start = Date(timeIntervalSince1970: 1_000)
func at(_ seconds: TimeInterval) -> Date { start.addingTimeInterval(seconds) }
var policy = AlertPolicy(rules: [
    .cpu: .init(threshold: 80, holdDuration: 10, recoveryNotice: true),
    .memoryUsage: .init(threshold: 80, holdDuration: 0),
    .storage: .init(threshold: 90, holdDuration: 0, recoveryNotice: true)
])
precondition(policy.sample(.cpu, value: 80, at: at(0)) == nil)
precondition(policy.sample(.cpu, value: 81, at: at(9)) == nil)
precondition(policy.sample(.cpu, value: nil, at: at(10)) == nil)
precondition(policy.sample(.cpu, value: 90, at: at(11)) == nil)
precondition(policy.sample(.cpu, value: 90, at: at(21)) == .triggered(.cpu))
precondition(policy.sample(.cpu, value: .nan, at: at(22)) == nil)
precondition(policy.sample(.cpu, value: 90, at: at(23)) == nil)
precondition(policy.sample(.cpu, value: 79, at: at(24)) == .recovered(.cpu))
precondition(policy.sample(.cpu, value: 90, at: at(25)) == nil)
precondition(policy.sample(.cpu, value: 90, at: at(320)) == nil)
precondition(policy.sample(.cpu, value: 90, at: at(321)) == .triggered(.cpu))
precondition(policy.sample(.cpu, value: 1, at: at(300)) == nil) // stale sample
precondition(policy.sample(.cpu, value: 1, at: at(322)) == .recovered(.cpu))
precondition(policy.sample(.memoryUsage, value: 80, at: at(1)) == .triggered(.memoryUsage))
precondition(policy.sample(.memoryUsage, value: 79, at: at(2)) == nil) // recovery notice disabled
precondition(policy.sample(.storage, value: 90, at: at(1)) == .triggered(.storage))
precondition(policy.sample(.storage, value: nil, at: at(2)) == nil)
precondition(policy.sample(.storage, value: 89, at: at(3)) == .recovered(.storage))
let readings = AlertReadings(cpuFraction: 0.8, memoryUsed: 8, memoryTotal: 10,
                             storageAvailable: 2, storageTotal: 10)
precondition(readings.cpuPercent == 80 && readings.memoryPercent == 80 && readings.storagePercent == 80)
let unknown = AlertReadings(cpuFraction: .nan, memoryUsed: 11, memoryTotal: 10,
                            storageAvailable: -1, storageTotal: 10)
precondition(unknown.cpuPercent == nil && unknown.memoryPercent == nil && unknown.storagePercent == nil)
print("Alert threshold, hold, cooldown, and recovery checks passed")
