import Foundation

func health(_ cpu: Double?, _ gpu: Double? = nil, _ memory: MemoryMood = .unknown,
            _ available: UInt64? = nil, _ total: UInt64? = nil) -> IndicatorHealth.Status {
    IndicatorHealth.evaluate(cpu: cpu, gpu: gpu, memory: memory,
                             storageAvailable: available, storageTotal: total)
}
precondition(health(nil) == .unknown)
precondition(health(.nan) == .unknown)
precondition(health(-0.01) == .unknown)
precondition(health(1.01) == .unknown)
precondition(health(0.5).label == "No issues in measured indicators")
precondition(health(0.899, 0.899, .relaxed, 11, 100) == .normal)
precondition(health(0.9) == .highCPU)
precondition(health(0.5, 0.9) == .highGPU)
precondition(health(0.5, nil, .relaxed, 10, 100) == .lowStorage)
precondition(health(0.5, nil, .relaxed, 0, 0) == .normal)
precondition(health(0.5, nil, .relaxed, 101, 100) == .normal)
precondition(health(nil, nil, .concerned) == .memoryWarning)
precondition(health(nil, nil, .stressed) == .memoryCritical)
precondition(health(nil, 0.9) == .highGPU)
precondition(health(0.95, 0.95, .stressed, 1, 100) == .memoryCritical)
precondition(health(0.5, .infinity) == .normal)
print("Indicator health checks passed")
