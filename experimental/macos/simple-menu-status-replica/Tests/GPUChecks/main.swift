import Foundation

precondition(GPUCounterParsing.bytes(NSNumber(value: 42)) == 42)
precondition(GPUCounterParsing.bytes(NSNumber(value: UInt64.max)) == UInt64.max)
precondition(GPUCounterParsing.bytes(NSNumber(value: true)) == nil)
precondition(GPUCounterParsing.bytes(NSNumber(value: -1)) == nil)
precondition(GPUCounterParsing.bytes(NSNumber(value: 1.5)) == nil)
precondition(GPUCounterParsing.bytes(nil) == nil)

let sample = GPUMetrics.sample()
print("GPU: \(sample.name ?? "unavailable")")
for (label, value) in [("Device", sample.utilizationPercent), ("Renderer", sample.rendererUtilizationPercent), ("Tiler", sample.tilerUtilizationPercent)] {
    if let value = value {
        precondition(value.isFinite && (0...100).contains(value))
        print("\(label) utilization: \(value)%")
    } else {
        print("\(label) utilization: unavailable")
    }
}
if let cores = sample.coreCount {
    precondition(cores > 0)
    print("GPU cores: \(cores)")
} else {
    print("GPU cores: unavailable")
}
for (label, value) in [("In use system memory", sample.inUseSystemMemoryBytes),
                       ("Allocated system memory", sample.allocatedSystemMemoryBytes),
                       ("Driver system memory", sample.driverInUseSystemMemoryBytes),
                       ("Recommended working set", sample.recommendedMaxWorkingSetBytes)] {
    print("\(label): \(value.map(String.init) ?? "unavailable") bytes")
}
