# SNES Shadowrun room and keyword-conversation recovery

The supported native route matches **3,764 original checkpoints**, through the
morgue, hallway and first street update. The next update refuses an unmodeled
hardware-dependent random draw. **Live keyword play is not yet qualified.** The
conversation coroutine and three original response components are recovered
and independently checked; they have not been reached by a complete accepted
title-seeded native replay.

This study extends the private, source-bound macOS ARM64 `opening` profile.
It starts from the same qualified title checkpoint, derives game state from
the caller's pinned ROM and replays ordinary controller observations. Later
original checkpoints are comparisons, never replacement seeds. Original artwork,
portrait pixels, raster timing and APU playback remain adapted or excluded.
The C fragments are authored reconstructions of identified machine-code routines
and compile to UIL; they are not the game's recovered original C project.

## Source dependencies

The morgue exit is a volume in the second list consumed by `$80:8000`. Its
matched entry calls `$A44C` directly; it does not first write the queued request
handled by `$CC1B`. Player positions are shifted right by two before comparison
with the ROM table. The observed path loads entry `$1F`, crosses the hallway,
then loads entry `$01` onto the street. Opening a door and entering an exit
volume are separate actions. The original route needed a second opening of the
first door after stepping back; a blocked earlier approach did not prove the
exit inaccessible.

The staged room loader reads the source entry descriptor, retains world records,
resets the task and actor allocators, reconstructs the carried player, expands
the destination zone and creates its real actor tasks. It computes the source
camera and static collision lists before returning to the main loop. Entry
`$1F` has no camera clamp rectangle; entry `$01` has one. The street zone also
extends beyond the original morgue parser's end bound, so the new transition
parser uses each qualified decompressed stream's actual extent. Unsupported
entries, carried-party configurations and layouts still refuse.

The first checkpoint after a load retains the former dynamic collision heads.
Source graphics-cache decompression can overwrite those old links, including
producing invalid odd node values. The model marks that entire dynamic grid
unreadable until the source rebuild, and admits only the audited task-primer
path with closed cursor, absent target, no pending callback/request and no
active forced movement. The checker verifies those guards and compares static
collision at this boundary; it resumes strict reachable dynamic-list comparison
after the rebuild. This is an explicit transient exclusion, including the
already-excluded initial new-game grid, rather than byte equality for stale
graphics-clobbered data. Arbitrary script reads into the omitted raw cache
workspace remain guarded after rebuilding the logical grid.

The longer comparison exposed an omitted part of new-game initialization:
`$986C` expands 3,515 world-record bytes, then clears a counter table, copies
two ROM tables and initializes selected player statistics and flags. The new
producer preserves the source's untouched gaps. Ordinary room loads never run
that new-game reset. This matters for later portrait selection and script reads,
even though the earlier actor-only comparisons did not inspect those bytes.

Reused actor slots also retain animation reload and selector words. The source
direction setter can use those words even when the new action is `$FFFF` and
the animation-table pointer was cleared. Its low-bank lookup aliases live WRAM,
including the just-written call arguments. Reproducing that ordering fixed the
first street pending-animation mismatch without seeding the later checkpoint.

The street conversation is entered by source VM callback `$94`, not only by a
cursor Talk action. The callback remains suspended while `$92EF` runs and resumes
the same scheduler pass after return. The direct Talk dispatcher instead resumes
its own target-close/final-input continuation. Neither path advances world tasks
once per menu poll.

The conversation coroutine owns record selection, learned keywords, windows and
source service order. The `$A654` selector has hotkeys disabled. The primary
menu and keyword menu share instruction addresses but have different observed
stack return words, so the observer records their contexts separately. Exit has
its own final input poll at `$92B9`. Display waits, source input polls, main-loop
passes and video frames remain different clocks.

The real initial response learns keyword `$17`. Talk learns `$10`; asking about
that keyword exercises the source fallback entry and clears the response window
again before rendering it. SELECT in the keyword selector exits the whole
conversation. Optional response scripts are real task creations with one
immediate execution slice; the coroutine does not invent their effects or wait
for an unrelated task to complete.

The observed street responses contain no child script. That child-task branch
and the direct cursor-Talk continuation remain source-derived, with live
qualification pending; the recovered street conversation starts automatically.

## Hardware-dependent continuation

At task `$22`, callback `$63` targets `$80:C530`. Its output contributes to
`200 + (random_word & $003F)` task ticks, so skipping the draw or supplying a
constant changes real behavior and later persistent state. The generator reads
the NMI counter bytes `$1C92/$1C93` separately, and latched display-beam bytes
after a `$2137` latch. It updates byte seed `$1D04`. The counter is maintained by
the display interrupt; it is not an APU latch. Prior unmodeled generator calls
already tainted the seed, so the known logical-loop state cannot derive this
output.

The separate `shadowrun_snes_rng` fragment implements the pure source
calculation. Its inputs are `rng_seed`, `rng_nmi_low`, `rng_nmi_high`,
`rng_beam_h` and `rng_beam_v`; outputs are `rng_result`, `rng_next_seed` and
`rng_supported`. One independent observation-only original trace and compiled
native/UIL comparison qualify that transform. It is deliberately unconnected
to the live opening VM. Observed seed/counter/register values were verification
inputs only; no RNG return or later gameplay state was supplied to the runtime.

The remaining design is an explicit platform-input module with recorded
hardware observations for input-conditioned comparisons and a separately
labeled local source, or recovery of the original clock before continuing.
That choice is open. Neither the standalone proof nor the original conversation
captures establish autonomous hardware timing. The current native app stops
transactionally at this boundary and preserves its previous accepted state.

