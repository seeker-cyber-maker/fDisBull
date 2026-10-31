import Foundation
import Darwin

final class MachSampler {
    private var history = CPUHistory()
    func sample() -> CPUSample {
        var cpuCount: natural_t = 0
        var information: processor_info_array_t?
        var count: mach_msg_type_number_t = 0
        let coreResult = host_processor_info(mach_host_self(), PROCESSOR_CPU_LOAD_INFO,
                                             &cpuCount, &information, &count)
        guard coreResult == KERN_SUCCESS, let information else {
            return CPUSample(capturedAt: ISO8601DateFormatter().string(from: Date()),
                             overall: nil, cores: [], error: "host_processor_info: \(coreResult)")
        }
        defer {
            vm_deallocate(mach_task_self_, vm_address_t(bitPattern: information),
                          vm_size_t(Int(count) * MemoryLayout<integer_t>.stride))
        }
        let stride = Int(CPU_STATE_MAX)
        guard cpuCount > 0, cpuCount <= 1024, Int(count) >= Int(cpuCount) * stride else {
            return CPUSample(capturedAt: ISO8601DateFormatter().string(from: Date()),
                             overall: nil, cores: [], error: "inconsistent processor count")
        }
        var cores: [CPUTicks] = []
        for index in 0..<Int(cpuCount) {
            let base = index * stride
            cores.append(CPUTicks(user: UInt32(bitPattern: information[base + Int(CPU_STATE_USER)]),
                                  system: UInt32(bitPattern: information[base + Int(CPU_STATE_SYSTEM)]),
                                  idle: UInt32(bitPattern: information[base + Int(CPU_STATE_IDLE)]),
                                  nice: UInt32(bitPattern: information[base + Int(CPU_STATE_NICE)])))
        }
        var size = mach_msg_type_number_t(MemoryLayout<host_cpu_load_info_data_t>.stride / MemoryLayout<integer_t>.stride)
        var host = host_cpu_load_info_data_t()
        let hostResult = withUnsafeMutablePointer(to: &host) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(size)) {
                host_statistics(mach_host_self(), HOST_CPU_LOAD_INFO, $0, &size)
            }
        }
        guard hostResult == KERN_SUCCESS else {
            return CPUSample(capturedAt: ISO8601DateFormatter().string(from: Date()),
                             overall: nil, cores: [], error: "host_statistics: \(hostResult)")
        }
        let t = host.cpu_ticks
        return history.update(host: CPUTicks(user: t.0, system: t.1, idle: t.2, nice: t.3), cores: cores)
    }
}
