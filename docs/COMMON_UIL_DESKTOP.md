# Native desktop shells over common UIL

The desktop shell connects indexed common UIL functions to an AppKit window on
macOS ARM64, an X11 window on Linux x86-64, or a Win64 window and GDI renderer.
The UIL supplies state transitions and indexed pixels. Platform adapters supply
the window, physical-keycode mapping, pointer geometry, clock and presentation.
They do not add Snake movement, food placement or outcome rules.

The current source/API implementation and bounded build admission are distinct
from native runtime qualification. Fresh window, callback, framebuffer and
original-code comparisons require their own dated study receipts. A successful
build or seal does not establish that an application ran. Wine execution must
remain labelled Wine execution until a Microsoft Windows runtime is tested.
These are feature-development outputs, not a release or system installation.

## Inputs and commands

The shell takes six documents: program, presentation, catalog, orchestration,
desktop plan and initial arena. Keep the output in a new private directory
outside Git. The documents retain their separate identities; a host adapter
does not rewrite the common UIL into a platform-specific program.

```text
fdisbull uil-desktop program.json presentation.json catalog.json orchestration.json plan.json initial.json /path/to/new/private-shell --target macos-arm64 --source-only
fdisbull uil-desktop-build /path/to/new/private-shell --c-compiler /path/to/clang
fdisbull uil-desktop-seal /path/to/another/externally-compiled-shell
```

Targets are `macos-arm64`, `linux-x64` and `windows-x64`. Without `--source-only`,
`uil-desktop` emits, compiles and seals the shell using the selected compiler.
Source-only emission does not accept `--c-compiler`. Existing source emission
can be compiled later with `uil-desktop-build`; sealing separately admits the
objects and images from an external compilation. Neither operation launches
the game. Existing destinations and retained artifacts are protected from
accidental overwrite.

The standalone JSON methods use these fields:

| Method | Required fields | Optional fields |
|---|---|---|
| `uil-desktop` | `program`, `presentation`, `catalog`, `orchestration`, `plan`, `initial`, `output` | `target`, `source_only`, `variants`, `c_compiler` |
| `uil-desktop-build` | `output` | `c_compiler` |
| `uil-desktop-seal` | `output` | None |

Input documents may be JSON values or paths to JSON files. `target` defaults
to `macos-arm64`; `source_only` defaults to `false`. Unknown parameters refuse.
These methods need no analysis database and do not inject a default project.
The Python functions in `fdisbull.uil_desktop` are `emit_desktop_shell`,
`build_desktop_shell`, `compile_desktop_shell` and `seal_desktop_shell`.

## Plan and ownership

The `fdisbull-common-uil-desktop-plan-1` plan binds indexed functions to a
fixed-length u32 arena. Every desktop function has exactly one array input and
one array output of that same length. The initial profile requires an
effects-free closure. General text variables, arbitrary host services and
implicit OS-call replacement are outside this arena interface.

The plan declares `function_names`, `initialize`, `inputs`, `outputs`,
`commit_ranges`, `replace_ranges`, `scratch_ranges`, `guards`, `array_guards`,
`render`, `frame`, `events` and `keymap`, plus `format`, `title` and `help`.
Function bindings and word indices are numeric. The frame declares dimensions,
offset and palette; event bindings declare keyboard, pointer and clock fields.
Input, scratch and committed storage have distinct declared footprints.

One synchronous platform event-loop owner stages a writable arena, patches only
declared inputs, snapshots the selected backing for each function, executes the
native function, validates its output footprint and invariants, and commits the
declared state/frame ranges together. Refusal preserves committed words and
revision. Reentrant, wrong-owner, stale or terminal operations refuse. Drawing
uses an owned committed snapshot, including the final snapshot before teardown.
This is synchronous CPU orchestration, not an asynchronous GPU completion claim.

The generated native core exposes the existing `fdb_block(words)` entry adapter
and indexed `fdb_function_block(function_index, words)`. Admitted function indices
and their shared word count are retained in `legacy_arena_adapter.functions`.
The function count is not a dense index bound: callers must use the admitted
rows. Unknown or incompatible indices refuse without changing the caller's
array. ABI prologues and epilogues remain the target C compiler's responsibility.

`fdb_function_block_limit(function_index, words, remaining_steps)` admits an
explicit remaining budget from 1 through 4,000,000. The desktop transaction
passes its remaining budget to follow-up rendering, so logic and rendering
share that limit. Exhaustion stops before the next logical charge and leaves
the caller's array unchanged. The default indexed and entry adapters retain
their existing signatures. Per-attempt arithmetic counters reset even when
admission refuses before execution.

## Selectable implementations

Default backings are portable C and native arithmetic. `--variants FILE.json`
supplies one to eight declared variants; each has `name`, `label`, `arithmetic`
and optional `module_requirements`. Exact nested requirements follow the
[native component contract](COMMON_UIL_NATIVE.md). A mixed backing can select
C for one arithmetic child and assembly for another.

All backings retain the same program, presentation, catalog, orchestration and
arena interface. Only implementation locks and generated realizations differ.
The selector changes a backing without reseeding or replacing game state; the
captured choices govern a complete transaction. Invocation/provider counters
are observations of executed modules, not machine-instruction or speed claims.
Each runtime function choice selects a sealed realization. Local callees inside
that realization retain its compiled link choices; the window selector does not
silently rewrite those internal bindings. Use another declared realization and
its exact nested requirements to change a deeper arithmetic child. In particular,
a mixed realization can keep addition in C while using native multiplication
inside the same unchanged function.
An intentionally different RNG is a behavior variant and must not be presented
as an equivalent implementation merely because its ports match.

