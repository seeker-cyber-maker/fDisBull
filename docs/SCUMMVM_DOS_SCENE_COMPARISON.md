# ScummVM AGI, original DOS, and Z scene comparison

This experiment compares **real execution** of one licensed King's Quest I
AGI 2.917 edition in the original DOS interpreter under DOSBox-X and in the
patched ScummVM AGI engine. A separate, authored partial Z scene replays the
declared transition. The fixed source identity is the `AGI` SHA-256
`5ab189ebd9822739962767afe0113853e23797ef16dd4784d2dc93423934fb74`.
The complete regular-file inventory must also match across the two runs.
Original files, game copies, databases, screenshots and raw receipts stay in a
private external workspace.

## First matched task: room transition

Begin a fresh game in room 1 with score 0. Use physical Up input until the
original or compatible engine reaches room 16, still at score 0. Observe a
completed frame at both boundaries. No memory edit, register edit, checkpoint
load, teleport or substituted model state is admitted. The DOS route has a
limit of 80 accepted Up input attempts. ScummVM queues one Up press, which
selects AGI's continuing direction, and takes at most 200 bounded guest
execution slices to reach the exit. The patched ScummVM bridge confirms queueing, while per-event
consumption is not yet independently exposed; the resulting scene transition
is a separate observation. Unexpected stops or an input that cannot be queued
leave an incomplete receipt.

This first task exercises boot, physical input, interpreter progression, room
state reads and stored frames. It deliberately avoids parser dialogue, moving
actors and autonomously timed effects. The [existing natural goat route on the
unmerged KQ1 branch](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/codex/kq1-boundary-exceptions/examples/agi/verify_goat.py)
provides the next, richer task: fresh room 1, carrot acquisition, gate opening,
`show carrot`, following/score commitment and room-9 pen exit. Its [capture
contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/codex/kq1-boundary-exceptions/docs/AGI_NATURAL_GOAT.md)
distinguishes state, displayed frames, message completion and the authored Z
projection. That draft is not part of the installed 0.29.0 release.

## Reproduce the transition

Run from this source checkout after both patched backends and the shared local
installation are verified. Allocate fresh, separate private output directories.
The commands create game copies, an FDB and stored frames; run the storage
admission check before a new material output phase.

```sh
PYTHONPATH=src:. python examples/scummvm/capture_transition.py \
  --source /private/kq1 --backend dosbox-x \
  --backend-binary /private/patched-dosbox-x \
  --output /private/comparison/dos-01

PYTHONPATH=src:. python examples/scummvm/capture_transition.py \
  --source /private/kq1 --backend scummvm-agi \
  --backend-binary /private/patched-scummvm \
  --game-id kq1 --output /private/comparison/scummvm-01

PYTHONPATH=src:. python examples/scummvm/scene_comparison.py \
  --dos-receipt /private/comparison/dos-01/run.json \
  --scummvm-receipt /private/comparison/scummvm-01/run.json \
  --output /private/comparison/pair-01
```

The comparison refuses incomplete runs, a different source inventory, a
nonphysical route, intervention, wrong endpoint, missing stored frame or a
frame that did not advance. It writes `comparison.json` and `scene.json` only
for an accepted pair. The scene executes through the existing
`fdisbull-il-scene-1` backend, starts in room 1 and exposes one `go north`
action to room 16. Its `partial: true` marker is essential: this is a small
state projection, not extracted game dialogue, a ScummVM-powered Z runtime or
an automatic UIL conversion. The comparison binds receipt and scene hashes but
does not authenticate operator assertions in a copied JSON file.

One early matched transition pair completed and produced a partial Z replay:
the DOS run took 3,425 ms inclusive (startup 2,248 ms, route 1,132 ms,
observation 22 ms) and the ScummVM run took 911 ms (startup 464 ms,
route 437 ms, observation 68 ms). Startup and route occupied 65.6%/33.1%
of the DOS inclusive time and 51.0%/48.0% of the ScummVM inclusive time;
observation was nested at 0.6% and 7.5%. This was an exploratory plumbing
pair made while the native bridge was still changing. Its ScummVM binary hash
differs from the frozen rich-task cohort below. It is not a repeated speed
estimate, and its single transition does not establish parser or scene
authoring behavior.

