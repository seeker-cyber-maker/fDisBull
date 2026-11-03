# Experimental ScummVM Gob debugger

The `scummvm-gob` backend is a separate Gob Inter_v3 adapter. It runs the real
ScummVM engine and retains its evidence separately from original DOS execution.
The sidecar is built from ScummVM 2026.4.0, upstream commit
`7d2709da5136866589f7602f5f5a7b17de03420e`. The earlier AGI backend and its
separately pinned runtime remain available.
The launch surface is limited to the Lost in Time family IDs `lit`, `lit1`
and `lit2`; other Gob interpreter families are refused before process launch.
English US v1.10 DOS CD resources are the actually qualified input here.

The dated verification receipt records the November 1 implementation, preserved
in commit `b028527`, and its private package. Subsequent integration with current
main and handoff validation are separate from that frozen runtime experiment.

## Launch and identity

Create a project from the original interpreter executable with automatic MZ
loading. Do not force the packed executable into a raw 16-bit image. Keep the
project outside the original game directory. Supply a separately prepared
patched Gob executable:

```text
fdisbull debug PRIVATE.fdb --backend scummvm-gob --game-id gob:lit \
  --language us --platform dos --executable /private/patched-scummvm \
  --game-dir /private/lost-in-time-en
```

The qualified English input is detected as Lost in Time v1.10, language `us`
and platform `pc`. `dos` is accepted as the platform launch alias. Generic `en`
can select an unrecognized fallback in ScummVM; this adapter refuses unknown or
mismatched detection rather than presenting it as the qualified edition.

The input manifest binds the complete original file set and runtime executable.
The initial manifest policy refuses symbolic links. A multilingual CD directory
and linked audio need separately qualified input identities; the folder name
alone does not select its language.

## Script and variable addresses

The execution context is `gob-vm`. Locations contain the current TOT name,
loaded generation, opcode family and byte offset from the original TOT-file
start, including its 128-byte header. They are not original DOS CPU addresses.
`debug-code` returns verified encoding bytes without claiming a general Gob
decoder. Trace spans cover opcode encoding, not complete decoded operands.

ScummVM loads a code prefix ending before the TOT text/resource tables. The
adapter independently reads the original STK/ITK or loose-file candidate,
decompresses it, derives that boundary from the original header, and checks the
loaded prefix byte-for-byte. Evidence keeps both the full decompressed member
hash and the loaded-prefix hash, original packed span/compression, actual native
lookup receipt and loaded generation. Same-named or changed resources cannot
silently replace the original source binding.

Gob variables are overlapping views of an allocated byte arena. Use
`debug-read-variable` and `debug-write-variable` with `offset`, `width`, `signed`
and `endian`, or the corresponding Python methods. Supported widths are 1, 2
and 4 bytes. Writes check their expected bytes before mutation, retain the
before/after values and identify diagnostic assistance. A write requires a
paused opcode boundary; an input/backend yield is not that boundary. A bounded
step can establish a qualifying stop before a diagnostic edit.

Scene comparisons can read a typed variable directly:

```json
{"compare":{"left":{"engine_variable":{"offset":12637,"type":"i8"}},"op":"eq","right":1}}
```

`before` can retain that typed reference as an action baseline. Each observation
caches its reads and refuses a changed state revision rather than mixing states.
Gob scene identity binds the backend, full input manifest, runtime executable
and loaded/decompressed script hashes. A generation change invalidates stale
live input while allowing the same immutable scene to be requalified after a
byte-identical script reload.

## Execution, input and frames

The adapter exposes finite run, step, pause/resume, source-bound breakpoints,
typed range watches, capped trace and actual hotspot dispatch receipts.
Function, draw and gob dispatch families retain correlated starts and returns.
Nested completion does not imply that a pending caller completed. Breakpoint
resume skips only the boundary that caused the stop; deleting a stored stale
breakpoint does not require reloading its old script.
Repeated registration of the same native breakpoint or watch returns its
existing wrapper ID after revalidation. Typed watches sharing a byte range and
access mode share that control, including signed/unsigned aliases.

