# Continuous play and predictive scene preparation

Use this reference for the play lead and a worker preparing one harness slice.
Keep the game's immediate continuation ahead of speculative research. Dot leads
the live game and conversation. When platform support and usage allow, Dot can
spawn full cloud agents to retrieve information, recover behavior and edit
candidate scenes ahead of the player. These can be independent investigation
environments, not just short local helper calls. Single-agent play remains the
fallback when cloud workers are unavailable or exhausted.
Player-led conversation waits for the player's scene decision when it is not
already known. Autonomous play chooses within the delegated goal. Both use the
same observation and action contracts; working controls do not decide agency.

## Retain the live owner

Reuse the established process/service and its supported client interface.
Determine the installed build's lifecycle before choosing a transport: a
persistent service may support short-lived clients, while a controller that owns
the guest through an open stream may close it on EOF. Do not transfer fDisBull
`z-controller` process rules to DotBox without checking the actual implementation.
Read the current runtime's help or documentation only when needed for that decision.

Keep session descriptors, ownership leases, games, saves, projects and output
stores in a private writable workspace outside Git ancestry. In cloud tasks,
`$HOME` may itself be inside a checkout. Ephemeral scratch storage is not a
durability guarantee. Preserve the private workspace through the environment's
supported persistence mechanism and verify the receipt before claiming reuse.
Retained controls do not necessarily retain the live guest or its game state.

Inspect takeover-state access once when establishing the runtime, and again
after a relevant change or failure. A visible button, chat owner or lack of input
is not an ownership API. If programmatic state is unavailable, keep that gap
explicit and use an agreed handoff. Never claim that a development service's
manual owner selection is integrated with the built-in desktop control channel.

## Keep the buffer useful

Keep one foreground question and a bounded predictive frontier: current
scene/action, selected destination or next likely need, a cheap accessible
alternative when useful, fallback, worker objective and its bound. At startup
this may cover a menu, opening room and first exit. During play it follows the
user's actual branch. A newly entered room is a useful trigger to prepare likely
adjoining locations before the player selects an exit. Predicting a route does
not select that route for the player or establish that a guide-listed exit is
currently accessible.
Do not create the frontier merely to name a control already usable now. Act,
observe its effect and save the recipe afterward without replay.

An operational slice connects entry/readiness, bounded input, observed effect
and a usable next state. Learn it from the authentic graphical game, retain the
small recipe and reuse it on the next visit. A scene plan, control label or
accepted input is not evidence of that complete slice. Share one relevant frame
or snapshot among compatible questions; avoid revisiting menus or redoing probes
just to give each worker a separate observation.

If an optimized action is pending, continue through its working input route.
If the next interaction is blocked, give it priority now: stop the unrelated
worker, learn the smallest missing input and publish a usable partial. Do not
pause the game to finish a broad harness plan. Save/checkpoint discovery is useful
when available, but must not gate otherwise working movement and interaction.

Use the entrypoint's recorded initial-control profile and deadline (default 180 s).
Write them before launch/input. At readiness emit `buffer_usable`; on a miss emit
`budget_expired` once, retain the working subset and use an available route.
Never reset the deadline to make a long preparation look short. Record each
launch before process creation and distinguish installer/setup from the configured
game without dropping either from the end-to-end timeline. Capture actual waits,
failed actions and observation gaps as they happen, not at the final summary.

Distinguish that first useful slice from full interface/process preparation.
A complex cold job may declare a longer bound and milestones before it starts;
retain the original timeline and any earlier deadline miss. Do not convert its
duration into an automatic foreground wait or renew a missing-control focus.
Read `dotbox guide --topic loops` for goal-driven startup, isolated save tests,
action-event captures and separate host/guest/game clocks. A known control stays
usable while broader process knowledge is incomplete. A menu-only route may
offer no natural buffering window; describe an actual preparation block plainly.

For a missing current control, use the separate `dotbox learn` focus: one goal,
observed context, question, next interaction and fallback. The default trial
bound is 15 seconds and two probe admissions, including elapsed reasoning and
dispatch time. Reopening or updating the same context keeps its deadline and
probe count. Retire work explicitly when a real route change supersedes it.
On exhaustion, use the applicable fallback or explain the game-facing block.
The helper cannot stop an already running tool or grant input permission.
Optional improvements with a working route add no intentional wait.

That `dotbox learn` allowance governs the lead's foreground missing-control
focus. It is not a blanket 15-second deadline on every background cloud job.
Each worker has a separate useful-by point and hard work bound, described below.
Do not let workers share the live learning store or combine monotonic clocks
from different machines. Returning evidence does not renew an expired focus.
If the lead deliberately uses a learning focus for a task, its existing elapsed
clock and probe admissions still apply during movement; background execution
does not pause or reset that journal.

