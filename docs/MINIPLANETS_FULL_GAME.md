# Miniplanets full-game UIL and native NES profile

The uncapped-rendering follow-up at the end is the latest qualified build.
It removes the two-epoch drawing gate, reaching 32.24 completed globe swaps/s
in the seeded orb-stage benchmark and 26.29 in the dense fireball stage.
The moving-player test reaches 15.42 swaps/s. These are bounded measurements;
60 Hz remains an optimization target. Earlier builds and receipts remain history.

This profile expands the source-bound Stage 1-1 experiment into the original
55-stage game rules: all placed actor types, moving terrain, score, lives,
countdown, stage transitions, continue/password/options, ending and hidden
world. Its NES adapter uses the original globe projection data, adapted
terrain graphics, authored icons and the complete soundtrack arranged for
NES sound hardware. The earlier mapper-0, flat first-level experiment remains
available with its own contract and receipts.

This is a **reviewed source-bound rewrite into procedural UIL**, using the
official open-source Miniplanets implementation and the exact shipped ROM.
It is not an automatic arbitrary-68000 decompiler. The data comes from the
supplied cartridge; the reviewed authoring source expresses the recovered
rules. Each edge is checked separately against the actual original CPU,
reference UIL execution, native NES execution and the audio event model.

## Inputs and permanent modules

