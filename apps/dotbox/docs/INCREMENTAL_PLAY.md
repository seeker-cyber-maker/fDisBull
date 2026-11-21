# Incremental play for an ordinary player

Decision: updated 18 November 2026. The player should be able to say "let's play" and
make game choices without learning what a harness, debugger or Z scene is.
DotBox must supply the tools and operating instructions Dot needs. The source
implementation below is not yet qualification of uninterrupted play on Dot's
actual computer.

Dot is also the [conversational interface](CONVERSATIONAL_PLAY.md): a Z-scene
supplies grounded descriptions and choices. Player-led and autonomous modes
share the same action model. A bounded [initial guide pass](GUIDE_RECONSTRUCTION.md)
provides the overall goal and nearby expected objects/exits for reconstruction.

## The interaction rule

When a fresh observation, a known applicable control and the supported input
path suffice for the player's selected intent or delegated autonomous goal,
act now. Observe its result and retain
the useful recipe afterward. Naming a scene, creating a wrapper or completing
a starting buffer must not delay an otherwise available action.

Knowing a key binding is one part of play. Dot also needs to recognize enough
of the present situation, choose a bounded action and determine its effect.
Build those pieces for the next interaction, using the original game as the
authority. Do not treat a disassembly, accepted input or authored description
as evidence that the game progressed.

The ordinary loop is:

1. Observe the current game and the player's immediate goal.
2. In player-led mode, describe useful choices and obtain intent if it is not
   already clear. In autonomous mode, choose within the delegated goal.
3. Use an applicable known control through the supported current input owner.
4. Observe the result, including failure or uncertainty.
5. Save the useful control and observation without replaying the input.
6. Continue; prepare the selected destination and likely accessible next scenes
   through a bounded predictive frontier when cloud workers are available.

An unknown scene name alone does not invalidate visibly applicable ordinary
movement or menu controls. A scene-specific coordinate recipe does need its
actual starting conditions checked. Never restore an earlier game state merely
to make a recipe fit.

## Keep one question on the critical path

Retain a small frontier: current goal, relevant observed scene/context, one
unanswered operational question, one immediate next interaction and a known
applicable fallback. Keep the selected working control revision with the lead.
Preserve learned facts, but retire queued intentions when the player changes
direction or an observation becomes stale.

Examples of useful questions:

- Does Enter select the highlighted menu item here?
- Does releasing Right stop movement, or does this game use toggled movement?
- Which observed flag distinguishes the closed door from the opening animation?

Exhaustive semantic recovery of all rooms, interactions and variables does not
belong on the foreground play path. Cheap whole-resource extraction and cached
conditional drafts are useful preparation for Dot's
[internal world model](WORLD_MODEL.md); do them once within their declared
budgets instead of rediscovering each room. Keep only the next relevant part
in the active context. A foreground finding is useful when it changes the next
bounded action or how its outcome is observed.

## Bootstrap the next useful operation

Ask what the current prompt requires to continue toward the selected goal.
Options/help may expose controls; Load/save may expose persistent records and
reconstruction; New Game may require alternating observed waits and input.
Use those branches when useful, without exploring every menu or silently changing
settings. Existing [XCOM work](XCOM_REUSE.md) supplies named controls, serializer
experiments and sparse recognition; [DinoPark](DINOPARK_REUSE.md) supplies
native/pixel witnesses and phase-aware transaction controls.

Learn enough of the relevant event loop to distinguish immediate input, queued
work, later phase/timer effects, redraw and readiness. Use controlled helper
experiments without modifying the player's guest or mounted mutable files.
[Bootstrap and event loops](BOOTSTRAP_AND_EVENT_LOOPS.md) defines the capture,
process and clock contracts. This guidance does not implement a live analyzer.

## Foreground bounds and background deadlines

