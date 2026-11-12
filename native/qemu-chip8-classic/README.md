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
the RNG seed, current state, and draw count. Only same-binary restore is
intended; cross-binary VMState compatibility is not claimed.

## Build and verification status

The source diff and incremental patch are prepared, and the isolated patch
replay validates the six changed-file hashes against the source candidate.
The source is **unbuilt**. Configure succeeded in the isolated
`R/native-runtime/chip8-classic-runtime/build-classic` tree, but the required
`memory-run --kind cpu --peak-bytes 4000000000` gate refused the Ninja command
before the build started. The sanitized refusal record is referenced in
`source-manifest.json`; no binary hash, build pass, or native test pass is
claimed for this increment.

The manifest records the exact external `TMPDIR`, configure/build working
directories, refused command, refusal reason, parent patch hash, and source
hashes. Once resource admission changes, the required memory-run gate must be
re-evaluated before building; this package does not authorize bypassing it.
