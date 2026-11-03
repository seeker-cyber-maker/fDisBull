# KQ1's eastern bridge corner: description to native witness

The eastern bridge clip is now independently reproduced in the supplied KQ1
AGI 2.917 edition. A fresh physical route reaches room 40 without paying or
removing the troll, taking the carrot, entering water, or changing the score.
The adjacent control enters the script's water region instead. This is separate
from the [room-41 boundary water-walk](AGI_GOAT_BRANCHES.md).

The [verification receipt](evidence/agi-bridge-clip-2026-10-31/receipt.json)
retains source/backend identities, final collector hashes, native boundaries,
selected frames, private artifact hashes and local checks. Game resources,
native states, databases, complete raw captures and native traces stay private.

## Finding the location from the description

The [runner's glitch guide](https://www.speedrun.com/kings_quest_quest_for_the_crown/guides/2r57k)
credits Robb and places a small gap below the eastern bridge, approached from
the southeast. The [runner's route](https://www.speedrun.com/kings_quest_quest_for_the_crown/guides/qnbmx)
and [original gameplay video](https://www.youtube.com/watch?v=gD3Bvhqk98I&t=7s)
provide movement context. The public sources do not provide our numeric
coordinates or identify an exact game edition for this particular clip. We
derived the following route from the owner's resources and tested it separately.

1. Match the pictured bridge and room connections to PIC/LOGIC 39. This is
   the horizontal wooden bridge, reached from the east after the stone bridge
   in room 42; it is not the earlier goat encounter in room 25.
2. Decode the priority/control plane with the normal six-unit-wide land actor
   baseline. Four rows below the rail appear traversable in the geometric
   model, but that alone does not make a safe route.
3. Inspect the room logic. The OR condition at `0x0408`, within the parent at
   `0x0401`, contains a `posn` test at `0x0410` for ego origin
   `(72,84)..(72,87)`. Its true body at `0x041a` sets the water flag. This
   one-column guard closes the tempting straight geometric path.
4. Step around its lower corner: `(73,89) -> (72,88) -> (71,87)`, then west
   along y87. At `(72,88)` the decoded baseline is mixed water/dry, while the
   origin is one row below the scripted trap. The original game admits this
   route. At `(72,87)` the script instead takes its water branch.

Coordinates here are AGI game units, not screenshot pixels. The public name
“three-pixel clip” is retained as attribution. We qualified this staircase and
one adjacent failure; we have not measured an exhaustive three-pixel window.
The [AGI test specification](https://www.agidev.com/articles/agispec/agispecs-8.html)
and [ScummVM's `testPosn`](https://github.com/scummvm/scummvm/blob/master/engines/agi/op_test.cpp)
corroborate an inclusive origin test. The native witness below, rather than a
replacement interpreter, establishes which result this original game produced.

## Original interpreter observation

The collector checks the unpacked interpreter fingerprint, posn table entry,
complete loaded logic bytes, source condition boundary and original OR call
frame. Owned execution breakpoints observe the original handler at `CS:08c6`,
its return at `CS:07fb`, and the next source fetch. No handler is redirected or
replaced, and no return value, guest register, code, coordinate or flag is set.

| Observation | Safe corner | Adjacent control |
| --- | --- | --- |
| Ego origin / width | `(72,88)` / 6 | `(72,87)` / 6 |
| Source test | Logic 39, `0x0410` | Same |
| Original posn return | false | true |
| Next source instruction | `0x041e`, false successor | `0x041a`, true body |
| Subsequent outcome | Crosses to western bank, then room 40 | Original water flag becomes true at `(72,87)` |

A bounded trace accompanies each handler/continuation observation. The ceiling
is 128 fetches; the collector refuses a full or truncated capture. The receipt
records the actual count. A fetch is not a certificate that every instruction
completed. The original collision routine itself was not fully traced; decoded
baseline geometry and the native results remain separately identified evidence.

The route starts a new process and fresh private game copy, walks
`1 -> 8 -> 41 -> 42 -> 39 -> 40`, and never loads the launch helper's private
baseline. The ordinary approach respects room 42's horizon at y50. Tight
waypoints temporarily disable fast-forward because its measured slices can
overshoot a one-unit target. Ordinary distant movement can still fast-forward.
Guest and wall budgets remain separate, and foreign stops are preserved.

```sh
PYTHONPATH=src:. python -m examples.agi.verify_bridge_clip \
  --source /private/kq1 --backend /private/dosbox-x \
  --output /private/fresh-bridge-clip
# A separate fresh copy/process for the one-row control:
PYTHONPATH=src:. python -m examples.agi.verify_bridge_clip \
  --source /private/kq1 --backend /private/dosbox-x \
  --output /private/fresh-bridge-control --adjacent-control
```

## Reusable partial Z scene

`examples/agi/build_clip_scene.py` extends the shared IL scene backend and
separate player with `use corner`, `use gap`, then `use route`. It validates
four contiguous observed states, physical input receipts, source/PIC hashes,
native predicate/trace artifacts and the completed original room-40 greeting.
Only authored response text enters the scene. Phase and state guards reject
stale or repeated actions. This is an auditable projection of the captured
route, not autonomous AGI execution or a complete KQ1 reconstruction.

```sh
PYTHONPATH=src:. python -m examples.agi.build_clip_scene \
  --source /private/kq1 --capture /private/fresh-bridge-clip/capture.private.json \
  --artifacts /private/fresh-bridge-clip --output /private/new-bridge-scene
PYTHONPATH=src:player python -m fdisbull_player --backend-command \
  "python -m fdisbull.il_scenes /private/new-bridge-scene/scene.json"
```

The exported `scene.json` and `provenance.json` stay in a fresh private directory.
Hashes check supplied artifact identity and consistency; they do not
authenticate a claimed run. In-memory checkpoint restoration is tested
separately from durable persistence, which this IL scene backend does not add.

## Other candidates and how to investigate them

The reusable bounded scanner checks selected PIC/LOGIC resources, not every
room or arbitrary game automatically:

```sh
PYTHONPATH=src:. python -m examples.agi.scan_collision_candidates \
  --source /private/kq1 --output /private/fresh-collision-candidates.json \
  --allow-priority-one --neighbors 8 --avoid-script-guards \
  --path 39:73,89:68,87
```

Its seven-room scan found four matching guard IFs, nine rectangles and 262
edge-baseline candidates, retained as sparse ranges. These are candidate
coordinates, not 262 distinct glitches. Its geometry ignores horizons, dynamic
objects, overlays and runtime blocks; conditional guard parents remain unknown.
The priority-one allowance is explicit because original logic 39 ignores those
blocks before its bridge encounter. Destination-only diagonal BFS does not
prove swept clearance or original interpreter behavior.

| Candidate | Current evidence | Useful next probe |
| --- | --- | --- |
| Room 41, x154 / y109–150 | Prior native boundary crossing and adjacent failure | Already qualified; use as a scanner positive control |
| Room 39, x72 / y84–87 | Geometry permits it, source guard closes it; adjacent control now confirms that trap | Reject a straight-path “gap” claim; keep the qualified lower-corner route |
| Room 33 left edge, y66–101; room 34 right edge, y64–101 | Static mixed-baseline seams near all-water neighbors | Fresh physical approach and adjacent-origin control; runtime/source guards may still close them |
| Room 25 and room 42 edge seams | Static candidates only | Check legal room transitions, horizon, script guards and dynamic actors before attempting a route |
| Other narrow script/geometry corners or changed actor widths | A proposed search class | Compare baseline masks with origin guards, then test normal reachable actor modes and one-step neighbors |

The best next candidate is a reachable seam with an inexpensive neighboring
failure control. Preserve source conditions, action receipts and stop evidence;
do not convert a geometry-only path, budget exhaustion or missing observation
into a confirmed glitch. The mushroom-island crossing remains unqualified by
this follow-up.

## MR !13 review and failure handling

The exact `2ad1b07` review found one P2: the invisibility-check CLI could overwrite
an existing source or receipt path, including on refused analysis. The fix
admits only a fresh output outside source/checkouts and creates it exclusively.
Authored regressions retain source bytes and existing receipts unchanged.

The new collector also retains its original failure if later receipt storage
or native-context cleanup fails. It independently attempts breakpoint/trace
cleanup, partial capture/predicate storage and both source/copy integrity checks.
Verified status is assigned only after the final proof write succeeds.
The focused AGI/scene/player checks passed 807 tests with four skipped. The
broader ARM64 macOS run, with the checkout import path supplied to child
processes, passed 2,889 tests and skipped 123; 25 Linux/x86/GNU-toolchain checks
failed or errored. Their failures reproduce on exact MR !13 head `2ad1b07`.
This broader run remains red and does not qualify Linux compatibility.
Linux CI, integration merges, packaging, release and installation changes are
separate gates; none is performed by this follow-up.
