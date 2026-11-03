# KQ1 mushroom-island crossing and observed pickup

A fresh physical route now crosses the river north along room 33's right edge,
lands in room 48, walks west to room 47 and picks up the mushroom. The original
parser accepts `GET MUSHROOM`; the score changes from zero to one and inventory
item 24 becomes carried. The neighboring x153 alignment stops at the bush.
The [sanitized receipt](evidence/agi-mushroom-crossing-2026-10-31/receipt.json)
binds source identities, native observations, selected stored frames, player
checks and private artifact hashes. Original resources, states, databases, raw
captures/traces and generated scenes remain outside Git.

## Resolve the description before choosing coordinates

The [runner's glitch guide](https://www.speedrun.com/kings_quest_quest_for_the_crown/guides/2r57k)
describes an exact edge alignment that bypasses a bush, followed by northward
water-walking. The [written route](https://www.speedrun.com/kings_quest_quest_for_the_crown/guides/qnbmx)
uses normal speed for alignment. Direct inspection of the
[runner's original video](https://www.youtube.com/watch?v=gD3Bvhqk98I&t=12s)
resolves its relative room description: PIC 33 is visible at 12.500 seconds,
and PIC 48 by 12.600 seconds. Numeric room IDs and coordinates below are our
resource-derived adaptation, not a published numeric input recipe.

The [firsthand TAS submission](https://tasvideos.org/7105S) identifies KQ1.COM
2.0F and the mushroom-island water-walk that skips the bird. Nine selected
local file-size/MD5 pairs match its public table. This is an identity comparison
of selected files, not authentication of a complete distribution.

The earlier static catalogue's room33-left/room34-right seams are a different
candidate pair. They do not identify the crossing shown in this run. Following
the public description literally without checking its visual room context
would have sent the investigation to the wrong side of the river.

## Original-game route and adjacent control

The collector starts a new process and fresh private game copy, walks
`1 -> 8 -> 41 -> 40 -> 33 -> 48 -> 47`, and types the pickup command. Its
approach explicitly uses the already-qualified
[room-41 boundary water-walk](AGI_GOAT_BRANCHES.md). Both skips use ordinary
arrows. There are no debugger memory/code/register edits, redirected calls,
teleports or native-state loads. The shared launch helper saves a private
baseline but this route never restores it.

| Boundary | Observed result |
| --- | --- |
| Before crossing | Room 33, `(154,87)`, normal VIEW 0, width 6, score 0 |
| Over the river | Room 33, `(154,55)`, fresh native frame, no water/swimming/death state |
| After north exit | Room 48; original game settles near `(129,140)`, then ordinary input normalizes that anchor |
| Mushroom interaction anchor | Room 47, `(94,90)`, item not carried, score 0 |
| After original pickup | Same anchor, item 24 location `0xff`, f121/f123 true, score 1 |
| Adjacent control | From `(153,87)`, north request reaches `(153,85)` and remains there over 20 repeat polls; direction and control direction remain north, keyboard queue settled |

Room 48's ordinary arrival from 33 reaches `draw(ego)` at source offset `0x39`.
Its explicit position branch applies to previous room 80, not this route. The
observed room-entry placement is owned by the original game; no debugger
coordinate operation supplies it. The complete native placement routine was
not traced, so its internal search mechanism remains an inference.

At source control row 84, the x153 baseline contains priority 0; x154 excludes
that blocking pixel. At row 55, x153 is entirely water (six 3s), while x154 is
`[3,3,3,3,3,15]`. This decoded geometry supports the observed alignment and
whole-baseline explanation. It remains separate from tracing the entire native
collision routine. The neighboring control establishes bounded non-advancement
under a received north request, not a proof of permanent unreachability.

The replay uses bounded static paths for the gnome screen and island interior.
They exclude unconditional barriers, water-only baselines, triggers, a
conservative upper boundary and extracted conditional water rectangles.
Priority-one allowance is explicit. The planner ignores dynamic actors and
does not establish native safety; every proposed segment is executed through
physical input, with exact neutral waypoints and failure on unexpected stops,
displacement, hazard state or blocked movement. Tight movement disables
fast-forward temporarily. Guest and wall limits remain separate.

```sh
PYTHONPATH=src:. python -m examples.agi.verify_mushroom \
  --source /private/kq1 --backend /private/dosbox-x \
  --output /private/fresh-mushroom-route
PYTHONPATH=src:. python -m examples.agi.verify_mushroom \
  --source /private/kq1 --backend /private/dosbox-x \
  --output /private/fresh-mushroom-control --adjacent-control
```

## Source-linked score and inventory evidence

Logic 47 tests the parsed word groups at `0x162` and the inclusive ego-position
rectangle `(74,70)..(94,90)` at `0x183`. The action erases object 1, prints
message 9 at `0x18f`, sets f121/f123, adds one to score variable 3 at `0x195`
and gets inventory item 24 at `0x198`. The native collector observes the
original blocking print handler and uses one settled physical Enter to close
the message before continuing.

The OBJECT hash, live table bounds, three-byte stride, item index, name pointer
and loaded `mushroom` name bind the inventory read independently of story flags.
The collector then checks:

- Score write `CS:72da`, resume `CS:72de`, BX=3, AL=1, exact loaded logic 47
  and source cursor `0x198` after the addition.
- Item-location write `CS:7482`, resume `CS:7486`, DI at the live item-24
  record, carried byte `0xff` and the original get-handler call frame.
- The actual original return at `CS:02fa`, expected stack transition, and
  returned source cursor `0x19a`.

A bounded fetch trace covers the score-to-get-return interval. The receipt
records its actual count below the 128 ceiling. Original writes and handler
return are observed separately; fetch events do not certify completion of every
instruction. A fault retains the primary exception, known committed effects
and any partial trace, independently of cleanup/persistence failures. A reread
must preserve the complete known event prefix, not merely its length.

## Reusable partial Z scene

The separate scene exporter supplies `use crossing`, `use trail` and
`take mushroom`. It binds the four route states plus the midwater frame,
source/PIC/OBJECT identities, input delivery, completed original dialogue,
native pickup proof and trace artifact. It refuses missing, contradictory,
stale or incomplete evidence. Responses are authored; original message text and
frames do not enter the scene. Hashes check supplied identity and consistency,
not execution authenticity.

```sh
PYTHONPATH=src:. python -m examples.agi.build_mushroom_scene \
  --source /private/kq1 --capture /private/fresh-mushroom-route/capture.private.json \
  --artifacts /private/fresh-mushroom-route --output /private/new-mushroom-scene
PYTHONPATH=src:player python -m fdisbull_player --backend-command \
  "python -m fdisbull.il_scenes /private/new-mushroom-scene/scene.json"
```

This is an authored projection of observed transitions, not autonomous AGI
execution or a full KQ1 recovery. Phase/state guards reject repeats and stale
requests. Checkpoints restore in memory and invalidate old context tokens; a
fresh content process has no saved checkpoint. Durable IL-scene saves are not
added by this follow-up.

## Verification scope

MR !15 head `4e8ab3a` was reviewed against `2ad1b07` with fresh existing tests,
authored failure probes and artifact readback. No material actionable finding
was established in that diff. The new collector's fault tests separately
exposed and closed partial-trace retention and contradictory-reread gaps.
The focused AGI/scene/player checks passed 950 tests with four skipped. The
full macOS ARM64 suite passed 3,032 tests and skipped 123, with two failures
and 23 setup errors in inherited Linux/x86/GNU-toolchain checks. That run
remains red; it supplies no Linux CI qualification.

Failed approaches remain in the receipt: the first crossed water in room 40;
the second stopped at an obstacle. Their original/private-copy files remained
unchanged. The successful replay uses a qualified physical approach around
those hazards. Repeated runs qualify the selected route and edition, not
deterministic replay for all game timings or arbitrary dynamic actors.
Linux CI, integration merges, packaging, release and system installation are
separate gates and are not performed here.
