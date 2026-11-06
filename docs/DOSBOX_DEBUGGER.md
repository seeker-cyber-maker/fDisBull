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

A prepared local project can retain analyzed routines, actual-game sessions, screenshots and traces. Keep original game files and runtime artifacts in a private local workspace; use your own project, game-directory and backend paths in the examples above.

## Dot-mode

Headless no-pop-ups mode is on by default without the agent having to set
environment variables or extra flags. Its launch profile sets
`SDL_VIDEODRIVER=dummy`, `SDL_AUDIODRIVER=dummy` and
`SDL_RENDER_DRIVER=software`, passes `--nogui`, `--nomenu`, `--noconsole` and
`--fastlaunch`, forces `sdl videodriver=dummy`, `sdl output=surface`,
`sdl showmenu=false` and `sdl usesystemcursor=false`, disables host
quit-warning dialogs with `dosbox quit warning=false` across owned sessions,
and disables SDL/mixer/MIDI sound output. `DOSBoxRPC` also registers a
finalizer that terminates and reaps the emulator process before deleting its
temporary directory if a caller exits without calling `.close()`. This keeps an
owned session from opening desktop windows or waiting for a host confirmation
dialog, and prevents orphaned child processes on normal interpreter exit. It
does not turn native cleanup failures into successful shutdowns. See the
[source running-park verification and native crash investigation](VERIFICATION-DINOPARK-SOURCE-SHUTDOWN-2026-11-03.md).

To request a **view-only** native window for the same
agent-owned DOSBox session, use a backend rebuilt from the current compatible
patch and launch with:

```bash
fdisbull debug dinopark.fdb --executable /path/to/patched/dosbox-x --game-dir /path/to/dinopark --dot-mode
```

For `serve`, add `"window":true` to `debug-launch` parameters; in Python use
`project.debugger(executable, game_dir, version=1, window=True)`. The native
DOSBox IDA endpoint also accepts `--dot-mode` (`--window` remains an alias) / `window=True`. State-fork launches
accept the same option. Other backends reject it. The agent remains the sole
source of guest keyboard and mouse input; window events do not provide manual
game control. The target starts stopped at entry, and an image updates only as
agent commands run the guest. Closing the window can terminate the owned
emulator; the server must not treat saved run history as live state.

A window requires an accessible host display and a compatible native backend
advertising `video.controlled_window: true` and `video.headless: false`; older
backends are rejected before starting the game, not silently treated as safe.
SDL's `dummy` and `offscreen` video drivers (including fallback lists containing
either) are rejected for window requests. Before starting the target, the rebuilt
backend checks the actual selected SDL driver and that an SDL window was created
and shown; it rejects dummy/offscreen fallback or a missing/hidden/minimized window. On
Linux without an explicitly chosen
SDL driver, `DISPLAY` or `WAYLAND_DISPLAY` must be set. Environment variables
alone do not prove the display is reachable or visible to the user; remote and
container sessions may have no display connection. The launch metadata records
`window_requested`, not proof that pixels were seen. No desktop, browser stream,
or display forwarding is configured by fDisBull. A Linux/X11 cloud-desktop
smoke test on a synthetic guest showed a window and
checked host-input filtering, RPC input, paused frames, and cleanup. It does not
qualify every platform or prove general stopped IRQ stability; see the
[verification record](VERIFICATION-SPECTATOR-CLOUD.md).

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
- `guest_exit`: a backend advertising `lifecycle.dos_guest_exit` observed the selected DOS process complete its termination cleanup. See the process evidence below.
- `guest_tsr`: the selected DOS process returned to its parent while remaining resident; this is distinct from normal exit.
- Other native stop reasons, including a trace's bounded pause, remain distinguishable. Trace completeness is reported independently.

The host budget covers the running interval. Pausing, restoring speed, and orderly cleanup add bounded RPC latency, so it is not a hard real-time return deadline. A real DinoPark replay advanced 10,295 guest ms in 445.378 host ms; throughput depends on the game, emulated CPU, and host. The complete title intro is longer than ten seconds; ten guest seconds skips that interval rather than promising the title menu is already ready.

