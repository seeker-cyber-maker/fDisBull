# Deterministic pseudo-oracle: situations and choices

The pseudo-oracle turns a qualified current observation into a compact account
of relevant situations, conditional forecasts and useful action choices. It
combines HUD-like information with the same scene/action interface used for
conversational adventure play. The original game owns outcomes; the provider
owns live observation, input readiness and execution.

The packaged [oracle module](../src/dotbox/oracle.py) implements this deterministic
evaluation boundary. It performs no I/O, language-model call or input. The
experimental [Keen adapter](../scripts/experiments/keen_oracle.py) supplies a
narrow mapping from qualified original-game observations. The initial checkpoint
below used retained-trace replay. The subsequent [live real-time qualification](ORACLE_REALTIME.md)
exercised actual original-game controls and measured the complete local loop;
it supports bounded normal-speed use, with explicit latency-tail limitations.

## The player-facing result

The six [authored examples](../examples/oracle_cases.json) demonstrate the intended
interaction. Their source identities, physics and input routes are explicit
fixtures, not claims about Keen or executable live controls.

| Current situation | Derived information | Suggested existing choices |
| --- | --- | --- |
| An anvil is falling | First contact at `(28, 100)` in six simulation frames, under the declared linear model | Move left; move right |
| An enemy is approaching; ammunition is two | The supplied attack's resource/range/cooldown conditions pass | Attack; retreat |
| Same encounter; ammunition is zero | The attack's resource condition fails | Retreat |
| A cherry is at `(120, 48)`, worth three stars | Optional objective, separate from the main goal | Continue; collect cherry |
| A closed mailbox is observed | The opening condition holds | Open mailbox; move north |
| The mailbox is observed open | Opening is no longer applicable | Move north |

These are suggestions, not an exhaustive grammar or a promise of success.
The complete eligible choice list remains available. Existing `on_request`
options stay out of the automatic shortlist. A useful attempt can be offered
without claiming that it will win a fight, avoid every hazard or complete a
puzzle.

## Three separate kinds of information

**Observed facts**
: Current source- and observation-bound values: position, inventory, activity,
  state, timers, contacts and observed object status. These are the only facts
  passed to the existing observation store.

**Derived situations and forecasts**
: Deterministic interpretations of those facts under identified rules. A
  forecast carries its model, source, rule digest, observation, clock domain,
  origin, horizon, dependencies and assumptions. It stays in a sidecar; it does
  not become a collected item, a changed flag or a future position in memory.

**Action candidates**
: Existing provider choices whose current gates and relevant rule conditions
  pass. The oracle can narrow and rank this set. It cannot create an input route,
  assert readiness, reserve input ownership or execute a choice.

“Verified” at this boundary means deterministic binding and predicate checks
over the supplied observation. The underlying decoder/provider must establish
that the observation represents the current game. Comparing two supplied hashes
does not authenticate a process or refresh a historical capture.

## Evaluation and selection

```python
from dotbox.oracle import evaluate_oracle
from dotbox.scenes import project_scene, select_choice

base_view = project_scene(current_scene)
assessment = evaluate_oracle(
    current_scene,
    qualified_rules,
    expected_scene_sha256=base_view["scene_sha256"],
    expected_observation_id=current_observation_id,
    expected_state_context=current_provider_context,
    choice_limit=3,
)
hud = assessment["hud"]  # Public facts, concise situations and eligible choices.

# The player or a delegated local policy selects an existing choice.
intent = select_choice(
    assessment["scene"],
    selected_choice_id,
    hud["scene_sha256"],
    hud["observation_id"],
)
# Existing live control reobserves/rechecks admission before executing intent.
```

The caller checks the exact scene digest, observation ID and full provider
context, including session, branch, revision and token. Rule source and edition
must match the scene. Changed or stale expected bindings are refused. Routes,
choice IDs and observed fact values are preserved.

Compile the oracle result before recording one scene for that provider revision.
Recording the base packet and then a different compiled packet at the same
revision would correctly trigger the existing conflicting-observation guard.
`SceneStore` retains the observed packet; it never receives the forecast sidecar.

## Typed conditions and choice reduction

Rules are closed, bounded JSON, with no expression evaluation or arbitrary
Python execution. Conditions use fact IDs and `eq`, `ne`, `lt`, `le`, `gt`, `ge`.
For example:

```json
{"fact_id": "ammo", "op": "ge", "value": 1}
```

Conditions evaluate to true, false or unknown. Missing, old, internal-only or
explicitly unknown values cannot enable a public action. Ordered comparisons
require strict integers; booleans and numeric-looking strings are not ammo
counts. A known false condition dominates an unknown condition in a conjunction.
The existing scene `requires` list still checks fact presence; this new layer
is where value-based conditions are evaluated.

