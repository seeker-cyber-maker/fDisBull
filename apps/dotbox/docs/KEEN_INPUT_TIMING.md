# Keen Dreams: feedback phase and predictive stopping

The subsequent [visible gameplay checkpoint](KEEN_GAMEPLAY.md) uses this phase
for a bounded collection route and measures presentation and representation costs.

The November 20, 2026 checkpoint qualifies a second observation phase and adds
a small predictive walking policy. The post-actor hook exposed sampled-input
changes in 28–29 guest milliseconds, compared with 57 ms at the earlier
pre-input hook. First press-induced movement was visible after 29 ms versus
57 ms. The game completed its input read at the same absolute guest
timestamps in the paired traces. The improvement is earlier coherent feedback.

The new policy completed seven predeclared live waypoint cases, with endpoints
exactly matching the predictions recorded before the controller matrix. Every
case settled within the requested two-pixel tolerance. For the 32-pixel left
reference, the previous threshold policy overshot by seven pixels; the predictive
policy stopped two pixels short. Short neutral trials sustained approximately
real-time progress, while one movement trial still had a 73.05 ms cycle.

This extends [the initial feedback prototype](KEEN_REALTIME.md). The exact test
identities and authored measurements are in
[the result receipt](evidence/keen-input-timing-2026-11-20.json).

## Scope and trial design

All 15 fresh guests used the installed DotBox `0.1.0.dev8` wheel and the same
qualified native executable and game executable as the first checkpoint:

- Game SHA-256: `36a22dbd3119c0b4cdff7adaf50a8abc3b11c21f7bc0d4d7c0d5dbf7b347e3ae`.
- Native SHA-256: `af4d353c128dbb58fa433a0f8601cb92d8fb93acc907e25827c038d6dea77e8e`.
- Tested base source: `2adf54cfd95408e2c5a8f1448918b5d62d83bde9`.
- Existing loop SHA-256: `cf82d45c5bdec8c135968ccfa0436ed7724b1f833bc68b67c754619f09c41c60`.
- Waypoint policy SHA-256: `62ac20e9a8fe246838c5f1cb04635eae247b07d54507054686467797f5387063`.

The root controller alone ran the original game through ordinary keyboard input.
Each guest used a fresh byte-identical private copy, followed the established
opening route, qualified its source/code/layout/control ownership, and closed
with a reaped process and return code zero. All seven installed original game
files retained their hashes. Raw RAM, game files, screenshots, diagnostic
drivers, and target disassembly remain private.

The matrix contains two diagnostic traces, two fixed-input controller runs,
two 100-update neutral timing runs, two threshold-release reference runs, six
predictive cases at the new phase, and one predictive check at the old phase.
This is a source-informed local experiment. The 32-pixel left leg also appears
in the previous checkpoint and serves as a reference case.

The private driver bounds preparation at 180 seconds, establishes a host
deadline of at most 120 seconds before launch, and gives the post-admission
trial at most 3,000 guest ms including a reserved final renderer advance.
Bootstrap and first-hook admission are reported separately. Uncertain native
operations are preserved and never replayed. Terminal shutdown retains the
runtime's separate bounded reaping allowance.

## The phase comparison

The new main hook is `0B7A:13F2`, linear `0xCB92`, at the call to `RF_Refresh`.
Actor updates, collision processing, camera scrolling, and reaction callbacks
have completed. Its 23-byte selected-code guard has SHA-256
`f6e7436d6cbe770f28e0bd86be41f7f6c2972f8899f119d89e342a8ac81c3c9f`.

The established hook is `0B7A:1277`, linear `0xCA17`, before input sampling.
It exposes the preceding actor update after the refresh interval. The diagnostic
observer is `0B7A:1288`, linear `0xCA28`, immediately after `IN_ReadControl`
returns. Its 16-byte guard has SHA-256
`1f0b12e31723dfaa131163818189cd4458ac318ce69635b906470f36d388077b`.
Both new guards matched frozen snapshots and fresh live memory.

