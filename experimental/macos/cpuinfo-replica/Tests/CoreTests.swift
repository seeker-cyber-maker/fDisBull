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
