# KQ1 checkpointed gnome, key and giant route

Closed Native05 qualified eight normal-input actions from score **14 to 34**
after **one supported quest-start checkpoint load**. The original game retained
the key, shield and chest at the end. The exported authored scene then passed
all nine phases in the genuine installed direct and separate-process player.
This qualification covers the checkpointed segment, with `fresh_game: false`.
A complete cold-boot route remains unqualified.

The [verification receipt](evidence/agi-gnome-giant-route-2026-11-01/receipt.json)
links the native, trace, player, attempted-run and platform summaries and six
selected original-engine frames. Independent native, export and installed-player
checks passed; their scope is recorded in the review summary. Hosted Linux CI
is unqualified; the full macOS suite was not rerun.
The affected AGI, IL-scene and player checks passed **1902 tests, 3 skipped**.

## Scope, origin and coordinates

The selected target is the user's original DOS AGI KQ1 edition. The
[resume runner](../examples/agi/resume_gnome_giant.py) loaded a real
`quest-start.sav` prepared through normal gameplay, then performed all eight
actions in one subsequent session. Its donor had completed the shield prefix:
room 36, score 14, clover and shield carried, shield protection active, no key
or chest. The [cave route guide](AGI_LEPRECHAUN_ROUTE.md) describes that earlier
preparation. The cave prefix is provenance for the saved state; Native05 did
not replay it.

The hash-bound origin records exactly one supported load, equal saved/restored
CPU state, matching session and CS/DS, a verified disk manifest, no guest edits
and the same initial 40-field projected state. Donor capture/result hashes,
checkpoint time and state hash are checked together. The runner primes a new
completed frame after loading because the old framebuffer is invalidated.
These supplied-record checks establish consistency and lineage. Their claim
ceiling is an observed checkpointed continuation, not independent
authentication of execution or full-game equivalence.

Coordinates below are **native AGI actor origins and walking baselines**. The
picture grid is 160 logical columns by 168 picture rows. Actor x is the left
baseline origin; y is the bottom baseline row. Normal ego is VIEW 0, width 6,
step size 1. A 320-pixel-wide screenshot normally doubles horizontal units;
status/input bands, viewport origin and crops affect vertical mapping. Read
actual frame metadata before converting. Video crop coordinates or red-torso
image anchors do not establish an AGI baseline.

## Qualified boundaries

| Phase / boundary | Room | Native ego anchor | Score |
| --- | --- | --- | --- |
| 0 / Quest start | 36 | `(88,131)` | 14 |
| 1 / Gnome ready | 40 | `(50,120)` | 14 |
| 2 / Three wrong guesses complete | 40 | `(50,120)` | 14 |
| 3 / Key taken | 40 | `(50,120)` | 17 |
| 4 / Tree ready | 19 | `(110,105)` | 17 |
| 5 / Tree unlocked | 19 | `(110,105)` | 19 |
| 6 / Giant awake | 58 | `(151,110)` | 19 |
| 7 / Giant asleep and close enough | 58 | Dynamic; witnessed `(51,143)` | 26 |
| 8 / Chest taken | 58 | Same as phase 7; witnessed `(51,143)` | 34 |

`ROUTE_CONTRACT` in the
[exporter](../examples/agi/build_gnome_giant_scene.py) has status
`qualified-checkpoint-segment`. Phases 0 through 6 have fixed coordinates.
Phases 7 and 8 deliberately use the stopped giant's dynamic source predicate,
command-time native distance proof and complete chest proof, with the same ego
pose at both boundaries. `(51,143)` is this run's witness, not a universal
pickup coordinate. The validator still supports fresh-origin captures; its
native qualification witness is explicitly restored-only.

At every boundary wait for original room initialization, animation and blocking
messages to finish. Check a fresh completed frame, neutral drawn ego, player
control 1, idle input, no active message window, dry state and no death.
Room identity alone does not establish readiness.

