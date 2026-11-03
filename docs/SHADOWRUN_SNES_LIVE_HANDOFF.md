# SNES Shadowrun live actor research: handoff

Date: 2026-11-03. Base: `c813158d24c19e4781973acb8c9e0a5f455ee111`.
The resumed checkout was clean at that commit. Its GitLab draft !40 was closed
when inspected; this follow-up preserves that history and supplies a new local
and GitLab handoff. Original inputs, captures and prior delivered apps remain
private and unchanged.

The follow-up recovers actor-flag production, source actor ordering and mutable
collision rebuilds, then compiles the composed UIL to ARM64. A separate source
NPC controller/kinematic projection demonstrates two moving actors. These are
bounded research profiles with explicit exclusions, rather than a full scene
or a complete NPC/script implementation.

## Available profiles

| `shadowrun-snes-build --profile` | Initial source frame | Behavior and limits |
| --- | --- | --- |
| `static-morgue` (default) | 2999 | Preserved original captured-geometry profile |
| `live-morgue` | 2999 | Mutable collision lists, source ordering, cardinal animation and projected flags; 200 successful updates maximum |
| `npc-intro` | 2000 | Two noncolliding NPC controllers and kinematics; both stop together when either reaches an unqualified edge |

The live limit is an **analysis budget**, not a recovered original-game timer.
The live profile assumes the captured 7F tables, camera, stationary nonplayer
poses and scene context. It has no reliable general detector for later script
dispatch, table mutation or a scene change. Successful observed routes do not
establish every possible trajectory or unrestricted exploration.

The NPC profile projects coordinate-target control, countdowns, ROM velocity
lookup, positions and depth. It excludes rendering flags, animation, gravity,
colliding actors and general script dispatch. A new direction, actor-follow
target, nonnegative task-completion signal or unsupported physics edge refuses.
Two controllers are advanced transactionally as one frame, so the first actor's
refusal also prevents partial advancement of the second.

```text
fdisbull shadowrun-snes-build --profile live-morgue \
  --rom /private/source.sfc --ram /private/ram-002999.bin \
  --save-ram /private/save_ram.bin --output /private/new-live-study

fdisbull shadowrun-snes-build --profile npc-intro \
  --rom /private/source.sfc --ram /private/ram-002000.bin \
  --save-ram /private/save_ram.bin --output /private/new-npc-study
```

All generated output stays outside Git. The original ROM is independently
hash-checked at native context creation; captured data is private build input.
The app starts paused: Space runs/pauses, R resets, Esc closes. Arrows move in
the morgue profiles; the NPC study runs autonomously. The world-coordinate
view draws modeled collision rectangles for the live profile and two markers
for the NPC profile. Cyan is slot `44`, orange slot `46`; these are observed
slot identities, not invented character names. Original artwork, camera and
audio are not reproduced. Snapshots render stored native state without GUI
operation. Live keyboard behavior is not independently qualified here.

## Source recovery and ordering

The exact SNES ROM remains SHA-256
`e6bc0a595d5c7c4bc0bbb61ffe35a70288a77eb78544ed74682d489a9e6f07f4`.
The frame-2999 seed remains
`0032d4c7e01fce638a8ef653be6ab94871d7aa51ce48bb65d5d7b1444f791211`.
The NPC frame-2000 seed is
`faa776f34a5b2d9f0aad328ffc44d9d4065523a77caf3d412d46b2d9258f52ab`.
The baseline core is the previously pinned official SNES9x build. Source routes
use ordinary controller input without RAM patches. Snapshots are zero-based,
after `retro_run`; observer traces retain instruction-entry mode/registers.

| Dependency | Recovered source |
| --- | --- |
| Dynamic collision heads | `81:80F7–83FA` resets 256 heads |
| Dynamic actor rectangles | `81:8799–8858`, using actor pose/bounds/height |
| Node insertion and ownership | `81:846E`; heads, node record/next and byte-addressed owners |
| Actor depth | `80:ABB0–ABB8`, wrapped word sum shifted right |
| Actor order | Two adjacent passes `80:AF89–B031`, with `B032/B07A` adjustments; stable ties |
| Actor flag scan/merge | `80:B1DE–B82E`, current pose/camera/ROM sprite geometry and reconstructed scratch |
| Walking/idle animation metadata | `80:ABCD–AC58`, `AD52`, `AA3C` and `A912` branches |
| NPC target controller | `80:C7DC–C8E2`, countdown, Manhattan distance, axis choice and ROM velocity tables |
| NPC noncolliding kinematics | `80:AAB3–ABBB`; actor slots `44` and `46` |

Trace order establishes collision rebuilding from the preceding actor poses,
followed by motion, depth/order and flag scanning. A source-fed same-frame
rebuild gives different results. The composed model seeds once and derives
later state itself; later original poses, scratch values and rectangles are
comparison evidence only.

The flag scan's presentation-queue side effects are excluded. Its marker means
a potentially effectful nonzero tile call, not proof every call writes. The
projection preserves the selected actor flags and source collision state on
the compared routes; it does not claim whole-WRAM or graphics equivalence.

