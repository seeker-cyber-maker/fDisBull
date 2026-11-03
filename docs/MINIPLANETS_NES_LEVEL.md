# Playable Miniplanets Stage 1-1 on NES

This is the retained mapper-0 first-level experiment. The separate
[full-game profile](MINIPLANETS_FULL_GAME.md) adds all stages, score, lives,
timer, audio and a globe presentation through procedural UIL and MMC3.
Its scope and measurements do not replace this experiment's frozen receipts.

The source-bound console pipeline now produces a playable NES version of the
first level's logical gameplay. The original map, movement and collision data
come from the official Miniplanets REMIX REV04 cartridge. Native 6502 code runs
the recovered UIL rules; an authored flat-map NES presentation replaces the
Genesis globe renderer.

Use the D-pad to move, A or B to jump, and Start to restart. Collect the key,
jump across the water and reach a goal. Grass/flowers block movement even in
the air. Water kills on landing. Coordinates wrap around the original 256×256
world. The level displays win/death feedback and can be restarted after either.

This build covers Stage 1-1 through its first win or death. Score/tally, lives,
the time limit, audio, later levels and the original globe graphics are outside
the port. Freezing at the terminal screen and Start-to-restart are explicit
adapters. The original game's Start-to-pause behavior is not mapped here.

## Source and recovery contract