The qualified input is the official Miniplanets REMIX Ver. REV04 cartridge,
524,288 bytes, SHA-256
`e8aee1b9fedca87b638a7624709d7f6e1a2aff8a5222083346d1cd63963acbe7`.
The attributed source is [Javier Degirolmo's pinned upstream
commit](https://github.com/sikthehedgehog/miniplanets/tree/0ac9c395289cc5d0837c96d45e61a27300e8eebc).
The zlib-style notice and alteration attribution accompany the package and
exported UIL. Original cartridges, lookup tables, game art/audio, generated
ROMs, raw states and captures remain in private directories outside Git.

- `udl_miniplanets_full.lift_full_game` checks ROM identity and returns the
  procedural game UIL, stage inventory, scene metadata and provenance.
- `game_il` validates the versioned document and replays its typed procedures.
  The artifact contains a syntax tree, rather than an opaque C-code string.
- `miniplanets_audio` parses every original music/effect stream into typed
  audio events, validates and re-encodes those events, and supplies the
  original logical sound state separately from the NES voice arrangement.
- `udc_nes_game` emits C from the **same game UIL tree**, then uses an explicit,
  hash-recorded cc65 toolchain to generate banked native 6502 code. The
  cartridge contains no 68000 emulator or game-UIL interpreter.
- `nes_game_platform`, `nes_globe_renderer` and the audio C/6502 adapter own the
  NES hardware boundary. Their source hashes are part of the build manifest.

The ordinary `console-udc` API/CLI selects this profile from its document
version. Its original scalar NES/Genesis and first-level profiles retain their
separate limits. The full-game profile currently has a NES backend; the
original Genesis cartridge supplies the comparison runtime.

## Replay and build

Install the optional `console` dependencies. Prepare cc65 outside the checkout
from the tested official commit
`52727a5b407bfeac0dfac1fdd84be8cd2af4f814`; this revision supports the
[`wrapped-call` bank attribute](https://cc65.github.io/doc/cc65.html#pragma-wrapped-call).
The older V2.19 toolchain does not accept that attribute. Build tools are
explicit inputs; the module does not install tools or download games.

```sh
fdisbull rom-game-lift /private/intake/miniplanets.bin \
  --output /private/experiment/miniplanets-uil

fdisbull console-udc /private/experiment/miniplanets-uil/program.uil.json \
  --target nes --region /private/intake/miniplanets.bin \
  --cc65-root /private/tools/cc65 \
  --output /private/experiment/miniplanets-nes
```

`rom-game-lift --variant baseline` exports the first reviewed actor version;
the default `efficient` version narrows legal slot offsets and skips redundant
empty-slot dispatch work. Both have the same game-state contract and separately
match the original CPU tests. `mix_full_game_variants(rom, {procedure: variant})`
selects those known bodies by procedure; native compilation accepts only these
qualified alternatives with unchanged declarations and region bindings.
This supports alternating implementation tests while retaining the same rules.

Both destinations must be new directories outside Git. Export writes game
UIL, audio UIL, scene and hash receipts. Compilation retains the inspectable
program, generated native source/build metadata, audio UIL, cartridge and
symbol/state manifest privately. The exact original ROM remains an external,
hash-bound region for replay; no original bytes are installed with the tool.

The NES controls are D-pad movement, A/B jump, Start pause, and Select as
Genesis C. Title, options, sound test, password, continue and stage-select
follow the original decisions through a target menu adapter. Pressing Start
during title zoom reveals its menu; selecting Play requires another press.
The original reset chord is A+B+C while unpausing, with Select supplying C.

## Procedural UIL contract

`fdisbull-game-il-2` is separate from the small `fdisbull-il-1` block profile
and its bounded Z3 claims. It adds typed scalar procedures, procedure-scope
automatic locals, mutable flat arrays, bounded execution, integer casts, comparisons,
bitwise operations and loops. The call graph must be statically acyclic.
Pointers, structs, indirect calls, preprocessor directives, floats, strings and
block-local declarations and procedure-local static/extern storage are outside
the game authoring subset.

The integer model is explicitly **16-bit int / 32-bit long**, matching cc65.
Unsigned arithmetic wraps at the selected width; signed-byte/word projections
and arithmetic shifts are explicit. ROM words/longs are read big-endian from
immutable external regions. The reference executor checks array/region bounds,
finite environmental recordings and operation/loop budgets; a failed public
call restores its state, events and environment cursor. Consumers drain the
bounded event queue after each frame.

The native backend accepts reviewed Miniplanets procedure bodies, including
qualified baseline/efficient mixes, with the same declarations and original
region bindings. It does not advertise the reference executor's dynamic
bounds/transaction guarantees for arbitrary generated C. Its normal game
domain uses the original 256-byte map and 48 four-byte object slots. Original
AddObject scans beyond its pool when full; this profile instead records a
capacity fault. The 55 authored populations start at at most 28 objects; the
normal spring effect has an eight-frame lifetime separated by the player's
airborne interval. Injected full-pool behavior is an excluded negative case.

## Preserved game rules and explicit environments

The model preserves X-then-Y wall movement, toroidal coordinates, the original
phase/subpixel correction, spring holding, belts, hazard/death actions, all
actor updates and original slot order. Rafts rewrite their six-cell footprint
and carry the player; switches affect subsequent object slots; bombs rewrite
4-by-4 terrain regions. Maces use original signed sine words. The shipped
pink-orb target bug is retained.

Score uses six packed-BCD digits, saturating at 999999; lives use packed BCD
and saturate at 99. The countdown retains the zero-second interval and kills
on borrow from 00. Win tally and stage bonuses retain the original arithmetic
and animation gates. Actors keep updating during tally. Shake decreases at
the presentation boundary even while paused; the paused game timer does not.

Two environmental inputs cannot be silently transferred between consoles:

1. Original RNG reads the Genesis VDP HV counter twice per Rand call. Original
   controlled tests record the actual callback returns while forwarding the
   original MMIO handler, then replay those exact values into UIL/NES. Normal
   NES play uses a declared deterministic clock/boot-seed adapter. This is
   random-input-conditioned state comparison, not cross-console clock parity.
2. Sound priority reads the original Sona completion status. The logical
   stream model retains its status timing separately from which NES voices
   remain audible. BGM requests, stop-all and effects retain source ordering.
   Controlled state tests supply an explicit sound-status input; normal play
   reads the logical audio engine's latched status.

## Globe and sound adaptation

The globe uses all 256 source camera phases and the original 64 depth-ordered
terrain projections. Terrain positions are quantized to the NES's eight-pixel
background grid, with at most four pixels of error on each axis. Thirty-two
animation phases retain water/fire and positive/negative horizontal/vertical
belt motion. The terrain is rendered through background tiles so it does not
consume all 64 NES sprite slots. Objects use the original projected position
tables; icons, menus and font are target adaptations. Actor draw order rotates
to share the NES's eight-sprites-per-scanline limit.

The 2bpp atlas has 214 resident terrain patterns. Quantization and color
reduction have measured losses recorded in `projection.json`. Background
painter ordering cannot reproduce every source per-pixel transparency
overlap. Globe geometry is qualified separately from exact pixel/occlusion
parity. Small icons also simplify original art and raft presentation.

MMC3 provides 512KiB PRG, 8KiB CHR and 8KiB cartridge RAM. Native procedures
are banked; hardware adapter routines are co-located so internal calls use
direct JSR/RTS. Display transfers write an inactive nametable in bounded
parts and publish the completed terrain, palette and sprite view together.
Logic/IRQ/display speed must be measured in the actual core; compiling a ROM
does not establish a real-time or physical-hardware timing result.
Code/data bank selection preserves the incoming interrupt mask and updates the
mapper register and its software shadow inside one interrupt-masked transaction.
NMI does not touch those bank registers. The runtime library is captured once,
linked from that retained copy, and hash-bound in the manifest along with the
tool executables and captured adapter sources.

The audio module covers all 13 BGM tracks, 19 effects, 28 instruments and
seven source PCM samples. Typed audio events re-encode byte-identically before
native replay. FM/PSG/PCM source channel state remains separate from its NES
arrangement: pulse lead, triangle bass, round-robin remaining tones, noise and
one priority DMC percussion voice. FM timbre, excess polyphony and two-to-one
PCM mixing are explicit adaptations, not waveform equivalence.

The original driver's Timer B was measured at about **118.89964Hz**, rather
than treating its rounded 120Hz documentation as exact. SFX streams advance
every second source tick. The NES interrupt cadence uses a phase correction
to follow that source rate. Voice/envelope rendering uses a native 6502 hot
path; its state/register output must agree with the portable event engine.

NMI schedules two service slots per display frame independently of whether a
long update misses a mapper interrupt. The IRQ owner catches up at most four
slots per entry. A sound request carries its production slot, so catch-up
cannot run a new sound through older logical time. Long requests can still
introduce jitter; scheduled time, completed services, source ticks, debt,
catch-up and request latency have separate diagnostics.

The native backend also uses nine checked 6502 intrinsics for subpixel,
mace, tile/collision, wrapped-radius, ordered actor dispatch and fireball
operations. Sine/collision bytes are
materialized privately from the original region. A separate lowering uses
byte offsets for flat arrays occupying at most 256 bytes, preserving element
width, signedness, qualifiers, index evaluation and scope. These optimizations
leave the inspectable UIL unchanged and depend on its declared valid-index
domain. They are not additional operations accepted from arbitrary C.

## Comparison methodology

Keep three claims separate:

1. **Original CPU to UIL:** execute actual mapped original instructions in the
   pinned Genesis Plus GX core, with controlled registers/RAM, declared code
   ranges, fetched-byte checks, bounded execution and no undeclared writes.
   Cover every actor family, wrapped geometry, original RNG observations,
   movement/tile combinations, packed BCD boundaries and flow components.
2. **UIL to native NES:** compile the retained same tree, inject the same
   declared component state in a fresh pinned FCEUmm process, invoke the real
   native banked procedure, and require command completion. Compare all 79
   public game variables/arrays, scalar return, events and environmental
   consumption. Native state layouts come from linked symbols. Assistance
   and command latency are recorded; an unfinished command cannot pass.
3. **Normal runtime and speed:** use ordinary input-only boot/play attempts,
   actual audio/screenshots and completed logic epochs. Separate assisted
   steady-stage measurements use valid initialized states and declare any
   invulnerability setting. Report completed ticks per host time, loading
   latency, route DNFs, display behavior and audio throughput separately from
   host emulator wall time. A live mid-call RAM image is not a completed state.

The public sanitized receipts live in
[`evidence/miniplanets-full-game-2026-10-31`](evidence/miniplanets-full-game-2026-10-31).
Raw programs, state vectors, audio/chip traces and images remain private.
`check_miniplanets_common_native.py`, `check_miniplanets_full_flow.py`,
`check_miniplanets_nes_game.py`, `check_miniplanets_audio.py` and
`capture_miniplanets_audio.py` provide the repeatable gates.
`check_miniplanets_nes_audio.py` checks mapped sound execution;
`check_miniplanets_nes_timing.py` measures normal timing.
`check_nes_audio_clock.py`, `check_nes_mapper_atomic.py` and
`check_native_array_offsets.py` isolate the scheduler, real interrupt/bank
boundary and address-lowering contracts. The mapper checker takes explicit
before/after helper source files, the qualified core and prepared assembler;
the public bank-race receipt describes the unprotected transaction to retain
as its negative control. Its generated test cartridges contain authored
sentinels, with no original game assets.

## Verification results and performance

The original-CPU common-rule gate passes **2,678 cases** and 146,905 executed
instructions. The separate actor gate passes **1,262 cases**, 292,870 original
instructions and 192 observed/replayed HV reads. The source-flow suite loads
**all 55 stages and 479 initial actors**, and exercises 6,044 frame updates,
menus, passwords, attract entries, game over/continue, tally, ending and the
hidden world. These are finite controlled tests. The ordinary input-only NES
route separately reaches the first goal, tallies to **4,700**, and advances to
Stage 1-2 with five lives and the 60-second setting.

Both actor variants agree with the original CPU. Across the same actor cases,
the efficient variant reduces reference UIL work from 1,569,630 to 664,134
steps (**57.69%**). Across the source-flow suite, it reduces work from
11,982,428 to 6,880,212 steps. Those are reference execution counts, not NES
frame rates or a native compiler speed ranking.

The complete native NES component bridge passes **4,822 cases**, comparing all
79 game variables/arrays, return values, events and consumed environmental
inputs. Separate normal-play publication shadows pass **7,163 completed
ticks**, comparing 34 published fields, the independently predicted input
actually sampled for each tick and absence of runtime faults. Positive
orange-orb sessions include 140 actual consumed/replayed HV words. A static
host-timed route remains a declared DNF; feedback using only controller input
reaches the goal and next stage despite variable execution speed.

Audio validation covers **32 source streams**, 22,955 decoded commands,
byte-identical event re-encoding, **270,752 controlled mapped NES service
calls**, all stream extents and a mixed music/effect/stop/restart schedule.
Native logical state and portable sound arrangement diagnostics agree with
the typed-event model and portable C reference. Original chip captures compare
5,841 FM frequency events over 648.23 seconds, with a maximum aligned timing
error of 11.84ms. This is not a PSG or waveform/timbre equivalence result.

Native optimization checks include **40,960** renderer C/6502 comparisons,
101,704 array-lowering cases with two incorrect controls, and dedicated
subpixel/mace/tile/collision vectors. The clear/copy/paint renderer hot loops
fall from 110,849 to 20,068 cycles summed across their measured operations.
The audio-clock test covers 15 scenarios and rejects four deliberately wrong
clock implementations.

The final r14 cartridge is SHA-256
`aecdb39cb4b112de6de64069aab8deb397640cf684ac6942cb4c8e79ac48663e`.
Across warmed 3,200-host-interval windows, the measured completed game updates
are:

| Declared session | Game updates per emulated second |
| --- | ---: |
| Light first stage | 32.49 |
| Mace-heavy stage, index 40 | 16.55 |
| Orange-orb stage, index 43 | 20.02 |
| Sixteen-fireball stage, index 44 | 9.56 |

A targeted observer forwards the unmodified core behavior and checks identical
states, controller observations, audio and final image against its control.
These measurements show a substantial real-time limit. All systems and stage
data are implemented, but this cartridge remains an experimental full-game
port with slow busy levels. It does not match the Genesis gameplay speed.
The input-only feedback route reaches the goal at epoch 902/host 1,806 and
Stage 1-2 at epoch 1,152/host 2,393, then continues for a declared 1,500 neutral
host frames. Earlier short-window/profiler results remain bound to their own
cartridge versions and are not transferred to this fixed image.

Music scheduling runs independently. Five fresh 3,000-interval windows measure
**118.87746–118.89749 source ticks per emulated second** against the observed
Genesis target of **118.89964Hz**. They complete 5,999–6,000 services and
5,934–5,935 source ticks per window, with up to one pending endpoint slot,
maximum observed debt of three to five slots, and no late sound requests.
The frozen v2 protocol unwraps atomic counter low bytes under explicit
per-interval/debt bounds, retains raw words as diagnostics, and allows two
source ticks for endpoint service/phase quantization. Wrong slow clocks fail
its negative controls; debt is not used to erase a sustained slow rate.

Earlier r12 audio measurements exposed sustained tempo loss, and the r13
initial timing receipt retains one torn 16-bit diagnostic and a strict
endpoint-tolerance failure. A fresh long r13 run then exposes a real bank race:
IRQ sees a new software bank before the mapper store completes, takes a
same-bank fast path and fetches the wrong opcode. An instruction/write trace
from the unchanged core proves that interleaving. R14 masks IRQ during the
entire code/data bank transaction. A separate asset-free native test injects
pending IRQ at four transaction boundaries: all 16 fixed cases preserve the
incoming I flag and pass physical-bank sentinel checks; both original
shadow-store counterexamples fail. All 32 before/after observer runs are
byte-neutral. The r14 long replay has no lost services or inconsistent raw
words. Earlier failures remain separate and are not reclassified as passing.

Finite component comparisons and all-stage loading do not establish that all
55 stages were completed naturally, whole-game formal equivalence, matching
Genesis graphics/waveforms, arbitrary-ROM conversion or real NES hardware
qualification. Each receipt states its actual observations and exclusions.

After integration with main `90e748c`, all 25 game/compiler/profile resources
remain byte-identical to the qualified source commit `8da0933`. A fresh build
from the combined 0.27.0 source produces the identical complete r14 cartridge
and UIL program; the native runtime evidence above remains bound to that
same image. The conflict resolution preserves console commands alongside
main's NE, media, source-storage and type-catalog interfaces.

The fresh full macOS repository suite records **2,756 passed, 142 skipped,
three failed and 23 errors**. The remaining failures/errors belong to unchanged
Linux ELF fixture groups that invoke Linux linker options or expect ELF from
the macOS compiler, plus main's existing case-sensitive `VOL.2`/`vol.2`
ambiguity fixture on this case-insensitive filesystem. This full local suite
is not green. The final source
archive/resource guard and offline-kit fixture checks pass separately; native
game/audio qualification uses the explicit private inputs described above.

A further private, accuracy-controlled address-form experiment reduced native
code by 766 bytes and improved the dense-stage sample by 5.65% with fixed bank
placement. Its broader generator and layout requirements are not included in
this module. Earlier unprotected layout timings include a CPU-jam observation
and are invalid for performance ranking. The simpler qualified lowering is
retained; the exploratory receipt states its separate canary and runtime scope.

## October 31 optimization follow-up and local review for PR 56

The optimized cartridge has SHA-256
`11ac422f96f13c5d168a55aeb747e0b73d153e67b0cc14d3ed0e0ce743673bfb`.
The baseline is the retained R14 cartridge,
`aecdb39cb4b112de6de64069aab8deb397640cf684ac6942cb4c8e79ac48663e`.
Both use the same source ROM, authored rules, controller contract, original
level data, globe presentation and audio arrangement. The UIL program hash
remains `198484bd9fe39d16f48d6785adcebe172b29b00511af1d77942088f7497e591b`.
The sanitized [optimization receipt](evidence/miniplanets-full-game-2026-10-31/optimization.json)
binds the toolchain, adapters, runtime library and private observations.

The implementation makes five changes:

- Native actor dispatch captures each slot's type once, visits all 48 slots
  in source order, and retains same-scan insertion of later-slot effects.
  Native fireballs preserve byte wrapping, collision guards and sound priority.
- The compiler first measures fully wrapped game procedures, freezes their
  bank placement, then recompiles each bank with direct local-call prototypes.
  Calls across banks keep the existing trampoline. Global definitions occur
  once; other translation units import them. Final assembled bank sizes are
  checked again, without repacking after the calling convention is chosen.
- Visible objects fetch both transposed projection coordinates from one
  privately generated, bank-contained row. All 33,282 front-domain coordinate
  pairs are checked against the retained full source tables in the actual NES
  core. Lookup metadata occupies verified unused DMC bank padding; every
  active encoded sample range is checked before that padding is reused.
- Terrain reuses its projection cache only after initialization and while the
  camera phase is unchanged. Terrain painting, actor drawing and coherent
  PPU publication continue normally. The data-bank selector also skips writes
  for a confirmed cache hit, retaining the atomic bank-change transaction and
  the caller's interrupt flag. Reset marks its shadow invalid after BSS clear.
- Audio assembly and its C caller share a bank. Fixed envelope traversal is
  unrolled in the original order, and silent-volume paths avoid redundant
  arithmetic. Track count, channel ownership, event interpretation and timer
  cadence are retained.

### Matched performance protocol

Each build runs in the pinned FCEUmm core for 3,100 physical frames. The first
100 frames warm up the runtime; 3,000 frame intervals supply the rates below.
At frame 40, the harness seeds the same valid source-initialized stage state
and `Muteki=255` to keep an unattended, neutral-controller run alive. Ordinary
native logic, rendering and audio run throughout the measured window. These
are assisted steady-stage benchmarks. They are not ordinary playthroughs.
Time comes from the core's 60.0998265 Hz NTSC hardware clock. Host emulator
execution speed does not enter the game-rate calculation.

| Stage index and workload | R14 logic updates/s | Optimized logic updates/s | Improvement | R14 completed views/s | Optimized completed views/s |
|---|---:|---:|---:|---:|---:|
| 0, light | 32.474 | 40.928 | 26.0% | 11.639 | 13.903 |
| 40, eight maces | 16.648 | 22.417 | 34.7% | 10.497 | 12.180 |
| 43, orb/RNG | 20.093 | 30.250 | 50.5% | 11.119 | 12.561 |
| 44, 28 actors/fireballs | 9.576 | 20.013 | 109.0% | 8.694 | 10.758 |

Logic counts completed epochs. Completed views count nametable flips after
both upload halves. A swapped view can have the same pixels as its predecessor.
The physical refresh rate, logic rate and view publication rate are distinct.
One deterministic warmed run per stage/build is reported, with a repeated
control/observer replay; these measurements do not supply statistical
confidence intervals or a general performance ranking. Hardware-derived RNG
observations can differ when code timing changes. The accuracy checks replay
those observations explicitly.

The observer forwards the core's real mapped read handler and checks each
returned code byte against the cartridge and current code-bank shadow. Each
run checks 32.9–39.7 million reads in `0x8000..0x9fff`; all eight runs report
zero mismatches, jammed instructions and sampled faults after initialization.
For each run, the observer and corrected control match byte for byte in audio,
serialized state, save RAM, system RAM, image, profile and watch trace. An early
control retained an obsolete diagnostic address; it was corrected and rerun,
and the failed diagnostic comparison remains in the private record.

The ordinary native checker also ran longer, independent 3,301-frame sessions.
Its 3,200-interval rates were 40.868, 22.312, 30.087 and 20.002 updates/s for
stages 0, 40, 43 and 44. Window endpoints explain the small differences from
the matched 3,000-interval table. Those windows are kept separate.

### Accuracy and original-Genesis comparison

The fresh original CPU comparisons pass 2,678 common-rule cases with 146,905
68000 instructions and 1,262 actor cases with 292,870 instructions and 192
observed HV samples. Both reviewed actor variants agree with the original.
Fresh actor contracts, watched state, registers and HV results also match the
retained baseline and optimized original-CPU receipts. The separate assisted
UIL flow check passes 6,044 frames; it is not original CPU execution. These
checks preserve the same semantic comparison against Genesis used before the
optimization. A fresh natural whole-game Genesis frame-rate comparison was
not performed.

The final NES passes the same 4,822-case native component matrix, comparing
all 79 game variables/arrays, returns, events and environmental consumption.
It is recorded in two nonoverlapping runs: 4,687 main cases and the remaining
135 original actor-dispatch cases. Their summed procedure counts equal the
R14 matrix exactly. A redundant clear-all diagnostic is excluded from that
total. The older authored variant also compiles and passes its 114 base native
component cases; its full 4,822-case native matrix was not rerun.

Additional optimization checks pass:

- 67,788 C-versus-native actor cases, including all 256 type bytes in every
  dispatch slot, movement and collision boundaries, guards, sound priorities,
  ordering, full state, HV consumption and software-stack balance. Of these,
  5,428 also run through typed UIL; 198 use retained original CPU vectors.
- 33,282 coordinate-pair calls in the mapped NES cartridge; 40,960 existing
  native terrain cases covering 256 views, 32 animation phases and five maps.
- 100,000 host object-drawing cases and 100,000 cache-sequence steps. Those
  checks use deterministic synthetic inputs and actual C bodies; they are
  distinct from native hardware qualification.
- 114 native completed renders, matched by full 616-byte captured game state
  and equal game/render epoch. Plane, palettes, attributes, projection cache,
  OAM index and staged OAM agree exactly: 11 matches on stage 0 and 103 on
  stage 44. Different host frames are expected after changing execution speed.
- Real pending-IRQ mapper tests retain the old bank race as a negative
  control. Store-boundary tests pass with the new selector. They do not
  exhaustively inject into the new no-write cache-hit branch or every native
  instruction boundary.

Normal native sessions pass 9,410 completed-state comparisons across 34
published fields, 9,410 independent controller checks and 208 replayed HV
words. Read-only feedback with ordinary controller input reaches the first
level's goal at epoch 897 / host frame 1,407, then the next stage at epoch
1,147 / host frame 1,882. A further 1,500 neutral frames pass. The unchanged
fixed host-frame input route remains a DNF: a hold lasting a fixed number of
physical frames traverses more game updates after optimization. Its result is
retained rather than changing its acceptance condition.

All 32 tracks and a mixed priority/stop/restart case pass 270,752 controlled
native sound services and 1,161 completed commands. The stricter sound checker
now compares all 2,579,855 ordered APU writes with the portable C oracle, not
only final register values. Five normal schedules also pass the unchanged
version-2 tempo protocol: each 3,000-interval window observes 6,000 service
entries and 5,935 source ticks, or 118.89749 ticks/s against 118.89964 Hz.
Completed services remain within the one-call endpoint allowance. Inconsistent
sampled high words remain unknown diagnostics; no debt is added to measured
rates. These results do not establish Genesis-to-NES waveform identity.

### Reproduction and delivery boundary

Use the lift/compile commands above with new private output directories. Keep
all input ROMs, generated ROMs, assets, raw traces and audio outside Git.
The permanent checkers accept explicit private inputs:

```sh
python scripts/check_miniplanets_actor_fast.py --rom "$ROM" \
  --cc65-root "$CC65" --original-root "$ACTOR_CASES" --output "$PRIVATE/actors"
python scripts/check_miniplanets_projection_pair.py --rom "$ROM" \
  --cartridge "$CART/program.nes" --core "$CORE" --output "$PRIVATE/pairs"
python scripts/check_miniplanets_globe_fast.py --rom "$ROM" \
  --cc65-root "$CC65" --output "$PRIVATE/terrain"
python scripts/check_miniplanets_renderer_objects.py --baseline "$BASELINE_RENDERER" \
  --output "$PRIVATE/objects"
python scripts/check_miniplanets_projection_cache.py --baseline "$BASELINE_RENDERER" \
  --output "$PRIVATE/cache"
python scripts/check_miniplanets_nes_game.py --rom "$ROM" \
  --cartridge "$CART/program.nes" --core "$CORE" --cc65-root "$CC65" \
  --common-cases-root "$COMMON_CASES" \
  --actor-cases-root "$ACTOR_CASES_1" --actor-cases-root "$ACTOR_CASES_2" \
  --actor-cases-root "$ACTOR_GEOMETRY_CASES" --phase all \
  --performance-host-frames 3301 --feedback-post-transition-host-frames 1500 \
  --output "$PRIVATE/native"
python scripts/check_miniplanets_nes_audio.py --rom "$ROM" \
  --cartridge "$CART/program.nes" --core "$CORE" --cc65-root "$CC65" \
  --output "$PRIVATE/audio"
python scripts/check_miniplanets_nes_timing.py --cartridge "$CART/program.nes" \
  --core "$CORE" --sessions-root "$PRIVATE/native" --protocol atomic-low-v2 \
  --output "$PRIVATE/tempo"
```

Set `PYTHONPATH=src` when running from the checkout. Use its prepared console
and test dependencies. The private profiling scripts and exact watch schedules
are retained with the hash-bound raw receipts for the matched table and native
render joins. The ordinary public checker supplies the independent longer
performance and accuracy replay. Their different windows remain explicit.

The local macOS full suite reports 2,756 passed, 142 skipped, three failed and
23 setup errors. All 26 failing/error test IDs match the prior integrated-main
run: Linux/GNU-linker fixture assumptions and the case-sensitive `VOL.2`/`vol.2`
media fixture on the case-insensitive host filesystem. This is not a green
whole-suite result. The affected console and packaging checks are run
separately; native hardware evidence is also separate from pytest.

GitHub is disabled for the account. This section and the sanitized receipt
are the local review update prepared for PR 56; they have not been posted to
GitHub. Delivery uses the configured local Git hub. No hosted CI, release,
merge, global installation, natural whole-game completion or 60-fps result
is claimed. The remaining large costs are game/renderer work and coherent
PPU upload bandwidth; full 60-fps presentation will require further measured
work on those boundaries.

## Globe rendering and bounded display uploads

The next qualified cartridge is
`265f3f1ea51baf46cc5e49bfb647348370d13ca929ac6a7c6def19a79587da35`.
Its source ROM, authored game tree and game-state contract remain unchanged.
The [display optimization receipt](evidence/miniplanets-full-game-2026-10-31/display-optimization.json)
records exact source/tool identities, measurements and private receipt hashes.
This section supersedes the previous upload implementation; its earlier
measurements remain historical observations of their stated cartridge hashes.

### Rendering and upload changes

HUD, palette-attribute packing, sprite emission and actor drawing now use
checked native routines. The retained C actor body remains an oracle. Native
actor drawing keeps all 48 slots, byte wrapping, culling, mace coordinates,
raft composition, player priority, rotating order and overflow behavior.
These are presentation changes; the source game procedures remain in UIL.

The fixed two-half upload is replaced by an immutable dirty-region plan.
Each physical nametable has an independent 296-byte shadow:256 terrain bytes,
24 HUD bytes and 16 attributes. The native planner compares 22 regions of at
most 16 bytes and queues complete changed regions in source order. Both shadows
start invalid, so first use uploads all contents even when they are zero.

NMI processes at most seven jobs per physical frame using fixed ROM routines.
A short stack of return addresses dispatches those unrolled jobs without C or
cc65 zero-page state. Each job sets its own PPU address, including nametable
selection. Main publishes `video_ready` after preparing the complete plan and
leaves staging, plan and selected OAM page unchanged until NMI finishes.
The final transfer, OAM DMA and nametable selection publish a coherent view.
A zero-data plan can still publish changed sprites. A completely dirty view
requires 22 jobs / 296 bytes / four upload frames; it is never called complete
before all four frames. Main cannot reuse speculative shadows while a plan
is pending. The controller's 256-entry lookup exactly preserves the old bit
mapping and sampled input frame while shortening NMI work.

The faster display handoff also makes rendering eligible more often. The
unpaced experiment increased complete swaps but spent enough extra time
rendering to reduce logic throughput. The selected adapter starts rendering
at most once per two completed game epochs. This controls presentation work;
it does not skip game updates or change game rules. Its theoretical render
start ceiling is 30 Hz when logic reaches 60 Hz. The retained unpaced cartridge
and its source snapshot describe the measured tradeoff, rather than a second
fully packaged runtime configuration.

### Matched performance and timing

Each native core run uses 3,100 physical frames with 100 warmup frames. These
receipts measure 2,999 intervals from frame 100 through 3099, rather than the
previous iteration's differently indexed 3,000-interval window. The same stage
seeds, invulnerability and neutral input apply to each build. Rates use the
core's emulated NTSC clock; host execution speed is excluded. This is one
bounded deterministic workload per stage/build with control replay, not a
statistical or natural whole-game performance ranking.

| Stage | Previous logic/s | Selected logic/s | Previous swaps/s | Selected swaps/s | Unpaced experiment logic / swaps/s |
|---|---:|---:|---:|---:|---:|
| 0, light | 40.922 | 41.182 | 13.908 | 20.601 | 34.208 / 22.785 |
| 40, eight maces | 22.405 | 27.595 | 12.184 | 13.787 | 18.577 / 18.236 |
| 43, orb/RNG | 30.240 | 33.326 | 12.545 | 16.673 | 24.870 / 20.000 |
| 44, fireballs | 20.000 | 25.872 | 10.761 | 12.946 | 17.495 / 16.713 |

Swaps count completed coherent buffers, not necessarily different pixels.
Logic and presentation are separate measurements. The chosen build improves
both over its immediate predecessor in all four scenarios. The unpaced
experiment favors visual swaps and regresses logic; it is not the default.

A new forwarding observer checks actual PPU writes, including OAM DMA and
scroll/control restoration. It uses the inspected pinned FCEUmm CPU and frame
batching to date writes at instruction completion. The conservative vblank
window is PPU dots 341 through 7160. This is an instruction-level emulator
timing check, not exact bus-cycle or physical NES qualification.

That check found the earlier build completed tile writes in vblank but let
some DMA and restoration writes extend into pre-render. The earlier cartridge
fails the new gate and remains its negative control. All four selected seeded
runs pass with no out-of-window writes, active-nametable writes, runtime
faults or content/control differences across 3,195 checked swaps. Captured
observer and uninstrumented control agree in audio, state, RAM, frame and trace.
Hardware stack samples show no possible downward wrap; they are not a formal
worst-case stack proof.

A separate 3,000-frame stage/movement schedule with active audio performs
95,968 PPU data writes and 681 coherent swaps. Its latest checked write is at
dot 6534, about 209 CPU cycles before the conservative deadline. Fully changed
synthetic buffers separately test both cold nametables, four full-dirty
uploads and two zero-data sprite-only commits. Each full upload takes exactly
four data frames, and all eight commits match the complete staged data and
OAM. The synthetic test pauses audio IRQs; the movement and tempo checks cover
active audio separately. A deliberately shifted HUD reference fails the
coherence gate. Missing observations and output inside Git are rejected.

### Preserved accuracy checks

Fresh original Genesis execution passes the same 2,678 common cases and 1,262
actor cases, 439,775 actual 68000 instructions in total, with 192 original HV
samples replayed into UIL. Both actor variants agree with the original. The
assisted typed UIL flow passes 6,044 frame updates across 55 stages and 479
placed actors. This is separate from natural whole-game completion.

The final NES passes all 4,822 complete-state component cases across 79 game
variables/arrays. Normal sessions pass 10,312 completed 34-field comparisons
and independent controller checks, with 228 recorded/replayed HV words. The
feedback route reaches the goal at epoch 897 / host 1214 and the next stage at
epoch 1147 / host 1643, followed by 1,500 neutral frames. The unchanged fixed
host-frame route remains a DNF.

The presentation primitives pass 4,096 HUD, 16,384 sprite, 40,960 terrain and
100,000 native actor-render cases. A further 4,096 actor cases include every
byte type and arbitrary OAM indices. Projection/mace helpers in the actor
simulation are synthetic; the separate 33,282 mapped projection-pair calls
and full cartridge checks cover real assets and bank integration. The native
planner passes 2,212 sequential calls / 11,900 jobs against an independent C
model, including both shadows, cold initialization, unchanged data and every
individual staging byte. Its isolated test assumes the runtime ownership
contract; the NMI stress test verifies that integration separately.

Completed-render comparisons join equal captured 616-byte game state and
equal logic/render epoch, with a ready staging buffer. Against the immediately
previous cartridge, 88 observed matching renders agree in terrain, palettes,
attributes, projection cache, OAM count and selected OAM page. Another 106 agree
with the earlier R 14 cartridge. Host frames differ after changing execution
speed. The comparison is bounded to those observed states.

All 32 audio tracks plus the mixed case pass 270,752 native services, 1,161
commands and 2,579,855 ordered APU writes. Five normal schedules pass the
unchanged atomic-low-v 2 tempo check at 118.89749 source ticks/s against the
118.89964 Hz target. State/controller/video replays match and inputs remain
unchanged. This does not claim Genesis-to-NES waveform identity.

### Repeatable local gates and GitLab review

The existing lift and compile interface remains unchanged. Add the following
to the earlier accuracy commands, using a prepared cc65 toolchain and fresh
private outputs:

```sh
python scripts/check_miniplanets_hud_fast.py --cc65-root "$CC65" --output "$PRIVATE/hud"
python scripts/check_miniplanets_sprite_fast.py --cc65-root "$CC65" --output "$PRIVATE/sprites"
python scripts/check_miniplanets_objects_native.py --cc65-root "$CC65" --output "$PRIVATE/objects"
python scripts/check_miniplanets_upload_plan.py --cc65-root "$CC65" --output "$PRIVATE/plan"
python scripts/check_miniplanets_upload_stress.py --core "$CORE" \
  --rom "$CART/program.nes" --manifest "$CART/manifest.json" \
  --map "$CART/build/game.map" --output "$PRIVATE/uploads"
```

`check_miniplanets_nes_display.py` accepts the cartridge, core, declared input
and watch schedules, and SRAM offsets resolved from that cartridge's linker
map. `--require-safe-display` fails on timing, coherence, active-table writes,
missing observations and possible stack wrap. Its receipts capture/recheck
all inputs and compile the packaged `miniplanets_display_observer.c`. Raw core,
ROM, state, code, pixel and audio observations remain outside Git.

The final source rebuild reproduces the paced measurement cartridge byte for
byte. The bridge also compares PRG and labels; generated source differs only
by the recorded platform comment and debug metadata. Maps differ and are not
claimed identical. This transfers the bounded observations for the same
executable bytes, not a broader source-equivalence claim.

The full Mac suite reports 2,770 passed, 142 skipped, three failed and 23 setup
errors. Its 26 failing/error test IDs exactly match the prior baseline's
Linux/ELF and case-sensitive-filesystem fixture issues. Affected and package
guards run separately; the whole suite is not described as green.

The GitLab intake confirmed that the previous optimization commit was already
present on its private imported branch. Of 120 expected published local refs,
119 matched and one unrelated PR 41 ref had advanced locally;214 additional
local preservation refs were intentionally outside that publication set.
GitLab main matched local integration. No Miniplanets merge request was visible; a later read found two draft
requests for other work. Historical GitHub discussion/CI receipts remain
local. This update publishes only this work's new
branch and a draft merge request, alongside its local PR 56 record. It leaves
other branches and integration unchanged. The connector handles project,
branch and merge-request metadata; ordinary Git transports the multi-file
history that its single-file commit tools cannot preserve. Publication and
readback receipts remain separate from executable qualification.

The new build remains below 60 Hz. Full-dirty views take four NMIs, source
hardware behavior is represented through declared adapters, and natural
all-level completion and physical NES operation remain unqualified.

## Uncapped rendering, exact terrain reuse and audio optimization (2026-10-31)

The previous balanced build, commit
`f34f6ef06f8a9e708073d095499205345d3950a6`, started drawing only after two
logical epochs. The new main loop attempts a draw after every completed game
update whenever the previous upload has finished. There is no software
30 fps render cap or minimum render-epoch spacing. Game updates still
synchronize to physical frames, and drawing waits for staging ownership.

The tested cartridge SHA-256 is
`8da56a19cf65be2aae46a913584d72776df0da6819d9784ec577e3ca75c012e6`.
Its source cartridge and UIL program are unchanged. Code-bank use is
7,952 / 5,011 / 6,872 / 5,945 bytes, with the same 55 data banks.
The sanitized [uncapped-rendering receipt](evidence/miniplanets-full-game-2026-10-31/uncapped-rendering.json)
binds the cartridge, adapter sources, compiler/runtime and private test receipts.
Generated cartridges, original assets, instruction traces and state dumps remain
outside the repository and distributable packages.

### What changed and why the output is preserved

Removing the epoch gate alone leaves rendering, upload planning and audio
competing for the CPU. The globe renderer now caches exact terrain output
when the complete world, camera and relevant animation bits match. Conservative
animation masks are checked against the actual generated terrain atlas:
21,504 same-mask frame pairs match all tile shapes; an intentionally wrong
zero mask differs on 13,824 pairs. Cache capture waits for a repeated camera
position to avoid copying every frame while the player moves.

The cache retains the terrain plane and palette plus world/projection data.
A hit restores the full plane after a different view or invalidating write.
When staging already contains that cached terrain, it restores only the first
row, which the pause overlay may have overwritten. Sprite preparation still
clears and recomposes OAM. Menus, endings and diagnostic upload command 253
invalidate the relevant ownership flags. Cache keys never assume an unchanged
world solely because its pointer is unchanged.

Each nametable has a conservative terrain-valid bit. A terrain miss invalidates
both bits. Only a certified cache hit with the same pause overlay may bypass
the terrain/attribute comparison; HUD bytes are always compared. Nonterrain
views clear the target certificate. There is no wrapping generation counter.
In the isolated assembled planner benchmark, the unchanged certified path
falls from approximately 6,072 to 646 CPU cycles per call. This excludes
interrupts, mapper and PPU work and is not a whole-frame speedup figure.

Audio now avoids envelope work for quiescent and stable phases, specializes
volume calculations, uses an exact PSG attenuation table and combines channel
selection scans. The original 512-state audio corpus drops from 6,763.47 to
6,254.47 mean cycles, a 7.53% reduction. A separate expanded 512-state corpus
falls from 5,469.58 to 4,871.02 cycles, a 10.94% reduction; these are different
datasets. All 32,768 PSG level/attenuation pairs match the C state and APU
snapshots, and the actual cartridge passes a separate ordered-write comparison.

The pending display plan remains immutable. Seven bounded jobs per NMI and
the existing vblank deadline are preserved. A fully dirty 296-byte plan still
requires four data-transfer frames, so removing the cap cannot guarantee
60 completed globe uploads per second.

### Matched performance protocol and results

Both builds run in the same pinned FCEUmm core. Each seeded stage has the same
valid source-initialized state, invulnerability assistance and neutral input.
Runs last 3,100 physical frames; after 100 warmup frames, rates use the 2,999
intervals between remaining samples and the core's 60.0998265 Hz clock.
Rates describe emulated hardware time, not the host's execution throughput.
The observer is checked against an uninstrumented replay for unchanged RAM,
state, audio/video output and controller input. These are deterministic bounded
workloads, without a statistical confidence interval or all-level FPS claim.

| Stage / workload | Previous game updates/s | New game updates/s | Previous completed swaps/s | New completed swaps/s |
|---|---:|---:|---:|---:|
| 0, ordinary terrain | 41.18 | 49.06 | 20.60 | 29.76 |
| 40, eight maces | 27.60 | 29.02 | 13.79 | 28.40 |
| 43, orbs | 33.33 | 41.06 | 16.67 | 32.24 |
| 44, dense fireballs | 25.87 | 28.10 | 12.95 | 26.29 |

The orb workload exceeds the former 30 fps render ceiling. Completed swaps
mean coherent buffer flips, which can repeat identical pixels. They are
reported separately from logical game updates and host display refresh.
Across these four runs, 5,823 flips have zero observed staging, physical-nametable, OAM,
active-nametable, fault or vblank-write mismatches. The intermediate uncapped
whole-restore build and earlier cache-only measurements are retained in the
receipt hashes so the selected partial-restore build can be traced.

A separate 3,000-frame run with varied movement and active audio records
43.54 game updates/s and 15.42 completed swaps/s, 104,044 PPU data writes and
744 coherent flips. Its latest observed write is at frame-boundary dot 6,533 against
the exclusive 7,161-dot deadline; the sampled minimum stack pointer is 0xA5,
with no observed wrap. Eight synthetic upload cases also pass, including six
full-dirty 22-job / 296-byte transfers and two OAM-only commits. Those synthetic
cases pause debug audio; the normal movement and cadence tests cover active
audio separately. Movement and full-dirty uploads remain material bottlenecks.

Native instruction-hook profiles forward the original hooks and pass byte-neutral
control replays. Audio still consumes approximately 12,062 CPU cycles per
physical frame in stage 0 and 13,490 in stage 44, about 40–45% of the budget.
The renderer consumes approximately 6,894 / 6,859 cycles per frame, while
upload planning consumes 1,998 / 281. Dynamic profiles describe each observed
workload, including its changed number of game updates and draws. They are
not identical-work per-call comparisons; hook categorization can assign a
small number of deferred branch/DMA cycles to a neighboring category.

### Accuracy, negative controls and outstanding limits

Fresh original Genesis CPU runs retain 2,678 common-function cases / 146,905
instructions and 1,262 actor cases / 292,870 instructions, including 192
observed HV samples and both actor implementations. The separate 55-stage,
479-actor / 6,044-frame reference-flow run is assisted UIL execution. It does
not establish a natural original-CPU playthrough.

The final cartridge passes all 4,822 native complete-state cases across 79
fields, 11,599 completed 34-field state/controller checks and 280 replayed
HV words. Its feedback route reaches the goal at logical epoch 896 / host
frame 1,194 and the next stage at epoch 1,146 / host frame 1,576. The fixed
host-frame route still records its DNF. The projection gate passes 33,282
native coordinate pairs. Terrain comparisons include 40,960 native cases,
two distinct 65,536-case cache protocols and 2,236 native upload-planner calls.
A matched-render comparison against the previous cartridge finds 229 shared
complete 616-byte game states with matching epochs, and no differences in
plane, palette, attributes, projection cache, OAM count or selected OAM page.

The cartridge's 32 tracks plus mixed workload execute 270,752 audio services
and 1,161 commands; all 2,579,855 ordered APU writes match the C reference.
All five strict version-2 normal-cadence windows pass, each covering 3,000
intervals after 100 warmup frames, 6,000 services and 5,935 source ticks.
The first timing attempt correctly rejects the faster feedback capture because
it has only 3,077 rows, below the unchanged 3,101-row requirement. A fresh
capture appends 24 neutral frames, extending its post-transition tail from
1,500 to 1,524. All 3,077 original-prefix frames, controls and raw states
match; no timing rule or tolerance is relaxed. The short rejected observation
is retained. A separate longer diagnostic capture is not counted again.

Negative controls detect omitted staging invalidation, an ignored target-valid
bit, incorrect animation masks and the historical mapper race. The final
mapper test also passes its fixed cases. None of these finite comparisons
prove whole-game semantic equivalence, Genesis pixel or waveform identity,
physical NES operation, or general ROM-to-ROM translation.

The full Mac suite records 2,771 passed, 142 skipped, 3 failed and 23 errors.
The 26 failure/error identifiers match the previous environment's Linux/ELF
and case-sensitive filesystem fixture problems; the full suite is not green.
Final affected checks and source-package / installed-cartridge reproduction
are recorded with the local and GitLab review receipts. The private source
snapshot includes the new cache/hint checkers and sanitized evidence under
distribution guards. This is a draft code update, with no integration merge,
tag, package publication or system installation.