### DOS process completion and debugger cleanup

The rebuilt native backend binds the selected program's actual DOS PSP at its
entry stop. It reports `guest_exit` only after the built-in DOS kernel has
cleaned up that PSP and restored its parent. A child process exiting does not
complete the parent's run. Merely reaching an `INT 20h` or `INT 21h` instruction,
pausing outside the mapped program, closing a debugger context, or reaping the
emulator does not establish this event.

The result has `session.state: "exited"` for the selected program and retains
process evidence in `session.stop_reason.guest_exit` and `stop.guest_exit`:

```json
{"kind":"guest_exit","guest_exit":{"psp":"0x0814","parent_psp":"0x071B","requested_exit_code":37,"resident":false,"source":"DOS_Terminate","stage":"after-process-cleanup"}}
```

`requested_exit_code` is the argument received by `DOS_Terminate`. DOSBox can
subsequently override the status returned to the parent, so this field is not a
claim about that later status. `guest_tsr` has `resident: true`; its retained
resident code and memory are not a normally terminated process.

The parent CPU context has already been restored at this boundary. The event
does not invent a final instruction address or register snapshot for the exited
target. Inspect any required target registers or memory at an earlier verified
breakpoint, then resume to observe completion. The event is retained in the
project's run evidence after the debugger and project close.

A native state saved by the same live session retains the selected PSP binding
when its exact saved bytes are restored. An unrecognized or foreign-session
state disables this exit tracking rather than guessing which restored process
is the target. Cross-session checkpoint restoration can still support its
existing debugger operations; it does not establish this new completion event.

`program_exit` from legacy `session.stop` remains a debugger/session cleanup
event and has no `guest_exit` process evidence. Stopping an already completed
target preserves the observed guest event and does not terminate its DOS parent.
Older backend binaries must be rebuilt; a Python-package update alone cannot
add the kernel notification. This reporting covers the built-in DOS kernel,
not a separately booted operating system or arbitrary protected-mode lifecycle.

## Breakpoints and input

```json
{"id":4,"method":"debug-breakpoint","params":{"run":"RUN","address":"1000:75bc"}}
{"id":5,"method":"debug-registers","params":{"run":"RUN"}}
{"id":6,"method":"debug-screenshot","params":{"run":"RUN","name":"title.png"}}
{"id":7,"method":"debug-click","params":{"run":"RUN","x":75,"y":160,"button":"left","hold_ms":150,"mode_id":5}}
```

Read `mode_id` from your actual screenshot; do not assume the example's value. Click coordinates are native screenshot pixels. Input queued while stopped is consumed on subsequent execution; the release timer uses guest milliseconds. Fast-forward accelerates that guest time too.

### Optional lossless native screenshot encodings

The rebuilt native backend advertises `video.screenshot_encodings`. Existing
calls still request the original RGBA PNG. Select an encoding explicitly:

```python
frame = debug.screenshot("catalogue.png", hooks=False, encoding="png-indexed")
frame = debug.screenshot("catalogue-transfer.png", hooks=False, encoding="rgba-zstd")
```

The JSON method accepts the same `encoding` parameter. `png-indexed` constructs
an exact palette from the completed RGBA snapshot, with no quantization. If a
frame has more than 256 colours or nonopaque pixels, it returns the original
RGBA PNG and an explicit `fallback_reason`. Palette contents are rebuilt for
every screenshot, including palette-only animation.

`rgba-zstd` compresses the completed RGBA8 buffer with Zstandard level 1. It is
advertised only when the backend was built with Zstandard. Configure detects
the library automatically; `--enable-agent-zstd` requires it, and
`--disable-agent-zstd` omits it. The Python client needs the optional
`fdisbull[screenshot]` dependency. Unsupported encodings or a missing decoder
are refused before screenshot preparation hooks run.

