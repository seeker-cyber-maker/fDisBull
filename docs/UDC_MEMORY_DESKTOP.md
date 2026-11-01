# Native Windows x86/x64 and Linux graphics/input over memory UIL

The desktop profile realizes the same bounded-memory UDL/UIL, exact cuts and
selectable regions used by the browser and macOS pilots. It emits native
x86-32 or x86-64 code with a Win32/GDI shell, or x86-64 code with an X11 shell.
Game rules, rendering and input interpretation remain in UIL; the host supplies OS services and owns
presentation, input translation and time.

| Platform | Artifact | Profile | Native services |
| --- | --- | --- | --- |
| `windows-x86` | I386 PE32, GUI subsystem | `windows-x86-memory-win32-1` | Win32 messages, combo boxes, GDI DIBs |
| `windows-x64` | AMD64 PE32+, GUI subsystem | `windows-x64-memory-win32-1` | Win32 messages, combo boxes, GDI DIBs |
| `linux-x64` | x86-64 ELF executable | `linux-x64-memory-x11-1` | X server events, XKB physical names, XImage/Pixmap |

Both Windows desktop targets use the Win32 API; their executable formats and
pointer ABIs differ. The [Win16 NE profile](UDC_MEMORY_WIN16.md) uses a separate
segmented storage adapter while retaining the same logical memory UIL.

The canonical program and source selection identities are retained. Persisted
Wasm/WebGPU layers remain source provenance. Each generated native realization
has its actual target, source digest and function identity. These profiles use
the platform C ABI; byte identity between machine-code blocks compiled for the
different ABIs is not asserted.

## Build and execution gates

The Python module is `fdisbull.udc_memory_desktop`. Its JSON methods are:

- `emit-memory-desktop-shell`: source-only recipe from exact project selections.
- `compile-memory-desktop-shell`: invoke a GCC-compatible native or cross compiler.
- `seal-memory-desktop-shell`: validate format, architecture and artifact hashes
  after an explicitly managed external build.
- `build-memory-desktop-shell`: emit and compile in one local operation.

Emission accepts `project`, `selections`, `plan`, `initial`, a new private
`destination`, `target`, and optional `cuts` and `regions`. Compilation accepts
an optional explicit `c_compiler`. Builders never run the resulting programs.
Source emission preserves `source-shell.json`; compiled receipts are immutable.
Re-sealing unchanged artifacts is idempotent. Changed inputs or outputs need a
new private build directory.

```python
from fdisbull.udc_memory_desktop import build_memory_desktop_shell

build = build_memory_desktop_shell(
    project, selections, plan, initial, new_private_directory,
    target="linux-x64", cuts=cuts, regions=regions,
    c_compiler="/explicit/path/to/gcc",
)
```

A Windows recipe uses the matching MinGW compiler and links a GUI application
plus a console study probe. A Linux recipe links Xlib and the platform C runtime. The application
embeds its core object; the separately emitted library supports analysis.
Configuration is compiled from the validated plan and byte-hash-bound to the
core. No configuration parser, browser, UIL interpreter or original executable
is required at game runtime.

Select `target="windows-x86"` for the i686 recipe, whose default compiler is
`i686-w64-mingw32-gcc`; `windows-x64` retains
`x86_64-w64-mingw32-gcc`. An explicit `c_compiler` may name a versioned matching
driver when a separately prepared SDK has no generic compiler alias. Admission
checks I386/PE32 for the former and AMD64/PE32+ for the latter; an x64 executable
cannot stand in for the requested 32-bit artifact.

`native-shell.json` distinguishes `source-only` and `compiled` stages and keeps
`native_execution: false`. Artifact admission establishes the declared file
format, architecture and identity. Compiler lineage is supplied evidence;
execution and original fidelity require separate receipts. Do not infer them
from sealing. Compile recipes and output paths are checked before invocation;
source/manifest/artifact links that could redirect writes refuse.

The compiler's bounded-memory expression lowering and orchestration are shared
with the [macOS profile](UDC_MEMORY_MACOS.md). This extends native UDC realization
without changing source UIL or relabelling stored source layers.

## Ownership and refusal

The native core captures the module-load thread as its owner. Other threads and
reentrant mutations refuse. The interactive entry loads it on its UI thread.
Calls stage an owned word arena, enforce the canonical caller budget across
cuts/children, check logical footprints and guards, and commit declared state
and frame ranges atomically. Scratch and host inputs remain outside commits.

The host owns copies of committed words and palette RGBA. OS callbacks never
borrow mutable core storage for drawing. A selector changes future region
invocations without reseeding or editing the arena. Selection is captured for
the whole synchronous operation. No asynchronous GPU completion protocol is
implied by these native profiles.

A UIL quit is captured before terminal close clears the core. The final owned
snapshot remains available for observation. A live expected-refusal study reads
the actual core again before reporting state, so stale display caches cannot
hide an erroneous mutation. A deliberately faulty authored core regression
exercises that observer: a refused call which writes a word must be detectable.

## Drawing and pointer coordinates

