import Foundation

@main struct CoreTests {
    static func main() {
        var checks = 0
        func check(_ value: Bool, _ label: String) {
            precondition(value, label); checks += 1
        }
        let zero = CPUTicks(user:0, system:0, idle:0, nice:0)
        check(UsageDelta.fraction(previous:nil, current:zero) == nil, "first sample unknown")
        check(UsageDelta.fraction(previous:zero, current:zero) == 0, "no elapsed ticks")
        check(UsageDelta.fraction(previous:zero, current:CPUTicks(user:20,system:10,idle:60,nice:10)) == 0.4, "busy includes nice")
        check(UsageDelta.fraction(previous:zero, current:CPUTicks(user:100,system:0,idle:0,nice:0)) == 1, "fully busy")
        check(UsageDelta.fraction(previous:zero, current:CPUTicks(user:0,system:0,idle:100,nice:0)) == 0, "idle")
        check(UsageDelta.fraction(previous:CPUTicks(user:100,system:100,idle:100,nice:100),current:zero) == nil, "counter reset unknown")
        check(UsageDelta.fraction(previous:CPUTicks(user:UInt32.max-2,system:0,idle:0,nice:0),
                                  current:CPUTicks(user:2,system:0,idle:5,nice:0)) == 0.5, "unsigned wrap")
        var history = CPUHistory()
        let first = history.update(host:zero, cores:[zero,zero])
        check(first.overall == nil && first.cores.allSatisfy{$0 == nil}, "baseline")
        let busy = CPUTicks(user:100,system:0,idle:0,nice:0)
        let second = history.update(host:busy, cores:[busy,busy])
        check(second.overall == 1 && second.cores == [1,1], "second sample")
        let changed = history.update(host:busy, cores:[busy])
        check(changed.cores == [nil], "hotplug count invalidates baseline")
        var selected = SelectedCPUHistory(coreCount: 2)
        let initial = selected.snapshot()
        check(initial.overall == 0 && initial.cores == [0, 0], "menu starts at source zero readings")
        let firstCoreA = CPUTicks(user:40, system:0, idle:60, nice:0)
        let firstCoreB = CPUTicks(user:10, system:10, idle:80, nice:0)
        let firstCores = selected.update(cores:[firstCoreA, firstCoreB])
        check(firstCores.cores == [0.4, 0.2], "first selected cores use since-boot ratio")
        check(firstCores.overall == 0, "cores do not advance inactive host")
        let firstHostTicks = CPUTicks(user:20, system:10, idle:60, nice:10)
        let firstHost = selected.update(host:firstHostTicks)
        check(firstHost.overall == 0.4 && firstHost.cores == firstCores.cores,
              "first host selection starts at zero ticks and retains cores")
        let failure = selected.snapshot(error:"authored Mach read failure")
        check(failure.error == "authored Mach read failure" && failure.overall == 0.4 && failure.cores == [0.4, 0.2],
              "failed API read retains both visible modes")
        let nextCoreA = CPUTicks(user:70, system:0, idle:130, nice:0)
        let nextCoreB = CPUTicks(user:20, system:20, idle:160, nice:0)
        let resumedCores = selected.update(cores:[nextCoreA, nextCoreB])
        check(resumedCores.cores == [0.3, 0.2] && resumedCores.overall == 0.4,
              "resumed cores use only their own prior ticks")
        check(resumedCores.error == nil, "successful reading clears transient failure")
        let resumedHost = selected.update(host:CPUTicks(user:60,system:20,idle:100,nice:20))
        check(resumedHost.overall == 0.6 && resumedHost.cores == resumedCores.cores,
              "resumed host includes nice and preserves inactive cores")
        let unchangedHost = selected.update(host:CPUTicks(user:60,system:20,idle:100,nice:20))
        check(unchangedHost.overall == 0 && unchangedHost.cores == resumedCores.cores,
              "no elapsed selected ticks matches source zero result")
        let newTopology = selected.update(cores:[busy])
        check(newTopology.cores == [nil] && newTopology.overall == 0 && newTopology.error != nil,
              "topology change safely invalidates only selected core identities")
        let topologyRecovered = selected.update(cores:[CPUTicks(user:150,system:0,idle:50,nice:0)])
        check(topologyRecovered.cores == [0.5] && topologyRecovered.error == nil,
              "changed topology recovers after fresh elapsed interval")
        let resetHost = selected.update(host:zero)
        check(resetHost.overall == nil && resetHost.cores == topologyRecovered.cores && resetHost.error != nil,
              "counter reset remains unknown without destroying inactive cores")
        let recoveredHost = selected.update(host:CPUTicks(user:25,system:0,idle:75,nice:0))
        check(recoveredHost.overall == 0.25 && recoveredHost.error == nil,
              "host reset establishes next bounded interval")
        let restart = SelectedCPUHistory(coreCount: 2).snapshot()
        check(restart.overall == 0 && restart.cores == [0, 0], "new menu sampler restarts with source zero readings")
        var wrapHistory = SelectedCPUHistory(coreCount: 1)
        _ = wrapHistory.update(cores:[CPUTicks(user:UInt32.max-2,system:0,idle:0,nice:0)])
        let wrappedCore = wrapHistory.update(cores:[CPUTicks(user:2,system:0,idle:5,nice:0)])
        check(wrappedCore.cores == [0.5], "selected mode retains UInt32 wrap safety")
        check(MeterLayout.width(coreCount:0) == 0, "empty width")
        check(MeterLayout.width(coreCount:1) == 7, "one core geometry")
        check(MeterLayout.width(coreCount:10) == 52, "ten core geometry")
        let bars = MeterLayout.bars([0,0.7499,0.75,0.8999,0.9,1,nil,-1,2])
        check(bars[0].fillHeight == 3 && bars[5].fillHeight == 14, "minimum nub and full height")
        check(bars[0].x == 2 && bars[1].x == 7 && bars[0].y == 5, "spacing")
        check(bars[1].color == .green && bars[2].color == .orange && bars[3].color == .orange && bars[4].color == .red, "threshold boundaries")
        check(bars[6].color == .unknown && bars[6].fillHeight == nil, "unknown no false zero")
        check(bars[7].fillHeight == 3 && bars[8].fillHeight == 14, "clamp")
        check(MeterLayout.color(.nan) == .unknown && MeterLayout.color(.infinity) == .unknown, "invalid readings")
        check(MeterLayout.bars([1],monochrome:true)[0].color == .monochrome, "theme")
        var options = DisplayOptions()
        check(options.intervalMilliseconds == 500 && options.showCoresIndividually && !options.showText, "defaults")
        options.setInterval(100); check(options.intervalMilliseconds == 100, "valid interval")
        options.setInterval(17); check(options.intervalMilliseconds == 100, "invalid interval refused")
        options.showText = true; check(options.widthWithoutCores == 60, "overall image text")
        print("\(checks) core checks passed")
    }
}
