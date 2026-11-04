# SNES Shadowrun: title-to-morgue initialization

This continues the [task-dispatch study](SHADOWRUN_SNES_SCRIPT_DISPATCH.md)
on 2026-11-03. The `opening` profile starts from the qualified title-menu state,
consumes NEW GAME, constructs the first scene and its tasks from ROM, executes
the scripted introduction, creates the player, and accepts cardinal movement
in the morgue. It is an adapted native study: actors appear on a coordinate
grid with decoded source text, rather than original artwork. Audio delivery,
original video pacing, combat, inventory, other rooms and unrestricted play
remain outside the qualified route.

The sole state seed is the title snapshot after video frame 839, before START.
No later actor poses, task PCs, room state or collision snapshots are injected
into this profile. The title is itself a prepared state; boot, logos and the
construction of that title state are not recovered by this experiment.

## Private local build

```text
fdisbull shadowrun-snes-build --profile opening \
  --rom /private/source.sfc --ram /private/ram-000839.bin \
  --save-ram /private/save_ram.bin --output /private/new-opening-study
```

The factory checks the exact ROM, title and save hashes. The new output directory
must remain outside the checkout: its native library and UIL seed contain private
game-derived data. Source ROM SHA-256 is
`e6bc0a595d5c7c4bc0bbb61ffe35a70288a77eb78544ed74682d489a9e6f07f4`;
title SHA-256 is
`15caaf78faed99408c783119ac5e1703da066b904e5570dd895b7bcb49db9d93`.

The title runs immediately. Return confirms NEW GAME; arrows move the cursor or
player. Space pauses, R resets and Esc closes. B and Select have their source
menu mappings; unsupported in-game continuations refuse transactionally. An
unsupported update preserves the complete native state. The host requests 60 Hz
logical updates, which does not reproduce the original game's video-frame timing.
The earlier four prepared-state profiles retain their separate seeds and contracts.

## Recovered chain

| Producer | Modeled effect |
| --- | --- |
| Title input and selection | Held/previous/edge words, source selection order, NEW GAME initialization and input reset |
| Task pool and frames | Real heap headers, free list, root tasks and argument frames from ROM tables; child insertion and parent resumption |
| Scene construction | World and room decompression, persistence filter, actor allocation, camera clamps, scene pointers and static collision geometry |
| Script execution | Active linked scheduler, ROM bytecode, supported native ABI and task-local stack/PC/waits |
| Actor behavior | Coordinate and diagonal controllers, follow targets, direction/action changes, motion countdown, movement and animation completion |
| Presentation dependencies | Sprite-pool allocation/freeing, sort metadata, window ownership/timers, ROM Huffman text and logical font layout |
| Player readiness | Real party allocator, input-reset and forced-motion ordering, supported player controller and live collision rebuild |

Native callbacks are recovered effects, not generic acknowledgements. Child tasks
can run and resume a waiting parent in the same scheduler pass. A newly allocated
sprite can change later sorting even when the display is an adapted grid.
Window text must be decoded and laid out before its close condition is evaluated.
These dependencies explain why adding isolated movement functions was insufficient.

The source has nondeterministic or unmodeled presentation inputs. The model records
opaque audio requests and marks their latches, RNG and raster scratch as unknown.
Subsequent supported script reads of these unknown regions refuse. The RNG taint
is byte `$1D04`; the adjacent word `$1D05` is a scene-request field with a known
initializer. Width and address identity matter here. The observed no-focus `C1`
refresh path emits a typed refresh event and taints display scratch; it is not a
general display implementation. Unknown room triggers and scene changes refuse.

## Comparison protocol

The reference is the user's exact ROM under official SNES9x source commit
`fae2fea08f74180759ef540ee94259213f503480`, ordinary controller input and no
memory patches. A bounded observer records WRAM immediately before `80:962E`,
the source main-loop boundary. The canonical run contains 2,716 video frames and
1,615 consecutive checkpoints, with no dropped observations. START pulses advance
the opening, then RIGHT is held on video frames 2700–2710 and released at 2711.

