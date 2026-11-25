# Doom BDA timing window sweep — 2026-11-25

Two guarded native paired tests passed for original Doom E1M1 at pre-increment leveltime tic 70. Each backend ran its own requested guest-time window. DOSBox-X elapsed time is measured from PIC guest milliseconds with a 10 ms poll followed by pause; QEMU elapsed time is its virtual clock. The windows are not a shared-clock comparison.

| Requested window | DOSBox-X PIC elapsed | DOSBox BDA / Doom delta | QEMU virtual elapsed | QEMU BDA / Doom delta | Doom delta difference (DOSBox−QEMU) |
|---:|---:|---:|---:|---:|---:|
| 300 ms | 301 ms (+1 ms) | +6 / +14 | 300,000,000 ns | +6 / +12 | +2 tics |
| 900 ms | 902 ms (+2 ms) | +18 / +35 | 900,000,000 ns | +18 / +30 | +5 tics |

Both engine owners returned code 0 in both runs; the native test reported 2 passed in 104.67 seconds. The earlier 1,800 ms start-tic-70 observation was DOSBox-X +59 Doom tics versus QEMU +63, a difference of −4. The observed difference therefore changes sign across window lengths. This is a bounded sign reversal, not a stable fixed offset or rate.

DOSBox-X threshold observation is poll-then-pause and non-atomic. DOSBox PIC milliseconds and QEMU virtual nanoseconds are distinct clocks. BDA start/end phases are independent and uncalibrated, so matching BDA tick deltas do not establish equivalent elapsed time. Input/state histories remain bounded to these runs; no audio was captured. These observations establish neither general timing parity nor failure.

The four raw JSON files are retained privately under `/Volumes/GitHub/GitHub/fDisBull-private/qemu-doom-bda-window-20261125/`; their byte sizes and SHA-256 values are in that directory's `manifest.json`. This repository directory contains only sanitized counters and methodology. No game media, FDB, VM state, screenshot or audio is included.
