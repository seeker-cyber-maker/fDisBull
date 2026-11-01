# KQ1: the dragon and magic mirror

One fresh original-DOS run completed the dagger, well, water, dragon and mirror
route, then returned to the surface with the mirror at **score 28**. All eight
actions and nine main observations belong to that one session. The run exported
two private diagnostic checkpoints and performed no state loads. The collector
used ordinary keyboard input, with no guest memory/register edits, teleports
or code layers.

The [native summary](evidence/agi-dragon-mirror-route-2026-11-01/native-summary.json)
records source identities, completed actions, frames, original message bindings,
writer/return observations and teardown checks. The
[attempt ledger](evidence/agi-dragon-mirror-route-2026-11-01/attempts.json)
preserves the earlier incomplete runs separately. This qualifies the recorded
segment; whole-game recovery, a winning campaign and arbitrary timing/RNG
reliability remain outside its scope.

## Observed route

Coordinates below are AGI game units: a 160-by-168 picture grid with the actor's
left x origin and bottom walking baseline y. They are not screenshot click
coordinates. Each boundary is neutral and has its own newly completed frame.

| Boundary | Room | Position | Score |
| --- | --- | --- | --- |
| Fresh game | 1 | 110,100 | 0 |
| Dagger carried | 3 | 120,114 | 7 |
| Bucket detached and carried | 12 | 65,120 | 9 |
| On the well rope | 49 | 81,51 | 10 |
| Underwater passage; water acquired | 52 | 75,26 | 14 |
| Dragon chamber | 51 | 131,136 | 15 |
| Dragon retreat completed | 51 | 146,131 | 20 |
| Mirror carried | 51 | 45,115 | 28 |
| Returned to the surface | 22 | 140,83 | 28 |

The run has 223 accepted/completed action input records and six completed
source-bound action messages. Two separate controls add four input records
and two completed messages. Repeating `GET MIRROR` and then `THROW WATER`
preserved the selected score, inventory and resolved-dragon state. Both
controls retain before/after frames; their replies are checked against their
actual source call sites.

All 24 original files and all 24 private game-copy files matched their manifests
after teardown. The tested backend and 21 declared runtime dependencies also
matched their frozen hashes. The process exited 0, with no supervisor timeout
or recorded persistence error. The complete capture SHA-256 is
`2af06b3630806fa1c967740444eaf2f4a69b79ef870506815caae6417051b35f`.

## Source-led movement and readiness