The original game is by Javier Degirolmo (Sik), under its preserved zlib-style
license. See the [official pinned source](https://github.com/sikthehedgehog/miniplanets/tree/0ac9c395289cc5d0837c96d45e61a27300e8eebc).
The exact 524,288-byte ROM SHA-256 remains
`e8aee1b9fedca87b638a7624709d7f6e1a2aff8a5222083346d1cd63963acbe7`.

`fdisbull.udl_miniplanets.lift_level` is a **reviewed source-bound
specialization**, rather than a generic 68000 decompiler. It checks the complete
ROM identity and reads the level map, object seed, direction, momentum and
collision tables from that original file. Its provenance binds the relevant
native code/data ranges, including `UpdateSubpixel`, `RunPlayer`, `GetTile`,
`RunKey`, `CollidesPlayer`, hurt/win handlers and the sound-request routine.
Unknown ROM versions, other stages, objects or tile mechanics are refused.

The result contains a standard `fdisbull-il-1` program, separate scene metadata
and provenance. The program uses 28 unsigned byte variables and eleven immutable
256-entry byte tables. The original notice and alteration attribution travel
with the exported UIL's evidence metadata. Original ROM bytes, assets and
generated level/table files stay outside Git and tool packages.

The implementation preserves the original X-then-Y collision order, toroidal
coordinates, 181/256 diagonal momentum with the original bit-reversed phase
correction, jump-button edges and decrement-before-ground testing. Key collision
uses the original wrapped signed-byte radius and special eligibility on the
first jump frame. Player processing precedes key processing, so goal checks use
the key state from the start of that frame.

## Shared UIL and NES module changes

The language now accepts optional immutable `tables`, each with `type` (`u8` or
`u16`) and `values`, and a `lookup` statement with `var`, `table` and `index`.
Table/type/index budgets are validated. A dynamic out-of-range read refuses the
entire evaluation and returns its original state without effects.

Native NES lookup initially supports exactly 256-byte tables and unsigned byte
indices, guaranteeing bounds without a partial-state fault path. The Genesis
UDC does not implement this additional table/scene profile and refuses it. The
existing shared scalar profile remains available on both targets.

The NES level backend compiles the same UIL arithmetic and branches, uses indexed
ROM reads, and renders a 16×16 tile map at half the logical coordinate scale.
The sprites, colors, font and HUD are authored adaptations. It publishes complete
state snapshots while executing the next tick in separate work RAM. Display
updates occur at vertical blank, with bounded publication and a conservative
20,000-cycle logic limit. These bounds and emulator observations are not a
real-hardware timing qualification.

In the qualified FCEUmm core, published input is one host frame behind its input
callback. The verifier predicts that delay from the scheduled input masks; it
does not accept observed button RAM as its own oracle. Startup takes four host
frames, after which each sampled frame completes one tick.

## Comparisons and results, 2026-10-31

The repeatable experiment uses the same hash-qualified FCEUmm and Genesis Plus
GX binaries recorded in the preceding [real-ROM pilot](GENESIS_ROM_TO_NES.md).
Every session checks the actual core and ROM receipt identities, and the final
guard rechecks both binaries, the original ROM and compiler/harness source hashes.

There are three independent comparisons:

1. **NES execution against UIL:** seven controller replays passed **1,562 full
   published-state comparisons**. They exercise level completion, horizontal
   and vertical wall blocking, jumping against walls, water death, wrapping and
   restart. The key is collected at logical tick **472**, the goal reached at
   **784**, and the unprotected water approach dies at **160**.
2. **Original CPU against transitions:** the original `UpdateSubpixel` executes
   for all **256 phase inputs**. Those actual outputs feed original `RunPlayer`;
   original `RunKey` then consumes the actual native player result. **1,796
   active player transitions** and **1,484 key calls** passed, covering the
   replays plus all sixteen D-pad combinations at three momentum classes and
   six floor/wall/water/key/goal boundaries. The probe executed **183,835 native
   instructions**, with no RAM changes outside the declared contract. Already
   terminal and Start-reset cases are explicitly excluded as adapters.
3. **Unmodified complete game against the port:** the original cartridge loads
   normally through its title and level intro, using only controller input.
   From an observed loaded-game baseline, **784 natural gameplay transitions**
   match a UIL shadow, including phase/subpixel. A second NES cartridge starts
   from that same observed logical input state and its **784 projected
   transitions match the actual Genesis replay directly**, through key pickup
   and the first win. The comparison aligns application ticks, not physical
   frame rates or pixels.

The ordinary NES cartridge starts with `InitPlayer`'s jump 16 / phase 0. The
natural-game baseline has settled jump 0 / phase 78. Those protocols are recorded
separately. The aligned cartridge uses the latter inputs specifically for the
direct replay comparison. Derived scratch variables are overwritten by each
tick; the declared projection consists of player position, angle, action, jump,
death/win, key count/activity, phase and resulting subpixel. The original game's
RAM and PC are never modified for the natural gameplay replay.

The original sound-request code executes during controlled CPU checks; no
gameplay or audio-request stubs replace its callees. Rendered audio and the
global score/time loop are excluded. A deliberately incorrect expected position
causes a persisted first-divergence failure in the original-CPU checker.

The [sanitized receipt](evidence/miniplanets-nes-level-2026-10-31/verification.json)
retains session counts, state projections, source/range hashes, native budgets,
trace/frame digests, exclusions and immutability results. Raw frame/RAM/CPU traces,
the recovered UIL, actual map tables and generated cartridges remain private.

## Build and replay

Use a new output directory outside every Git worktree. From an environment with
fDisBull installed, the public API is:

```python
from pathlib import Path
from fdisbull.udl_miniplanets import lift_level
from fdisbull.console_udc import write_console_rom

recovered = lift_level(Path('/private/intake/Miniplanets REV04.bin').read_bytes())
receipt = write_console_rom(
    recovered['program'], target='nes', scene=recovered['scene'],
    output='/private/new-miniplanets-nes')
```

The result contains `program.nes`, `program.uil.json`, `scene.json` and a manifest.
Open the cartridge in a compatible NES emulator. The exported UIL retains the
original license/alteration notice. To compile those saved inputs again from the
source checkout:

```sh
PYTHONPATH=src python -m fdisbull console-udc /private/level/program.uil.json \
  --target nes --scene /private/level/scene.json --output /private/new-replay
```

Reproduce the complete native comparison with the pinned external cores:

```sh
python scripts/verify_miniplanets_level.py \
  --rom '/private/intake/Miniplanets REV04.bin' \
  --nes-core /private/tools/fceumm_libretro.dylib \
  --genesis-core /private/tools/genesis_plus_gx_libretro.dylib \
  --output /private/new-level-verification
```

The orchestrator creates the normal playable cartridge, the separately aligned
comparison cartridge, replay inputs and private observations. Its original-game
title/intro schedule and checkpoint are qualified for these exact inputs and
core defaults; they are not a generic emulator-navigation procedure.
