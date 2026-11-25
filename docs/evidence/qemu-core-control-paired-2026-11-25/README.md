# Paired authored COM core-control evidence

One guarded native attempt passed on 2026-11-25: the selected paired authored
COM node completed with **1 passed in 6.32 seconds**. The native inputs and
attempt manifest remain in the private CACHE attempt directory; no boot media,
firmware, private project database, or emulator state is included here.

The control fixture used identical 34-byte authored COM files on both engines.
Each stopped at the loop breakpoint, continued and paused at IP `0x010A`, and
kept the guest process active. DOSBox-X exercised its legacy
`execution.continue` / `execution.wait` / `execution.pause` / `execution.wait`
sequence. QEMU used its public resume, status, and pause methods. DOSBox-X
returned a legacy `breakpoints.list` reply; QEMU exposed its public
`debug.breakpoints` session alias map. Those are backend-specific surfaces,
not equivalent reply-schema evidence.

A second identical 5-byte authored COM requested DOS exit code 37 through
`INT 21h/AH=4Ch`. Both engines reported normal selected-process exit with code
37. Each emulator owner was reaped and exited with host process code 0.

## Evidence and limits

The exact test node and runtime, boot-image, prepared-baseline, authored-input,
and test-source SHA-256 values are recorded in `verification.json`. The private
manifest records paths and sizes as well. QEMU's legacy `breakpoints.list`
RPC remains unsupported and was not exercised; its listing observation used
the supported public alias map. This result does not qualify general DOS or
debugger parity, MZ loading, child or TSR lifecycle, diagnostics, step-over,
vendor software, migration, or DOSBox-X retirement.