## Comparison method

Route planning consulted [Draco_Knight's walkthrough](https://gamefaqs.gamespot.com/snes/588651-shadowrun/faqs/12605).
Its door/hallway guidance was a planning hypothesis; the execution, memory
writers, task behavior and comparisons reported here were established locally.

The official SNES9x source revision is
`fae2fea08f74180759ef540ee94259213f503480`. Two uninterrupted ordinary-input
references cross both room boundaries and exercise different conversation paths.
Each has a checkpoint-only observer comparison at every retained main-loop
checkpoint, plus selected RAM/images and final hashes from the unmodified core.
This is one emulator family, not independent hardware.

The complete original-only references contain 4,045 and 3,993 checkpoints. The
first asks about keyword `$17` and exits; the second uses Talk to learn `$10`,
asks about it through the fallback response, then cancels a reopened keyword
menu. These are reference runs, not successful full native replays.

The comparison covers actor/task state, initialized animation, sprite allocation,
reachable collision records and owners, camera, cursor/action selection,
windows/text, persistent records, party identity and the sorted keyword list.
Original before/after predicates establish room entry and a live carried player,
item ownership/removal and learned-keyword changes. Source-record and writer
probes additionally distinguish an actual insertion from a displayed menu label.

The native compiler is checked against the complete exposed UIL state over a
short continuous prefix and declared one-step samples. Complete original-input
native replay and sampled native/UIL equality are different coverage claims.
Unsupported operations restore the complete native state transactionally.

| Current source/native validation | Result |
| --- | --- |
| Title through first street update | 3,764 checkpoints; 3,902 public steps; 139 interaction polls |
| Persistent records | 3,761 bytes plus declared party/room words at every prefix checkpoint |
| Native versus UIL | 5,686,434 exposed state elements over continuous prefix and declared one-step samples |
| Transient dynamic-grid exclusion | Initial checkpoint and first post-load checkpoints 3,478 and 3,763 only; guards and static comparison remain active |
| Earlier interaction routes | Patch 1,973; Scalpel 1,928; repeat 2,128; door response 2,363 checkpoints |
| Earlier profiles | Opening 1,615 checkpoints; scripted profile 60 checkpoints |
| Unmodeled RNG update | Repeated refusal with complete state rollback; no invented random value |
| Component-focused regressions | 68 passed; native/UIL/source checks for three response layouts, two vertical queries and one isolated RNG transform |
| Broad macOS suite | 4,194 passed, 142 skipped, 3 failed, 23 setup errors; same 26 non-green cases/types as the preceding baseline; source unchanged during run |
| Distribution and checker follow-up | 1,015 passed |
| Native app | Same program/core as the independent checker; 3,903 accepted updates including title; next RNG update stops without moving the player |
| Refusal contract | Eight complete-state readbacks compare 1,197,144 elements; forged stale-state cases are diagnostic guard tests, not ordinary reachability |

These route counts overlap and are not unique coverage added together. The
sanitized [evidence directory](evidence/shadowrun-snes-transitions-2026-11-03/)
separates original-only references, components, native prefix, regressions,
packaging gates and remaining limits.
An early provisional component receipt had a filename collision; its
reconstruction is historical only and is excluded from acceptance evidence.
The final component receipt was freshly recomputed against frozen sources and
written to a new path with source hashes checked before and after.

Three separate source response cases qualify raw text decoding, the subsequent
in-place style-control rewrite and portrait-aware word wrapping. The source
left margin applies on every line while retaining the full window stride.
These component checks are separate from main-loop comparisons, which skip
the suspended conversation, and from the typed input-phase checks inside it.

Portrait/OAM buffers, raster scratch, decompressor scratch and unknown music
restore decisions carry explicit taint. Later script reads of those unknown
regions refuse. The observed no-pending-animation exit branch is guarded; it
does not acknowledge an unimplemented deferred-animation drain. A typed display
service is an adapted presentation boundary, not original pixels or timing.

## Reproduction and scope

Use the same caller-owned ROM, title WRAM and save-RAM identities documented in
[the opening study](SHADOWRUN_SNES_OPENING.md). Build with
`shadowrun-snes-build --profile opening` into a fresh private output directory.
The native view uses adapted actor markers, recovered camera/cursor, source menu
labels and decoded conversation text. Arrows choose, B confirms and Tab maps to
source SELECT cancellation. Live keyboard and onscreen operation require their
own qualification; offscreen rendering does not establish either.

`scripts/check_shadowrun_snes_interactions.py` accepts the reference directory,
checkpoint-only baseline and unmodified baseline. `--require-room 1` requires a
real entry change and a live carried player; `--require-keyword` additionally
requires a learned-list change, typed keyword confirmation and subsequent
source conversation return. The current native route does not pass that gate.
The checker binds source, input journal, native
program and artifact hashes before and after the run. The controller host's
`--inputs` argument is a JSON file path. Its selected-video-slot limit is 6,000,
still bounded and with one checkpoint per selected frame for larger selections.

The prior profiles and interaction checks remain separate regression contracts.
General scene progression, arbitrary NPC conversations, long keyword-list
scrolling, combat, original graphics/audio and full-game equivalence are outside
this bounded route. Original ROMs, RAM, states, saves, decoded text, images and
generated private apps stay outside Git and tool packages. Local verification,
packaging, hosted CI, merge, release and system installation remain distinct gates.
