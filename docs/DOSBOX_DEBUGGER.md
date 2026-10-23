# Project DOSBox debugger

The 0.10.0 build integrates the separately built DOSBox-X agent with fDisBull projects. Live sessions run in the foreground `serve` process or a Python context. Screenshots, traces, run metadata, and operation receipts are stored inside the SQLite `.fdb`; exporting saved evidence never launches an emulator.

The backend must be built with the current `experimental/dosbox-x/headless-agent.patch`, including `execution.timing`. A stock DOSBox binary does not provide this protocol. The backend executable is supplied explicitly; no emulator, game, or native executable is bundled in the Python tool package. The current inherited-pipe integration supports macOS/Linux POSIX hosts; native runtime acceptance was performed on macOS Apple Silicon.

## Launch

Import the executable, then analyze code addresses where you want execution breakpoints. Data watches do not require disassembly. CS:IP strings are hexadecimal disassembly addresses in the project's load context:

```bash
fdisbull import /path/to/dinopark/DINOPARK.EXE dinopark.fdb --load-segment 0x1000
fdisbull analyze dinopark.fdb --start 1000:75bc --max-instructions 12
fdisbull disasm dinopark.fdb --address 1000:75bc --lines 4
fdisbull debug dinopark.fdb --executable /path/to/patched/dosbox-x --game-dir /path/to/dinopark
```

In 0.10.0 an explicit DOS seed is attempted first within that call's instruction budget, even when an older recursive queue is pending. `analyze(start="334b:0aec", max_instructions=1)` can prepare that one valid instruction for breakpoint placement. Remaining recursive work is retained and the analysis still reports its pending status. This does not bypass explicit data definitions, address validation, or runtime byte verification.

`debug` emits a launch result containing a `run` ID and then accepts the existing fDisBull JSON-lines request format on stdin. `serve --project dinopark.fdb` can also launch explicitly:

```json
{"id":1,"method":"debug-launch","params":{"executable":"/path/to/patched/dosbox-x","game_dir":"/path/to/dinopark","version":1}}
```

Use the returned ID in place of `RUN` below. One-shot `request` calls cannot retain live sessions; live operations require the same foreground server. EOF, server exit, `debug-stop`, or Python context exit stops and reaps owned emulators. Saved history is explicitly not a liveness check; it cannot reattach an emulator after server restart.

The prepared local DinoPark project is `/Users/tiga/Documents/ChatGPT/fDisBull/examples/dinopark/local/dinopark-debug.fdb`. It includes the analyzed mouse-polling routine, a completed actual-game session, five guest screenshots, and a 512-instruction trace. The current game directory is `/Users/tiga/Documents/ChatGPT/fDisBull/examples/dinopark/local/dosbox-20261023/dinopark`; the backend is `/Users/tiga/Documents/ChatGPT/fDisBull/.recovery/2026-10-23/dosbox-checkout/src/dosbox-x`.

## Fast-forward and bounded runs

Skip approximately ten **guest seconds**, using DOSBox's native fast-forward control:

```json
{"id":2,"method":"debug-run","params":{"run":"RUN","guest_ms":10000,"fast_forward":true,"timeout_ms":5000}}
```

`guest_ms` is an emulated-time target. `timeout_ms` is a separate host-time execution budget. The adapter polls the emulation-thread clock; some guest-time overshoot is expected and the actual delta is returned. The call pauses at the guest target, a breakpoint, another native stop, or its host timeout. Normal/prior speed is restored on every normal completion, breakpoint, or timeout; an uncertain RPC failure closes the emulator rather than leaving it running uncontrolled.

For **run until a breakpoint**, omit `guest_ms`:

```json
{"id":3,"method":"debug-run","params":{"run":"RUN","fast_forward":true,"timeout_ms":3000}}
```

Inspect `outcome`, not just whether the request succeeded:

- `breakpoint`: an actual native breakpoint fired; `session.stop_reason` identifies it and includes its mapped project address.
- `guest_time`: the requested guest duration was reached.
- `timeout`, with `timed_out:true`: no earlier stop satisfied the call; the target was paused. A timeout is never converted to a breakpoint hit.
- Other native stop reasons, such as program exit or a trace's bounded pause, remain distinguishable. Trace completeness is reported independently.

The host budget covers the running interval. Pausing, restoring speed, and orderly cleanup add bounded RPC latency, so it is not a hard real-time return deadline. A real DinoPark replay advanced 10,295 guest ms in 445.378 host ms; throughput depends on the game, emulated CPU, and host. The complete title intro is longer than ten seconds; ten guest seconds skips that interval rather than promising the title menu is already ready.

## Breakpoints and input

```json
{"id":4,"method":"debug-breakpoint","params":{"run":"RUN","address":"1000:75bc"}}
{"id":5,"method":"debug-registers","params":{"run":"RUN"}}
{"id":6,"method":"debug-screenshot","params":{"run":"RUN","name":"title.png"}}
{"id":7,"method":"debug-click","params":{"run":"RUN","x":75,"y":160,"button":"left","hold_ms":150,"mode_id":5}}
```

Read `mode_id` from your actual screenshot; do not assume the example's value. Click coordinates are native screenshot pixels. Input queued while stopped is consumed on subsequent execution; the release timer uses guest milliseconds. Fast-forward accelerates that guest time too.

