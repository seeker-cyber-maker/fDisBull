> Implementation note: the 0.21.0 development candidate implements the bounded live-original workflow and separate text interpreter described in [UNRELEASED-0.21.md](UNRELEASED-0.21.md). This retained proposal also describes future semantic-recovery work; its acceptance tables are requirements, not a record of passed original-game tests. Source: PRs #13/#14, `87d1079a49dd448dd43e80f84d81896bf1f42bf9`.

# Draft contract: playable Z text-adventure projection

Status: **draft design and experiment**, 28 October 2026. Author: **Codex**,
from the user's requirement that Z also allow a graphical game to be played
as a Zork-like text adventure for agent testing. This extends the
[intent pipeline](INTENT_PIPELINE_RFC.md) and
[progressive scene workflow](SCENE_STREAMING_WORKFLOW.md). The expected agent
benefit is a hypothesis to measure. No text runtime, Sierra conversion or
benchmark result is implemented or claimed by this document.

## Play the scene through text

Z should provide enough recovered scene and action structure for a downstream
consumer to produce a playable text view: observed surroundings, objects,
inventory, dialogue and events, together with commands for interacting with
them. The same model can support graphical views. A text-only agent need not
interpret each frame or repeatedly locate a control before making a decision.

Commands might include `look`, `examine`, `inventory`, `talk`, `use` and `go`.
Those words are illustrative interface vocabulary, not reserved UIL syntax.
Each supported command has a defined binding, visibility policy and time cost;
a familiar English verb cannot supply missing execution semantics.

For example, an authored synthetic interface might display:

```text
Courtyard
A closed gate stands to the north. A notice is beside it.
Visible exit: west. You carry a brass key.

> open gate
The gate does not open.

> examine notice
The notice reads: "Deliveries use the west entrance."
```

These descriptions and outcomes are fixture assumptions. A real projection
needs supporting observations and command results. A command guide can explain
generic forms such as `use <item> on <target>` without enumerating hidden
solutions or only the combinations guaranteed to succeed.

## Two backends, one authority

| Backend | Command execution | Scope of the resulting claim |
| --- | --- | --- |
| Live original | Resolve the command to a qualified scene action or declared input sequence; send real guest input and observe the result. | A usable text harness over the original, including a partially recovered game. |
| Qualified reconstruction | Resolve to the corresponding defined action in the reconstructed runtime, with its required state, services and dependencies. | Execution of the recovered semantic slice under its declared qualification. |

Text and graphics observe the selected backend's authoritative state. The text
frontend must not maintain a second imagined world or narrate success merely
because an input was submitted. Optional language generation can improve
wording only within the grounded facts; deterministic rendering of the same
structured observations is useful for reproducible tests.

The existing [scene framework](SCENE_FRAMEWORK.md) supplies useful bindings for
the live-original path. Progressive authoring can expose one supported action
through text before the rest of the room is understood. A downloaded package
can supply the same knowledge subject to compatibility and fresh checks.
An unsupported interaction is reported as outside the interface's current
coverage, rather than evidence that the game makes it impossible.

