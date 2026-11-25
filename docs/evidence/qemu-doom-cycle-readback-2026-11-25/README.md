# Doom cycle-mode readback and rotated timing trials

A separate DOSBox-X candidate adds read-only CPU cycle state to
`execution.timing`, sampled on the emulation thread. An authored COM probe
passed: requested auto cycles reported auto detection and a 3,000 cycle
maximum at entry; requested fixed 157600 reported fixed mode and 157,600.

Two guarded original Doom E1M1 three-arm trials then passed with pinned private
inputs. Each arm began at the same pre-increment `leveltime` tic 80 and ran one
uninterrupted approximately 900 ms guest-clock window. Trial 04 rotated the arm
order from auto/fixed/QEMU to fixed/QEMU/auto. Both DOSBox-X boundary samples in
both runs confirmed the requested fixed setting as 157,600 with automatic
adjustment and detection off. The auto request had switched into adaptive
max-cycle mode at both boundaries; its observed maximum changed during each
window. The readback does **not** observe the mode continuously while running.

| Trial | Arm | Guest clock delta | BDA ticks | Doom tics | Cycle maximum at start → end |
|---|---|---:|---:|---:|---:|
| 03 | DOSBox-X auto | 911 PIC ms | 19 | 33 | 4,140 → 26,124 (adaptive max) |
| 03 | DOSBox-X fixed | 903 PIC ms | 18 | 32 | 157,600 → 157,600 |
| 03 | QEMU unchanged | 900 virtual ms | 18 | 30 | not applicable |
| 04 | DOSBox-X fixed | 900 PIC ms | 18 | 32 | 157,600 → 157,600 |
| 04 | QEMU unchanged | 900 virtual ms | 18 | 30 | not applicable |
| 04 | DOSBox-X auto | 901 PIC ms | 18 | 34 | 5,906 → 25,153 (adaptive max) |

The fixed-minus-QEMU Doom delta repeated at +2 tics with equal BDA tick
deltas. These are separate engine clock domains. DOSBox-X observes the time
threshold through 10 ms polling and then requests a pause, while QEMU uses a
virtual-clock timer stop. Endpoints and BDA phases are not a shared atomic
measurement. The result does not identify why the Doom counters differ or
establish a cycle-accurate conversion between the engines.

The candidate also passed 19 native DOS guest-exit and paired parent/child
checkpoint regressions. Affected host source/companion and timing tests
reported 22 passed and 17 opt-in skips; skips are not native passes. The
candidate binary SHA-256 is
`065b47d4d6a83e08c10a60401b7563e8f6a4cca1203629d96783775613525bb8`;
its source patch SHA-256 is
`a9d31f59e0a53fb795dd5567c290f7dd47d2e74a5ad9f0c920a0287db751f7d3`.
The prior installed DOSBox-X remains unchanged and default. No CI, release,
installation, activation, or backend switch occurred.

The [sanitized record](verification.json) identifies the scope and raw receipt
hashes. The private `cycle-readback-manifest.json` has SHA-256
`67814393eee8a8848b4eb479221e207a0f00fc6d5d3e50aeb153e715f427952e`.
Raw Doom media, states, JUnit, and receipt files remain outside Git. The next
gate is an endpoint/clock experiment that can distinguish source execution
rate from poll-and-pause timing without claiming full 1:1 parity. The 143
formal DOS surfaces and seven campaigns remain unqualified for promotion.
