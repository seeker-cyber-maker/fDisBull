# Doom cycles timing observations — 2026-11-25

Two passed guarded native three-arm trials measured source-bound Doom E1M1 at
pre-increment tic 80 for one requested 900 ms interval per arm. Both trials used
DOSBox-X polling at 10 ms with a 20 ms maximum accepted overshoot, and unchanged
QEMU. All emulator owners were reaped with return code 0.

| Attempt | Arm | Engine-local elapsed | BDA delta | Doom delta |
|---|---|---:|---:|---:|
| 03 | DOSBox-X default cycles (not verified auto) | 908 PIC ms (+8) | +19 | +31 |
| 03 | DOSBox-X requested fixed 157600 | 906 PIC ms (+6) | +18 | +32 |
| 03 | QEMU unchanged | 900,000,000 virtual ns | +18 | +30 |
| 04 | DOSBox-X requested auto (application unverified) | 904 PIC ms (+4) | +18 | +20 |
| 04 | DOSBox-X requested fixed 157600 | 905 PIC ms (+5) | +18 | +32 |
| 04 | QEMU unchanged | 900,000,000 virtual ns | +18 | +30 |

The fixed-cycle and QEMU Doom deltas repeated at +32 and +30 in both attempts.
Attempt 04's explicitly requested auto arm recorded +20, while attempt 03's
bare DOSBox binary is now labeled default cycles, not verified auto, and
recorded +31. The explicit auto profile's effect was not verified. These
observations therefore do not identify a cycle-setting cause and do not support
a rate or parity inference.

Attempt 04's pairwise counters were auto-minus-fixed −12 Doom tics / 0 BDA
ticks and fixed-minus-QEMU +2 Doom tics / 0 BDA ticks. Attempt 03's default
cycles-minus-fixed counters were −1 Doom tic / +1 BDA tick; fixed-minus-QEMU
was +2 Doom tics / 0 BDA ticks. These are per-run descriptive differences.
DOSBox-X uses PIC guest milliseconds and QEMU uses its virtual clock; these are
independent domains and were not subtracted. DOSBox endpoints use poll-then-pause
and are non-atomic; QEMU uses its virtual-clock timer stop. Each comparison is
one interval per arm in each attempt.

Attempt 04 additionally recorded a whole-machine QEMU `query-replay.icount`
delta of 7,031,250 instructions. This is an execution instruction count for the
whole QEMU machine, not a Doom-only count, retired-instruction count, or hardware
cycle count. It is not comparable to the DOSBox cycle request.

Next test: verify the active DOSBox cycle configuration through a read-only
engine-side query, then run repeated tic-80, 900 ms three-arm rounds with the
arm order rotated. Retain per-round Doom/BDA deltas and separate clock domains;
this can check repeatability without presuming parity.

The sanitized record is [verification.json](verification.json). Private raw
receipt manifests are identified by basename and hash only:

- Attempt 03 `receipt-manifest.json`, SHA-256 `e3bd8c67f940599f16739ee798d0999017bdf9b67650fef8521f0e33e7008cf8`.
- Attempt 04 `receipt-manifest.json`, SHA-256 `b76b976f461a1bee8a4182e191cdf78e95a6980f1c429e434602729f6971381f`.

No private inputs, raw receipts, screenshots, FDBs, VM states, or audio are
included here. The evidence establishes neither full timing parity nor
causality or general DOSBox-X replacement behavior. DOSBox-X remains the
default; no CI ran.