The [Sierra Help AGI walkthrough](https://sierrahelp.com/Walkthroughs/KQ1AGIWalkthrough.html)
provided a secondary lead connecting the dagger, well, water and mirror. The
[external source-derived playthrough](https://peterkelly.github.io/agi-re/docs/games/kq1_playthrough_analysis.html)
explicitly describes an unreplayed static candidate. Their positions, timing
and edition correspondence were treated as hypotheses. The selected local
LOGDIR/VOL, picture and view resources supplied the source checks; the original
guest supplied the runtime outcomes.

Several boundaries required more than a room number:

- The rock is a live object that the background-picture path model omits. The
  successful ordinary approach goes north of it, then into the upper source
  interaction rectangle. An earlier approach stopped against the rock.
- Room 5's source horizon is 55. The inherited planner's north approach at
  row 48 was invalid for that room. The collector uses a source-qualified
  row-56 approach before the ordinary north exit.
- `CLIMB ROPE` first mounts Graham at room 12's top-rope pose. A settled
  VIEW 143, position 39,132 and f180 are checked before sending Down. The
  original game then enters room 49. Further downward movement reaches water;
  `DIVE` accepts the selected source's v94 states 1 or 2.
- Room 52 automatically acquires inventory item 26 and sets f88 when the
  detached bucket is available. Another room-49 source path can set f88
  without acquiring item 26, so the exporter checks actual inventory too.
- The legacy `in_water` observation is physical flag 0. At the recorded
  underwater pose, the original PIC52 baseline is entirely priority 4 and the
  settled flag is false. Room 52, VIEW 73, v94, air counters and inventory
  establish the relevant underwater context. The exporter binds the original
  picture and sampled baseline instead of treating flag 0 as a story label.
- The dragon's follow callback can cause death before the water parser runs.
  The collector pretypes one `THROW WATER`, walks the short east detour via
  135,136 and 135,131 to 146,131, then submits one Enter. Source flag and
  observed actor-separation checks can abort the attempt. They do not prove
  safety between every guest slice.
- Retreat readiness requires the dragon actor hidden and room-local callbacks
  21/22/23 cleared. A changed v75 alone does not qualify the next interaction.
- The remaining boulder is another live obstacle. The exit uses ordinary
  movement through a checked x35..40/y133..139 corridor below its baseline.
  This admits the observed neutral coast while rejecting movement outside
  the modeled corridor. Original movement and the actual room transition
  still decide whether the route succeeds.

Source initialization and settled positions are distinct: the dragon-room
script places Graham at x133, while the observed ordinary entry settles at
x131. The surface script places him at x142; the completed exit settles at
x140. The exported witness records the actual boundaries.

## Original writers, returns and short traces

The source offsets here are in AGI logic 51. Native offsets are relative to
the observed interpreter CS; they are not file offsets or project disassembly
addresses. The probe binds the whole loaded logic, named OBJECT record,
runtime segments, operands and original call frame before accepting a write.

| Transaction | Original source order | Observed effect |
| --- | --- | --- |
| Water | Print 34 at `0x45e`; DROP 26 at `0x460`; real return; SUBN 2 at `0x462`; ADDN 7 at `0x465` | Item location 255 to 0; score 15 to 13 to 20 |
| Mirror | GET 19 at `0x37f`; real return; blocking print 24 at `0x381`; treasure increment; ADDN 8 at `0x385` | Item location 0 to 255; score 20 to 28 |

The water DROP writer is `CS:74ba`, observed at resume `CS:74be`; its real
return is `CS:02fa`, with the original source cursor `code+0x462`. The mirror
GET writer is `CS:7482`, resume `CS:7486`, with real return `CS:02fa` and
cursor `code+0x381`. Score writers and their operands are observed separately.
See the [sanitized trace record](evidence/agi-dragon-mirror-route-2026-11-01/trace-summary.json).

Each trace contains six fetch observations and ends at the original handler
return, below its 128-fetch budget. The mirror trace ends before its blocking
dialogue; the later award requires a separate score observation after completed
dialogue. These traces do not cover every instruction in the transaction.
Individual after-access stops retain `instruction_completed: null`; the
observed memory effect and later real handler return have separate evidence.

## Reproduce and export privately

Use the exact selected originals, a compatible separately prepared backend,
the source checkout and an environment with its real dependencies. Choose new
canonical private paths outside the checkout, source and prior artifacts.

```sh
PYTHONPATH=src:player:. python -m examples.agi.verify_dragon_mirror \
  --source /private/original-kq1 \
  --backend /private/backend/dosbox-x \
  --output /private/new-native-route \
  --checkpoints

PYTHONPATH=src:player:. python -m examples.agi.build_dragon_mirror_scene \
  --source /private/original-kq1 \
  --capture /private/new-native-route/capture.private.json \
  --artifacts /private/new-native-route \
  --output /private/new-dragon-scene

PYTHONPATH=src:player:. python -m fdisbull_player --backend-command \
  'python -m fdisbull.il_scenes /private/new-dragon-scene/scene.json'
```

The collector saves optional private `bucket-carried.sav` and
`dragon-before.sav` checkpoints. Saving is recorded separately from loading;
this route qualifies no subsequent native restore or cross-backend state
compatibility. A failed or unknown input is not replayed. Failed results and
known effects remain available for inspection in their original attempt.

The exporter requires eight ordered actions, nine main observations, both
launch observations and both controls. It checks typed state, actual completed
frames, guest clocks, source/session identity, named inventory bindings,
messages, writers and original returns. An incomplete seven-action original
capture was tested and refused without emitting a scene. Hash and consistency
checks bind supplied evidence; they do not authenticate arbitrary captures.
The declared qualification pins the nine recorded anchors. A new route or
settling position requires its own witness review.

The standalone scene offers `take dagger`, `take bucket`, `use rope`,
`use water`, `use passage`, `use dragon`, `take mirror` and `use exit`.
These authored actions update **44 projected native fields plus phase** with
preconditions on all 45 variables. They do not issue emulator inputs or run a
general AGI interpreter. Original dialogue and frame bytes are not embedded.
Native NPC timing and other routes remain outside the partial projection.

Genuine installed core/player **0.28.0**, invoked with isolated Python and
`PYTHONPATH` removed, matched all nine native-derived boundary states and
inventories in direct and separate-content-process checks. All 44 native
fields plus phase matched with their types. Stale and repeated actions and
failed preconditions preserved state. Before-mirror in-memory save/load
restored the model, invalidated the earlier context token, and a new backend
reported that checkpoint missing. These are model-lifetime checks; durable
player persistence and native checkpoint restoration were not qualified here.

The [independent native checklist](evidence/agi-dragon-mirror-route-2026-11-01/independent-native-review.json)
checked the raw action/input/message journal, original writes and returns,
23 stored screenshot bindings, source/copy integrity and exited/reaped backend.
A separate rebuild produced byte-identical scene and provenance, and repeated
the installed-player checks against independently mapped raw observations;
see the [player receipt](evidence/agi-dragon-mirror-route-2026-11-01/player-verification.json).
Scene SHA-256 is `18a45ccfe80c37999a0be6eb18e823aaf97e132e6dab31bc965743920950dd61`;
provenance SHA-256 is `92d949e8313bcb19e42e581070a8ad2c2d149bdac067c587ec1bbf64b379a78e`.

The final affected source suite passed **2,051 tests, with four skips** across
43 AGI, IL-scene and text/player files on Python 3.13.13/macOS ARM64. Optional
private/native selectors were removed for that authored suite. The real DOS
route is a separate acceptance result. Full-suite and hosted ordinary/native
Linux qualification remain outside these checks.

## Review and retained limits

The [MR !22 review](evidence/agi-dragon-mirror-route-2026-11-01/review-summary.json)
found a raw-read retention gap: a returned score could disappear if a later
inventory read failed. The follow-up preserves a per-stage `last_observed`
record while keeping qualified `known_effects` unchanged until validation.
Four authored fault cases failed before that fix and passed afterward.

Independent review also found that an offline exporter variable could
overwrite the underwater picture provenance with a later state record. The
narrow naming fix and full-schema regression preserve the original PIC52
hash, position, footprint and priority evidence.
The [source-review summary](evidence/agi-dragon-mirror-route-2026-11-01/source-review-summary.json)
binds that regression and the final independent checks.

The attempt ledger retains the live-rock blockage, invalid horizon proposal,
missing downward input, exact-position guard, exit obstruction and one-pixel
coast failures. A host storage failure in the first attempt left the collector
exit status unknown; a read-only database recovery separately established that
its backend exited and was reaped. It does not reconstruct missing receipts.

Game/story files, native states, byte-retaining databases, raw captures,
generated scene/provenance and third-party material remain private. Selected
original-engine PNGs, authored source/tests and sanitized receipts are the
public evidence. Native qualification was on macOS ARM64; hosted ordinary
and native Linux acceptance are separate, unqualified gates. No release,
merge, tag or system installation update is part of this follow-up.