Stored screenshots remain PNG for existing exports, grids, scene bundles and
offline consumers. For raw transport, the client validates the compressed
payload hash, exact RGBA layout, bounded frame size and decoded-pixel hash,
then encodes a canonical PNG. Its artifact hash identifies that PNG;
`metadata.transport` separately records the native compressed-payload and raw
pixel hashes. This host conversion is additional work, so a faster native
encoder does not establish a faster stored-screenshot call.

For a wire-only experiment, call `video.screenshot` with `encoding` and optional
`measure:true`. PNG replies retain `format:"png"` and `png_base64`; raw replies
use `format:"rgba-zstd"`, `data_base64`, `pixel_format:"RGBA8"`, `stride`,
`uncompressed_bytes` and `raw_sha256`. `sha256` identifies the encoded payload.
All encodings retain the same completed-frame, mode and guest-tick identity.
`encode_us`, present only when requested, measures native encoding including
palette construction; it excludes snapshot acquisition, hashing, base64,
JSON, IPC, host decoding and persistence. Older backends keep the default PNG
path and do not gain codecs without rebuilding.

### Direct RGBA consumer without PNG conversion

For an in-process pixel consumer, use the Python API:

```python
frame = debug.frame_rgba()  # Requests rgba-zstd explicitly.
rgba = frame.pixel(160, 100)
buffer = memoryview(frame.pixels)  # Immutable RGBA8 bytes, no image encoding.
width, height, stride = frame.width, frame.height, frame.stride
frame_id = frame.metadata["frame_id"]
```

`frame_rgba` returns an `RGBAFrame` with validated pixels and native frame/mode/
tick metadata. `frame.sha256` and `frame.metadata["sha256"]` identify the decoded
RGBA bytes. `frame.metadata["transport"]` separately identifies the compressed
native payload, its encoding and size. The Zstandard path performs neither PNG
loading nor PNG saving. It preserves all existing layout, size, decompression
and hash checks.

This direct call does not run screenshot preparation hooks, create a database
event or artifact, write an image, pause the guest, or advance execution. The
normal guarded RPC path still applies. Own a paused session when comparing
several encodings of one completed frame. Returned bytes are an in-memory
observation; use the existing `screenshot()` API when a persistent PNG artifact
is required. A raw frame object is a Python buffer consumer API, not a JSON tool
reply containing all pixels.

For a comparable direct PNG consumer, select
`debug.frame_rgba(encoding="png")` or `encoding="png-indexed"`; those paths
decode their native PNG into RGBA without re-encoding it or storing an artifact.
The original PNG option also works with older native backends. The default
Zstandard option requires the advertised native codec and optional Python
`fdisbull[screenshot]` decoder; it does not silently substitute another encoding.

### Optional screenshot coordinate grid (0.11.0)

`debug.screenshot("menu-grid.png", grid=True, grid_step=32)` saves a clean native frame and a separate annotated `screenshot-grid` artifact. The JSON equivalent is:

```json
{"method":"debug-screenshot","params":{"run":"RUN","name":"menu-grid.png","grid":true,"grid_step":32}}
```

Numbers across the top are **x**; numbers down the left are **y**. The origin is the top left, x increases rightward, and y increases downward. The grid never rescales or adds a border: a 320×200 frame still uses x=0..319 and y=0..199 for clicks. Do not multiply coordinates because `double_width` or `double_height` is true; those flags describe display presentation, not screenshot/input coordinates. The step defaults to 32 native pixels and accepts integers from **8 to 512**, including 8 for DOS art boundaries and 10 for a decimal grid. Clean screenshots remain the default.

Fine lines and labels have separate spacing. With `grid_step=8`, lines appear every eight pixels and labels every 32; minor lines are faint so they do not obscure the art. Other steps use a label pitch that is a multiple of the line step and at least 32 pixels. `coordinate_grid.label_step`, `x_labels`, and `y_labels` record it. This changes annotation spacing only; click coordinates are never rounded to the grid.

Use the returned `metadata.mode_id` with `debug.click`. A queued click requires subsequent execution to be consumed. A grid helps locate pixels; it does not identify controls or ensure the game has reached the expected menu. Changing video mode can invalidate a previously captured mode ID.