Every action remains subject to the provider's `available`, `enabled` and
`ready` gates and current public fact requirements. The oracle never promotes
a false or unknown provider gate. Unmentioned actions retain their original
gates. Eligible rule-associated choices are ranked by declared priority with
stable ties, while existing `on_request` policy is preserved.

Situations and their text are disclosed only when their current public
dependencies pass. Internal facts and guide claims do not reveal an unseen
object by promoting a choice. Per-action assessments retain internal reasons
for eligibility, blocking or uncertainty. A player interface uses the dedicated
`hud` projection. It exposes concise conditional forecasts and omits private
qualification, evidence, context tokens and diagnostic reasons. The full
assessment retains these details for the harness. The HUD digest identifies
the returned gated scene; the binding digest identifies the original input.

The first bounds are 16 situations, 32 action rules, eight conditions per rule,
32 referenced facts and 128 KiB of rule JSON. The existing 48 KiB scene bound
and 32-choice/fact limits also apply. These limits keep work local and finite;
they are not a hard real-time scheduling guarantee.

## A forecast has a model and a clock

The first built-in forecast is deliberately narrow: constant-velocity downward
point contact with a fixed horizontal surface. All six numeric dependencies
must be current public integers. The calculation finds the first positive
discrete crossing within a horizon of at most 120 steps and returns a contact
point, ETA and absolute deadline. Unsupported or missing data produces unknown
or unavailable, not a claim that the path is safe.

In the authored anvil case, its bottom starts at 76, the surface is at 100 and
downward speed is four units per simulation frame. It reaches 96 after five
steps and 100 after six. Horizontal motion from x=10 at three units per step
gives x=28. With an origin clock of 40, the deadline is frame 46. This model
assumes no acceleration, intervening collision or motion change, and a landing
surface under the predicted point. It does not model Keen gravity or clipping.

Clock units are explicit: simulation frames, game ticks, updates or turns.
Screenshots, render cadence and CSS display dimensions are not simulation
clocks. Keen's recorded two-tick updates must not silently become two frames.
All geometry stays in the provider's original world coordinate space.

When a deadline is shorter than a conversational response, an already delegated
local policy must handle the time-sensitive choice. Dot can receive the compact
situation and describe the outcome while the fast loop continues. This module
does not pause the game, add a scheduler, or autonomously authorize that policy.

## Original-game replay and verification

The [authored receipt](evidence/pseudo-oracle-2026-11-20.json) records exact
source, commands, replay results, installation identities and limits. The
targeted oracle, scene and existing Keen suites passed **478 tests**, including
65 core oracle and 17 authored adapter cases. Six authored examples also passed
through the isolated installed module and existing nonexecuting choice selector.

An independent replay reproduced **154 retained original-game observations**:
83 from the active-carrot run and 71 from collection. Zero flower power blocks
the attack resource condition in all 154. Twenty observations contain the active
carrot; eight establish that the carrot itself moved closer. The last horizontal
body gap is 1,272 world units, or 79.5 game pixels. Player motion alone and an
activation edge do not establish closing enemy motion.

The optional bonus objective disappears at observation 39, when collection
changes its class to inert and raises score by 100. The actor remains in the
complete live list through observation 58 and is removed at 59. Collection is
offered only at each trace's retained initial state, after the existing private
constructor accepts its state and hashed terrain; this produces a historical,
nonexecuted intent. The replay offers no newly invented attack or retreat route.

The replay preserves Keen's resource and actor semantics: the carrot can push
the player, and flower power is the relevant ammunition in the sampled level.
Two collection samples have game-clock increments of three then one despite
two actor ticks per update. Their current facts remain usable, but the replay
withholds adjacent-clock motion comparisons for those pairs. No contact ETA
is inferred from this trace.

The adapter requires explicit permitted actor identities; `nearby` and `active`
are not visibility assertions. Historical choices retain historical readiness
and cannot authorize input into a closed or different guest. Currently usable
attack, retreat and collection routes remain provider responsibilities.

## Local evaluation cost

An isolated installed-process measurement warmed all six examples and 16
retained snapshots, then timed 1,000 calls each on the anvil example and final
Keen snapshot. Expected bindings were precomputed; validation, defensive copying,
internal hashing, rule evaluation and HUD construction were inside the timing.

| Fixed input | Median wall time | p95 | Largest observed call |
| --- | ---: | ---: | ---: |
| Authored anvil | 0.410 ms | 0.708 ms | 4.068 ms |
| Retained final Keen observation | 0.643 ms | 0.916 ms | 2.428 ms |

This measures the small evaluator's local cost. State retrieval, RPC, input,
rendering and language-model work are outside it. One warmed process with fixed
small inputs does not establish a deadline guarantee or live-loop throughput.

The broader persistent world graph, general collision prediction, event-based
read scheduling and live conversational frontend remain separate work. This
slice connects deterministic situation reasoning to the existing scene and
action boundary without introducing another game-state authority.