| Work | Initial evaluation policy | On exhaustion |
| --- | --- | --- |
| Initial usable-control evaluation | Existing 180-second end-to-end profile; stop earlier when the selected useful action is supported | Record any miss; retain the working subset and use it; report a real block if no action is possible |
| Complex cold interface/process preparation | Separately declared work bound and readiness milestones, possibly longer than the initial-control profile | Preserve actual elapsed time and prior misses; return partials, use working controls, or describe the real preparation block |
| A missing current control | 15 seconds and at most two probe admissions | Stop admitting probes; use an applicable fallback or report one game-facing block |
| Optional improvement with a working route | No intentional gameplay wait | Continue playing; adopt the improvement between completed actions |
| Predictive cloud-worker preparation | Separate useful-by point and hard work/resource bound, including startup and dispatch | Return useful partials; stop or reprioritize within actual platform support; continue through a working live route |

These are trial settings, not measured latency promises. Include model
reasoning, tool dispatch, unsuccessful probes and publication time in the
player-visible interval. The 180-second profile is neither a minimum wait, a
universal game-loop reconstruction limit, nor a new allowance for each room.
First visibility, useful input, the current operating slice, relevant loop
coverage and full-goal completion have separate milestones. The user's 10+
minute XCOM estimate is unmeasured; historical times have different readiness
and assistance scopes. Declare longer preparation explicitly, retain the
original timeline, and never rename a blocked focus to extend its allowance.
Repeating the same learning focus must not reset its deadline or probe count.

The 15-second/two-probe setting is the lead's foreground missing-control
allowance, not a cap on all background scene construction. Background work may
use natural traversal, necessary animation and player decision time without
adding a stall. It cannot reset or pause a learning focus already started by
the lead. Reaching a destination does not grant a new automatic waiting period.

The `dotbox learn` helper persists the current focus and refuses further probe
admissions when its time/probe allowance is exhausted. It does not preempt model
reasoning or an already running tool, recognize the scene, establish input
ownership, or execute a game action. A caller's stated fallback must still be
applicable to the fresh observation and current input path. A source hash supplied
to that journal is a binding assertion; use `dotbox inspect identity` to obtain
actual file hashes first.

An investigative probe is a bounded analysis or trial selected to answer the
current question. Routine supported passive observation of ordinary play does
not consume an admission. A targeted comparison or test is still a probe, even
when called an observation. A new screenshot alone does not renew the allowance
for an unchanged question. When joining an active run without its original
timing record, keep that earlier interval unknown and record from now; continue
usable play instead of reconstructing a fictitious cold start.

## Choose the cheapest sufficient investigation

| Step | Use when | Stop condition |
| --- | --- | --- |
| Reuse | A compatible prior control or finding exists | Current applicability is checked |
| Observe and use ordinary controls | The visible interface makes the next interaction clear | The intended effect is observed |
| Read supplied instructions or a bounded file region | One control or format question remains | One testable control hypothesis exists |
| Inspect a supported engine's state | A qualified reader provides the needed fact cheaply | One relevant state predicate is understood |
| Compare frozen bytes or disassemble a small window | A concrete question needs native evidence | One candidate condition/control can be tested |
| Plan a short owned capture or trace | Existing frozen evidence cannot answer that question | A bounded packet is captured and the game is resumed before reasoning |

This is a cost preference, not a mandatory sequence. A known engine reader can
be cheaper than visual guessing. Engine-specific readers must report their
actual supported edition; a missing reader does not justify importing a whole
analysis pipeline or rebuilding it during ordinary play.

Reverse engineering remains available for ambiguous meanings and relationships,
including writers and consumers outside the current room and temporary storage
reused in another context. Use the [investigation contract](REVERSE_ENGINEERING.md)
to return reusable evidence to the world model. Foreground limits bound blocked
play; they do not prohibit broader cached preparation or separately bounded
worker analysis. A working route takes precedence over optional research.

The current Python toolkit implements the frozen-file half: identification,
explicit resource hashes, bounded strings/patterns, x86 instruction windows and
range differences. Native memory/register reads require a stopped guest in the
pinned backend. A live capture facade must therefore be a separately qualified
short owned transaction, with aggregate limits and resumption before analysis.
The offline tools never pause, step, write memory or take ownership.

## Persist a useful result, not a research project

Record the concrete question, evidence identity, what changed, remaining
uncertainty and next usable action. Keep candidate findings distinct from an
observed effect. The learning journal records an agent's evidence claim; it
does not certify a game outcome from a label or file hash.