Annotated metadata includes `coordinate_grid.source_artifact`, `source_sha256`, `step`, `origin`, `max_coordinate`, and the exact grid lines. The annotated artifact has its own SHA-256; the original PNG remains unchanged in the project. Grid rendering uses the stored pixels and operates after emulator/project restart too:

```python
with Project("dinopark.fdb") as project:
    grid = project.debug_grid(CLEAN_SCREENSHOT_ID, step=20, name="menu-grid-20.png")
    project.debug_export(grid["artifact"], "/new/path/menu-grid-20.png")
```

The offline JSON method is `debug-grid` with `artifact`, optional `name`, `step` and `target:[x,y]`; the CLI is `fdisbull debug-grid PROJECT ARTIFACT --step 8 --target '[160,160]'`. It accepts original `screenshot` artifacts, so repeated grids derive from the clean source instead of accumulating annotations. No GUI or emulator is used for this operation, and it works with screenshots from the published 0.10.0 backend. Both clean and annotated images count toward the existing project artifact budget. An offline target is a visual marker, not evidence that a click was queued or consumed.

### Capture, mark and click in one action

`debug.click_frame(x,y,grid_step=8)` captures a clean current frame, derives a gridded image marking and labelling that exact coordinate, and queues the click with the captured mode ID. JSON callers use **one** `debug-click-frame` request with `run`, `x`, `y`, and optional `name`, `grid_step`, `button`, `hold_ms`, `mode_id`. The result contains `frame`, `click`, `mode_id`, and `frame_phase:"before_queued_click"`. The frame is the actual pre-click view. If an expected `mode_id` is supplied and differs from the fresh frame, or the target is outside its dimensions, no click is queued.

The `click-frame` script operation has the same fields. Capture/mark/click, bounded execution and an after-frame can all occur in one client `debug-script` request:

```json
{"format":"fdisbull-script-1","steps":[
  {"op":"click-frame","x":160,"y":160,"grid_step":8,"hold_ms":150,"as":"action"},
  {"op":"run","guest_ms":1500,"fast_forward":true,"timeout_ms":5000},
  {"op":"screenshot","name":"after-click.png","grid":true,"grid_step":8}
]}
```

The coordinate is an explicit input. When an agent must choose a new target from pixels, it still has to inspect a frame before sending that coordinate; scripts do not contain image recognition or invoke an agent inside the emulator. The compound action removes separate client calls for capturing/marking/queuing an already chosen point. Internal native RPCs still occur while the guest is paused, and a later run consumes the queued input. Clean source images, the target marker and the input receipt remain linked in project history.

Execution breakpoint placement pins the static version and instruction context, checks the on-disk executable against the project's source hash, derives the runtime DOS load segment from observed entry registers, adjusts MZ relocation words where applicable, and compares expected bytes with live memory before creating the native breakpoint. Addresses outside the mapped original image, missing stored instructions, byte mismatches, wrapping translations, and patched static versions are rejected explicitly.

The current source launches the **original unpatched MZ or explicitly selected COM version** only. It does not silently apply a child project's patches to a game. Use `version:1` when a project's latest version is a child. Runtime evidence remains attached to its launch version and is not copied into patched children.

### Explicit COM profile

Use `fdisbull import GAME.COM PROJECT --image com` (or JSON `import` with `image: "com"`). An extension alone does not identify a COM program; explicit selection is required. Inputs must contain 1–65,280 bytes and cannot have an MZ signature. `--load-segment` identifies the static PSP segment (default `0x1000`). Only the original file bytes are mapped at PSP:0100; the PSP, stack, allocation beyond the file, and later dynamically loaded or overlaid code are not fabricated. Initial SP depends on DOS allocation and is unknown statically. Launch checks CS:IP, the COM startup segment registers, and up to the first 16 file bytes in guest memory; static execution breakpoints separately compare the instruction bytes at placement. The numeric address translation is not evidence that later self-modified or dynamically loaded bytes remain the original code. The selected source hash and original version are required, and long or non-COM guest names use guarded disposable `.COM` aliases. This profile does not statically map additional game executables or resources.

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

