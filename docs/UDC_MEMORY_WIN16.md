# Win16 NE shells over the same memory UDL/UIL

The Win16 profile realizes the bounded-memory program used by the
[browser](UDC_MEMORY_BROWSER.md), [macOS](UDC_MEMORY_MACOS.md), and
[Windows x86/x64/Linux](UDC_MEMORY_DESKTOP.md) shells. It generates C89 native
blocks and a Windows 3.x API shell for a genuine x86-16 NE executable. Game
transitions, indexed rendering, key interpretation and RNG contracts remain
in the selected UIL. The shell supplies storage, scheduling, file transfer,
GDI presentation and input adapters.

The shell target is `windows-x86-16-memory-1`, with profile
`windows-x86-16-memory-win16-1`. Pure block lowering records
`windows-x86-16-memory-c89-segmented-1`. These identify generated realizations;
stored Wasm/WebGPU layer targets remain source provenance. A common source UIL
does not imply identical machine code across 16-bit, 32-bit and 64-bit ABIs.

## Source, build, runtime and original gates

Keep four independently inspectable edges:

1. **Source:** resolve exact project selections, cuts, regions, plan and initial
   words. Retain the canonical UDL/UIL hashes and the source endpoints. Emission
   produces a source-only recipe and claims no native execution or recovery.
2. **Compile and admit:** use a real compatible C16 compiler/linker, retain their
   actual commands, and admit the resulting Windows NE images, segment tables
   and artifact hashes. Successful compilation and sealing do not run code.
3. **Native boundary:** execute the admitted images and compare complete state,
   frame bytes, GDI surfaces, input translation, refusal and lifecycle effects.
   Require actual output observations; a process exit alone is insufficient.
4. **Original and composed behavior:** run the original instruction spans or
   original process under declared adapters. Compare original to UIL, UIL to
   each generated backing, and then the composed shell on the same inputs.
   Shared source ancestry and two agreeing implementations are not an
   independent original oracle.

Use new private output directories outside Git. Retain original executable
hashes, source/compile receipts, test commands, actual observations and the
remaining unknowns. Keep generated applications, original data/font bytes and
byte-retaining projects private.

## Python and JSON interfaces

`fdisbull.udc_memory_win16_shell` exposes:

```text
emit_memory_win16_shell(
    project, selections, plan, initial, destination, *, cuts=None, regions=None
)
build_memory_win16_shell(
    project, selections, plan, initial, destination, *, cuts=None, regions=None,
    c_compiler=None, linker=None
)
compile_memory_win16_shell(destination, *, c_compiler=None, linker=None)
seal_memory_win16_shell(destination, *, compiler_evidence=None)
```

The corresponding JSON methods use the open project context:

| Method | Parameters | Resulting gate |
| --- | --- | --- |
| `emit-memory-win16-shell` | `selections`, `plan`, `initial`, `destination`, optional `cuts`, `regions` | Source-only recipe |
| `build-memory-win16-shell` | Emission parameters, optional `c_compiler`, `linker` | Emit, compile and admit |
| `compile-memory-win16-shell` | `destination`, optional `c_compiler`, `linker` | Compile an admitted source recipe |
| `seal-memory-win16-shell` | `destination`, optional `compiler_evidence` | Admit an explicitly managed external build |

Confirm these names in the selected runtime's `fdisbull methods` inventory.
A newer source checkout or skill does not add methods to an older install.

```python
from fdisbull.udc_memory_win16_shell import (
    emit_memory_win16_shell,
    compile_memory_win16_shell,
)

recipe = emit_memory_win16_shell(
    project, selections, plan, initial, new_private_directory,
    cuts=cuts, regions=regions,
)
build = compile_memory_win16_shell(
    new_private_directory,
    c_compiler="/opt/watcom/binl/wcc",
    linker="/opt/watcom/binl/wlink",
)
```

