import Foundation
@main struct SamplingTests {
 static func main() {
  let sampler = MachSampler()
  let first = sampler.initialSample()
  precondition(first.error == nil && first.overall == 0 && !first.cores.isEmpty && first.cores.allSatisfy { $0 == 0 })
  let cores = sampler.sample(mode: .cores)
  precondition(cores.error == nil && cores.overall == 0 && cores.cores.count == first.cores.count)
  precondition(cores.cores.allSatisfy { $0 != nil && (0...1).contains($0!) })
  let host = sampler.sample(mode: .host)
  precondition(host.error == nil && host.overall != nil && (0...1).contains(host.overall!))
  precondition(host.cores == cores.cores)
  let diagnostic = sampler.sample()
  precondition(diagnostic.overall == nil && diagnostic.cores.allSatisfy { $0 == nil })
  let retained = sampler.initialSample()
  precondition(retained.overall == host.overall && retained.cores == host.cores)
  Thread.sleep(forTimeInterval: 0.11)
  let diagnosticNext = sampler.sample()
  precondition(diagnosticNext.overall != nil && diagnosticNext.cores.allSatisfy { $0 != nil })
  let restart = MachSampler().initialSample()
  precondition(restart.overall == 0 && restart.cores == first.cores)
  print("9 native selected/diagnostic sampling checks passed; no GUI or preferences")
 }
}