## Verification

| Check | Result |
| --- | --- |
| Independent short route | 61/61 consecutive source frames; 307,210 native/UIL elements |
| Independent extended route | 191 updates; 63/63 sampled source frames including flag transitions; 951,360 native/UIL elements |
| Live analysis budget | 200 accepted updates; call 201 refused twice with complete native rollback; this is not additional original-source coverage |
| Individual NPC controllers | Slot `44`: 30 frames through 2030; slot `46`: 37 through 2037; eight original fields each, then direction-change refusal |
| Two-NPC demo | Both actors: 30 frames through 2030, then frame-2031 refusal and repeat rollback; 1,815 native/UIL elements |
| Source-fed collision component | 61 frames, five arrays / 4,249 elements each; source-fed inputs make this a separate component edge |
| Broad macOS suite | 3,852 passed, 194 skipped, 3 failed, 23 errors; all 26 non-green cases/types exactly match baseline |
| Prepared-input follow-up | All 52 cases initially skipped for missing cc65/m68k/Miniplanets selections passed with the recovered prior inputs |

The live comparisons cover six player fields, all twelve 44-slot actor arrays,
active actor order and all five collision arrays. Native/UIL complete-state
agreement qualifies the compiler edge separately. Original coverage is sampled
where stated. The extended source route ends at frame 3190; the 200-step cap
check does not extend that original-behavior claim.

Reproducers: `check_shadowrun_snes_live_heldout.py` (source-fed component),
`check_shadowrun_snes_live_frame_heldout.py` (composed source/native),
`check_shadowrun_snes_flags.py` and `check_shadowrun_snes_flag_projection.py`
(flag stages), and `check_shadowrun_snes_npc.py` /
`check_shadowrun_snes_npc_demo.py` (NPC projections), all under `scripts/`.
They verify source/capture/core hashes and input/phase contracts. The native
backend restores the complete state on status 2 or a runtime fault. Direct
GameMachine callers must snapshot and restore if the procedure returns an
unsupported status; a raw procedural call can have partially changed state.

Broad-suite and package results, exact final source head and publication
readback are retained in the local handoff review. No hosted CI, merge,
release, whole-game qualification or global installation is claimed.
The broad run and 52-case follow-up are separate invocations; the latter
restores coverage of those cases without recasting the broad run as green.

## Friction and the resulting investigation decisions

- **Frame-end equality hid mutable scratch.** The scan matrix looked identical
  in snapshots, yet the CPU wrote it hundreds of times within a frame. Trace
  producer/consumer stages; derive intermediates instead of substituting a
  captured matrix. This decision is now in the bundled investigation skill.
- **A rebuild needed ordering, not just new coordinates.** UP first diverged
  at frame 3004 because the preceding actor-order pass swapped two entries.
  Source sorting and byte-addressed ownership resolved the mismatch.
- **Sparse checkpoints mislocated the cause.** The initial DOWN checkpoint
  was 3100; consecutive traces found the first flag transition at 3078. A later
  composed mismatch at 3139 exposed the negative-second-height branch at
  `80:B375`. A focused regression now covers that branch.
- **Component agreement was too easy to overstate.** Flag comparisons supplied
  observed pose/camera; collision comparisons supplied preceding actor state.
  They are documented separately from replay seeded once and evolved without
  future source inputs. The skill now makes that distinction explicit.
- **A position jump was not proof of walking.** Slot `54` moved at frame 1051
  through placement writers `D0E7/D0F0`. Slots `44/46` instead had consecutive
  walking and controller/velocity writers around frames 2000–2010.
- **Restricted UIL authoring is a subset of C.** A ternary expression was
  rejected; the source helper was rewritten with explicit branches, keeping
  the existing IR contract.
- **Interruption did not restore an emulator.** Retained receipts identify
  evidence and inputs, while a live process belongs to its current owner. The
  skill now directs agents to recheck that boundary before issuing more input.

## Next work, in dependency order

1. Establish a source-derived scene/script and table-mutation gate. Watch the
   room-transition and actor-dispatch producers before widening the research
   budget; the current captured-table assumption is not a runtime detector.
2. Extend the NPC direction setter at `80:AA3C` and its animation/action edges.
   The current refusal occurs when axis control changes and direction 2 would
   become 0. Keep the existing source-seeded cases as regressions.
3. Recover `C8C3` task completion (`136C` actor field, redirected task links
   and `0C7E` flags), then the surrounding `C9B0` script dispatch. Distinguish
   script placement from locomotion and waypoint completion.
4. Compose NPC controllers into the live scene only after source flags,
   animation, script ordering and collision/gravity branches are qualified.
   The current intro kinematics do not authorize arbitrary moving NPCs.
5. Extend original-backed held-out routes across the new boundary. Preserve
   all current unsupported results and compare the first divergence before
   widening input, scene or performance claims.

The original static profile is retained as a compatibility/reference lane.
The new models and guarded refusals are reusable work, with the unresolved
edges above left explicit for the next agent.