## Reach the gnome, make three wrong guesses and take the key

From room 36 go north to 45, then east through 46, 47 and 48. In room 48 approach
`(110,165)` and go Down into 33. Confirm the actual bank and entry position;
an exploratory generic exit reached the wrong bank. Leave east for room 40
and stop at `(50,120)`. Native05 completed this path.

1. Type `HI` and complete the original riddle message.
2. Type `GET KEY`. During the riddle this is a wrong guess.
3. Press F3 and Enter to repeat it, then F3 and Enter once more. Complete the
   original messages and capture stages 1, 2 and 3 individually.
4. Once the third wrong guess makes the key available, issue another ordinary
   `GET KEY` to take it.

The stage variable v84 advances 0 to 1 to 2 to 3. Stages 1 and 2 have f22 true,
key readiness false and no carried key. Stage 3 has f22 false and room-40 f21
true. All three intermediate scores remain 14. Flag 21 is a room-local
callback; derive key readiness only in room 40.

Required completed prints are logic 40 at `0x113` (message 5), `0x1e0` (19),
`0x1ff` (20), `0x201` (21) and `0x22f` (22). Their original handler completion,
modal input, source/session identities, frames and guest times are retained.
Each stage's print partition completes after its preceding snapshot and before
its own snapshot. The three extra guess records remain distinct from the nine
main boundaries.

The pickup completes print `40:0x2cc` (message 12), `get(5)` at `0x2d6`, the real
handler return and the score addition at `0x2db`. Native05's complete **59-fetch**
proof observes item 5 change from 0 to `0xff`, then return, then score 14 to 17.
Named OBJECT records and the live inventory table bind the item identity.
A completed message alone does not establish committed inventory effects.

## Walk to the tree, unlock it and climb

The qualified surface room sequence is:

```text
40 north 41 north 8 north 9 west 16 west 15 north 18 west 19
```

At `(110,105)` type `UNLOCK DOOR`. Original print `19:0x194` (message 6) completes,
v66 changes 0 to 1 and score rises 17 to 19; the key remains carried. Then use
`OPEN DOOR` and finish the animation. A separate ready observation establishes
v66 = 2, actor 1 drawn with VIEW 20/cel 3, ego `ignore.blocks` true and player
control 1 before entry to room 66.

Follow the collector's coordinate-watch route through rooms 66, 67, 68 and 69,
then west through 59 into 58. The
[collector](../examples/agi/verify_gnome_giant.py) contains the bounded waypoints.
The helper watches original coordinate writes and delivers an ordinary stop
input at the selected predicate, then verifies neutral direction and final
state. Releasing a direction key does not generally stop original AGI motion.
Native05 retained **631 complete verified precise motions and 865 coordinate
writes**. These counts describe movement observations, not whole-game actions.

Room 68 uses a conservative **arrows-only** admission policy at settled entry
`(95,159)`, after original initialization and entry callback f148. Require the
normal neutral/drawn/dry/controlled state, score 19, unchanged inventory and
active carried shield. Admit only **f23 false, v62 at least 150 within 0..250,
and v70 zero**. The source skipped dwarf initialization for that visit. Hidden
actor 1 alone is insufficient: an initialized visit may still have a spawn
timer. f20 is a fall callback, not an admission flag.

For a fully observed rejected but still safe visit, go left to `(94,159)`,
down to `(94,165)`, then Down into 67. Its entry script positions ego at
`(120,41)` and moves it to `(119,42)` with f148. After readiness and unchanged
state, go Up in column 119 to reenter 68 and observe normalized `(95,159)`.
The cap is **16 total visits and 15 completed retreat/reentry cycles**. A
rejected visit 16 stops before another retreat. Unknown input, contradictory
state, a changed safety predicate, score or inventory aborts immediately.
Menus and inventory-controller input are excluded because a global handler
can repurpose v62.