Watches cover instrumented scalar, string and copy accessors with byte-range
overlap. Direct pointers and uninstrumented stream I/O remain outside their
coverage. A trace reports truncation; a budget stop is not stable completion.

Keyboard and mouse operations report queued delivery separately from consumed
game actions. `debug-hotspot-events` reads capped actual selection/handler
receipts. Polling those receipts is passive. The foreground JSON server also
supports `debug-run-async`, `debug-pause` and `debug-run-result`; it owns and
reaps the process when stopped.

Named native scene actions and waits use the session's explicit
`native_hooks_available` capability. Both ScummVM adapters declare it false;
an explicit `stop_on_hook=True` request is refused. This does not disable their
VM breakpoints, range watches or trace. Queued scene inputs, including popup
acknowledgments, remain attached to retained failures if outcome waiting raises.
A known popup can advance while its acknowledgment is pending, but it must
disappear before dismissal succeeds. A different blocking modal stops the wait.

Frames come from the real committed headless framebuffer. PNGs persist in the
project and can be exported after the process closes and the project reopens.
Display metadata retains game/surface dimensions, coordinate scale, scroll and
screen deltas. The tested title uses 640x400 and gameplay uses 320x200; that is
an actual mode change. Verify the current frame and transform before input.

## Nail-under-furniture regression

The early hold stool nail is distinct from the later cabin nail and desk-chair
key. Its local rectangle exists before its underside presentation is open.
That table entry alone cannot qualify visibility or an input target.

For the tested English source, qualify current script, camera 0, subview 3,
selected item, current enabled/intersecting active rectangle and current popup
origin. The stool-underside local rectangle is `[87,27,20,20]`; translate using
the current origin at signed 32-bit arena offsets 220 and 224, and verify the
result against the current active raw-target-1 rectangle at
`17964 + 8 * 1`. Reopening at another position must re-resolve the origin.
The same raw target number in the stool-front view identifies a different
interaction. Neither historical absolute coordinates nor local-table presence
alone establishes current availability.

## Qualified comparisons and limits

Poster and bilge models are selected shared-IL branches, not complete native
handlers. Compare only each model's retained effects at its declared boundary.
In particular, water response text can be visible before acknowledgment commits
its checked flag. Pump drain can commit before the final message/view closes.
Check presentation, selection, hotspot registration and completion separately.

Native Gob save/load checkpoints, exact machine snapshots, loaded-script edits
and AGI cycle operations are explicitly unsupported. Original files remain
unchanged. Virtual ScummVM time is not established as original DOS timing.
Pure Z execution does not itself perform or verify native Gob instructions.

The repository's `experimental/scummvm/gob-build-headless.sh`,
`gob-headless-bridge.patch` and `gob-source-manifest.json` preserve the source
pin, build procedure and native qualification. Native binaries, licensed game
resources, saves, FDBs, captures and derived game-text exports stay outside the
Python distribution. Source experiment support is separate from a release or
shared-installation activation.

The [verification receipt](evidence/scummvm-gob-2026-11-01/verification.json)
records final source hashes, native identity and test scope. A real DOS/Gob/AGI
focused gate passed 100 tests; the expanded popup/named-scene gate passed 18.
The final whole macOS run reported 2,702 passed, 127 skipped, five failed and
23 errors. Every failure/error node matched the preserved unchanged 0.29.0
baseline: Linux ELF/GCC fixtures, a case-insensitive filesystem fixture and LLDB
wall-time tests. The whole suite is therefore not green. No Linux CI or release
qualification is implied by these local experimental checks.

See the [Lost in Time comparison](SCUMMVM_LOSTTIME_COMPARISON.md) for the existing
branch-model checks and independently graded fresh Z reconstructions.