Execution breakpoint placement pins the static version and instruction context, checks the on-disk executable against the project's source hash, derives the runtime MZ load segment from observed entry registers, relocates the expected instruction bytes, and compares those bytes with live memory before creating the native breakpoint. Addresses outside the mapped MZ image, missing stored instructions, byte mismatches, wrapping translations, and patched static versions are rejected explicitly.

The first implementation launches the **original unpatched MZ version** only. It does not silently apply a child project's patches to a game. Use `version:1` when a project's latest version is a child. Runtime evidence remains attached to its launch version and is not copied into patched children.

For the verified DinoPark image, project `1000:75bc` becomes runtime `0824:75bc`; the CPU may report equivalent alias `0eb7:0c8c`. Both runtime forms name the same linear byte. Source bytes are verified at placement, not inferred from matching numeric addresses.

## Save and export traces/screenshots

Remove a recurring breakpoint before tracing through its loop if you want a full instruction budget:

```json
{"id":8,"method":"debug-delete-breakpoint","params":{"run":"RUN","breakpoint_id":"bp-1"}}
{"id":9,"method":"debug-trace","params":{"run":"RUN","name":"mouse-input.json","count":512,"timeout_ms":3000}}
{"id":10,"method":"debug-artifacts","params":{"version":1,"run":"RUN"}}
{"id":11,"method":"debug-stop","params":{"run":"RUN"}}
```

Trace events retain native addresses, instructions, and register deltas. Events within the original loaded module additionally receive project linear and segmented addresses. Driver/BIOS/out-of-image events stay unmapped; a load-offset mapping does not establish that self-modified or overlaid code still matches static instructions. Register values in the backend trace are observations before the listed instruction.

Each artifact has an ID, SHA-256, size, launch version, and runtime metadata. A trace can be partial after an early breakpoint or timeout; inspect `complete` and `event_count`. Limits are 10,000 trace instructions, 16 MiB per screenshot/trace artifact (128 MiB per native state), and 256 MiB of runtime artifacts per project.

After closing and reopening the server or shell, list/export using artifact IDs:

```bash
fdisbull debug-runs dinopark.fdb --version 1
fdisbull debug-artifacts dinopark.fdb --version 1
fdisbull debug-export dinopark.fdb ARTIFACT_ID /new/path/to/frame.png
```

Exports verify the stored hash and refuse to overwrite existing files, the project, or SQLite sidecars. The project database alone retains the artifact bytes; external exports are optional copies.

## Python API

```python
from fdisbull.project import Project

with Project("dinopark.fdb") as project:
    with project.debugger("/path/to/patched/dosbox-x", "/path/to/dinopark", version=1) as debug:
        skipped = debug.run(guest_ms=10000, fast_forward=True, timeout_ms=5000)
        screenshot = debug.screenshot("after-intro.png")
        breakpoint = debug.breakpoint("1000:75bc")
        stopped = debug.run(fast_forward=True, timeout_ms=3000)
        if stopped["outcome"] == "breakpoint":
            debug.delete_breakpoint(breakpoint["breakpoint_id"])
            trace = debug.trace("input.json", count=512, timeout_ms=3000)
    project.debug_export(screenshot["artifact"], "/new/path/to/after-intro.png")
```

Native CPU observations and guest screenshots are stored separately from static facts. They do not mark an analysis queue stable, create inferred functions, or rewrite static instruction bytes.

## Verification and limits

`tests/test_debugger.py` tests source/version rejection and the live ownership contract. Set `FDISBULL_DOSBOX=/absolute/path/to/patched/dosbox-x` to additionally run real-MZ tests for relocation-aware breakpoints, observed trace addresses, timeout/pause/speed restoration, runtime-byte mismatch rejection, restart/export, patch isolation, and server EOF cleanup.

`examples/dinopark/verify_debugger.py --executable PATH --game-dir DIR --output NEW_DIR` replays the actual-game path through fDisBull's public JSON interface. It creates a project and exports its evidence only after server/emulator exit. No game data is shipped with the script. The actual-game session reached Real Estate after title, bank, and city interactions; a full playthrough and sound are not established. Native state editing/reinjection and the separate in-game load-menu route are covered by the later state verification below.

The backend's absolute input remains scoped to built-in real/v8086 INT33. Headless operation is not security sandbox isolation. Native Windows integration, arbitrary guest drivers, complete memory-access tracing, and performance guarantees remain outside this verified scope.

## Native states, editable dumps, scripts, and data breakpoints

See [reusable debugger routes and native checkpoints](DEBUGGER_SCRIPTS.md) for native save/load states, isolated state forks with verified RAM/register edits, bounded JSON routes, and `x/r/w/rw` breakpoint modes.

`debug.registers()` and `debug-registers` return hexadecimal runtime `cs` and `ip` aliases at the top level. The original `segments.cs` and `instruction_pointer` fields remain available. `project_address` is the separately mapped static address.

For the supplied investigation, `debug.breakpoint("0x471a6", access="w", length=8)` arms byte watches across the proposed four-word block without requiring analysis at that data range. `run(timeout_ms=..., fast_forward=True)` waits for a write or pauses on timeout. Inspect `session.stop_reason.data_access` for the actual access and originating instruction; a timeout does not establish that a counter is never written. Execution breakpoints at routines such as `38ff:211f` still require analysis first.