## Rich matched task: take the carrot twice

The second task starts from the same fresh room-1 state, walks north with
physical input into room 16, stops movement at the carrot (`ego_y <= 140`),
types `get carrot`, and dismisses the resulting message. It requires the
original AGI flag 77 to become true and the score to become 2. It types
`get carrot` again, dismisses the second message, and requires the room,
score, flag, ego position and direction to remain unchanged. The DOS witness
is the real interpreter's message-window open/close and `DS` state. The
ScummVM witness is an AGI message-box open/close revision, `vars`, `flags`,
ego object and a committed display frame. Both runs record every keyboard
submission. ScummVM queueing remains distinct from per-event consumption;
the subsequent game-state and modal transitions establish the bounded
outcome.

```sh
PYTHONPATH=src:. python examples/scummvm/capture_carrot_scene.py \
  --source /private/kq1 --backend dosbox-x \
  --backend-binary /private/patched-dosbox-x \
  --output /private/comparison/carrot-dos-01

PYTHONPATH=src:. python examples/scummvm/capture_carrot_scene.py \
  --source /private/kq1 --backend scummvm-agi \
  --backend-binary /private/patched-scummvm --game-id kq1 \
  --output /private/comparison/carrot-scummvm-01

PYTHONPATH=src:. python examples/scummvm/carrot_comparison.py \
  --dos-receipt /private/comparison/carrot-dos-01/run.json \
  --scummvm-receipt /private/comparison/carrot-scummvm-01/run.json \
  --output /private/comparison/carrot-pair-01
```

This comparator checks four boundaries, both completed message exchanges,
the source and runtime identities, chronological completed frames, and the
unchanged state after repeat take. It writes `comparison.json`, `scene.json`
and `replay.json`. The authored scene runs in `ILSceneBackend`: `go north`,
`take carrot`, then a rejected second `take carrot`. The `require` guard,
inventory predicate and score effect are a small scene model built from the
observed AGI variables and original behavior. They are not automatically
extracted AGI logic or a complete UIL translation.

### Final frozen five-pair result

