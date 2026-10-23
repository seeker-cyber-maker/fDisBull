# Reusable debugger routes and native checkpoints

A native checkpoint is an editable machine-state artifact, like a restorable crash dump. It can be inspected, forked with explicit RAM/register changes, and reinjected into a compatible debugger session.

A route is a bounded JSON script executed by the foreground debugger owner. It can navigate menus, load an in-game save with mouse clicks, set breakpoints, run until a hit, capture evidence, and restore an emulator checkpoint within the same run. No Python, shell commands, expressions, or arbitrary RPC calls execute from a route.

There are two different saved states:

- An **in-game save** such as `DINOSG.000` is a game-owned file loaded through the game's menu. Its meaning belongs to DinoPark.
- An **emulator checkpoint** stores DOSBox-X's native machine serialization inside the local fDisBull project. It restores CPU, memory, and the devices covered by DOSBox-X's serializer. It is tied to the original project version, exact emulator binary, launch profile, load segment, and game directory. It can be restored in an existing run or after launching another compatible session.

Native state support comes from [DOSBox-X](https://dosbox-x.com/wiki/Home.html). Cross-version, cross-platform, other CPU-core, arbitrary disk-image, and arbitrary-device compatibility is not established. A native state is not a security sandbox or a complete disk snapshot.

## JSON API

The existing `fdisbull serve --project PROJECT` and `fdisbull debug PROJECT --executable DOSBOX --game-dir DIRECTORY` accept:

| Method | Parameters | Result |
| --- | --- | --- |
| `debug-save-script` | `name`, `script`, optional `version` | Immutable script ID and SHA-256, stored with the project version |
| `debug-scripts` | Optional `version` | Saved script identities |
| `debug-script` | `run`, exactly one of `script` or `script_id`, optional `timeout_ms` | Step results and saved execution-report artifact |
| `debug-save-state` | `run`, optional `name` | Native state artifact ID |
| `debug-load-state` | `run`, `artifact` | Restored CPU identity and restore-history event |
| `debug-state-info` | `artifact` | Offline native-component sizes, saved registers, identity, and derivation |
| `debug-fork-state` | `artifact`, `executable`, `game_dir`, optional `name`, `memory`, `registers` | Derived native checkpoint captured in an isolated paused emulator |
| `debug-memory` | `run`, `address`, optional `cs`, `length` | Runtime bytes at a mapped project address |
| `debug-breakpoint` | `run`, `address`, optional `cs`, `access`, `length` | Execution breakpoint or a group of byte-address data watches |

Saved scripts can also be listed with `fdisbull debug-scripts PROJECT`. `fdisbull debug-save-script PROJECT NAME 'JSON'` stores one without launching the emulator. Python callers use `project.debug_save_script`, `project.debug_scripts`, `debug.script`, `debug.save_state`, `debug.load_state`, and `debug.memory`.

A script uses `format: "fdisbull-script-1"` and a `steps` array. Supported `op` values are `run`, `click`, `screenshot`, `trace`, `breakpoint`, `delete-breakpoint`, `save-state`, `load-state`, `registers`, `memory`, `status`, `assert`, and `repeat`. Other fields are the corresponding Python method's keyword arguments. `as` names a result; a string such as `$checkpoint.artifact` substitutes that result field in a later step. List indices also work, for example `$watch.breakpoints.0.breakpoint_id`. References are values, with no expression evaluation or string interpolation.

```json
{
  "format": "fdisbull-script-1",
  "steps": [
    {"op": "save-state", "as": "checkpoint"},
    {"op": "repeat", "count": 3, "steps": [
      {"op": "run", "guest_ms": 1000, "timeout_ms": 5000, "fast_forward": true},
      {"op": "load-state", "artifact": "$checkpoint.artifact"}
    ]},
    {"op": "registers", "as": "cpu"}
  ]
}
```

`assert` compares `value` with `equals`. A `run` step expects `guest_time` when `guest_ms` is supplied, otherwise `breakpoint`; specify `expect` to require another outcome. An unexpected timeout or an incomplete trace stops the route and saves the failed step report. Each screenshot, trace, checkpoint, script source, and execution report is retained as a separate project artifact. The complete script is structurally validated before the first guest mutation. Execution stops at the first failure; prior actions remain recorded and are not rolled back automatically.

Limits are 1 MiB of script JSON, eight nesting levels, 1,000 expanded steps, and a script dispatch budget of at most 600,000 host milliseconds. Bounded run/trace calls use the remaining budget. An already dispatched native serialization or RPC is governed by its own RPC deadline and is not preempted by the script dispatch budget.

## Edit a saved machine state and reinject it

`debug-fork-state` is available through JSON, the one-shot CLI, and `project.debug_fork_state`. It launches a separate emulator, restores the source checkpoint, checks **every** expected memory/register value, applies the edits without executing guest instructions, verifies readback, and captures a new native checkpoint. That temporary emulator is closed afterward. A live run in another server is not changed by forking. The original checkpoint remains immutable; the derivative records its parent artifact/hash and before/after edits.

For example, given a checkpoint where a word at a proposed counter address is `03 00`:

```json
{
  "method": "debug-fork-state",
  "params": {
    "project": "/absolute/path/dinopark.fdb",
    "artifact": "PARENT_STATE_ID",
    "executable": "/absolute/path/dosbox-x",
    "game_dir": "/absolute/path/game",
    "name": "counter-experiment.sav",
    "memory": [
      {"address": "0x471a6", "expected_hex": "0300", "data_hex": "0400"}
    ]
  }
}
```

The address and expected value are experimental inputs, not a claim about the game's counter layout. A mismatch refuses the fork. Register edits use a mapping such as `"registers": {"eax": {"expected": "0x1234", "value": "0xbeef"}}`. Supported names are `eax`, `ebx`, `ecx`, `edx`, `esi`, `edi`, `ebp`, `esp`, `eip`, the six segment registers, and `flags`. Values are unsigned integers or explicit `0x` strings; real-mode segment/IP/flags widths are enforced. Memory edits are limited to the mapped original MZ module, do not resize memory, require nonoverlapping ranges, and total at most 65,536 bytes across at most 64 edits. This interface does not edit arbitrary serialized device structures.

Use the returned artifact ID with `debug-load-state` to inject the derivative into an existing compatible run. Inspect its registers and memory while paused, set breakpoints, and trace or resume it. A route can insert it with `{"op":"load-state","artifact":"DERIVED_STATE_ID"}` at any step. `debug-state-info` inspects saved registers, native components, and derivation without launching an emulator.

RAM edits change the machine snapshot, not static project bytes or code versions. Execution breakpoint placement still checks current instruction bytes against static disassembly. An edited code instruction may therefore be refused until a suitable static representation exists; runtime traces retain the actual executed instruction. There is no inferred promotion of runtime edits into the static source.

## Breakpoint access modes

`access` defaults to `x`. An execution breakpoint requires an analyzed instruction and verifies its relocated bytes before placement. Data watches do not require analyzed instructions. They accept mapped module data addresses without requiring disassembly or equality with the original bytes.

| Access | Trigger |
| --- | --- |
| `x` | Execution reaches the selected instruction |
| `r` | A guest CPU data read overlaps a watched byte |
| `w` | A guest CPU data write overlaps a watched byte, including same-value writes |
| `rw` | Either data access |

Data watches currently require the normal CPU core in real mode; fDisBull selects that core explicitly. `length` is 1–256 bytes and creates one native breakpoint per byte; delete the returned IDs individually. Stops occur after the CPU instruction completes and before the following instruction. A repeated instruction such as `REP MOVSW` can finish its entire copy before stopping. Overlapping byte watches report one selected overlap; their IDs do not represent independent write operations or queued stops. The stop reason includes the access address, width, direction, and originating instruction address, plus its mapped project address. Current registers are the post-instruction registers. Instruction fetch, debugger inspection, and host-side reads are excluded. This is scoped CPU data-access instrumentation, not complete device/DMA or protected-mode memory tracing.

## Checkpoint boundaries

States are captured only while stopped and after pending mouse releases complete. Each checkpoint includes a hash manifest of mounted regular game files. Restoring requires an exact manifest match; native flagged-file save/restore is disabled for agent state operations. Restore does not roll back save files or other host files. If a route writes an in-game save, preserve and restore those matching game files separately before restoring an older checkpoint.

A failed native restore closes the session because partial deserialization can leave an inconsistent machine. Successful restore verifies CPU registers, clears pending input, records provenance, and invalidates the cached framebuffer. Run enough guest time for a completed frame before taking another screenshot; a stale pre-restore picture is never returned. Debugger breakpoints are session-owned controls and are not imported from the native checkpoint; existing watches remain configured, while a fresh session starts without the old session's breakpoints.

State artifacts can contain game code, data, and filenames. Keep the project database and any exported `.sav` files local. The repository's DinoPark routes include no game or state bytes.

## DinoPark investigation supplied by the user

The supplied report proposes loading STF7, watching the counters at project linear address `0x471a6`, and tracing the writer around `38ff:211f`; it separately proposes observing division and multiplication routines for revenue. The revenue formula remains an investigation hypothesis. The [parking-purchase experiment](PARKING_COMMIT.md) now records the observed writer and OK-versus-tick timing for the available pmm save. The local game copy initially contains eight `DINOSG.000`–`.007` saves; the reported thirteenth STF7 entry is not present there.

`examples/dinopark/routes/load-dialog.json` is a route from a fresh game entry to OLD GAME and a checkpoint of its dialog. Menu coordinates and save ordering are game-specific. Inspect a captured dialog before adding scroll/select clicks for another save collection. Use `debug-memory` and `r/w/rw` watches to observe the proposed counters; actual runtime observations should be saved separately from static annotations.

Register snapshots expose top-level runtime `cs` and `ip` aliases as hex strings, alongside `segments.cs`, `instruction_pointer`, and mapped `project_address`.