Each trace pressed left at its initial main hook, held it for ten main
observations, released, and required three stable neutral observations. The
extra observer measured the returned control fields at native millisecond
resolution. It is an upper bound on the preceding control-field update, not an
instruction-level timestamp. Its additional pauses exclude these traces from
throughput comparisons.

| Measurement, guest ms after edge submission | Pre-input | Post-actor/pre-refresh |
| --- | ---: | ---: |
| Press: matching input at read return | 29 | 28 |
| Press: changed input and movement at main hook | 57 | 29 |
| Release: neutral input at read return | 28 | 27 |
| Release: neutral input at main hook | 57 | 28 |
| Release: first stable main observation | 85 | 57 |

The first matching press returns occur at native tick `19187` in both traces;
the first neutral returns occur at tick `19472` in both. The edge-submission
baselines differ by one millisecond. All 15 corresponding player and input
states match when the old-phase observations are shifted by one position.
Both fixed holds travel 34.5 pixels and settle at x `32728`; they are separate
from the 32-pixel waypoint reference.

The trace also permits zero whole guest milliseconds and zero video frames
between distinct qualified PCs. Such a short instruction interval is valid when
the owned breakpoint, expected PC, revision and alternating trace sequence agree.
Repeated zero-progress at the same main hook remains a refusal.

At the post-actor hook, `tics` describes the update just applied, while
`lasttimecount` belongs to the preceding refresh. The framebuffer may still
display the previous state. Native guest ticks govern elapsed-time comparison;
neither a screenshot nor equality between the game's two counters establishes
the phase. A display-only bounded renderer advance follows each finished trial.

## Why release needs prediction

