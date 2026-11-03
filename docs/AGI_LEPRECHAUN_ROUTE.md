# KQ1 cave route: diamonds, shield and mushroom exit

The final collector completed this branch from a fresh original-game process:
clover, unopened bag and mushroom preparation; diamonds for the rat; the shield;
and the small-opening exit. It finished in room 36 at `(88,131)`, normal VIEW 0
and width 6, score **14**, with clover and shield carried. Source and copied
originals rehashed unchanged after shutdown. No guest edits, redirected calls,
teleports or state loads were used.

The [verification receipt](evidence/agi-leprechaun-route-2026-11-01/receipt.json)
binds the implementation, backend, source and stored evidence. A preceding
collector revision also completed a fresh route; its positive result remains
separate from qualification of the final failure-handling correction.

This guide covers one branch in the selected original DOS AGI KQ1 edition. It
combines ordinary guest arrows and parser commands with read-only source,
position, print-handler and writer observations. The collector is
[verify_leprechaun.py](../examples/agi/verify_leprechaun.py); the separate partial
scene exporter is
[build_leprechaun_scene.py](../examples/agi/build_leprechaun_scene.py).
The receipt binds this exact game edition, backend, collector and exporter.
It does not establish whole-game recovery or general AGI compatibility.

## Prepare the three carried items

Start a fresh original-game process at room 1 with score zero. The route needs
the clover for the leprechaun passage, the unopened bag for its diamonds, and
the mushroom for the eventual small opening. The final fresh preparation has
these milestones:

| Milestone | Final fresh observation |
| --- | --- |
| Clover in room 24 | `GET CLOVER`; carried clover and active clover flag; score 0 to 2 |
| Stump in room 6 | `GET BAG` directly, without a prior `LOOK`; unopened bag carried; score 2 to 5 |
| Island approach | Use the earlier room-41 boundary skip, then the room-33 northward island crossing |
| Mushroom in room 47 | `GET MUSHROOM`; mushroom carried and available; score 5 to 6 |

The two river approaches have their own evidence and limits in
[the goat-branch investigation](AGI_GOAT_BRANCHES.md) and
[the mushroom-island crossing](AGI_MUSHROOM_CROSSING.md). Their earlier
qualification does not by itself qualify the new connected cave replay.
Static interior paths propose how to connect the milestones; the original
engine must accept each segment.