A video frame is not a game-loop pass. Scripted waits and display transfers can
span several frames, and player input can be read at a later point in the same
pass. A separate controller journal records input at the actual main consumer
and player-controller consumer. It contains 1,614 main samples and 31 player
samples, with no dropped, duplicate, conflicting or disagreeing observations.
The model receives the observed external button word. Its own previous-button
word is compared to the source, never replaced by an observed future value.

The observer was checked against a previous checkpoint-only observer: all 1,615
checkpoint serials, video-frame locations and WRAM digests agree. A separate
unmodified-core run agrees at seven selected WRAM snapshots, six selected images
and all five final RAM/state/frame/save hashes. That unmodified core has no
instruction hook; these are selected/final comparisons, not 1,615 unmodified-core
instruction observations. Instruction/write hooks do not establish DMA or MMIO
coverage.

`scripts/check_shadowrun_snes_opening.py` seeds once at the title, invokes the
public transactional native entry, and compares each subsequent source checkpoint.
It validates the original, seed, observer, controller journal, compiler outputs
and authoring-source hashes, and rechecks them after execution. Later checkpoints
are comparison evidence only. Compiler checks compare complete native and UIL
state for the initial continuous prefix and declared one-step samples seeded from
the already-running native model. Those samples establish a compiler edge; they
are not a complete continuous UIL interpretation of every pass.

The original comparison covers active actors and relevant physical flags, task
list order and frames, initialized animation and sort metadata, sprite allocation,
logical window state and decoded text through its terminator. Collision checks
walk every active head and reachable node. Unused array slots and rendering flags
are excluded explicitly; their stale contents do not establish collision behavior.
The first dynamic list is checked only after its first producer has run.

The complete recorded route passes all **1,615 source checkpoints** (initial
construction plus 1,614 logical transitions), including eleven consumed RIGHT
samples and release. No selected source value diverged.

| Check | Result |
| --- | --- |
| Actor state and physical flags | 664,302 values; mask `$056B` includes collision bit `$0100` |
| Task state, order and frames | 387,426 values |
| Logical windows | 39,510 values |
| Reachable collision geometry | 2,022,636 elements |
| Sprite allocation and actor metadata | 312,090 values |
| Decoded text through terminator | 40,235 bytes compared privately; text excluded from receipts |
| Native/UIL compiler edge | 1,584,605 complete state elements; continuous title/first-two-pass prefix plus seven sampled one-step comparisons |
| Native app | Same program, seed, generated C/header and core; 1,615 updates accepted; final player `(1395, 2023, 256)` |
| Refusal after the route | B interaction and reserved input each retried; 576,220 exposed state elements unchanged across four refusals |
| Prior scripted profile | Fresh 60-pass original comparison, 17,920 source values and 4,318,524 complete native/UIL elements; repeated update-61 rollback |
| Broad macOS regression | 3,986 passed, 142 skipped, 3 failed and 23 setup errors; all 26 non-green cases/types match the prior baseline; tested source unchanged |

The source-fed construction component separately checks 3,515 world bytes,
263 room bytes, 1,756 actor/task write bytes and 1,975 collision/camera/pointer
values. Party creation and text layout have separate instruction-boundary
comparisons. These support diagnosis without substituting for the composed route.
The save bytes consumed for rotation were independently observed equal at title
frame 839 and the end of the same original run.

Sanitized receipts are in
[`docs/evidence/shadowrun-snes-opening-2026-11-03/`](evidence/shadowrun-snes-opening-2026-11-03/).
Broader regression and exact-commit package results are retained in the local
review. Original files, states, screenshots, text, generated apps and
byte-containing program/seed dumps stay in the private workspace.

## Friction and next analysis choices

The bundled investigation skill now directs the agent to identify initialization
writers before widening a replay. It distinguishes task creation from APU transfer,
initial allocation from per-pass mutation, source checkpoints from video frames,
and source-fed component tests from a replay seeded once. It also records the
low-WRAM aliases used by animation, allocator-to-sort dependencies, input-consumer
journals, byte-width taints and reachable collision coverage.

The next questions should start at the first unsupported consumer: additional
player actions, interaction/dialogue choices, room triggers or an original visual
projection. Recover the relevant writer and downstream reader, then extend the
same checkpoint comparison. Broadly inventing handlers or accepting callbacks
without their effects would weaken this contract. Local native/package results,
hosted CI, release publication and system installation remain separate gates.