Five fresh pairs were captured during a quiet measurement window after the
native binaries, Python providers and capture runner were frozen. Backend
order alternated DOS/ScummVM, ScummVM/DOS, DOS/ScummVM, ScummVM/DOS,
DOS/ScummVM. All 10 live runs completed and all five pairs passed the
comparison gate and partial Z replay. There were no incomplete attempts in
this final protocol. Original and private-copy file inventories matched in
every attempt. The original `AGI` hash is above and the full regular-file
manifest digest was
`35174dac00ed12c66440c90ef82700e35a2a0e2388b391c1483e339e1987471a`.
The DOSBox-X binary hash was
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`;
the ScummVM binary hash was
`f4f671cc3194cb290616644334a7dce5ba3233e9418d57e084438a76cc73659e`.
The selected Python provider and capture-file manifests were
`35c4d4f1f92623fdbafb1f7b39f9f3af8f8a73eae8430c88e52f40a89eb3cb58`
for DOS and
`0b80dc1ac442b5e3d23339e7dcdb22469adb170ddb1c9d8ec8511dff9898c3b8`
for ScummVM. Each run checked that those Python source bytes stayed
unchanged. Full code-hash inventories and aggregate measurements are in the
[sanitized comparison evidence](evidence/scummvm-2026-11-01/comparison.json).

| Phase, milliseconds | Original DOS median (range) | ScummVM median (range) |
| --- | ---: | ---: |
| Startup | 2,088 (2,055–2,425) | 303 (279–438) |
| Route including commands and frames | 2,512 (2,289–2,572) | 3,010 (2,858–3,964) |
| Observation, nested in startup and route | 327 (308–341) | 944 (882–1,198) |
| Teardown | 49 (48–56) | 11 (10–13) |
| Inclusive | **4,623 (4,494–4,990)** | **3,323 (3,151–4,353)** |

The ratio of inclusive medians was 1.391 (DOS divided by ScummVM), while
the ratio of route medians was 1.198 in the opposite direction (ScummVM
divided by DOS). ScummVM's shorter inclusive capture came from its much
shorter startup in this workflow; its combined route phase took longer.
Median per-run startup and route shares of inclusive time
were 46.45% and 52.44% on DOS, and 8.96% and 90.71% on ScummVM.
Observation accounted for 6.97% and 27.99%, respectively; it is already
included in startup and route. These are host wall-time measurements under
two different execution and input-control paths, not a general engine-speed
or scene-authoring-time result.

From the qualified room-1 frame onward, DOS made a median 71 bounded guest
runs and 69 normalized state observations, comprising 276 low-level memory
reads, 16 keyboard-state probes and 67 keyboard submissions. ScummVM made
66 guest runs, 70 engine-state observations and eight keyboard submissions.
Each route stored three frames after its initial room-1 frame. ScummVM also
submitted one title Enter during startup; the DOS `native_game` boot controls
occurred before these task-level counters began. The count difference is
part of this task's control workflow, and is not a normalized measure of
guest instruction work.

Every final pair observed room 16, score 2, flag 77 true, completed message
open/close for both take attempts, and unchanged game state after the second
attempt. The ScummVM modal revisions at the four stored boundaries were
0, 0, 2 and 4. The five Z replays each completed `go north`, completed the
first `take carrot`, and rejected the second `take carrot` with its state
unchanged. Visual inspection of final pair 1's two stored carrot frames
showed the same scene and score. Direct RGB comparisons of the post-carrot
frames found 66, 94, 66, 94 and 66 different pixels out of 64,000 for pairs
1–5. DOS settled ego at y=138–139 and ScummVM at y=140, both within the
qualified carrot reach. These sampled pixels do not establish general
rendering equivalence.

The private raw attempts and stored frames are retained under
`private/carrot-stable-01-*` through `private/carrot-stable-05-*` in the
external experiment workspace. The repository evidence contains no licensed
game bytes, artwork, original dialogue or raw runtime states. The authored Z
scene represents just this observed branch and does not measure whether
ScummVM reduces the time required for a person or agent to create a scene.

### Initial five-pair evidence (exploratory)

Five fresh pairs completed on the exact KQ1 edition. Backend order alternated:
DOS then ScummVM for pairs 1, 3 and 5; ScummVM then DOS for pairs 2 and 4.
All 10 captures and all five Z replays completed. The Python ScummVM provider
was still changing during these runs, so the timing table is exploratory;
a new cohort must freeze both native binaries and Python providers. The DOSBox-X binary hash
was `bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`;
the frozen patched ScummVM binary hash was
`f4f671cc3194cb290616644334a7dce5ba3233e9418d57e084438a76cc73659e`.
The original `AGI` hash is stated above; every pair also checked the full
source inventory and private copy. Raw receipts, screenshots, partial scenes
and replays are retained under `private/carrot-cohort-01-*` through
`private/carrot-cohort-05-*` in the external experiment workspace.

| Phase, milliseconds | Original DOS median (range) | ScummVM median (range) |
| --- | ---: | ---: |
| Startup | 2,068 (1,972–2,553) | 280 (260–467) |
| Route including commands and frames | 2,374 (2,254–3,051) | 2,891 (2,761–3,281) |
| Observation, nested in startup and route | 316 (300–455) | 894 (878–1,044) |
| Teardown | 45 (36–48) | 9 (9–10) |
| Inclusive | **4,437 (4,262–5,652)** | **3,227 (3,042–3,595)** |

In this exploratory cohort, the inclusive median was about 1.38 times as long with this DOS workflow as
with this ScummVM workflow. Separately, the ScummVM route phase was longer
in this five-run sample and its observation calls cost more. These numbers
describe one edition, route, host and debugger configuration. They measure
capture execution, not agent authoring time, decoder coverage or general
engine speed. DOS submitted 62–66 route/command keys per run because its
movement needed repeated Up delivery; ScummVM submitted eight route/command
actions plus one title Enter per run. The different input pacing is part of
the measured workflows.

As a fraction of each run's inclusive time, the median startup/route shares
were 46.3%/52.9% on DOS and 8.7%/91.0% on ScummVM. Observation occupied
median shares of 7.1% and 28.9%, respectively; it is already included in
startup and route, so these percentages do not add to 100%.

All final scenes had room 16, score 2 and flag 77 true. Both backends opened
and closed a message for each take attempt, and repeat take left the game
state unchanged. The ScummVM modal revisions reached 0→2→4. In stored
carrot frames the two backends showed the same room and score at 320×200;
a direct RGB comparison found 66, 0, 94, 0 and 66 different pixels for pairs
1–5, respectively, out of 64,000. The original and compatible engines
settled the ego at slightly different `y` values within the qualified carrot
reach. Pixel identity is neither required nor established beyond these
sampled frames. The five partial Z scene replays ended with `$room=16`,
`$score=2`, `$f77_carrot=true` and a rejected second take.

Development attempts are preserved separately. The first ScummVM transition
attempt stopped at its title room because the runner assumed room 1; the
second repeated Up and toggled AGI movement off. The first rich ScummVM
capture was marked incomplete by an overly strict comparison of its growing
modal revision, and the next rich attempt used an incorrect observation-time
instrumentation scope. A DOS diagnostic exposed the keyboard queue's need
for a guest-time drain before Enter. These were runner and measurement
development failures; they are not silently counted as successful frozen
cohort runs. The frozen protocol had 5/5 complete attempts on each backend.

## Measurements and acceptance

Each `run.json` retains the complete attempt, including failure. Record both
runtime binary hashes and the complete game-file inventory digest. Pair runs
from the same source and alternate backend order across at least five fresh
attempts per backend before reporting medians and ranges. Do not discard failed
attempts from the success denominator or compute successful-route medians as
though the failures never happened.

| Measure | Boundary |
| --- | --- |
| Startup | Before private game copy and project creation to the first qualified room-1 frame. |
| Route | First physical Up attempt to final room-16 state and completed frame. Includes state/frame observation. |
| Observation | Time spent in state reads and stored-frame capture, nested within startup or route. |
| Teardown | Final route frame to closed backend/project and unchanged-source checks. |
| Inclusive | Before setup to the closed, checked attempt. |

This timing definition differs from the historical [bow-to-king assisted-travel
benchmark](KQ1_ASSISTED_TRAVEL_BENCHMARK.md), whose inclusive measure excluded
game copying. Do not combine those numbers. For core engine speed, a later
benchmark must separately control emulator/ScummVM virtual time, rendering,
audio, input pacing and debugger instrumentation. The present measures describe
the end-to-end agent workflow under each declared backend configuration.

Correctness for the first task is the paired room/score endpoint,
host-queued physical-policy inputs and a newer stored frame at the respective
backend's completion boundary. The rich task adds flag 77, a completed
message for each command, and an unchanged state after repeat take. For
ScummVM, the display commit revision must advance too. The original DOS run
is the edition-specific observation;
ScummVM is a compatible-engine result and may differ. Raw DOS `DS` addresses
are not compared with ScummVM host memory. The Z scene must reproduce only
the two declared room/score boundaries. No matching pixel, timing, parser,
scheduler, actor, inventory or whole-game equivalence follows from this test.

For authoring-productivity claims, freeze a separate held-out scene task after
the backend bridge exists. Give both paths the same source files, prior public
documentation and task brief; measure elapsed time, manual interventions,
code/config changes and failed attempts to the first independently verified
scene. The existing goat collector and Z exporter are mature DOSBox work, so
their historical development time cannot be compared directly with a new
ScummVM implementation.

## Additional debugger parity checks

The transition tests only a subset of debugger functionality. Record a
separate capability result, with real execution receipts, for source AGI
`(logic, offset)` break and step, variable/flag/object reads, bounded watch
events, message-resource identity, input queue completion, stored frame
capture, save/restart and failure recovery. A ScummVM debugger command name or
an engine-state struct is not evidence that the matching operation works in
fDisBull. Unsupported and untested cells remain explicit.
