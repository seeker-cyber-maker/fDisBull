# Temporal code-layer verification — 2026-10-23

This is uncommitted 0.11.0.dev0 development on top of published 0.10.0 commit `6ba413e2f535c6294b3ddb767a5bc12a6a388162`. No new release, tag or push is claimed. The 0.10.0 backend binary and delivered packages remain unchanged.

The tested layers backend is macOS ARM64 with SHA-256 `0876e686d6a85f8c1b790db03314b81f471f5a5791dcad4929b90b63a1ebeced`. Its complete patch was replayed from the declared pristine DOSBox-X baseline; all **27 changed source-file hashes** matched the compiled source tree. The [backend manifest](../experimental/dosbox-x/layers/source-manifest.json) records the inputs. This is not a Linux native-backend acceptance claim.

## Authored real-MZ tests

The final layer, coordinate-grid and existing debugger tests passed together: **31 passed**. They use the actual external emulator, with no mocked CPU or synthetic passing RPC response. The cases cover:

- A guest CRC-16/XMODEM loop reads original `B8 11 11` code bytes while the instruction-fetch overlay executes `B8 22 22`. Guest DX matches Python's independent `binascii.crc_hqx` result for the original bytes and differs from the changed-code CRC; guest AX proves the alternate instruction executed.
- An actual guest self-check compares that CRC and branches to failure (`AX=DEAD`) when a RAM patch is enabled. Two execution hooks disable the layer before the first code read and restore it after a successful check. The guest then has original CRC `650C`, executes the patched instruction (`AX=2222`), and stops with the RAM layer re-enabled. This is guest software checking its own code, not a host checksum of fDisBull.
- Word and dword immediate fetches, physical guest data reads, top-layer precedence, RAM-visible edits, stack reordering, disabling, and unchanged static bytes/versions.
- A breakpoint action enables a fetch-only cave and redirects execution into it. The cave's normalized far return reaches the expected breakpoint, changes the intended register, and leaves its backing RAM zero. Trace byte windows distinguish the virtual instructions from RAM.
- A fresh emulator session restores a native checkpoint with both RAM and execution layers, including safe removal of the restored RAM patch.
- An actual guest self-modification makes an overlay guard stale and stops before that decode window. RAM-layer removal refuses conflicting bytes; explicit `keep_changed` clearing preserves differing bytes and records them.
- A bad later native precondition leaves earlier RAM edits and the prior execution overlay unchanged. Malformed/overlapping definitions are rejected without creating a layer.
- Bounded routes, hook removal, persisted events, and temporal code artifacts survive the expected ownership/restart boundaries.
- A real 320×200 guest screenshot becomes a separate native-coordinate grid without modifying the clean PNG. Scripts use its mode ID for clicks. Grid generation and export work offline after both owners close; step bounds and original-source identity are checked.

The foreground JSON protocol was also driven end to end: layer stack activation, effective code query, breakpoint-triggered automatic layer removal, run continuation, live grid screenshot, offline grid/event reading, explicit stop, server exit and native process cleanup all passed. The earlier 0.10.0 backend passes **14 existing-debugger/grid tests** with the development Python code, while layer activation requires the new capability. Backend client/transport tests passed: **31 tests and 18 subtests**.

## Actual DinoPark branch comparison

The source-only `examples/dinopark/verify_layers.py` runner creates a fresh project from the user-owned executable, skips 35 guest seconds, captures a menu frame, breaks in the verified mouse polling routine, and discovers a conditional branch in a bounded real trace. It checkpoints that exact machine state, compares the original branch with its execution-layer inverse, and restores the original view.

Observed branch: **project `1693:0358`, `JE` to `JNE`**. The baseline and alternate eight-event traces start at the same branch with the same underlying RAM bytes and reach different successors. The execution view contains the inverted opcode. Loading the checkpoint removes the overlay and restores the original view. All **192 game files** remain hash-identical, and the emulator is reaped.

This establishes a bounded change in actual-game control flow. It does not establish that the altered path completes a valid game transaction, that DinoPark's own integrity checks were run, or that timing is unchanged. The explicit CRC property is established separately by the authored guest CRC program.

Selected [structured evidence](../experimental/dosbox-x/layers/evidence/2026-10-23/verification.json), [baseline trace](../experimental/dosbox-x/layers/evidence/2026-10-23/dinopark-baseline.json), [alternate trace](../experimental/dosbox-x/layers/evidence/2026-10-23/dinopark-alternate.json), PNG and their hash manifest are retained with the backend source. The original game, native checkpoints and byte-retaining projects stay under ignored local working storage.

## Coordinate grid in actual DinoPark

The final acceptance run skips 35 guest seconds, captures the main menu with a 40-pixel grid, and queues **OLD GAME at native `(160,160)`** using the screenshot's mode ID. After 1,500 guest milliseconds, the actual Load Game dialog is visible, including the save list. Its 20-pixel grid and clean frame are exported separately. Native dimensions stay **320×200**, despite the emulator's display-doubling flags. A new 32-pixel grid is regenerated from the original stored menu frame after project/emulator closure; the project still contains only its single original run. All **192 input files remain unchanged**, and both acceptance emulators are reaped.

The [final receipt](../experimental/dosbox-x/layers/evidence/2026-10-23/verification-grid-final.json), [self-integrity result](../experimental/dosbox-x/layers/evidence/2026-10-23/self-integrity.json), [grid result](../experimental/dosbox-x/layers/evidence/2026-10-23/grid-result.json), clean/annotated PNGs, and added hash manifest supplement the earlier evidence without changing its sealed files. The self-check demonstration uses an authored guest program; DinoPark's own integrity routine has not been identified or tested.

## Complete suite and boundaries

With the final layers backend selected, `python -m pytest -q --tb=short` reports **758 passed, 3 skipped, 2 failed and 23 setup errors**, exit status 1. All 25 failing/error test identities match the recorded 0.10.0 macOS baseline: Linux ELF fixture compilation/linking on Apple's toolchain. The full Mac suite is not globally green. Linux CI has not run for these unpushed development changes.

Execution overlays add no guest RAM/disk installation bytes but do incur host work. Breakpoint actions use paused RPC dispatch; virtual cave and changed branch execution can change guest cycles and state. Guards cover the next 15-byte decode window and can stop conservatively. Protected-mode, device/DMA, dynamic-core overlays, automatic instruction rewind, and native in-core action scheduling are outside this implementation. See [CODE_LAYERS.md](CODE_LAYERS.md) for the exact API and limits.
