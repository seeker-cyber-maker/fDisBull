# Experimental ScummVM execution sidecars

The separate [Gob Inter_v3 adapter](../../docs/SCUMMVM_GOB_BACKEND.md) supports
the qualified Lost in Time slice. Its build helper is `gob-build-headless.sh`,
with `gob-headless-bridge.patch` and `gob-source-manifest.json` pinned to ScummVM
2026.4.0. The AGI procedure below retains its earlier independent source pin.

The dated verification receipts and source manifests describe the frozen
November 1 experiment, including its then-unpublished state. Current handoff
validation is recorded separately; publication does not extend those runtime
or benchmark claims to untested inputs or versions.

This directory holds a patch against the exact ScummVM v2.8.1 commit recorded in [source-manifest.json](source-manifest.json). The patched executable runs ScummVM's real AGI engine with an inherited, bidirectional JSON-lines control socket. It is an optional research runtime for fDisBull; it does not replace fDisBull's analyzer, database, decoders, original executable evidence, or its own interpreter work.

The binary has been built and exercised on macOS arm64 with the original KQ1 AGI data. The game files were read only; configuration and save slots were written to an isolated experiment directory. No fDisBull release or system installation was changed.

## Build and launch

Both source/build outputs and temporary output must be on an authorized external
volume. The build helper defaults to the 40 GB storage target. This experiment
received explicit approval for a 20 GB minimum; reproducing that approved
bounded run uses `FDISBULL_DESTINATION_RESERVE_BYTES=20000000000`. A later run
must use its own authorized reserve decision.

Before cloning this bulk source, admit at least 1 GB of new storage on an authorized external CODEX workspace. Then clone the pinned tag into that workspace and verify its commit equals `750f2373fb100efe08c6444e36b68c01387fc307`. Run `build-headless-agi.sh <clean-scummvm-checkout> <existing-external-workspace>`; the script checks the commit, clean tree, storage reserve, patch applicability, and then configures/builds the null backend with only AGI enabled. Keep the full ScummVM source and its `COPYING` notice with any distributed modified binary.

A controller creates a socket pair, passes one end to the child, sets `FDISBULL_SCUMMVM_FD` to that inherited descriptor, and launches the built `scummvm` with an isolated `--config`, `--savepath`, `--path=<AGI-data-dir>`, and `agi:<game-id>` target. The controller owns the child process; closing its socket causes the game process to exit. Protocol requests are one JSON object per line with positive integer `id` and `op`; replies carry the same `id` and `ok`, or `ok:false,error,message`.

## Native control surface

- `hello`: engine/version, capability list, virtual-clock support.
- `state.get` / `state.set`: room, loaded logic position, all 256 AGI vars and flags, inventory object locations, active screen-object records, frame revision, virtual time, and guarded variable/flag/object-location writes. State writes are accepted only at a paused opcode or cycle point.
- `run`, `step`, `run_until_cycle`: bounded AGI execution. `max_instructions` counts dispatched top-level AGI opcodes; `virtual_ms`/`max_guest_ms` bounds the null backend's simulated ScummVM clock; `max_ms` bounds host elapsed time (default 30 seconds). Stops return a reason, position, opcode count, guest time, actual message-box state, and backend-yield state. Breakpoints skip the current matching address once on resume.
- `break.add/remove` and `watch.add/remove`: logic plus loaded-buffer offset breakpoints, and `r`, `w`, or `rw` watches on AGI variable, flag, and inventory-object accessors. Same-value writes are observed. Direct raw field changes outside those accessors are outside watch coverage.
- `trace.start/stop/get/clear`: bounded ring of 2,048 top-level opcode byte, logic, offset, and guest-time records. This is not a full test-expression or native CPU trace.
- `logic.read/patch/restore`: exact loaded AGI logic-buffer byte ranges. A patch requires the expected current bytes and stays in process memory; original loaded bytes are retained for restore. Replies include FNV-1a 64-bit hashes, generation, and active status. Guards stop execution with `layer_conflict` if an active patched logic unloads, is replaced, or changes unexpectedly at a safe point. These are loaded, decoded ScummVM resource bytes, not a general original-file overlay, and native save slots do not persist edits.
- `input` / `input.status`: actual AGI event-queue injection for named keys, printable ASCII/Enter/Tab text, and mouse events. Optional `hold_ms` and `gap_ms` schedule events on the virtual clock. `key` actions `down` and `up` use a numbered lease. Status reports pending events, next due guest time, delivered held keycodes, and leases. Queued or delivered does not prove that AGI consumed an event. Modifier chords are rejected.
- `frame.get` / `pixel.get`: last `updateScreen()` committed CLUT8 display converted with its committed palette to RGB24 at ScummVM's native output dimensions. The revision counts display commits. Null-backend cursor and GUI overlays are not captured.
- `save` / `load`: ScummVM's native AGI save slots 1–999 at a cycle boundary. These are ordinary game saves, not exact mid-opcode machine snapshots. Loading follows ScummVM's normal engine behavior.

`at_modal` means the AGI message-box inner loop is active. `modal_revision` increments on observed opening and closing transitions. `at_backend_yield` means execution paused inside the null backend's event/delay service point; it does not by itself indicate a modal window. A scene action should use the modal transition and game state, not frame or queue timing alone, as its completion witness.

## Scope and licensing

The upstream license is retained verbatim in [COPYING](COPYING).

Only the AGI engine is configured. SCI, SCUMM, DOS executable behavior, script decompilation, general resource overlays, and exact VM snapshots are not provided. ScummVM may differ from the original DOS interpreter on timing, compatibility fixes, and rendering; retain original-runtime evidence separately when comparing scenes.

ScummVM v2.8.1 and this derivative patch are GPL-3.0-or-later. The sidecar boundary keeps this experiment operationally separate, but it does not remove the obligation to provide corresponding ScummVM source, patch, and notices if the modified executable is distributed. See the pinned [upstream source](https://github.com/scummvm/scummvm/tree/v2.8.1), especially the [AGI interpreter](https://github.com/scummvm/scummvm/blob/v2.8.1/engines/agi/op_cmd.cpp), [AGI state accessors](https://github.com/scummvm/scummvm/blob/v2.8.1/engines/agi/global.cpp), and [null backend](https://github.com/scummvm/scummvm/blob/v2.8.1/backends/platform/null/null.cpp).

## Experimental Kyra/EMC2 scaffold

The [Kyra controller](../../docs/SCUMMVM_KYRA_BACKEND.md) and
[`kyra-agent-v1.json`](kyra-agent-v1.json) adapt the existing ScummVM transport
contract for Kyrandia I and Lands of Lore I. **No native Kyra bridge has been
built or qualified yet.** The synthetic controller tests do not constitute a
ScummVM runtime test. Modified ScummVM binary distribution requires separate
corresponding GPL source and notices.
