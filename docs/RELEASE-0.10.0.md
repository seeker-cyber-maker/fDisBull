# fDisBull 0.10.0 release candidate

This candidate consolidates the native DOSBox debugger extension first delivered at `cd13636` and fixes an analysis queue issue exposed by its actual use. Publication and remote CI acceptance are separate from local packaging.

## Changes

- Capture and restore native DOSBox machine states, including restoration in a fresh emulator session. Inspect state components and fork immutable checkpoints with checked RAM/register edits before reinjecting them. Parent snapshots and static byte versions remain intact.
- Run bounded JSON menu scripts with named results, assertions, repeats, mouse input, native fast-forward, breakpoints, checkpoints, screenshots, and traces. Unexpected outcomes stop the script and retain the execution report.
- Place `x`, `r`, `w`, and `rw` breakpoints with runtime address translation. Execution breakpoints require analyzed, byte-verified instructions; data watches accept mapped data without disassembly and catch same-value writes. Register snapshots expose runtime `cs` and `ip` aliases.
- Prioritize an explicit DOS analysis seed within that call's instruction budget. Previously it could remain undecoded behind persisted recursive work. Older pending work is retained and resumed; a budget stop still reports pending work rather than stability.
- Document repeated-instruction watch semantics: `REP MOVSW` may complete its whole copy before stopping; overlapping byte-watch IDs are not independent writes or queued stops.
- Preserve the [parking-counter experiment](PARKING_COMMIT.md), showing an immediate staged-to-live copy during shop OK for the available pmm save. Add a parameterized checkpoint replay for validating another wheel with the same private fixture.
- Reject native state and local database extensions during distribution checks, in addition to the explicit source allowlist and existing game-asset exclusions.

## Compatibility and delivery

The Python version is now **0.10.0**, so this build is distinguishable from the two earlier 0.9.0 integrations. Existing debugger API names and persistent artifact schema remain unchanged. The native backend patch and tested binary identity are unchanged from `cd13636`; state compatibility still requires the exact backend, profile, source/load context, and mounted-file manifest.

The wheel, sdist, and tool ZIP exclude repository examples, backend binaries, game assets, native states, and local databases. The separate local delivery includes the complete backend patch/GPL notices, the tested Mac executable, and selected diagnostic evidence. See [delivery instructions](LOCAL_DELIVERY.md), [state/script API](DEBUGGER_SCRIPTS.md), and the [fresh candidate verification](VERIFICATION-0.10.md).

Native watchpoints are scoped to the normal CPU core in real mode, excluding host inspection, instruction fetch, device/DMA, and protected-mode tracing. Checkpoints restore machine state and require matching host files; they do not roll back files. The local Mac still has the established Linux ELF fixture/compiler incompatibility in the full test suite. No first-party license has been selected. These limitations remain visible in the candidate.
