# Doom BDA poll-window observations — 2026-11-25

This sanitized summary records four bounded, source-bound Doom E1M1 windows. Each requested 1,800 ms of guest time. The first three runs began at pre-increment leveltime tic 65; `b4-t70-p10` deliberately acquired tic 70 after settling at tic 65. That extra ordinary-speed acquisition took 817 DOSBox-X PIC guest ms and is outside the b4 measured window.

| Run | Start tic | DOSBox poll | DOSBox PIC elapsed / overshoot | DOSBox BDA / Doom delta | QEMU virtual elapsed | QEMU BDA / Doom delta | DOSBox−QEMU BDA / Doom |
|---|---:|---:|---:|---:|---:|---:|---:|
| b1 | 65 | 10 ms | 1,802 / +2 ms | +36 / +57 | 1,800,000,000 ns | +36 / +64 | 0 / −7 |
| b2-p50 | 65 | 50 ms | 1,843 / +43 ms | +37 / +59 | 1,800,000,000 ns | +36 / +64 | +1 / −5 |
| b3-p100 | 65 | 100 ms | 1,882 / +82 ms | +38 / +60 | 1,800,000,000 ns | +36 / +64 | +2 / −4 |
| b4-t70-p10 | 70 | 10 ms | 1,806 / +6 ms | +37 / +59 | 1,800,000,000 ns | +36 / +63 | +1 / −4 |

DOSBox elapsed values are PIC guest-millisecond deltas. QEMU values are `QEMU_CLOCK_VIRTUAL` nanoseconds; they are separate clock domains and no common-clock subtraction is claimed. The b1–b3 settle phase moved from tic 64 to 65, taking 335, 331, and 339 guest ticks respectively. B4 settled from tic 64 to 65 in 345 guest ticks, then reached its requested pre-increment tic 70 at ordinary speed before measuring.

The receipts record DOSBox owners reaped with return code 0 and QEMU owners reaped with return code 0 for all runs. DOSBox threshold detection is poll-then-pause and non-atomic; observed overshoot was +2, +43, +82, and +6 ms. QEMU recorded a 1.8 s virtual interval with zero timer overshoot in each run. BDA tick period is recorded as 54,925,493 ns, but independent endpoint phase is uncalibrated. No audio was captured.

These are bounded observations, not timing parity or failure conclusions. They do not establish a general timing rate, audio timing, or behavior outside the measured windows. The b4 start tic differs from the first three, so its Doom-tic delta should be read with that acquisition distinction. Private media, databases, screenshots, audio and VM state are excluded from this repository evidence directory; raw receipts remain in the private evidence area.