### Required native acceptance

Ordinary `python -m pytest -q` is useful without an emulator and intentionally skips native tests when `FDISBULL_DOSBOX` is absent. For native acceptance, use the existing tests with `--require-native`. That option fails before collection if the environment variable is missing or does not name an executable file; a stock or incompatible executable then fails the actual integration tests rather than substituting a mock.

From the repository root, select the separately built **layers backend** to test the current development source:

```bash
FDISBULL_DOSBOX=/absolute/path/to/layers/dosbox-x \
  python -m pytest -q --require-native \
  tests/test_debugger.py tests/test_code_layers.py tests/test_screenshot_grid.py
```

The current local Mac acceptance is **32 passed**, with native CPU, screenshots, checkpoint restart, static-patch isolation and process cleanup exercised. To check compatibility with the published 0.10 backend, run the same command without `tests/test_code_layers.py`: that backend supports the original debugger and optional screenshot grids but has no execution-layer capability, and the corresponding local check reports **15 passed**. Build each profile from its declared pristine DOSBox-X commit using either the [stable backend instructions](../experimental/dosbox-x/README.md) or the [layers instructions](../experimental/dosbox-x/layers/README.md); do not apply both complete patches to one checkout.

The separate [native CI workflow](../.github/workflows/native-debugger.yml) checks out that pinned upstream commit, checks the complete patch and resulting source-file hashes, compiles the heavy-debug SDL2 backend, records its new Linux executable identity, and runs these same tests in both profiles. It retains logs and JUnit results without uploading games, machine states, databases or the emulator executable. Native acceptance is established by a successful run for the release commit, separately from the broad Python/package job where native skips are allowed. See the [release verification and CI links](VERIFICATION-0.11.md).

The tests use authored MZ inputs. The source-only DinoPark replay requires the user's own game and remains a separate actual-game acceptance step. Native test success does not establish all-game compatibility, timing equivalence, or security isolation. Do not run less trustworthy targets on the assumption that headless emulation is a sandbox; checkpoint restore does not roll back mounted host files.

`tests/test_debugger.py` tests source/version rejection and the live ownership contract. Set `FDISBULL_DOSBOX=/absolute/path/to/patched/dosbox-x` to additionally run real-MZ tests for relocation-aware breakpoints, observed trace addresses, timeout/pause/speed restoration, runtime-byte mismatch rejection, restart/export, patch isolation, and server EOF cleanup.

`examples/dinopark/verify_debugger.py --executable PATH --game-dir DIR --output NEW_DIR` replays the actual-game path through fDisBull's public JSON interface. It creates a project and exports its evidence only after server/emulator exit. No game data is shipped with the script. The actual-game session reached Real Estate after title, bank, and city interactions; a full playthrough and sound are not established. Native state editing/reinjection and the separate in-game load-menu route are covered by the later state verification below.

The backend's absolute input remains scoped to built-in real/v8086 INT33. Headless operation is not security sandbox isolation. Native Windows integration, arbitrary guest drivers, complete memory-access tracing, and performance guarantees remain outside this verified scope.

## Native states, editable dumps, scripts, and data breakpoints

See [reusable debugger routes and native checkpoints](DEBUGGER_SCRIPTS.md) for native save/load states, isolated state forks with verified RAM/register edits, bounded JSON routes, and `x/r/w/rw` breakpoint modes.

`debug.registers()` and `debug-registers` return hexadecimal runtime `cs` and `ip` aliases at the top level. The original `segments.cs` and `instruction_pointer` fields remain available. `project_address` is the separately mapped static address.

For the supplied investigation, `debug.breakpoint("0x471a6", access="w", length=8)` arms byte watches across the proposed four-word block without requiring analysis at that data range. `run(timeout_ms=..., fast_forward=True)` waits for a write or pauses on timeout. Inspect `session.stop_reason.data_access` for the actual access and originating instruction; a timeout does not establish that a counter is never written. Execution breakpoints at routines such as `38ff:211f` still require analysis first.
