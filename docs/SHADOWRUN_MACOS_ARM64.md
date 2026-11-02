# Genesis-bound UIL to native macOS ARM64

This document records the initial native qualification at `acfb843`. The
[actor-stage extension](SHADOWRUN_MACOS_EXTENDED.md) adds the source-backed menu,
an unpatched captured courtyard and corrected/extended armed continuations.

The active local output is a native ARM64 AppKit application compiled from the
same recovered Shadowrun procedural UIL. Genesis input identity, capture seed,
movement/combat semantics and original comparisons are retained. The NES output
is preserved as [research with a handoff](GENESIS_NES_RESEARCH_HANDOFF.md):
possible for bounded slices, but not recommended as the primary Genesis output.

This first native profile is still the **bounded assisted scene-2 arena**.
Changing output architecture does not recover natural encounter reachability,
other actors, missing source branches, original artwork/audio or a complete
game. The required model entry is `shadowrun_arena_frame`; this is not an
arbitrary-ROM emulator or an unrestricted GameIL compiler.

## Build and run

Use the user's exact Genesis ROM and receipt-bound opening manifest/capture.
Run storage admission before building, choose a new private output directory
outside Git and set its external temporary directory per command.

```sh
fdisbull shadowrun-ai-profiles
fdisbull shadowrun-ai-build "$OPENING_MANIFEST" \
  --rom "$ROM" --capture "$CAPTURE" --target macos-arm64 \
  --preset moving --output "$PRIVATE_BUILD"
open "$PRIVATE_BUILD/Shadowrun Arena.app"
```

Use `--preset stationary` for the stationary opponent and damage/terminal test.
The window starts paused. **Space** starts/pauses, **arrows** move, **Z** fires
or equips, **X** targets or goes back, **Enter** opens/closes inventory,
**R** resets to the paused seed, and **Escape** quits. Short action taps are
latched for a simulation tick; this is a host input adaptation. Inventory shows
the captured slots and equipment, not an invented full-game inventory.
The default target remains `nes` for API compatibility; an explicit
`--target nes --cc65-root "$CC65_ROOT"` selects the preserved research output.
The ARM64 target requires macOS on Apple Silicon, Clang and the macOS SDK. No
cc65 toolchain is used for this output, and `--cc65-root` is rejected with it.

The private app stores a reference to the original ROM rather than copying the
file into its bundle. Every native context reads and verifies its exact length
and SHA-256 before execution. Keep that original available at the selected
path. Generated C, libraries, executables and the captured semantic seed remain
private outputs, not tool-package contents. The tool package ships only the
compiler, authored frontend source and sanitized evidence.

## Native contract

`udc_macos.build_macos(program, seed, output)` lowers the validated typed syntax
tree into ARM64 code and produces a dylib, C header and build receipt. The
current subprofile requires one immutable region with ID 0 and the Shadowrun
arena entry. Unsupported constructs refuse instead of being copied opaquely.

Ordinary host C would change the model's 16-bit integer promotions on a 64-bit
Mac. The lowering preserves GameIL's 16-bit int/32-bit long model explicitly,
including wrapping, signed division, shifts, evaluation order and array bounds.
Missing environmental samples (`hv16`/`sound_busy`) are rejected, not filled
with zero. The source model and its hash remain unchanged.
The compiler rejects call paths exceeding 128 procedures and bounds operations,
loop iterations and array access.

Each context owns independent state and a verified private ROM copy. A model
fault or unsupported frame rolls back the entire native state. Reset restores
the original seed. The exported `state_set` API is an explicit investigation
operation, not proof that an edited state is naturally reachable. UI controls
do not grant additional recovered game behavior.

The frontend renders authored symbolic terrain and player/enemy markers with
current health/ammo. Host pause/reset and display are target adaptations. The
host requests a 60 Hz simulation schedule; CPU work, drawing, scheduling and
visible presentation are separate performance observations.

## Verification and timing

Qualification compares every scalar and array element with an independent
GameMachine after each completed update, then separately checks the same
Genesis captures. It also exercises refusal rollback, terminal/reset, two
interleaved contexts, invalid ROMs and native state access boundaries.
Source checkpoints are comparison outputs only; the app does not replay future
captured coordinates as behavior.

Setup/model lifting, Clang compile/link, native update and offscreen drawing are
timed separately. Update benchmarks use repeated equal completed workloads
inside the qualified boundary. A fast update benchmark does not establish
onscreen frame delivery or future whole-game performance. Exact counts, hashes,
conditions and limits are recorded in
[native verification](evidence/shadowrun-macos-2026-11-01/verification.json).

The initial qualification stopped at source frame 6124; the linked extension
records the later supported windows and remaining boundaries. Faster hardware
does not authorize inventing the next state. Atari-to-NES multicart packaging and Master System
input remain deferred research candidates described in the handoff.
