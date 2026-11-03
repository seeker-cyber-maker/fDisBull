import Foundation
import Darwin

final class MachSampler {
    private var history = CPUHistory()
    private var selectedHistory: SelectedCPUHistory?

    private enum ReadFailure: Error {
        case message(String)
        var message: String {
            switch self { case .message(let message): return message }
        }
    }

    // cpuinfo constructs its core slots as zero readings before the first
    // timer update. The initial count probe deliberately discards the ticks.
    func initialSample() -> CPUSample {
        if let selectedHistory { return selectedHistory.snapshot() }
        switch readCores() {
        case .success(let cores):
            let initial = SelectedCPUHistory(coreCount: cores.count)
            selectedHistory = initial
            return initial.snapshot()
        case .failure(let failure):
            let initial = SelectedCPUHistory(coreCount: 0)
            selectedHistory = initial
            return initial.snapshot(error: failure.message)
        }
    }

    func sample(mode: SamplingMode) -> CPUSample {
        if selectedHistory == nil { _ = initialSample() }
        switch mode {
        case .cores:
            switch readCores() {
            case .success(let cores): return selectedHistory!.update(cores: cores)
            case .failure(let failure): return selectedHistory!.snapshot(error: failure.message)
            }
        case .host:
            switch readHost() {
            case .success(let host): return selectedHistory!.update(host: host)
            case .failure(let failure): return selectedHistory!.snapshot(error: failure.message)
            }
        }
    }

    // Read-only diagnostics retain their independent unknown-first-baseline
    // behavior. Calling them never advances the menu app's selected history.
    func sample() -> CPUSample {
        switch readCores() {
        case .failure(let failure): return diagnosticFailure(failure)
        case .success(let cores):
            switch readHost() {
            case .failure(let failure): return diagnosticFailure(failure)
            case .success(let host): return history.update(host: host, cores: cores)
            }
        }
    }

    private func diagnosticFailure(_ failure: ReadFailure) -> CPUSample {
        CPUSample(capturedAt: ISO8601DateFormatter().string(from: Date()),
                  overall: nil, cores: [], error: failure.message)
    }

    private func readCores() -> Result<[CPUTicks], ReadFailure> {
        var cpuCount: natural_t = 0
        var information: processor_info_array_t?
        var count: mach_msg_type_number_t = 0
        let result = host_processor_info(mach_host_self(), PROCESSOR_CPU_LOAD_INFO,
                                         &cpuCount, &information, &count)
        defer {
            if let information, count > 0 {
                vm_deallocate(mach_task_self_, vm_address_t(bitPattern: information),
                              vm_size_t(Int(count) * MemoryLayout<integer_t>.stride))
            }
        }
        guard result == KERN_SUCCESS, let information else {
            return .failure(.message("host_processor_info: \(result)"))
        }
        let stride = Int(CPU_STATE_MAX)
        guard cpuCount > 0, cpuCount <= 1024, Int(count) >= Int(cpuCount) * stride else {
            return .failure(.message("inconsistent processor count"))
        }
        var cores: [CPUTicks] = []
        for index in 0..<Int(cpuCount) {
            let base = index * stride
            cores.append(CPUTicks(user: UInt32(bitPattern: information[base + Int(CPU_STATE_USER)]),
                                  system: UInt32(bitPattern: information[base + Int(CPU_STATE_SYSTEM)]),
                                  idle: UInt32(bitPattern: information[base + Int(CPU_STATE_IDLE)]),
                                  nice: UInt32(bitPattern: information[base + Int(CPU_STATE_NICE)])))
        }
        return .success(cores)
    }

    private func readHost() -> Result<CPUTicks, ReadFailure> {
        let capacity = mach_msg_type_number_t(MemoryLayout<host_cpu_load_info_data_t>.stride / MemoryLayout<integer_t>.stride)
        var size = capacity
        var host = host_cpu_load_info_data_t()
        let result = withUnsafeMutablePointer(to: &host) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(capacity)) {
                host_statistics(mach_host_self(), HOST_CPU_LOAD_INFO, $0, &size)
            }
        }
        guard result == KERN_SUCCESS else {
            return .failure(.message("host_statistics: \(result)"))
        }
        guard size == capacity else { return .failure(.message("inconsistent host counter count")) }
        let t = host.cpu_ticks
        return .success(CPUTicks(user: t.0, system: t.1, idle: t.2, nice: t.3))
    }
}