Preserve immutable control revisions and their fallback. Saving a recipe is
metadata work and must cause zero additional inputs. Select a compatible child
revision between actions; retain the prior one. Executable identity alone is
not resource-edition identity, and descriptive context metadata is not automatic
scene recognition. The file toolkit can fingerprint explicit resources, but
the existing control executor does not yet enforce those resource bindings.

On uncertain partial effects, observe again before a recovery decision. Do not
repeat a submission, click or movement automatically. After human takeover,
refresh the actual game state and retire the old intention before resuming.

## Dot leads; cloud workers prepare ahead

The [analysis frontier](EVENT_TRANSITIONS.md#findings-expose-more-answerable-questions)
also includes questions unlocked by new knowledge. A recovered dispatcher,
table schema or state-field role may expose many related bindings and independent
consumers. Batch cheap enumeration, then distribute useful unresolved questions
with their prerequisite evidence; do not assign one agent to every raw match.
Transfer established common facts and investigate differences. Deduplicate work
and invalidate dependent interpretations when their assumptions change.
Keep knowledge readiness separate from player reachability and preserve the
single foreground question and its existing deadline.

Dot can spawn supported full cloud agents when usage permits. While Dot
narrates, retrieves the immediate information and operates the live game,
workers can recover and edit candidate scenes for the selected destination or
likely accessible adjoining locations. A worker may use frozen evidence or its
own isolated execution environment, including separate mutable files and saves.
Give each job one near-term consumer, evidence/branch identity, useful-by point,
hard work bound and an early partial deliverable. Only Dot adopts a candidate
after checking current applicability between completed actions.

Movement is a priority and a natural preparation window. If an appropriate
approach to the selected target already works, begin it while the interaction
slice is prepared. Keep a qualified stop/waypoint and refresh on arrival before
using scene-dependent input. Do not finish the whole room first, add detours or
extend narration to conceal late work. Instant text actions may provide no
comparable window. Reprioritize when the player changes direction.

Read `dotbox guide --topic lookahead` for the worker and timing contract.
Single-agent operation remains the fallback when workers are unavailable:
interleave brief authoring with play through the same live owner. Worker
availability is never a prerequisite for ordinary movement, menu use or
progression. A task list is not a scheduler, and no worker is assumed to continue
after its tool/task lifetime ends.

Only the live owner may mutate the game. Keep expensive reasoning on frozen
observations. Do not keep the emulator paused while an agent reads code, writes
JSON or waits for another agent. During human control, use only supported passive
observation and offline work.

## What the player sees

Talk about the current game, meaningful choices and actual blocks. Keep hashes,
revision IDs, leases, disassembly and harness coverage inside the implementation.
A useful explanation is "The door did not open; I'll check the inventory once."
Routine research updates should not replace playable interaction. Ask the player
about consequential game choices or preferences, not debugger setup.

The player should not install an analyzer, find another repository or recruit a
local agent while playing. The final platform-specific distribution must contain
the compatible native engine and libraries, Python/runtime dependencies,
inspection tools, playbook, recipes and required notices. The Python learning
kit is one tested part of that distribution; see [the package boundary](LEARNING_KIT.md).

## Acceptance and measurements

Use authored fixtures for deterministic policy/tool tests, then separately
qualify the real player flow on Dot's original computer. Record cold preparation,
warm reuse, intent-to-first-input, actual traversal/animation, worker
dispatch-to-usable-result, lead adoption and foreground blocked intervals.
Keep player decision time separate. A late worker with an applicable fallback
can cause no stall; do not equate worker duration with player-visible delay or
double-count overlapping intervals. Python tool duration is not the whole delay.

Required scenarios include known controls without a named scene, a new scene
with usable ordinary controls, expired discovery with a fallback, expired
discovery without one, a stale candidate after a player choice, uncertain effects,
metadata saving without replay, and reconnect without rediscovering controls.
Add preparation during movement, an unexpectedly early arrival, a different
exit, unavailable worker usage and an immediate text transition.
Also record long cold preparation with early usable controls, menu-only paths
with no natural buffer, and separate first-screen, first-action and loop-coverage
milestones. A missed initial-control profile remains a miss even when later
preparation succeeds.
No source test count establishes seamless visible play by itself.
