# Keen Dreams: actor rules and current state

The experimental [Carrot Courier model](../scripts/experiments/keen_actor.py)
recovers a small part of enemy behavior from source and checked binary evidence.
It predicts walking-state transitions and separately describes contact-driven
turns, leaps and landings. The original game continues to own movement, collision
resolution and outcomes. The model performs no emulator access or input.

## Code, data and current observations

These inputs answer different questions:

| Input | What it establishes | What still needs observation |
| --- | --- | --- |
| Executable rules | How states advance, when a reaction runs, and which conditions select a transition | Which actor/state is current and whether the conditions hold now |
| Resource and state-table data | Spawn candidates, tile attributes, shape/state definitions and their relationships | Current actor positions, collected objects and map mutations |
| Qualified RAM observation | Current linked actors, activity, state IDs, counters, positions, contacts, inputs and clocks | Subsequent effects and any facts outside the observation's scope |
| Original framebuffer | The game's rendered presentation | Internal state, exact timers and whether the image matches the selected update phase |

A spawn token is not a live enemy-location report. An inactive actor need not
advance merely because its state table contains a walking rule. A cached map
also needs mutation handling: animation and gameplay can change cells while
their allocation pointers stay the same. This follows the existing
[world-model](WORLD_MODEL.md) and [stateful-scene](STATEFUL_SCENES.md) contracts:
predicted effects remain predictions until observed.

## Source and binding scope

