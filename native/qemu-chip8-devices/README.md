# CHIP-8 QEMU display, keypad, and timer slice

This package extends the sealed CHIP-8 CPU-only target with a bounded display,
keypad, delay timer, sound timer, and stopped-state QMP controls. It applies to
QEMU 10.0.13 after applying the CPU-only patch recorded in
`native/qemu-chip8/source-manifest.json`. It does not replace or mutate that
v1 runtime.

## Implemented profile

The CHIP-8 profile remains `chip8-classic-pilot-default-v1`. The device-aware
CPU subset is `fdisbull-chip8-classic-devices-2`, with environment model
`fdisbull-chip8-display-keypad-timers-1`.

The supported instruction additions are `00E0`, `DxyN`, `Ex9E`, `ExA1`,
`Fx07`, `Fx0A`, `Fx15`, `Fx18`, and `Fx29`. `Fx55` and `Fx65` retain the
pilot's post-increment `I` behavior. The existing `8xy6/8xyE` shift-from-`Vy`
and logic-clears-`VF` quirks remain. Register aliases involving `VF` use
read-before-write behavior.

The display is 64 by 32 pixels. Native state stores one byte per pixel, with
only `0` and `1` accepted. `00E0` clears the framebuffer. `DxyN` XORs sprite
bits, clips rows and columns at the edges, and uses zero rows for `N=0`.
Coordinates are captured before writing collision status to `VF`; `VF` is zero
when no pixel collides and one if any set pixel is erased. The sprite read
extent is checked before the framebuffer changes. `Fx29` points into the
standard 16-glyph, 5-byte font initialized at `0x50`.

The key state is a 16-bit held-key mask. `Ex9E` and `ExA1` treat values above
15 as never pressed. `Fx0A` selects the lowest held key, including key zero.
With no key held, it stops explicitly at the same `Fx0A` PC, sets the
architectural key-wait latch, and makes no instruction progress. A host must
set a key and explicitly resume or step; `Fx0A` then re-executes. The separate
`key-wait-stop-owned` receipt is ephemeral stop attribution: it is cleared on
CPU resume entry before breakpoint checks and is false after state restore.

`Fx07`, `Fx15`, and `Fx18` read or set the 8-bit delay and sound timers. A
nonzero sound timer reports `sound-active`; this target emits no audio. A
60 Hz `QEMU_CLOCK_VIRTUAL` timer drives regular decrements. Its deadline and
rational phase use the prior scheduled deadline, with the 1e9/60 fractional
remainder preserved. Virtual time pauses when the VM stops. Stopped-state
manual ticks use the same timer decrement logic but do not advance virtual
time, phase, or virtual-tick count.

## QMP interface

`query-chip8-environment` returns the full stopped-state environment,
including CPU/profile identity, framebuffer bytes and SHA-256, display and
state generations, key mask/wait flags, timer values, tick counts, phase, and
virtual-clock time/deadline. `pixels-hex` encodes the raw 2048 framebuffer
bytes as 4096 lowercase hex characters; each decoded byte is `00` or `01`.
The host adapter maps off pixels to opaque black (`000000ff`) and on pixels to
opaque white (`ffffffff`).

`x-chip8-set-keys` takes a complete `key-mask` and required
`expected-generation`; `x-chip8-debug-ticks` takes a count from 1 through
65535 and the same generation guard. Both require a stopped VM, apply no
partial mutation on failed validation, and return the full post-state
environment. A successful key-mask no-op still advances `state-generation`.
Manual ticks increment `manual-ticks` only and leave virtual time, the virtual
deadline, phase, and `virtual-ticks` unchanged.

## State and limits

VMState version 2 stores the CHIP-8 device state and virtual timer along with
the machine RAM. Restore validation checks the bounded pixel values, key and
timer ranges, CPU state, and rational phase. The frozen candidate passed
same-binary cold-restore checks. Cross-binary restore is not qualified.

The implementation remains a helper-heavy TCG target with one instruction
boundary per translated block. It is a bounded classic CHIP-8 profile, not a
general CHIP-8 compatibility claim. It does not implement audio output, other
CHIP-8 variants, or arbitrary ROM compatibility.

## Build and verification

The candidate used a fresh QEMU source tree at
`R/native-runtime/chip8-devices-runtime`, independently configured from the
sealed CPU-only source. Configure and build commands, source-file hashes,
patch identity, and binary SHA-256 are recorded in `source-manifest.json`.
Apply this incremental patch with `patch -p1` to the source tree after the v1
CPU-only patch.

Nine locally authored device-focused native cases passed on the recorded
macOS arm64 TCG binary. They cover display/sprite behavior, register aliasing,
font lookup, key wait and held-key selection, manual ticks, timer/phase and
restore behavior, and stale/invalid CAS refusal. Ten retained CPU semantics/JSON cases also pass on this binary. The parent
preservation selection passes 2,697 cases across 163 files with all 1,194
Python source/test hashes unchanged; one unavailable private identification
fixture is explicitly deselected. Separate overlapping selections pass 323
DOSBox-X cases, 97 host/package cases and 32 storage/device cases. The private
consolidated receipt is R/chip8-devices-final-receipt.json. This package does
not claim hosted CI, Linux, cross-architecture, or cross-binary qualification.