The tested compiler host is Linux with the separately acquired
[Open Watcom 1.9 SDK](https://openwatcom.org/ftp/install/). The recipe expects
headers under `/opt/watcom/h` and `/opt/watcom/h/win`, with `WATCOM=/opt/watcom`.
It compiles with the large memory model (`-ml`), Windows code generation and
separate `wcc`/`wlink` commands. The explicit executable arguments select the
tools; they do not relocate the recipe's header paths. The helpers install
nothing. Other SDK versions and compiler host operating systems need their
own qualification.

Each lowered function or region variant has a separate `Nnnn.C` translation
unit and named code segment. `M16CORE.C` owns orchestration, `M16COMM.C` owns
paged storage and common host services, and `M16GUI.C` supplies the Win16 API
adapter. A distinct `M16PROB.C` entry supplies the study probe. The link recipe
requests a 16 KiB stack and 8 KiB local heap; these are loader resources, not
the logical UIL arena. A function or segment that does not fit needs an
explicit supported decomposition or a refusal, never byte truncation.

`PROGRAM.EXE` and `PROBE.EXE` are both Windows NE executables. Keep the emitted
`INITIAL.BIN` beside them. It contains the unchanged logical initial words,
with a word-count header and a CRC32 compiled into the configuration for
runtime admission. The source manifest also binds all emitted file hashes.
Configuration is compiled into the host; runtime execution requires no UIL
interpreter, browser, original executable or JSON configuration parser.

`source-shell.json` retains source-only identity. `native-shell.json` advances
to `compiled` after admission of all source files, object files, executables
and linker maps. The NE inspector checks Windows target, executable flags,
bounded segment payloads, code entry and stack/data groups. It does not prove
compiler lineage, runtime execution or original fidelity. Compiler lineage is
supplied evidence. Re-sealing unchanged artifacts is idempotent; changing a
sealed source, recipe or artifact requires a new build directory. Redirecting
artifact links and existing output files refuse.

## Logical words and segmented storage

The arena retains its original logical word count and exact unsigned 32-bit
carriers. A 16-bit `int`, `size_t` or pointer offset never becomes the logical
index. `fdb16_read`/`fdb16_write` use a 32-bit page/index adapter instead of
adding a large offset to a far pointer.

For a 70,000-word program, the representation is **280,000 logical bytes over
nine pages**: eight pages of 8,192 words (32,768 bytes) and a final page of
4,464 words (17,856 bytes). Windows `GlobalAlloc`/`GlobalLock` owns each page.
There is no single 280,000-byte C allocation, and no narrowing of the arena to
fit one segment. The shell currently admits at most 131,072 words.

The host captures the cooperative Windows task as owner. Reentrant or wrong
owner mutations refuse. A complete logical call captures region selection,
stages private pages, applies the declared inputs, runs blocks/cuts, checks
step budgets, guards and output footprints, and commits only the plan's state
and frame ranges. Host inputs and scratch do not enter commits. Closure or a
changed epoch prevents a stale commit. The host retains owned observations;
drawing never borrows a mutable core arena.

`fdisbull.udc_memory_win16` also exposes `segmented_layout`,
`emit_win16_memory_function` and `win16_function_receipt` for pure block work.
Standalone lowering defaults to owned rollback (`atomic=True`). The shell
emits blocks with `atomic=False` because its outer orchestration owns the
complete transaction. These source receipts do not claim compilation or
execution. Generated automatic storage is bounded separately from paged state.

Selectable RNG blocks use the same canonical source UIL, region interface and
state layout as the other shells. Each variant keeps its own selected model
identity and generated native function. Changing the selector changes future
invocations without reseeding or editing committed state. An alternative RNG
may intentionally produce a different path; qualify that declared variant
against its model rather than calling it original-equivalent.

## Far-buffer files and streamed graphics

Native Win16 file transfer uses exclusive CRT `open`, native `_lread`/`_lwrite`
over an owned 4,096-byte buffer, and CRT `close`. This is an adapter boundary:
actual Open Watcom 1.9/Wine 11 probes found that buffered C stdio and CRT
far-buffer transfers could return successful counts while corrupting bytes.
Raw transfers from the default data group did not expose the same failure.
Native far-buffer transfers were verified separately before using this route
for the initial arena and study streams. Successful byte counts alone must
never certify a snapshot or resource load.

The logical frame remains row-major indexed color with a top-left origin.
The current profile requires its aligned indexed raster to fit within 65,520
bytes. The host owns that indexed copy; full RGBA output need not fit in one
segment. Intrinsic RGBA is streamed through small chunks. GDI painting and
capture use owned surfaces and bottom-up 24-bit DIB strips of at most 32,760
bytes, then convert captured rows back to top-left opaque RGBA.

The viewport is bounded to 4,096 by 4,096 pixels. Drawing and picking use the
desktop profile's deterministic center sampling and letterbox contract.
Captured pointer motion/release clips to the fitted edge; a press in the
letterbox is ignored. Studies read an owned GDI surface rather than desktop
pixels. A large total raster is not permission for a large contiguous far
buffer or unchecked 16-bit multiplication.

## Win16 input, chrome and time

The Win16 shell uses far Pascal callbacks with per-instance
`MakeProcInstance` thunks. Message structures, callback pointers and
`WM_COMMAND` notification packing follow Win16 conventions. Physical PC scan
codes and the extended-key bit resolve the plan's keymap. Modified host
shortcuts are refused; Shift/Caps do not alter the physical-key mapping.
Only a focused game view consumes game keys.

Left/right/middle buttons use the declared low three bits. Capture, focus loss
and capture loss have explicit release behavior; selectors return focus to the
game. Native mouse coordinates have signed 16-bit carriers, and out-of-range
study inputs refuse. Minimize/restore preserves the last valid viewport.

Window titles, help and selector labels must be representable in CP1252 and
contain no NUL. Unrepresentable chrome refuses at emission rather than silently
changing labels. This ANSI service restriction does not change UIL arithmetic,
game-state words or the game's indexed frame.

The clock extends observed 32-bit `GetTickCount` wraps, divides elapsed
milliseconds by the supplied fractional `tick_ms`, and reduces to low16 ticks.
The Windows timer's integer wakeup interval does not round away that fractional
division. UIL decides whether a game step occurs; the shell adds no catch-up
movement. Explicit diagnostic clocks remain labelled interventions.

## Execution and claim ceiling

The interactive entry runs as `PROGRAM.EXE`. Both entries accept the shared
desktop study protocol:

```text
PROGRAM.EXE --adapter-test INPUT.BIN OUTPUT.BIN
PROBE.EXE --adapter-test INPUT.BIN OUTPUT.BIN
```

The GUI entry exercises Win16 message procedures and captures its owned GDI
surface. The probe executes the generated core and common host, computing its
viewport rows from the owned indexed frame in software. Matching probe output
alone does not qualify GDI painting or native message translation; use the GUI
entry for those boundaries.

Use `fdisbull.udc_memory_desktop.encode_study` and `decode_study` for strict
binary framing. Complete word snapshots, counters and streamed intrinsic/native
RGBA use the same protocol as the other desktop shells. Partial/trailing data,
invalid dimensions, bad coordinates and impossible selections refuse. Refused
calls expose the live state; closed observations retain a labelled final owned
snapshot. Keep this diagnostic path distinct from ordinary input reachability.

The authored native checks use an offline x86-64 Linux guest and Wine 11 in
new WoW64 mode. Wine's official
[11.0 release announcement](https://list.winehq.org/hyperkitty/list/wine-releases%40list.winehq.org/message/UL6L2GJ55VYUJ5KUMBZ3TZSXRFJ52QG6/)
documents Win16 support in that mode and the `WINEARCH=wow64` selection for a
64-bit prefix. Actual NE compilation and GDI/input execution remain required;
release notes are environment evidence, not a substitute for running the
emitted artifact.

These checks qualify the finite authored adapter boundary in that environment.
They do not qualify execution on original Windows 3.x, physical hardware,
global window hit-testing, arbitrary programs, all inputs or a complete game.
Full Snake integration and original comparisons have separate retained
state/frame/outcome receipts below; successful authored adapter checks alone
do not establish that result.

## Recovered Snake integration

The separate [Win32/Win16 milestone receipt](evidence/snake-win16-win32/verification.json)
qualifies the recovered Snake program under Wine11 in the owned offline guest.
Both platforms retain the same canonical UDL/UIL, execution model, plan, cuts,
regions and source endpoints. The Win16 build keeps all 70,000 u32 words in nine
pages; its admitted code segments are 46,236 and 61,474 bytes, below 65,536 bytes.

For each platform,342 original-RNG and342 intentionally different LFSR cases
match their respective references. Each RNG also passes69 carried core and 69
native GUI observations with complete 621-word state, 64,000 indices and palette
RGBA comparisons. Three 26-step routes exercise original, alternate and natural
mid-game selection without board/seed edits. A separate native NE batch passes
118 generic lowering comparisons across 19 functions, including all 16 operations,
high indices, rollback and 140,002 charged steps. Fresh original DOS execution
passes 368 isolated step calls. Packaged application files also run from new
folders and reproduce eight original UI records, including two GDI surfaces.

These are finite comparisons. The original input/raster witnesses remain the
recorded DOS corpus; native event/GDI execution is observed under Wine11,
while actual Microsoft Windows3.x installations and physical hardware input
remain unqualified. The original DOS executable is unchanged.