The [authored reconstruction of Robb's recorded route](research/kq1-robb-9.89/ROUTE.md)
helped identify useful parser actions, advance typing and the shield-to-mushroom
exit order. That external recording is a separate evidence source. Its visible
save restore followed by restart, timing profile and unknown inputs are not
substitutes for a fresh local witness. The video and extracted frame corpus
remain private; only authored route prose and provenance belong in this
repository.

## Enter the hole, open the bag and follow the tunnel

Coordinates here are native AGI actor coordinates, with a six-pixel walking
baseline unless stated otherwise. They are not coordinates measured from the
320 by 200 research-video crop.

1. Return from room 47 to room 48 and approach `(81,130)`. Ordinary movement
   enters the hole. The descent settled in room 73 at `(90,139)` after the original
   landing sequence finished.
2. Type `OPEN BAG`. The original action replaces the carried bag with diamonds
   and raises score from 6 to 9. The route keeps the mushroom and clover.
3. Continue from room 73 down into room 74, then take the left passage into
   room 75. Ordinary movement normalizes the rat-room boundary to
   `(149,115)` before the recorded approach.

Wait for room initialization and landing to finish, the actor to be drawn,
movement to settle, and each blocking message to complete before treating a
boundary as ready. An accepted keyboard request is input-delivery evidence;
the corresponding room, inventory, flag or score transition establishes the
action's observed outcome.

## Pay the rat and retain the refusals

The exploratory run made three `GIVE BAG` submissions. The first two reached
the original refusal print at logic 75, source offset `0x201`, message 22.
Those failed submissions remain part of the evidence. The third reached the
acceptance print at `75:0x1ed`, message 21, with an observed distance sample of
29. It changed inventory item 15 from carried location `0xff` to `0`, reduced
score from 9 to 3, and let the original rat departure finish with f138 set.

The distance sample is not a universal acceptance threshold or a promise that
the same delay works on another run. The rat and player can move between a
sample, typing, Enter delivery and parser execution. The collector therefore
pretypes the command through the ordinary parser and submits during a bounded
approach, then checks the original branch and committed effects. A refusal is
a known outcome that can inform a later approach; an unknown execution reply
does not authorize repeating the action.

Both fresh replays recorded one typed `GIVE BAG` submission and no original
refusal; the final collector normalizes the post-payment anchor to `(82,115)`
through ordinary movement after the rat has gone.

After departure, approach the door and use `OPEN DOOR`. Enter room 76, the
leprechaun entry hall, then continue into the separate throne room, 77. Clover
must remain carried and active. This is the clover-protected branch; it does
not qualify a clover-free passage, another rat solution or the scepter route.

## Approach the shield from below

A geometrically open route across the upper throne area is insufficient. The
King's conditional barrier and the drawn shield's own collision baseline
affect movement that the static picture alone does not describe. The successful
final approach went below both before moving east, reaching hero `(133,135)`
in room 77 through `(100,135)` and `(133,135)`. The fresh replay accepted those
waypoints; the upper approach and shield-baseline collision remain failed
controls rather than being silently replaced in the investigation record.

At the successful final anchor, `GET SHIELD` produced the following
separate observations:

| Boundary | Final native observation |
| --- | --- |
| Source operation | Logic 77 `get(21)` at `0x3dd`, followed by the score addition at `0x3df` |
| Original item write | `CS:7482`, resume `CS:7486`; item 21 becomes carried while score is still 3 |
| Real get-handler return | `CS:02fa`, with the expected original stack transition and source cursor `code + 0x3df` |
| Original score write | `CS:72da`, resume `CS:72de`; BX = 3, AL = 8; score 3 to 11 |
| Bounded continuation | Complete 32-fetch observation interval, below the 128-fetch ceiling |

The live inventory binding checks the selected `OBJECT` identity, table bounds,
three-byte record stride, item index and name reference. Item 21's record
starts at table base plus 63 and its location byte is at base plus 65. A flag
or a plausible final score alone would not establish that item binding.

The source offset, native writer offset and runtime source cursor are distinct
address spaces. The collector checks the loaded logic identity and its bytes,
the owned stop, native segments, writer/resume pair and call frame. It observes
the original handler return rather than inferring it from the source's next
instruction. The fetch trace covers that selected interval; it is not a trace
of every cave operation or the whole game.

## Small-opening exit and original regrowth

The final replay observed the complete source-predicted sequence:

1. Leave the throne along the left stair approach at `(2,95)`. In room 78,
   let the original move finish at `(145,130)` and observe its completion flag.
2. Walk to `(20,80)` and type `EAT MUSHROOM`. The original blocking print
   completes before VIEW 60, width 4, item consumption, f120 and the score
   change are accepted. The live actor has the original `ignore.blocks` flag
   and a positive remaining timer. Score changes from 11 to 13.
3. Walk left with the original four-pixel baseline and unit steps. The narrow
   control-line passage is allowed by the game's own small-form policy; the
   debugger does not change that policy or move the actor.
4. Room 36 adds another point, owns the move to `(88,131)`, restores VIEW 0
   and completes `36:0x58`, message 13. The final witness has width 6, no small
   form, timer zero and score 14. Clover and shield remain carried; the
   mushroom is consumed. f124 records consumption, not the active small form.

The [small-form frame](evidence/agi-leprechaun-route-2026-11-01/small-at-opening.png)
and [outside frame](evidence/agi-leprechaun-route-2026-11-01/cave-outside.png)
are distinct stored native observations. The receipt also records the timer,
inventory, completed original messages and normal final state. A decoded
branch or a single screenshot would not establish all those postconditions.

## How collision proposals support physical play

The route helper decodes selected room pictures and proposes bounded paths for
the current six-pixel actor baseline. It uses the first decoded `set.horizon`
in the room logic when present, otherwise a declared horizon of 43, and
excludes rows through that horizon. Its search is bounded to 26,880 nodes and
1,024 steps and includes extracted source water rectangles as conservative
hazards. These limits describe the route helper; they do not change the
separate collision scanner's documented horizon limitations.

Priority-one passability follows the live original actor's `ignore.blocks`
flag. Reading that flag does not change it to make a route pass. After the
original mushroom action, the small-form guard must observe the original
flag together with room 78, VIEW 60, width 4 and timer greater than one before
the precise leftward exit step is allowed.

A decoded static picture omits drawn actors, added cels, runtime blocks and
some script-dependent behavior. A found path remains a proposal. The King and
shield approach demonstrates why native collision still decides whether the
route works. Precise waypoint segments check room, position, view, width,
step size, water/death state and settled movement; precise movement disables
coarse fast-forward temporarily. Room transitions separately check bounded
progress, readiness and the destination room. A blocked or displaced segment
stays a failed path rather than becoming an inferred success.

## Seven-action partial Z projection

The exporter is designed to consume a complete capture with eight contiguous
boundaries and seven ordered actions:

| Action ID | Separate-player command | Expected room and score after the action |
| --- | --- | --- |
| `enter-hole` | `use hole` | 73, score 6 |
| `open-bag` | `use bag` | 73, score 9 |
| `follow-tunnel` | `use tunnel` | 75, score 9 |
| `pay-rat` | `use rat` | 75, score 3 |
| `enter-throne` | `use throne` | 77, score 3 |
| `take-shield` | `take shield` | 77, score 11 |
| `leave-cave` | `use exit` | 36, score 14 |

The initial boundary is room 48, score 6, with clover, bag and mushroom carried.
Every program requires both its expected phase and every captured projected
field before applying the recorded transition. Guards cover room, score,
position, direction, drawing state, view, width, step size, swimming, water and
death state, all five relevant carried-item states, clover activation,
mushroom availability, small form and rat removal. The exporter requires all eight declared room/x/y anchors, including the
normalized rat entry and payment boundaries; it also guards the exact
projected state at each action.

Accepted, completed keyboard delivery, increasing frame identities and
source-bound completed original prints are separate evidence requirements.
Shield export additionally requires its hash-bound inventory writer, real
handler return, score writer and bounded trace. Original dialogue is checked
privately through its resource and text identities; responses emitted by the Z
scene are authored. Hashes and consistency checks do not authenticate execution
or recover unmodeled branches.

The separate player consumes this authored partial projection. Repeated
actions and stale context tokens must be refused. In-memory checkpoints
restore projected state and invalidate old context tokens; a fresh content
process has no saved checkpoint. This is neither durable game saving nor
full-game equivalence, autonomous AGI execution or recovered timing.
The installed 0.28.0 core and player matched all eight native-derived scalar
and inventory phases directly and through a separate content process. The
independent rebuild produced byte-identical scene and provenance files. See
the [player receipt](evidence/agi-leprechaun-route-2026-11-01/player-verification.json).

## Command templates

Replace these placeholders with user-selected private locations and prepared
Python environments. Native output and scene output must be fresh directories
outside the checkout and separate from the source; scene output must also be
separate from the capture/artifact directory. These commands do not install
the backend or player.

```sh
KQ1_SOURCE='<private-original-game-directory>'
KQ1_BACKEND='<prepared-compatible-dosbox-x>'
KQ1_RUN='<new-private-native-output-directory>'
KQ1_SCENE='<new-private-scene-output-directory>'

PYTHONPATH=src:. python -m examples.agi.verify_leprechaun \
  --source "$KQ1_SOURCE" --backend "$KQ1_BACKEND" --output "$KQ1_RUN"

PYTHONPATH=src:. python -m examples.agi.build_leprechaun_scene \
  --source "$KQ1_SOURCE" --capture "$KQ1_RUN/capture.private.json" \
  --artifacts "$KQ1_RUN" --output "$KQ1_SCENE"
```

Use a separately prepared player interpreter and a core interpreter for the
content process. The backend-command value is parsed into arguments by the
player; the inner quotes preserve paths containing spaces.

```sh
KQ1_PLAYER_PYTHON='<python-with-the-separate-player>'
KQ1_CORE_PYTHON='<python-with-the-core-scene-service>'

"$KQ1_PLAYER_PYTHON" -m fdisbull_player \
  --backend-command "\"$KQ1_CORE_PYTHON\" -m fdisbull.il_scenes \"$KQ1_SCENE/scene.json\""
```

From the player, follow the seven commands in the table and inspect inventory
at the bag, payment, shield and final boundaries. A successful projection run
checks the exported slice; it does not execute those original game actions.

## Qualification record

| Gate | Result | Evidence |
| --- | --- | --- |
| Original and private copy | All 24 files unchanged after teardown | Final source/copy manifests and selected source identities |
| Final collector replay | Fresh complete route, no guest edits or state loads | `native-02`, collector `e277a72b`; eight anchors and seven actions |
| Rat payment | One typed submission, no original refusal in each fresh replay | Accepted print, diamonds removal, score reduction and completed departure |
| Shield | Item write, real get return and score write separately observed | Complete 32-fetch trace below 128; original OBJECT record/name binding |
| Small exit and regrowth | Complete, normal final state and score 14 | Original small-form policy, timed passage, room-36 print and final actor/inventory |
| Scene export | Exact eight-anchor capture accepted | Private scene/provenance hashes in the receipt; generated content stays private |
| Separate player | Passed with installed 0.28.0 | Direct and separate-process action/inventory/state checks, stale/repeat refusal, failed-precondition preservation and in-memory restore/token invalidation |
| New cave tests | 181 passed | [focused log](evidence/agi-leprechaun-route-2026-11-01/tests.log) |
| Full ordinary Mac suite | 3,213 passed, 123 skipped, 2 failed, 23 errors | Same inherited ELF/Linux/GNU fixture cases; full suite remains red |
| Hosted Linux CI | Unqualified | No ordinary/native Linux acceptance is claimed |

Independent review caught a failure-path gap: a returned saturated trace page
could be discarded before a later failed cleanup read. The final collector
retains that page first, keeps completion false, and preserves known inventory
and score effects. The regression is red on the retained old collector and
green on the final code. [Review metadata](evidence/agi-leprechaun-route-2026-11-01/review-summary.json)
and [platform limits](evidence/agi-leprechaun-route-2026-11-01/test-platform-limits.json)
keep those checks separate from the successful native route.

The launch helper saves a private baseline, but this collector route does not
restore it. Preserve refusals, blocked approaches, partial traces, unknown
execution outcomes and persistence/cleanup errors alongside successful
observations. A failure in native advancement or its stop/message observation latches a
refusal of further execution; readback cannot authorize replaying an action
to repair a missing receipt. A failed route predicate also ends the standalone
run with its partial capture.

Keep original game files, source dialogue, generated scene content, saves,
emulator states, databases and full raw captures/traces outside Git. The
sanitized receipt identifies private artifacts by hash and includes selected
authored summaries and stored frames. No release, package, installation, merge
or Linux CI result is claimed.
