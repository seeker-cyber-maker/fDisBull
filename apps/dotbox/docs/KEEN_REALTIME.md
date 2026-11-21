# Keen Dreams: a measured local feedback prototype

The later [visible gameplay checkpoint](KEEN_GAMEPLAY.md) completes a collectible
route and measures optional display cadence and reversible world-state factoring.

The [November 20 follow-up](KEEN_INPUT_TIMING.md) qualifies a post-actor
observation phase, separates input-read latency from feedback age, and tests a
predictive flat-ground waypoint policy. The measurements below remain the
original November 19 checkpoint.

The supplied Keen Dreams executable now runs through the installed DotBox
0.1.0.dev8 runtime. A source-informed investigation reached the world map and
first platform level, bound player/map/actor state to the actual unpacked
executable, and exercised a local feedback loop at a verified game-update
boundary. Short neutral trials sustained approximately real-time progress.
Feedback-controlled walking and a standing jump also completed.

This is an experimental controller and a qualification checkpoint for one
executable/load layout. It is not a production Keen scene provider, a complete
platformer planner, or evidence of uninterrupted, hard real-time execution.

## Exact scope

- Executable SHA-256:
  `36a22dbd3119c0b4cdff7adaf50a8abc3b11c21f7bc0d4d7c0d5dbf7b347e3ae`.
- Installed package: `0.1.0.dev8`; ordinary wheel SHA-256
  `90e21d835887a17855b7b9e190ffda9448ceff63993e81806db9820d6a590b49`.
- Native executable SHA-256:
  `af4d353c128dbb58fa433a0f8601cb92d8fb93acc907e25827c038d6dea77e8e`.
- Root alone controlled isolated headless research guests. The original game
  supplied all physics, rendering and authoritative state. No memory writes,
  cheats, state rewinds, or game-resource changes were used.
- All research guests were closed and reaped. All seven uploaded game files
  still match their original bytes.
- Game assets, screenshots, raw RAM, private diagnostic drivers and binary
  disassembly remain outside this repository.

The earlier wrapped-MZ launch fix is described in
[KEEN_DREAMS_SETUP.md](KEEN_DREAMS_SETUP.md).

## Source facts and actual binding