The authored recurrence follows `DoActor`/`StateMachine` and
`KeenStandThink`/`KeenWalkThink` in the released
[original source revision](https://github.com/keendreams/keen/tree/15be5be4a3382d0a1d99e1202219a84b09b11273),
with the actual binary bindings independently checked. Coordinates use 16 world
units per pixel. These tests consistently applied two game ticks per update.

A walking update normally advances 48 units, or three pixels. On the update
that consumes neutral input, the game accumulates movement before changing to
standing. If the current walking ticcount is `n`, the remaining displacement is
`direction * 24 * min(2, 6 - n)`: usually three pixels, or 1.5 pixels at `n=5`.
An additional old-input update changes both position and animation phase before
that calculation. A standing start can likewise move 48 or 72 units depending
on its current ticcount.

The policy's `input_delay_updates` parameter counts additional old-input actor
updates visible after submission. The paired live traces qualify one for the
pre-input phase and zero for the post-actor phase in this profile. Zero means
that the next main observation contains the input's effect; measured input-read
latency remains about 28 guest ms. The parameter is supplied explicitly and is
checked against each subsequent sampled control field.

[`keen_waypoint.py`](../scripts/experiments/keen_waypoint.py) compares the settled
x after releasing now with the settled x after holding one more update, then
releasing. It chooses the closer endpoint, releases on a tie, and latches
neutral input. This is a choice among continuations of the current unreversed
walk; it does not search alternative starting phases or reversing maneuvers.
It performs no I/O or native operations.

Every next observation must match predicted x, state, ticcount, direction,
horizontal movement, and sampled input. A mismatch ends the policy before
another hold is selected. Settlement requires three consecutive neutral
standing observations with zero horizontal movement, unchanged x/y/collider
bottom, and the expected floor/contact state. Attempted vertical floor motion
can alternate between zero and 16 while the actual collider remains stationary;
`ymove == 0` would reject legitimate settled states.

## Waypoint results

The reference uses the same 32-pixel target and fresh starting pose:

| Controller | Actual left travel | Endpoint relative to target |
| --- | ---: | --- |
| Threshold release, pre-input phase | 39 px | 7 px beyond |
| Threshold release, post-actor phase | 37.5 px | 5.5 px beyond |
| Predictive release, post-actor phase | 30 px | 2 px short |
| Predictive release, pre-input phase | 30 px | 2 px short |

The six post-actor cases were declared before the controller matrix. Their
observed endpoints exactly match the pre-trial predictions; no policy tuning
occurred between these runs.

| Requested move | Actual travel | Endpoint relative to target | Final x | Updates |
| --- | ---: | --- | ---: | ---: |
| Left 24 px | 25.5 px | 1.5 px beyond | 32872 | 11 |
| Left 32 px | 30 px | 2 px short | 32800 | 13 |
| Left 40 px | 39 px | 1 px short | 32656 | 16 |
| Left 52 px | 52.5 px | 0.5 px beyond | 32440 | 20 |
| Right 24 px | 25.5 px | 1.5 px beyond | 33688 | 11 |
| Right 32 px | 30 px | 2 px short | 33760 | 13 |

The old-phase predictive check completed in 14 updates at x `32800`, using the
measured one-update pending-input delay. All seven predictive cases have three
independently checked stable transitions and satisfy the requested two-pixel
tolerance. That bound describes these cases, rather than every target in the
admitted corridor.

The generic loop's `policy_stop` outcome indicates lifecycle completion. The
driver separately requires the waypoint receipt's outcome to be `settled`,
at least three stable samples, and measured error within the requested tolerance.
Refusal and outside-tolerance termination remain unsuccessful objectives even
when keyboard cleanup completes safely.

## Timing without the diagnostic observer

All controller runs use the existing single-hook loop, one 30,710-byte memory
window, and no model calls, screenshots or disk writes inside the feedback loop.
They enable native fast-forward and pace the host loop at 35 Hz. Timing includes
the private driver's in-memory receipt instrumentation.

| Neutral phase, 100 updates | Guest / wall time | Median cycle | p95 cycle | Maximum cycle | Late deadlines |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pre-input | 0.9958x | 18.47 ms | 23.75 ms | 49.40 ms | 4 / 100 |
| Post-actor/pre-refresh | 0.9961x | 18.38 ms | 20.10 ms | 33.61 ms | 1 / 100 |

Each neutral run advanced 2,856 guest ms. Cycle time excludes the explicit
post-cycle pacing sleep; the guest/wall ratio includes admission and cleanup.
A late cycle counts against its assigned deadline, so one delay can cause more
than one late completion. The two short samples do not establish a general
tail-latency improvement from the new hook.

The predictive 32-pixel left run had a 73.05 ms maximum cycle, with a 54.46 ms
`frame.step` and a 15.45 ms memory read in that cycle. It advanced 371 guest ms
in 427.20 wall ms, a ratio of 0.8685x, and missed three of 13 paced deadlines.
The long cycle occurred during stop confirmation; its endpoint still matched
the prediction. The measurement does not identify the host/runtime cause of
the pause. Average real-time progress and deterministic bounded feedback are
useful here, but hard deadlines and continuous execution remain unqualified.

## Guards, verification, and next coverage

Fresh terrain admission checks the small first-level body corridor in columns
125–133, rows 30–31, and its flat floor at row 32. Selected collision faces,
animation, speed, and tile interaction attributes must match. The policy accepts
only the fresh start, 24–52 pixel left targets or 24–32 pixel right targets,
the fixed camera/map identity, two-tick updates, known state records, floor
contact, and the observed nearby bonus-only actor profile. It refuses slopes,
airborne states, side/ceiling contact, new active threats, and changed assumptions.

The caller's fresh corridor attestation is separate from continuous terrain
validation. Pointer identity and actor/contact guards cannot detect every
in-place map edit. Enemy avoidance, moving hazards, jumps, poles, slopes,
scene transitions, recovery/rebinding, broader editions, long-duration play,
and desktop human/agent handoff remain outside this policy's qualification.

Verification includes 99 new waypoint tests and the existing 31 loop tests:
`python -m pytest -q tests/test_keen_waypoint.py tests/test_keen_loop.py`.
All 130 passed. An independent reviewer reran the 99 new cases and checked
the source recurrence, input queue, guards and settlement semantics. Separate
raw-evidence review checked live trace memory decoding, exact hook and clock
receipts, input attribution, model endpoints, and process closure.

The next practical control primitive is a bounded jump/landing policy with
current terrain and actor guards. For smoother uninterrupted play, the native
side would need a bounded observer/controller operation or sampling buffer;
the current stopped-only memory protocol still pauses between advancement and
inspection. Neither improvement is supplied by this checkpoint.