The source frame is row-major indexed color with a top-left origin. The host
converts it to opaque RGBA and fits it into an integer viewport rectangle with
black letterboxing. Viewports are bounded to 4096 by 4096 pixels. Ordinary window
size policies keep desktop resizing within that budget.

For source size `W,H` and viewport `w,h`, choose the limiting axis, round the
other fitted extent down, and center using integer division. A destination pixel
samples the source at its center:

```text
source_x = floor((2 * relative_x + 1) * W / (2 * fitted_width))
source_y = floor((2 * relative_y + 1) * H / (2 * fitted_height))
```

Integer native pointer coordinates use exactly the same center rule. A press
in the letterbox is ignored; captured motion and release clip to the edge.
Native message coordinates have signed 16-bit carriers, and out-of-range study
coordinates refuse. This is a discrete pixel contract; the macOS profile's
continuous AppKit coordinates and Quartz tie rules remain separately documented.

Win32 converts RGBA to an owned top-down BGRA DIB. Ordinary painting and
`WM_PRINTCLIENT` studies use the same drawing path. X11 packs the same RGBA into
the server's visual masks and uses the same XImage upload for window painting
and an owned offscreen Pixmap. Qualification reads that owned surface, never
desktop pixels. The recorded X11 environment is 24-bit TrueColor; other server
visuals are not qualified by that result.

## Keyboard, pointer and clock adapters

Win32 translates physical PC scan codes from window-message metadata. X11 uses
XKB physical key names. Both resolve the supplied keymap at startup and refuse
an unsupported declared key. Only a focused game view consumes game keys;
Command/Control/Option combinations remain host shortcuts. Shift and Caps do
not change the declared physical-key mapping.

Left/right/middle buttons use the declared low-three-bit interface. Capture is
owned explicitly, a second held button preserves that capture, and focus or
capture loss releases held buttons. Selection controls return focus to the game.
Minimizing the Windows shell preserves the last valid viewport.

Monotonic time is divided by `plan.events.tick_ms`, then reduced to low16 ticks.
Fractional tick intervals are retained. The UIL decides when a game step occurs;
the host adds no catch-up movement or game-specific timing rule.

## Diagnostic protocol and reproduction

The interactive application and headless core probe accept:

```text
program --adapter-test NEW-INPUT.bin NEW-OUTPUT.bin
```

`encode_study` and `decode_study` implement the strict versioned binary framing
specified in `native_runtime/memory-desktop.h`. The decoder refuses partial or
trailing data, wrong shapes, impossible pointer/selection states and invalid
flags. Large word snapshots are owned `array('I')` values; use an explicit
sequence conversion when comparing them with Python lists or byte indices.

Studies exercise the production window procedure or X server event dispatcher.
A command may capture intrinsic RGBA and the actual owned native surface.
`FDB_EXPECT_REFUSAL` requires rejection and exposes the post-refusal live core;
it does not excuse malformed protocol input. Initial service values, explicit
clocks and diagnostic RAM-prefix replacements remain labelled interventions.

`examples/recovery/snake_desktop.py` emits the private Snake project and recipe
from the qualified prior capsule. `verify_snake_desktop.py` checks both RNGs on
342 kernel cases, 69 carried observations, complete states/frames, scaled native
surfaces, seed footprints and the 26-move outcome/hot-switch routes. An explicit
Python runner can transfer bytes into an authorized local test VM; the default
runner executes locally. The verifier retains admission identities and refuses
changes during a study.

Original machine-code checks, retained DOS native observations, headless native
blocks and OS input/view adapters are distinct gates. The local study runs Linux
under QEMU and Windows APIs through Wine/QEMU, with networking disabled. Those
results do not qualify Microsoft Windows OS execution, physical hardware,
global window hit-testing or all-input/whole-binary equivalence.

The existing [x64 milestone receipt](evidence/snake-desktop-x64/verification.json)
records the finite comparisons, exact identities and separate environment
qualification. Generated applications, original font data, byte-retaining
projects and full observations remain private outside Git.

`tests/test_memory_win32_i686.py` separately compiles the established authored
adapter fixture as genuine I386/PE32 and checks its GDI pixels, key/modifier and
focus handling, mouse capture/buttons, selectors, timer, terminal snapshots,
refusal and viewport lifecycle. An explicit `FDISBULL_WIN32_VM_CLIENT` can select
an owned local offline guest; `FDISBULL_WIN32_CC` names its real compiler. The
x64 tests keep their own compiler/runtime selection. These native fixture tests
qualify the adapter boundary; full Snake/original fidelity needs its separate
state, frame and outcome comparisons.

The subsequent [Win32/Win16 milestone](evidence/snake-win16-win32/verification.json)
qualifies the I386/PE32 profile against the same recovered Snake UDL/UIL and
recorded DOS corpus:342 original-RNG cases,342 alternate cases,69 carried core and 69
native GDI/input observations per RNG, and three 26-step RNG routes. The
segmented NE profile is documented separately in the [Win16 guide](UDC_MEMORY_WIN16.md).
The local runtime is Wine11; these results do not qualify Microsoft Windows
installations or physical hardware.