For persisted mouse controls, use [runtime controls](runtime-controls.md).
Coordinates are absolute original-frame pixels. In explicit native diagnostic
mode, the server handles the bounded pause/fresh-frame/click/continue transaction.
Default desktop mode uses its supported outer input path; native `act` is refused.
In either mode, do not keep the guest paused while
the model reads frames or writes recipes. Its returned coordination markers can
be joined to the caller's command journal. A continue response acknowledges a
command rather than the exact instant of guest resumption. Compare only the
same interval definitions across trials; candidate-marker time is not the
worker's full reasoning time, and a configured replay is not a cold run.

## Use movement as useful preparation time

In a graphical game, reaching an object or exit is part of fulfilling the
player's intent. Prioritize a usable movement route, stopping behavior and
ordinary interaction. If the player says "use the radio" and the approach is
known and appropriate, begin the bounded approach while a worker finishes the
radio's interaction slice. Do not require the destination's whole scene to be
finished before starting applicable movement. Verify that approach is within
the selected goal, and preserve the option to stop at a safe waypoint before an
unqualified final interaction or transition.

Actual traversal, necessary animation and the player's natural decision time
can give workers preparation time without blocking progress. Dot continues
the relevant narration, monitors the live movement through supported controls
and observations, and handles steering. A running tool must not be assumed
interruptible; qualify the available cancellation or use suitably bounded
movement steps. A prepared candidate cannot change an in-flight action's
implementation or make Dot ignore a new player instruction.

Use natural progress as the buffer. Do not slow walking, add detours, stretch
speech or repeatedly ask unnecessary questions to conceal unfinished work.
Pause only for an actual game/ownership need under the established policy.
Narration and movement can overlap, so their durations are not additive spare
time. Instant text transitions may provide almost no preparation window.

For each near-term job distinguish:

| Bound | Meaning |
| --- | --- |
| Useful-by point | Estimated arrival or next interaction that will consume this result; refresh the estimate after actual route/progress changes |
| Hard work bound | Explicit worker/tool/resource ceiling, including startup and dispatch; do not silently extend it because conversation or travel lasts longer |
| Foreground allowance | Existing non-renewing bound for a missing current control; it is not an automatic wait granted at arrival |

Preparation begins as soon as evidence supports a useful prediction. Rank the
selected destination first, then likely accessible neighboring scenes and a
small alternative if its expected benefit justifies the cost. Prefer finishing
one usable entry/action/outcome slice over broadly polishing every room.
Arrival is a fresh observation point: check which scene was actually reached
and whether the candidate's assumptions still hold before use.

If arrival beats the worker, use an applicable ordinary route immediately.
Unfinished preparation is not itself a reason to stall. When a genuine missing
capability remains, narrow work to that blocker under the existing foreground
policy. Do not restart an existing focus, wait a fresh 15 seconds by default or
reopen the 180-second startup allowance. A worker can continue independently
within its original bound, but its pending result grants no live capability.

## Brief a full cloud worker with one near-term consumer

Supply only what the worker needs:

```text
Role/objective: prepare the likely adjoining room's first useful action slice.
Consumer/priority: Dot on arrival; selected destination before speculative exits.
Inputs: allowed frozen observation and revision, target/resource identity,
        relevant working controls, guide checklist, branch assumptions and
        copied-state provenance when an isolated experiment is needed.
Ownership/policy: no shared-guest mutation; selected assistance and information
                  policy; only the supplied evidence is player-visible.
Output: separate declarative candidate, entry/readiness, expected result,
        decisive evidence, tested scope, fallback, base revision and remaining
        unknowns; distinguish source recovery, clone tests and live observations.
Bound: useful-by point plus hard time/probe/resource limits; return an early
       usable partial, and stop when superseded or the hard bound expires.
```

A full worker may search permitted guides, inspect frozen files, recover
conditions and geometry, edit candidate scene/harness definitions and test them
in its own supported isolated guest. Isolation includes the mutable project,
game/save directory and session: copying an emulator checkpoint alone does not
isolate host-mounted files. Without an isolated execution path, return a
bounded probe for the lead at a safe play boundary instead of taking over input.
Success in a worker's clone establishes evidence for that branch/state, not an
action or progression in the player's game.

Use the platform's actual cloud-agent launch, result and cancellation tools when
available. Dot may provision the supported worker task; the player need not set
up a separate computer or cloud environment. Bound active jobs to available
usage and one near-term consumer each, and keep edits in separate candidates.
A task list alone does not create a scheduler, and a completed cloud task does
not imply its process keeps running. When usage or availability drops, retain
useful returned work, stop admitting new jobs and continue through known
controls. Without parallelism, interleave short authoring steps with play while
keeping live control responsive.

On an unexpected exit, turn-back, new user intent, takeover or invalidated
resource binding, reprioritize the frontier and cancel superseded work through
supported tooling. Preserve reusable partials as inactive candidates. Do not
wait for cancellation to finish before using a working live route. If a tool
cannot be interrupted, its late result remains unselected until applicability
is checked again. Never treat silent workers or missing usage information as
evidence that preparation completed.

## Promote a complete, compatible revision