Native05 rejected visit 1 with **v62 = 132, v70 = 13, f23 true**, completed one
retreat/reentry, then admitted visit 2 with **211, 0, false**. The earlier
tree-restored diagnostic's first timer was 14, not 13. This is source-linked
host admission from observed state, not a native conditional-handler trace or
a guarantee of favorable RNG. Eligible timer spawns occur by room-68 invocation
44 inclusive; no milliseconds bound is established.

Static picture proposals use source horizon and the actor's live
`ignore.blocks` state to choose the priority-1 policy. They omit drawn actors
and added cels. Original movement, collision and room-transition readback
remain necessary for a proposed path.

## Sleep, then prove distance and chest pickup inside one command

Room 58 starts at score 19 with active shield, no chest and v86 = 0. Original
`stop.motion(1)` at `58:0x435` sets raw motion mode 0 and direction 0; the path
selects VIEW 52, v86 = 1, adds 7 and completes print `58:0x450` (message 29).
Native05 reached score 26 with f205 true. Raw flags bit 7, named `motion_bit`,
is retained as an opaque boolean and is never evidence of stopping. The
predicate requires actual integer motion 0 and direction 0.

Before `GET CHEST`, verify the drawn sleeping actor and calculate this
**host-derived** center Manhattan distance:

```text
abs(ego.x + ego.width // 2 - giant.x - giant.width // 2)
  + abs(ego.y - giant.y) <= 30
```

Native05 had ego `(51,143)` and giant `(39,167)`, width 30/height 15, giving
24. Its pre-command v70 was still zero. That byte is scratch state: the source
computes the relevant distance only inside the chest parser path.

Submit **one** ordinary `GET CHEST` command. The read-only probe observes
opcode 69, `distance(0,1,70)`, at `58:0x234`: actual native v70 write at
`CS:48a2`, resume `CS:48a6`, then real return at `CS:02fa` with source cursor
`code+0x238`. Engine/whole-logic hashes, session/DS, actor table, unchanged pose,
operands and saved/restored call-frame facts bind the receipt. Native05's result
was **24**, equal to the derived geometry and within 30. The score probe is
armed before continuing the original IF, without issuing another GET.

The same command completes print `58:0x254` (message 10), adds 8 at `0x25a`,
then `get(2)` at `0x25d` and the real return. The complete **68-fetch** proof
retains score, item, return order; the key's order is item, return, score.
Both bounded traces finish below 128 fetches. Final room 58 retains `(51,143)`,
score 34, normal neutral/drawn/dry/live ego, key/shield/chest carried, active
shield, v86 = 3, f104 and f169 true. The slice ends here because leaving room
58 changes giant-state interpretation.

## Preserve failed and diagnostic runs

These separate records remain in the attempted-run evidence. A later success
does not replace them or splice their observations into Native05.

| Attempt | Observed result and limit |
| --- | --- |
| Exploratory parser input | A 20-character command at 1 ms left a partial line and unchanged door/score. Twenty ordinary Backspaces and a blank frame cleared it; short `UNLOCK DOOR` succeeded. No backend-overflow cause was established. |
| Exploratory stairs | A requested 10 ms poll returned 79 ms; ego x90 to x92 crossed target 91 at y76. f3 was true, baseline `[3,3,3,3,3,2]`, with logic-67 fall path `0x51`. The guest closed without further execution. |
| Native02 | Completed 629 motions/863 coordinate writes and original sleep at score 26. Stopped before GET because an obsolete host guard required fresh pre-command v70. Ego `(83,101)`, giant `(71,77)`, derived distance 24, v70 zero; another 100 ms did not refresh it. No chest proof or committed wait-for-sleep action. |
| Native03 | Five actions through unlock; 372 complete motions, 373rd incomplete. Room68 `(116,143)` score19/shield255 became score11/shield0 with no coordinate write. No giant or GET. Its source/copy and two save-only checkpoint receipts were preserved. |
| Tree-restored diagnostic | One supported tree-unlocked load, then only the climb/sleep/chest suffix: 631 motions, native distance24, chest68-fetch proof, final58 `(51,143)` score34. It omits the earlier five quest actions. |
| Native04 | Fresh cave prefix failed after accepted rat payment. Original `75:0x1ed` message21 completed; diamonds were consumed and score9 to3, then f21 death at `(66,115)`. Submit was `(67,115)`, direction7, captured v70=27 but derived center distance23. Payment/death ordering is source-linked, not writer-traced. |

