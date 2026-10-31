# Miniplanets full-game UIL and native NES profile

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

The native backend also uses seven checked 6502 intrinsics for subpixel,
mace, tile/collision and wrapped-radius operations. Sine/collision bytes are
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

The fresh full macOS repository suite records **2,534 passed, 141 skipped,
two failed and 23 errors**. The remaining failures/errors belong to unchanged
Linux ELF fixture groups that invoke Linux linker options or expect ELF from
the macOS compiler. This full local suite is not green. The final source
archive/resource guard and offline-kit fixture checks pass separately; native
game/audio qualification uses the explicit private inputs described above.

A further private, accuracy-controlled address-form experiment reduced native
code by 766 bytes and improved the dense-stage sample by 5.65% with fixed bank
placement. Its broader generator and layout requirements are not included in
this module. Earlier unprotected layout timings include a CPU-jam observation
and are invalid for performance ranking. The simpler qualified lowering is
retained; the exploratory receipt states its separate canary and runtime scope.