Z supplies the model and evidence links; executable rules remain in the
original backend or defined UIL semantics. Text presentation, command adapters
and players remain downstream consumers under the
[existing ownership boundary](UIL_BOUNDARY.md#explicit-stop-line).

## Observation and command contract

The projection should bind the following information without prescribing its
canonical encoding:

- **Grounded observations:** context, public object identities, observed
  descriptions and relationships, known inventory, dialogue and events, with
  source/evidence links and explicit unknown or ambiguous values. Spatial,
  animation and audible cues needed for a decision require a declared textual
  representation; omitting them narrows the supported interaction domain.
  Retain evidence links in provenance or privileged inspection; exposing those
  links must not give the player view unrestricted underlying source access.
- **Observation profile:** distinguish player-visible knowledge from privileged
  investigator data. Hidden flags, future dialogue, undiscovered objects,
  private guards and source-symbol names must not leak through prose, target
  identifiers, command lists, hints or errors. Record the information actually
  available to each experimental agent.
- **Command resolution:** bind a verb and resolved targets to the action,
  context and revision. Ask for disambiguation when two observed targets share
  a name. Unsupported or unresolved commands cause no speculative input.
  Revalidate current context and availability before dispatch, including after
  a clarification or revision change.
- **Execution and outcome:** retain the input expansion or semantic action,
  before/after observations, guest time, event order, stop reason and evidence.
  Report accepted, rejected, incomplete and successful outcomes according to
  the action contract. Partial execution retains its actual effects; a changed
  sentence is not a rollback or a completed transaction.

Projection reads and in-game commands are distinct operations. Reading the
current observation can be passive under a declared paused-guest policy; a
game's own `look` or `inventory` command may execute logic and advance time.
Specify the behavior of each exposed command, failed command, clarification
and reasoning interval. Text input does not automatically make a continuously
running game turn-based.

## Navigation and intentional assistance

A command such as `go east` can reduce control overhead while preserving the
game's consequences. Its binding must define the input/movement policy,
starting conditions, collision and hazard handling, time consumption, stopping
conditions and outcome. A live-original movement macro uses bounded input and
stops on unexpected contexts or outcomes; it does not teleport by editing state.

Separate the observation profile from the control/assistance profile. A text
view can use the same inputs as a graphical view. Higher-level movement,
parser aliases or command macros are additional choices whose effects and
costs must be recorded. A deliberate testing variant that removes traversal,
pauses deadlines or changes action timing can be useful for quest reasoning,
but its comparisons identify those changes instead of claiming unchanged
original behavior.

Suppressing image delivery to the agent does not imply that the original can
stop rendering internally. Any callbacks that advance logic still execute.
A reconstructed renderer may be omitted only after the corresponding logic
has been separated and compared under the declared contract.

## Test the agent benefit

Begin with one qualified Sierra interaction slice and matched starting state,
resources, input/observation privileges, guest-time policy, analysis policy,
package knowledge, agent configuration and budgets. First replay identical
inputs under graphics and text observation and compare the backend state/event
traces at declared boundaries. Only presentation should differ in that check.

Then give adaptive agents the **same supported named-action interface** and
compare graphics observations with grounded text observations. Measure verified
task success, decision errors, invalid/unsupported actions, time to first useful
action, stalls, guest time, wall time and inference/observation cost. Inspect
whether text descriptions disclose additional information or omit needed cues.
Agent-selected trajectories can differ; identical traces are not required of
adaptive agents choosing different actions.

Afterward, hold presentation fixed and compare original input granularity with
declared higher-level macros. A full graphics/text by low-level/semantic-control
comparison can separate perception and control benefits. Keep the sequential
versus on-demand analysis experiment and cold/warm package conditions recorded
as their own dimensions. Reducing screenshots is not by itself evidence that
quest completion improves.

Report intentional assistance and remaining unsupported visual/spatial puzzles
alongside the result. The useful question is whether this qualified text view
lets an agent solve the declared tasks more reliably or cheaply, and which
observation or control changes account for that result.

## Proposed acceptance cases

These authored synthetic cases are prospective requirements. Their local
profiles are examples, not default timing or observation rules for all games.

| ID | Case | Required result |
| --- | --- | --- |
| Z1 | Two states are otherwise identical, including visible inventory and prior player knowledge, and differ only in hidden latch/quest values; request descriptions, command help and action discovery. | Identical player-facing results, with no hidden differences leaked through labels, hints or errors. Investigator output may differ under its own profile. |
| Z2 | Two visible keys have distinct identities; in a paused-clarification profile, submit `take key`. | Ask which target, with no guest input or time advancement. Revalidate the selected target and current context before subsequent dispatch. |
| Z3 | One declared switch input increments a counter from 4 to 5 in one case and is ignored in another. | Narration follows the observed outcome; the ignored-input case cannot report success or advance a separate textual counter. |
| Z4 | `go east` expands into two movement steps costing one tick each; a declared hazard at tick 2 reduces health from 10 to 8. | Matched graphics/text runs reach the same position and time with health 8. A shortcut that avoids the hazard does not implement this control profile. |
| Z5 | A command targets a door in context A, but the game has moved to B before dispatch. | Withhold the stale action, observe current context and retain the mismatch; do not reuse A's coordinates or silently choose a new target. |
| Z6 | A fixture has passive projection reads, a player `look` action costing one tick, and a scheduled transition due at that tick. | Repeated projection reads do not advance time. The player action advances one tick and the transition occurs once; command naming does not erase its cost. |
| Z7 | Text and graphics alternate around one action; an original render callback also advances declared state. | Both views reflect one authoritative result. Suppressing image delivery preserves the callback's logical effect; omission of the callback needs a separate qualification. |
| Z8 | Replay identical inputs from matched state and guest timing with image observations versus text observations, using one control profile. | Backend state/event traces agree at the declared boundaries; subsequent adaptive-agent comparisons retain that same interface and assistance level. |

The first implementation can be a downstream text facade over the existing
scene actions. It should remain useful with partial, incrementally recovered
knowledge, and later consume a qualified reconstruction through the same
declared interaction contract.