The initial UI admits up to 64 function selectors on AppKit, 32 on X11 and 16
on Win32. Emission checks that target-specific bound. Study readers admit at
most 16 MiB of AppKit JSON or 128 MiB of binary input; both native writers reserve
a conservative 256 MiB total output budget before executing the next command or
allocating its captures. A partial failure receipt is not a complete result.
Host metadata preserves finite fractional clock periods; common UIL documents
retain their separate integer-only canonical format.

Python host metadata is admitted as a bounded regular-file snapshot before
JSON parsing. Each compiled object or image has a 128 MiB input cap; validation
and hashing use the same owned byte snapshot. Source/artifact ancestor symlinks
and preexisting compiler reports refuse, and new reports are written
exclusively.

## Graphics, input and evidence

The indexed framebuffer is row-major with a top-left origin. Palette conversion
and nearest-neighbor aspect fitting belong to the adapter. Pointer conversion
uses the same fitted rectangle, with half-open hit tests and declared captured
drag/release behavior. Keyboard input uses declared physical keycodes and
modifiers; the monotonic clock supplies low-16-bit ticks while UIL determines
when a transition occurs.

Qualify the boundaries separately:

1. Validate the unchanged common documents and sealed native module identities.
2. Compare complete typed/arena results, refusal behavior and selected-provider
   counters for C, assembly and mixed choices.
3. Compare indexed frame bytes and palette RGBA from committed state.
4. Observe actual native window creation and presentation callbacks; compare
   controlled stored-state drawing without operating the desktop for screenshots.
5. Exercise the production keyboard and pointer routing, focus, geometry,
   selector and close paths. Label programmatically constructed events explicitly.
6. Compare the declared state projection against original code, retaining the
   original oracle's prepared-state, route and platform limits.

An offscreen draw is not compositor readback. Direct responder calls are not
window hit-testing evidence. Queued native events are not physical hardware
observations. A sealed image, an original-code comparison and native GUI input
each support their own bounded claim.

## Snake qualification on 2026-11-01

The [sanitized study receipt](evidence/common-uil-desktop-2026-11-01/verification.json)
records nine passing target/backing combinations. Every combination uses common
program `8e59ebfa9b2535e5ef11c1b144a4fc18b5eb83dd32a647f4162db005b9ff8500`
and the same presentation, catalog, orchestration, plan and initial arena.

| Target and observed runtime | Portable C | Native arithmetic | Mixed C addition / native multiplication |
|---|---|---|---|
| macOS ARM64, AppKit on this Mac | Pass | Pass | Pass |
| Linux x86-64, X11/Xvfb in the AMD64 Linux environment using Rosetta | Pass | Pass | Pass |
| Win64, Wine 11/Xvfb in an isolated x86-64 QEMU Linux guest | Pass | Pass | Pass |

Each profile matches all 59 fresh original DOS observations: 621 projected
state words, 64,000 indexed pixels, the observed palette and intrinsic native
window-surface RGBA. The source corpus contains 53 distinct VGA frames, 48
keyboard-controller commands and 10 mouse clicks. The native adapters receive
48 programmatic keyboard events and 20 pointer press/release events per profile.
Selected action/render/initialization bodies, clean exit and process reaping
are checked separately. All three arithmetic profiles retain the original RNG.
The full 70,000-word arena is a model interface; its unobserved words are not
claimed as original-DOS state correspondence.

Separately, all 70,000 model words agree across all nine realizations at the
59 aligned snapshot boundaries. For each profile, the complete 68,319,052-byte
Win64 and Linux command traces are byte-identical, including 136 command
records, presentation captures, selections, counters and lifecycle fields.
This is cross-backend agreement in addition to the narrower original-code
projection above.

This is a source-assisted, paused and single-step study. One declared RAM-state
intervention reaches the winning branch. Fresh pause/resume keys, timer pacing,
a complete playthrough, physical input devices, compositor readback and a
Microsoft Windows host remain outside this qualification. The original DOS
executable remains byte-identical. Original bytes, fonts, states, generated
applications and raw captures remain in the private study workspace.

The study also exposed boundary errors that now have explicit checks: finite
fractional DOS clock periods in host metadata, one logical budget shared by
logic and rendering, and owned AppKit queue events with duplicate/foreign-event
refusal in diagnostic mode. A separate comparison-carrier regression checks
logical 8-bit pixel values rather than the byte representation of a u32 array.
The earlier failed comparisons and runtime attempts are retained privately.

After the native study, the Python builder received those bounded-file and
path/report-preservation checks. Regeneration with the final builder produced
all 68 native source payloads byte-identically across the three targets; compile
recipes and runtime metadata also matched. Its bounded readers separately
admitted all 30 existing compiled objects/images with their original hashes.
The receipt retains the actual historical builder identity and records this
later admission-only lineage. Native process observations were reused with
their original artifacts and were not replayed for a metadata-only change.

The Win64 result uses MinGW 13 and Wine 11 under QEMU. Its earlier Wine 10 /
Rosetta GUI attempt did not qualify and left the shared Apple container service
unavailable. The passing Linux GUI result was collected before that failure.
Focused source/native and distribution checks have their own receipts; the
earlier full ordinary Linux suite at base commit `c713ba9` does not qualify this
newer desktop change. The desktop study receipt does not establish a source-CI
gate: read the separate exact-source CI receipt for any later qualification.
Hosted CI, required-native release gates and system activation remain separate.