A future rat-payment proposal near `(98,127)` remains static, unimplemented and
unqualified. Native05 begins after that cave encounter and makes no repair or
cold-prefix claim. Source timing, helper schemas and cheap synthetic checks
should be reviewed before another long route. Preserve unknown/partial effects
and freeze runtime source hashes during a qualification run.

Private native snapshots are save-only during the original cold-start runs;
Native05 explicitly records its one subsequent load. Native03's quest-start
state hash is
`8b214e6ec4563a5e93fbbad83c45726e1ab1a9b553c545d1b2a8b1111293876b`.
Saving alone does not qualify restoration or cross-backend compatibility.
Native checkpoint files and the text player's in-memory checkpoint slots have
separate evidence and lifetimes.

## Reusable authored scene and installed player

The exporter checks the original AGI/OBJECT/resource hashes, nine contiguous
main boundaries, exactly three ordered guess snapshots, the door observation,
completed source-bound messages, command-time distance and separate pickup
proofs. Original text and frame bytes are not emitted in the scene. Every edge
guards all **40 projected typed native state fields plus phase: 41 variables**,
including seven inventory locations and carried flags for chest, key, clover,
diamonds, bag, shield and mushroom. Other OBJECT records, actors, timers,
alternate commands and routes are outside the projection.

| Authored text command | Captured segment |
| --- | --- |
| `use trail` | Quest-start to gnome |
| `use gnome` | Riddle and three wrong guesses |
| `take key` | Key pickup |
| `use tree` | Walk to the tree |
| `use door` | Unlock the door |
| `use stairs` | Door animation and ascent |
| `use giant` | Sleep and close-enough approach |
| `take chest` | Command-time distance and chest pickup |

The [player receipt](evidence/agi-gnome-giant-route-2026-11-01/player-verification.json)
records genuine installed core/player **0.28.0**, isolated `-I -B` execution
with `PYTHONPATH` absent, and matching installed identities in the parent and
three content workers. Direct and separate-process play checked every command,
all nine phases and all 40 native fields against the capture. Both modes
preserved state on stale, repeated and failed-precondition actions, restored a
before-chest in-memory checkpoint, invalidated old tokens after restore, and
reported the checkpoint missing in a fresh process.

The authored scene is a partial Z projection. It does not interpret AGI or
reproduce autonomous original-game timing. Its checkpoints are in-memory for
one backend lifetime, with no durable-save claim. The generated scene and
provenance remain private. Scene SHA-256:
`c119c90f9e1c9698971672e3fc22ee98fc96731a37c673a3b11fdc76a475fc84`;
provenance SHA-256:
`b3518909a659304d8c5cb7899a34f9e78335f5727f644239fd5da9fd7d816dd5`.

## Run with owner-supplied private inputs

Use the checkout root and new output directories outside checkout, source,
game-copy and donor directories. `PYTHONPATH=src:player:.` makes the source
packages available and is inherited by the example child backend. These are
source-invocation templates; the installed-player qualification above was
performed independently without that environment variable.