The retained provenance identifies released source revision
[`15be5be4a3382d0a1d99e1202219a84b09b11273`](https://github.com/keendreams/keen/tree/15be5be4a3382d0a1d99e1202219a84b09b11273).
The relevant rules are the carrot state declarations, `CarrotReact`,
`CarrotAirReact` and `ChangeState` in
[`kd_act1.c`](https://github.com/keendreams/keen/blob/15be5be4a3382d0a1d99e1202219a84b09b11273/kd_act1.c),
plus `DoActor`, `StateMachine`, clipping and dispatch in
[`kd_play.c`](https://github.com/keendreams/keen/blob/15be5be4a3382d0a1d99e1202219a84b09b11273/kd_play.c).

Selected state records and callback instructions correspond in the frozen
runtime evidence. This does not establish a byte-identical build of the entire
released source. Exact executable/load bindings, callback addresses, disassembly
and original-game captures remain private.

The public model accepts a caller-qualified profile containing a source hash,
qualification locator, four ordered walking-state IDs and one leap-state ID.
It checks the supplied observation's source identity and actual state-record
fields. The supplied hash is a guard, not independent authentication of a live
process or proof that the observation is fresh.

## The finite model

`CarrotModel.predict_walk_phase()` admits an ordinary active carrot, a supported
walking state, a legal counter and exactly two game ticks per update. Each
walking state lasts five ticks and proposes a 128-world-unit horizontal step
when it expires. Excess ticks enter the next walking state. For example, counter
four plus two ticks predicts the next state, counter one and one proposed step.
The model does not integrate ground movement from `xspeed` or prior `xmove`.

Its returned `state`, `ticcount`, `proposed_xmove` and `proposed_ymove` describe
the state-machine phase before clipping. A proposed step is not a claim that the
actor's final x changed by that amount. Floor pushing, slopes, walls and a new
shape's collider can change the resolved position.

`reaction_decision()` has a separate, explicit `reaction_callback_entry` phase
contract. Given current post-collision contacts, it describes wall reversal,
ledge-triggered leap, ceiling stop or landing. Wall reversal precedes the ledge
branch; ceiling and floor checks in the air are independent. A ledge rollback
is labeled intermediate. Entering a new state resets timing/motion and invokes
clipping again, so the result leaves `final_position` unspecified.

A main-loop snapshot does not establish that its contacts belong to a future
reaction callback. The caller must qualify that phase or supply separately
qualified collision results. Activation, random deactivation, gravity, terrain,
collider geometry and general actor contacts are outside this model. Different
screen sizes do not change these world-coordinate rules.

## Why direct RAM observations matter

Source explains the transition rules; current RAM supplies their arguments.
The harness needs to distinguish an inactive carrot from an active one, read the
current state/counter, and combine observed motion and contact fields with the
qualified state definitions. Those distinctions can be invisible or ambiguous
in a screenshot, especially when the last completed framebuffer precedes the
selected actor-update phase.

This is a reason to use structured observations for precise control, not a claim
that RAM reads are orders of magnitude faster than screenshots. The previous
[paired gameplay measurements](KEEN_GAMEPLAY.md#display-work-can-run-less-often-than-control)
must be interpreted at their measured scope; reducing display work did not
establish a throughput improvement. The original image remains useful for
presentation and visual verification.

## Offline verification

The [authored tests](../tests/test_keen_actor.py) cover all four walking-state
links, both directions, counter boundaries, branch precedence, leap/landing
effects, state-record/source guards and mutation isolation. All 87 cases passed
in the installed test environment, and independent source review passed.
These checks do not establish active-enemy prediction accuracy in the game.

## Live validation

The November 20, 2026 original-game trace produced **19 of 19 matching walking
state and timer predictions**, using a model frozen before gameplay. All four
walking states were observed as prediction inputs and endpoints; each of the
four transition edges matched twice. The exact source, frozen helper hashes,
results and limits are in the [authored receipt](evidence/keen-actor-model-2026-11-20.json).

One native owner used ordinary left-key edges to approach an inactive carrot.
The player followed the original bridge slopes, released left at update 63
when the carrot became active, and finished after 20 active observations with
18 unchanged neutral standing transitions. Total player travel was 181.5 game
pixels. Lives, score and inventory were preserved. Foreground, event plane and
tile-attribute endpoint hashes matched; this does not establish continuous map
immutability. The original game files were unchanged, and the native process
closed and reaped with return code zero.

The controller retained 83 coherent post-actor/pre-refresh observations over
82 updates. An independent extractor reconciled the compact fields with the
complete linked actor list decoded from the corresponding raw memory receipts.
The watched carrot remained available outside the nearby projection. The
selected state-table and reaction-code identities were checked at admission;
static state definitions below the hot window were retained from that seed.

| Original-game comparison | Result |
| --- | ---: |
| Active observations of the selected carrot | 20 |
| Eligible consecutive active pairs | 19 |
| Predicted state and timer both match | 19 / 19 |
| Walking-state transition edges exercised | All four, twice each |
| Actual horizontal displacement equals proposed step | 19 / 19, diagnostic only |
| Actual vertical displacement differs from proposed zero | 4 / 19 |
| Controller screenshots | 0 |

The eight nonzero horizontal steps were 128 world units each: 64 game pixels
in total. Four of those updates also moved the carrot upward by 64 world units,
for a total 16-pixel rise. Floor pushing and clipping resolved that vertical
motion. The horizontal agreement does not qualify a general position predictor;
the four vertical differences show why a pre-clipping movement proposal must
not be treated as the final position.

Across all five carrots, the validator considered 410 adjacent actor pairs.
It excluded 390 pairs with an inactive preceding actor and one activation edge.
For the selected carrot alone, those exclusions were 62 inactive pairs and one
activation edge. None of the 19 generated predictions was later discarded.
Earlier collection traces contained only inactive enemies and supply no active
transition successes here.

The model receives only the preceding actor, preceding two-tick duration and
qualified source/profile. Its output was then compared with the following
observation. The comparison script was authored after notification that the run
had completed, and frozen before reading the fresh observation artifact. This
is retrospective validation of a model fixed before the run, not an online
prediction-driven input trial. All observed walking was rightward at two ticks
per update. Reversal, leap, landing, gravity, changed cadence, deactivation and
reaction-callback entry still need separate original-game qualification.

## Timing and the next harness boundary

The no-display feedback loop advanced 2,342 guest milliseconds in 2,339.903 host
milliseconds. Complete update latency was 28.524 ms at p50 and 30.591 ms at p95.
Its 83 reads each retrieved the qualified 30,710-byte RAM window; raw read RPC
latency was 2.138 ms at p50 and 3.032 ms at p95. These read measurements exclude
decoder time. The loop used normal original timing, and no screenshot RPC ran
inside feedback. Seven bootstrap captures, one admission capture and one final
private capture remained outside that measurement.

This short warmed-up run kept approximately normal game speed. It does not
establish sustained or hard real-time performance. The previous paired runs
measured RAM-read medians around 1.6--1.7 ms and screenshot medians around 1.8 ms;
raw retrieval alone is not the main advantage. Structured state supplies exact
activity, positions and timers directly, without a pixel-interpretation stage.

The resulting architecture separates cached rules and map definitions from
fresh actor state, then runs bounded local controls against the original game.
Dot can consume relevant actor facts, rule predictions and observed events while
the display updates independently. Predictions can support shorter planning
work and future event-based observations, but this checkpoint does not skip
state reads or integrate the predictor into input selection. General future
positions still need qualified collision/gravity rules or bounded original-game
advancement and re-observation.

The targeted actor, loop, waypoint and world-stream suite passed 286 tests,
including the 87 new actor cases. Independent source and owner-result reviews
passed. Recorded preparation to the first completed useful active trace was
881.622 seconds within a 1,800-second research allowance; earlier discovery
and worker dispatch preceded that clock. This was warm reuse, not cold-start
qualification or player-facing startup latency.
