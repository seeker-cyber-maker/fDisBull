# CHIP-8 classic opcode and RNG increment

This package is an incremental source change on the device-aware CHIP-8 QEMU
target in `native/qemu-chip8-devices/`. It adds `Bnnn`, `Cxkk`, `Fx1e`, and
`Fx33`, plus a deterministic RNG seed command. The previous CPU-only and
device-aware packages and their binaries remain separate and unchanged.

## Source contract

The CPU subset identifier is `fdisbull-chip8-classic-complete-3`; the
environment model is `fdisbull-chip8-display-keypad-timers-rng-2`. The named
classic profile and its earlier shift-from-`Vy`, logic-clears-`VF`, transfer
post-increment, display, key, and timer behavior remain in place.

- `Bnnn` sets `PC = nnn + V0` without truncating the sum to 12 bits. The
  existing sticky odd-PC and out-of-range fetch faults apply on the attempted
  fetch.
- `Cxkk` advances the 32-bit state by `(1664525 * state + 1013904223) mod
  2^32`, then writes `(state >> 24) & kk` to `Vx`. It consumes a draw even when
  `kk` is zero. It preserves `VF`, except when `x` is `F` and `VF` is the
  destination.
- `Fx1e` sets `I = (I + Vx) mod 2^16`. It reads `Vx` before updating `I` and
  does not modify `VF`.
- `Fx33` preflights a three-byte RAM extent before writing the hundreds, tens,
  and ones digits. It leaves `Vx`, `VF`, and `I` unchanged; an invalid extent
  retains the existing atomic sticky data-fault behavior.

The RNG model is `fdisbull-lcg32-high8-v1`, with reset seed/state zero. The
environment query adds `rng-model`, `rng-seed`, `rng-state`, and `rng-draws`.
`x-chip8-seed-rng(seed:uint32, expected-generation:uint64)` is stopped-only,
uses the environment state-generation CAS, returns the full environment, and
on success sets seed/state to the supplied value, clears draws, advances the
state generation once, and clears only ephemeral key-wait-stop attribution.

The unsigned receipt counters `state-generation`, `frame-generation`,
`virtual-ticks`, and `rng-draws` saturate at `UINT64_MAX`; they never wrap.
Manual-tick and seed QMP mutations continue to refuse a state-generation value
of `UINT64_MAX`; manual ticks also refuse a count that would overflow their
counter before applying any timer decrement.

The CHIP-8 CPU VMState changes to version 3 with minimum version 3 and stores
the RNG seed, current state, and draw count. Same-binary cold/FDB-reopen restore is locally verified; cross-binary VMState
compatibility is not claimed.

## Build and verification status

The six-file incremental patch replays against the sealed v2 source hashes, and
lightweight QAPI generation passed. The isolated `build-classic` target was
built after the user explicitly overrode the prior `memory-run` refusal. The
original refusal remains recorded at `R/chip8-classic-memory-run-refusal.json`;
the authorized direct build and binary identity are recorded at
`R/chip8-classic-build-override-receipt.json`.

Native binary SHA-256: `c1dca2817894b3d45e0ea3262f3b907167c854f28e4c35df25e283a24262a987` (6,220,664 bytes). The frozen binary passed 30 native cases and one host family-map check, plus 19 retained CPU/device cases on v3. The executed representatives cover all 34 non-legacy classic families; this is not exhaustive dialect or arbitrary-ROM qualification.

Integrated preservation passed 2,731 tests across 166 files with all 1,197
Python source/test hashes unchanged. Separate overlapping selections passed
323 DOSBox-X history/undo cases and 138 host/package cases. Accepted selections
have zero failures/errors/skips. One private identification input is explicitly
deselected in the integrated run; the obsolete v1-only CLS refusal is excluded
when replaying old CPU cases on v3. Two already-created v2 artifacts restored
under the upgraded host with the original runtime and original evidence intact.

The private consolidated receipt is `R/chip8-classic-native-final-receipt.json`.
The package does not claim CI, Linux/other-host build, cross-binary VMState
compatibility, audio output, historical timing or arbitrary ROM compatibility.