```sh
cd "<CHECKOUT_ROOT>"

PYTHONPATH=src:player:. python -m examples.agi.resume_gnome_giant \
  --source "<PRIVATE_GAME_DIR>" \
  --backend "<PREPARED_BACKEND_PATH>" \
  --project "<DONOR_PROJECT_FDB>" \
  --artifact "<QUEST_START_ARTIFACT_ID>" \
  --source-capture "<DONOR_CAPTURE_JSON>" \
  --source-result "<DONOR_RESULT_JSON>" \
  --output "<NEW_PRIVATE_CONTINUATION_DIR>"

PYTHONPATH=src:player:. python -m examples.agi.build_gnome_giant_scene \
  --source "<PRIVATE_GAME_DIR>" \
  --capture "<PRIVATE_CONTINUATION_DIR>/capture.private.json" \
  --artifacts "<PRIVATE_CONTINUATION_DIR>" \
  --output "<NEW_PRIVATE_SCENE_DIR>"

PYTHONPATH=src:player:. python -m fdisbull_player --backend-command \
  'python -m fdisbull.il_scenes "<PRIVATE_SCENE_DIR>/scene.json"'
```

`--artifact` is the quest-start saved-artifact ID, not a `.sav` filename. A
tree-unlocked checkpoint would omit earlier actions. Keep the one-load origin
and every action in one session; no record splicing or additional restore is
admitted. The separate full cold-start collector remains available:

```sh
PYTHONPATH=src:player:. python -m examples.agi.verify_gnome_giant \
  --source "<PRIVATE_GAME_DIR>" \
  --backend "<PREPARED_BACKEND_PATH>" \
  --output "<NEW_PRIVATE_COLDSTART_DIR>" \
  --checkpoints
```

That optional flag saves private checkpoints; it does not load them. Its cold
prefix retains the Native04 rat-payment limitation.

## Historical lead, exact bindings and remaining limits

The [verified Robb PDF research](research/kq1-robb-guide/README.md) identifies
*KQ1 guide for SCM route*, credited to Robb and dated 28 June 2022, through its
[public guide landing page](https://www.speedrun.com/kings_quest_quest_for_the_crown/guides/sy3ri).
The `HI`/`GET KEY`/F3 sequence and shield/sleep/chest route are attributed leads.
That guide uses a historical Tandy DOSBox 60K-cycle profile, a 63K variation and
favorable encounter/RNG assumptions. The later
[9.89 TAS route](research/kq1-robb-9.89/ROUTE.md) reports 157600 cycles and a
bag/diamonds payment. These profiles do not supply verified input timing for
this native branch. The PDF, captions, recording and extracted corpus stay
private; the repository keeps authored research and provenance.

Native05 raw capture SHA-256 is
`0c840eb1bf94a563a3ab6442594a557ce037a007c55980bcc1f25395a059bf6e`.
Its producer `resume_gnome_giant.py` was
`64ae79177334bd88f9df0fd5416d2c7be68167879fa2adc6ce0974a1a538023d`;
quest collector `verify_gnome_giant.py` was
`288836be2c73e88b8a6027bdb679d7803313e0533b44a272400a3b8853e7c6dc`.
The [native summary](evidence/agi-gnome-giant-route-2026-11-01/native-summary.json)
retains the full producer map and checkpoint lineage. Original source and
copied-originals checks cover 24 files and are unchanged after teardown; the
original database, donor receipts, backend and frozen implementation checks
also pass. No persistence errors were recorded. The
[trace summary](evidence/agi-gnome-giant-route-2026-11-01/trace-summary.json)
binds source offsets, original writers, real returns and bounded trace hashes.

| Remaining boundary | Status |
| --- | --- |
| Checkpointed native segment, export and installed direct/process player | Qualified within the scope above |
| Independent native, export and installed-player closure review | Passed within the recorded scope |
| Hosted ordinary/native Linux acceptance | Unqualified |
| Full macOS suite | Not rerun; inherited parent platform failures retained |
| Complete cold-boot route or arbitrary future RNG outcome | Unqualified |
| Packaging, release, installation change or merge | No such action claimed |

Keep original game/story files, source dialogue, states, databases, raw captures,
full traces and generated story content outside Git. The repository evidence
contains authored summaries and selected verification frames; full private
corpora remain excluded.