The primary source references are the released
[original 1.00 revision](https://github.com/keendreams/keen/tree/15be5be4a3382d0a1d99e1202219a84b09b11273)
and [later 1.93 reconstruction](https://github.com/keendreams/keen/tree/4348b4719be87a0b873f5f4f77b4de82ddf7050c).
The archive's original startup sequence, CONFIG.KDR and 1991 title are consistent
with the earlier release family. A byte-identical source build and exact edition
number have not been established. The reviewed movement, timer, refresh and
enemy-physics source is unchanged between these revisions apart from whitespace;
absolute addresses still require independent binary qualification.

The source uses a 70 Hz timer and normally combines 2–6 ticks into one update.
The examined gameplay slice consistently used two ticks per update, yielding
approximately 35 input samples per guest second. Emulator frames, game updates,
game timer ticks and host milliseconds are distinct. In the EGA path, capped
elapsed time can also be subtracted from the game's TimeCount. It is not a
monotonic host/controller clock. See `id_sd.h`, `id_rf.h/c` and `kd_play.c` at
the pinned source revision.

Coordinates use 16 world units per pixel and 256 per tile. The source describes
directional collision faces, slopes, poles, state-dependent colliders, and actor
state machines. A binary solid/empty map and a universal x/y velocity pair are
insufficient for exact prediction. See `id_rf.h`, `id_ca.h`, `kd_def.h`,
`kd_keen.c` and `kd_act1.c` in the same revision.

Selected bindings were derived from decoded unpacked machine instructions,
allocator structure and multiple frozen observations, then checked with live
input. In the observed layout, DS is `2A5C`, the player pointer is at `DS:704E`,
the pool begins at `DS:7144`, and it contains 100 slots with a 76-byte stride.
The live list, rather than every nonzero pool slot, identifies current objects.
The source variable called objectcount is a cumulative allocation counter;
RemoveObj does not decrement it. Independent review corrected an early decoder
assumption about that counter.

The qualified update hook is `0B7A:1277`, linear `0xCA17`, immediately before
gravity calculation and input sampling in PlayLoop. Its 17-byte selected-code
guard has SHA-256
`165382c4b4235aeb67b0a061ae4f3c1ef36c96c032a5a93eb7df250fc93fa95a`.
An owned execution breakpoint reached that address with the expected code/data
segments. Repeated trials returned to the same owned hook with continuous guest
time and two game ticks per update. Ordinary renderer stops sometimes observed
the temporary tics value 1 inside the refresh wait; they do not certify a
completed game update.

The prototype reads one 30,710-byte region from `DS:7030` through `DS:E825`.
It covers the current object pool, input, map pointers, player state and clocks.
Static state records below that interval are seeded at the qualified hook.
Seeding at an arbitrary frame is unsafe because collision code can temporarily
modify a state record. Map planes are cached separately and must be rebound on
level changes; foreground animation and other mutations need further tracking.

## Implemented experiment

[`scripts/experiments/keen_loop.py`](../scripts/experiments/keen_loop.py) accepts
an existing owned NativeSession, an explicitly qualified memory range and hook,
a pure decoder, and a pure policy. It deliberately contains no guessed game
addresses. It is not exposed through the default desktop service.

One local iteration:

1. Compute the desired keys from the previous coherent observation.
2. Check the stopped session, revision and input generation.
3. Send only changed keyboard frame edges.
4. Advance to the owned hook under explicit frame/guest-time bounds.
5. Read the single memory region, decode, and record timing in memory.

No language-model call, screenshot, whole-machine save, disk write or remote
request occurs in this loop. The caller stores results after the trial. An
unexpected stop, source/context change or uncertain transport preserves the
state and refuses blind replay. One outer host deadline and one guest-time
budget cover the trial and reserved cleanup. A coherent-hook miss is reported
without admitting a partial update as an observation.

The interface is described in the module docstring. A production integration
would need a validated game profile, ownership coordination and a bounded
operation inside the session owner; this experiment does not establish those.

## Measured timing

Final neutral measurements used the reviewed helper, source hashes recorded at
run start, a prefix seeded at the qualified hook, one 30,710-byte memory read per
observation, and no screenshots inside the loop. Each trial contains 100 updates
and 2,856 guest milliseconds. These short, quiet first-level trials are not a
long-duration or combat-load benchmark.

| Mode | Guest time / wall time | Median cycle | p95 cycle | Maximum cycle | Missed paced deadlines |
| --- | ---: | ---: | ---: | ---: | ---: |
| Normal timing | 0.998× | 28.09 ms | 34.41 ms | 45.16 ms | Not paced |
| Fast-forward, unpaced | 1.149× | 23.09 ms | 36.83 ms | 49.02 ms | Not paced |
| Fast-forward, paced at 35 Hz | 0.995× | 22.51 ms | 32.84 ms | 54.68 ms | 27 / 100 |

Cycle latency measures local work and guest advancement, excluding an explicit
post-cycle pacing sleep. Guest/wall ratio includes controller admission and
cleanup. A missed paced deadline means that a cycle completed after its assigned
wall-clock deadline; consecutive late cycles can count separately. The loop did
not skip guest updates to catch up. Average real-time progress is demonstrated;
hard deadlines and uninterrupted execution are not.

An earlier neutral trial had 5/100 paced misses and a 43.61 ms maximum. That
variation, and the movement result below, show why the tail matters more than a
single favorable average.

## Actual feedback-controlled actions

The local policy completed a leftward waypoint test and a short standing jump.
It made decisions from coherent RAM observations while the language model was
outside the loop.

- Walking selected a target 32 pixels left of the start. It released direction
  after crossing that threshold and settled 39 pixels left, a 7-pixel overshoot.
  A queued hardware edge can be consumed in a later input sample, and the current
  movement state can finish additional displacement. Accurate waypoints need
  predictive release and a calibrated input-consumption delay.
- Walking took 15 updates, 428 guest ms and about 492 wall ms (0.869×). One
  frame-step call took about 123 ms; the maximum complete cycle was 127.98 ms.
  This short trial exposes scheduling jitter hidden by average neutral results.
- The short jump completed 40 updates, 1,143 guest ms and about 1,157 wall ms
  (0.988×). Its p95 cycle was 33.84 ms and maximum 53.51 ms. It rose approximately
  60.94 pixels and returned to the original x/y with standing state, floor
  contact, and released input.
- The raw vertical-speed field remained nonzero after landing (51 in one probe,
  54 in the feedback jump). The source does not clear it on the transition to
  standing. Grounding must use contacts, state and actual displacement.

The world-to-level transition also changed the map from 85×66 to 136×37 tiles
and relocated all three map planes. The level contained 41 linked objects,
including score, bonuses and enemies; this is not a count of enemies.

## Practical next implementation

Use three cooperating components:

- A source-bound observer produces player state, collider/contacts, input
  latches, update timing, map epoch and nearby actor states.
- A local controller predicts a short motion horizon and chooses held keys at
  each game update. First primitives should cover braking to a waypoint,
  standing/running jumps, landing confirmation, and interruption on a changed
  scene or unexpected hazard.
- A slower planner selects routes and subgoals from cached collision geometry.
  It is consulted at meaningful events rather than once per physics step.

Keep the original game's physics authoritative. A predictor helps choose actions
and is corrected from the next observation. Track directional faces, slopes,
drop-through floors and poles; nearby enemies need class, state/timer and motion,
not position alone. Reused object slots require an epoch/lifecycle identity.

The existing native protocol is enough for this bounded prototype. If tail
latency prevents useful play, the next native improvement should combine changed
key edges, a bounded update advance and selected state reads under one generation
fence. Truly continuous RAM feedback would require a bounded native sampling
buffer or an in-process observer: current memory.read is stopped-only. Any
continuous held-input controller also needs an expiry/watchdog policy.

## Verification and remaining limits

The new helper has 31 focused tests, independently rerun, covering changed-key
chords, release budgeting, source/session/generation/timeline invalidation,
transport uncertainty, foreign stops, coherent-hook misses and guest accounting.
The earlier native launch patch's 144-test result remains a separate checkpoint.
Live probes verified movement, release, jump phases, landing, level relocation,
owned hook identity and timing. Machine-readable findings are in
[`evidence/keen-realtime-2026-11-19.json`](evidence/keen-realtime-2026-11-19.json).

Not yet qualified: complete hazard semantics, enemy avoidance, map mutation
tracking, exact predictive physics, rewind/load rebinding, extended play, other
editions/load layouts, or desktop human/agent handoff for this controller.