Only the play lead publishes the active revision. Keep worker candidates separate
and preserve the last working revision. Check source/resource identity, current
applicability, assistance policy, parameter contracts, declared dependencies,
base revision and the actual destination/branch. A worker result is a proposal
even when its isolated checks passed. Use the existing provider's scene,
workflow and public Z contracts when available; keep DotBox's conversation
packet a presentation/evidence boundary instead of another game-state language.
Retain a separately callable input fallback if an optimized implementation would
otherwise hide it. Select an immutable revision explicitly when the runtime
supports that contract; never assume an automatic latest selection.

Include the observed game-state context when a candidate depends on flags,
inventory, a lock or a one-time interaction. The lead can record confirmed
offscreen changes while conversation and preparation continue, but only the
live provider can establish player progression. Read `dotbox guide --topic state`
for the separate observation store, stable entity IDs, revision ordering and
choice gates. A worker's return order cannot assign a newer game revision.
Refreshing a menu after an offscreen change does not mean rebuilding every
scene or restarting the existing learning allowance.

Keep accepted input, response text, committed effects and input readiness
separate. A pending handler may allow narration and isolated research while
withholding the next independent game input. Use only supported continuations
and read-only reconciliation; do not repeat the original action on uncertainty.
Once the game is ready, recheck the provider token and ownership before the
next action. A persisted snapshot or a confirmed flag is not that live check.

Use the runtime's actual validation and promotion interface. Declaration checks
alone do not verify an effect. Validate the smallest applicable operation during
ordinary play or a safe bounded coordination point, then observe the result.
Do not replay a previously performed action merely to record its recipe. If
publication or execution fails after possible effects, inspect current state
before recovery; do not silently repeat a turn, submission or save overwrite.

Prefer declarative community controls. Optional executable extensions require a
separate trust decision, side-effect-free loading and a compatible runtime; do
not import unknown code into the live owner to discover what it does. Publish
between completed actions, preserving contracts used by existing routes. Defer
an inapplicable or breaking candidate and keep using the working revision.

## Measure blocked play separately from preparation

Record intent arrival, first useful input, natural travel/animation, actual
next-use boundary, worker dispatch/result, lead validation/adoption and real
foreground blocks. Use the lead's clock for cross-worker scheduling events;
worker-local elapsed durations carry their own clock identity. An estimated
travel window is a scheduling hint, not a measured result.

Foreground blocked time is the union of intervals where a selected intent,
ready game and input owner could otherwise progress, but missing capability or
required preparation/adoption prevents it. Include lead integration and tool
dispatch when they cause that delay. Ordinary traversal and player deliberation
are separate intervals. Overlapping workers do not multiply a single stall.
Late preparation with a working fallback can still mean zero blocked time.

Track whether candidates are usable by the actual next-use boundary, fallback
use, useful/wasted speculative work and preparation costs when exposed by the
platform. Do not infer token quotas or billing from task count. Report unknown
measurements explicitly. The current package supplies instructions and the
single-focus journal and a provider-observation store; it does not implement a
cloud scheduler, predictive scene recognizer, interruptible narrator or movement
monitor.

Exercise at least these cases through the eventual live adapter: preparation
finishes during a normal walk; arrival precedes the result; the player chooses
another exit; takeover makes a candidate stale; usage disappears mid-route; and
an instant text transition consumes the buffer immediately. Working movement
and fallbacks must remain available under their actual ownership conditions.

## Yield and resume without undoing progress

Before a planned handoff, settle movement and release controller-owned holds
through the supported input path while the agent still owns input. On abrupt
ownership loss, do not inject cleanup during the user's turn; reconcile safely
after ownership returns. Frozen-evidence work can continue throughout user play.
Live observations must be supported and passive; if capture would advance or
pause the guest, retain an observation gap rather than interrupting play.

On a supported ownership return or explicit handback, observe the current game,
reconcile owned input state, refresh scene/runtime bindings and retire queued
intentions from the previous scene. Worker results from an earlier checkpoint
need current applicability checks. Never restore the user's old state just to
make a candidate fit. Separate harness coverage from observed game progression.

## Preserve blind information boundaries

The requested guide-informed path may read compatible guides for the overall
goal and nearby reconstruction checks. Keep those expectations separate from
current narration, and record guide exposure. The rules below apply to a strict
blind policy chosen for a session or evaluation; hiding read solutions from
spoken prose alone does not restore that policy.

For blind play, do not send the lead hidden units, future objectives, random
outcomes or spoiler labels through worker notes, scene names, readiness metadata
or logs. Give workers the allowed observation subset. Generic control mechanics
can be shared without target secrets; a worker that needs forbidden facts should
return a sanitized operational result or defer the action. An isolated future
scene does not authorize using its information in the current game.
If forbidden information has already reached the lead, record that exposure and
qualify subsequent blind-play claims; withholding it from the user does not undo
the lead's knowledge. Restrict further inputs and continue only within the agreed
information policy.

Keep the user-facing response about the current game and available actions.
Routine research belongs in the background dossier. A real block, consequential
choice or ownership question deserves a brief explicit handoff; unfinished
research should not become recurring progress chatter during otherwise usable play.
