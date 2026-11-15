# CHIP-8 virtual-tick frame fence

This incremental QEMU 10.0.13 patch adds a token-bound sample fence to the
retained 4 KiB CHIP-8 TCG target. It is based on the frozen v4
`native/qemu-chip8-layers/` source; v1 through v4 sources and binaries remain
separate and unchanged.

The candidate identifies itself as CPU subset
`fdisbull-chip8-frames-5`, environment
`fdisbull-chip8-display-keypad-timers-rng-layers-frames-4`, and frame model
`fdisbull-chip8-native-frame-sample-1`.

## Fence lifecycle

`x-chip8-arm-frame` arms the next virtual timer tick while the one-CPU TCG VM
is stopped. Its token must be 32 lowercase hexadecimal characters. It compares
the CPU state generation, virtual tick count, and absolute next deadline. A
successful arm advances only the frame control generation and reserves a
control-generation value for cancellation.

When the virtual timer callback reaches a due deadline, it advances exactly
one 60 Hz tick, records the consumed deadline, actual virtual callback time,
phase, display generation, pixels, and SHA-256, then marks a stop pending. It
does not consume overdue follow-up ticks or rearm while a sample stop is
pending or completed. At the next CHIP-8 helper entry, existing layer checks,
sticky CPU faults, and key-wait stop ownership take precedence. If those checks
pass, the helper consumes the pending frame stop before executing that
instruction. The sampled tick deadline equals the armed baseline deadline;
the next timer deadline is the baseline advanced by the rational 60 Hz phase.

A user breakpoint or host hook may stop before the helper consumes the fence.
In that case the receipt remains armed and unconsumed. The host must cancel it
before dispatching the breakpoint or hook. A frame cannot be inferred from a
GDB signal alone. If callback execution is late, `sampled-virtual-now-ns`
records that actual time; no fixed wall-clock latency is claimed.

`query-chip8-frame` returns a complete receipt. `state` is `idle`, `armed`, or
`completed`. A latched sample is exposed while pending and retained after the
owned stop is consumed. A completed frame has `stop-owned=true`,
`stop-consumed=true`, and `stop-pending=false`. Its `state-generation` is the
generation latched immediately after the tick so the host can compare it with
the stopped CPU environment.

`x-chip8-cancel-frame` requires the matching token and current control
generation. It clears the public fence fields and advances the control
generation without reverting timer or display state. Repeating the same
cancellation is idempotent. The existing absolute next deadline remains
unchanged; overdue virtual-tick debt can run after the guest resumes.

This is a sample at a CHIP-8 virtual 60 Hz timer boundary. It is not a VGA
publication, VBlank, guest drawing completion, wall-clock frame cadence, or
proof that a guest-visible display update occurred.

## Checkpoints and limits

The CPU VMState is version 5 with minimum version 5. Save and load preflight
refuses while the fence is armed or completed, including after its stop was
consumed; cancel it before checkpointing. The fence and its token are
process-local and are not serialized. A fresh load clears ephemeral frame
ownership while retaining the existing architectural state, display pixels,
timer deadline, virtual-tick count, and phase from the v5 checkpoint. Cross-
binary VMState compatibility is not claimed. Public save/load admission is
runtime-tested. Raw QMP migration with an active fence has not been qualified;
generic snapshot-load reset paths can differ from the public loader. The
single-tick behavior is tested at ordinary deadlines; deliberately forced
multi-tick backlog handling remains source-reviewed rather than runtime-proved.

The profile remains one stopped TCG vCPU with the existing fixed CHIP-8 CPU,
device, clock, RNG, and RAM/fetch-layer models. The native patch adds no display
device, VBlank model, native hook table, input schedule, or catch-up test
control. Host code owns breakpoint/hook dispatch and checkpoint history.

## Build evidence

The incremental patch replays against the sealed v4 source hashes. QEMU was
configured for the local `chip8-softmmu` TCG target and built on macOS arm64.
The candidate path, hash, exact commands, and build receipts are recorded in
`source-manifest.json`. Root-owned native validation passed 16 frame-history
cases with zero failures, errors, or skips on macOS arm64; the receipt is
`R/chip8-frames-native-final-03.xml`. A separate retained compatibility
selection passed 72 cases with the obsolete v1-only CLS refusal deselected.
The final frozen preservation run passed 3,243 tests across 193 files, with
zero failures, errors or skips and the two original predeclared deselections;
1,211 Python source/test hashes stayed unchanged. Elapsed time was 811.32 seconds.
Earlier full/tail diagnostics exposed a retained short-run deadline race; the
host now reserves stop handling time within the existing allowance, with
pre-dispatch owner preservation and post-dispatch fail-closed regressions. Both
affected native cases pass without timeout increases or exclusion. The shared
GDB client's emergency recovery still permits up to five extra seconds, so no
hard wall-clock return guarantee is claimed. The final result, XML and source
hash receipts are recorded in the private study workspace. No hosted CI or
other-host build is claimed.
