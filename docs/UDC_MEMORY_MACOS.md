# Native macOS graphics and input over recovered memory UIL

The native profile emits ARM64 Mach-O blocks and an AppKit application from the
same bounded-memory UDL/UIL used by the browser pilot. Game rules, rendering and
input interpretation remain ordinary UIL. Platform adapters own the window,
palette presentation, physical key mapping, pointer coordinates and monotonic
clock. Neither the compiler nor the AppKit adapter contains Snake movement,
food placement or RNG algorithms.

## Source identities and native realizations

`build-memory-macos-shell` accepts `selections`, `plan`, `initial` and a new
private `destination`, with optional `cuts`, `regions`, `c_compiler` and
`with_app`. Its Python entry point is
`udc_memory_macos.build_memory_macos_shell`. The existing exact source selections
are resolved again before emission. Their persisted Wasm/WebGPU target metadata
is preserved as provenance; it is not relabelled as a stored native layer.
Every emitted native realization has its actual program digest, source digest
and the explicit `macos-arm64-memory-1` target.

The `fdisbull-memory-macos-shell-1` manifest retains the canonical program,
source endpoints, derived execution view, cut and region definitions, compiler
identity, commands and artifact hashes. `native_execution: false` is a build-only
statement. Run and compare the output before adding execution evidence.

The backend reuses the established macOS compiler/target machinery and extends
it with the separate bounded-memory profile. `udc_memory_native` lowers unsigned
expressions, indexed memory and bounded control flow to generated C, then invokes
the local compiler for ARM64. It uses ordered expression temporaries, preserving
left-to-right faults, wrapping arithmetic and masked shifts. Every block owns a
heap rollback copy and returns complete/refused status, exact statement and
loop-condition charges, and an optional successful continuation token.

`build_native_memory_block` separately emits a dylib and a streaming native probe
for one function. It does not run an emulator or interpret UIL at runtime.

## Orchestration and ownership

The native shell uses one synchronous main-thread owner. Calls from other
threads and reentrant mutations refuse. Its C API stages an owned arena, applies
only declared input patches, invokes selected native blocks, checks logical
output footprints and application invariants, then commits declared state and
frame ranges together. Scratch and immutable inputs are not committed. Failed
calls preserve the previous arena and revision.

Exact cuts use the same separately derived prefix, selected child and lexical
continuation as the browser. A single source caller budget covers all phases and
children, excluding only the two introduced suspension statements. Intermediate
phases are private; application guards do not introduce extra observation points
inside a function. The current cut restrictions, including no loop ancestor or
live local values crossing a boundary, remain unchanged.

Named regions retain explicit exact/default versus intentional-variant policy.
The native selector changes the realization without reseeding or editing game
state. The captured selection governs a complete operation. A region must
preserve every other word and satisfy its declared output range. Native execution
is serialized rather than an asynchronous GPU job protocol.

`fdb_words()` is a borrowed, read-only main-thread view valid until the next
mutation. Use `fdb_copy_words` for an owned snapshot. The AppKit adapter copies
committed words before drawing and before final teardown. Explicit close is
terminal and clears the runtime arena. A logical quit observation is captured
before AppKit closes the core, so its final state remains inspectable.

## Native graphics and input adapters

AppKit displays the unchanged indexed framebuffer through the supplied palette,
using nearest-neighbor drawing and a fitted intrinsic aspect ratio. Image-edge
antialiasing is disabled so fractional letterbox positions do not introduce
blended colors. At a mathematically exact tie between source pixel centers,
either adjacent nearest source pixel is valid; at an exact destination-center
tie on the image boundary, binary coverage may select the source edge or black
letterbox. Qualification checks only those finite geometric tie sets, without a
channel tolerance or blended colors. Input hit tests still use a half-open
rectangle. Intrinsic and integer-scaled views must
remain byte-exact. The source
frame is row-major with its origin at the top left. Pointer conversion applies
the same fitting transform, including letterboxing. A press outside the drawn
frame is ignored; a captured drag/release is clipped to the frame bounds.

Physical macOS keycodes map to the declared keymap. Only a focused game view
consumes game keys. Command, Control and Option shortcuts remain host commands.
Mouse buttons use the declared low-three-bit interface, with press/release edges
and focus-loss release. The monotonic clock is converted to low-16-bit ticks
through `plan.events.tick_ms`; the UIL still decides when a game step occurs.
No catch-up movement or game-specific timing rule is added to the host.

App resources include a compact native config whose exact byte hash is embedded
in the runtime. The adapter checks it before parsing, preventing accidental
palette, input or selector-order drift. Ordinary bundle launch finds
`Resources/native-config.json`; explicit config paths are also supported.

Diagnostic modes are separate from normal play:

```text
program [CONFIG.json] --export-frame NEW.png
program [CONFIG.json] --adapter-test SCRIPT.json NEW-RESULT.json
```

Frame export reads stored state without operating a GUI. Adapter studies use
programmatic `NSEvent` delivery through the production window-key and view-pointer
responders. Offscreen capture calls the actual `drawRect` path in a controlled
flipped graphics context. This qualifies those adapters, not physical hardware
event delivery, global window hit-testing or a screenshot of the desktop.
Explicit clock, initial service values and one declared RAM-prefix intervention
must remain labelled. Prefix replacement preserves the actual frame, font and
all other current words outside that prefix.

## Snake reproduction

`examples/recovery/snake_macos.py` consumes the earlier qualified private RNG
delivery, copies its project with SQLite backup, validates capsule and initial
arena identities, and emits a new native build. It reuses the same source UIL,
UDL, original font/palette, plans and original/LFSR region definitions. It does
not alter the original executable or earlier delivery.

`verify_snake_macos.py` exercises the actual native library against the original
342-case corpus, alternative references, 69 carried observations per algorithm,
complete state/raster buffers and the 26-move outcome/switch routes.
`verify_snake_appkit.py` separately qualifies event and palette/view adapters.
Original CPU execution, preserved native DOS observations, generated ARM64
execution and AppKit responder evidence are distinct gates. Finite agreement
does not establish whole-binary recovery or all-input equivalence.

The sanitized local milestone receipt is in
[`docs/evidence/snake-macos-arm64/verification.json`](evidence/snake-macos-arm64/verification.json).
The application, original font, full observations and byte-retaining project
remain in the private delivery outside Git.
