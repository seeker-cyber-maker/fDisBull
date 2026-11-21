# DotBox

Play DOS games with Dot using an independent DOSBox-X session framework.
The original graphical game remains authoritative.

Dot's planned [internal game model](docs/WORLD_MODEL.md) retains entities,
relationships, rules, evidence and her own useful abstractions. Z-scenes are
bounded views of that knowledge plus current observations. The proposed model
uses exact structured queries with optional text/vector retrieval; the current
observation store is only one part. `dotbox guide --topic world` explains the
design and its implementation boundary.

[Reverse engineering](docs/REVERSE_ENGINEERING.md) remains available to resolve
ambiguous state and discover relationships, including native games and reused
storage. The next [Dune transfer test](docs/DUNE_VALIDATION.md) covers menus,
selected entities and strategic orders after a frozen generic baseline. The
new `reversing` and `dune` guide topics document required work and prior evidence;
they do not claim a newly implemented live analyzer or Dune harness.

The [DinoPark reuse guide](docs/DINOPARK_REUSE.md), available through
`dotbox guide --topic dinopark`, locates prior recovered mechanics and the
existing fDisBull native scene provider. Use its state lifetimes, purchase
phases and guarded recovery contracts to develop the shared model and menu
machinery. This guidance does not yet port the provider into DotBox.

[Bootstrap and event-loop guidance](docs/BOOTSTRAP_AND_EVENT_LOOPS.md), available
as `dotbox guide --topic loops`, adds goal-driven main-menu investigation,
isolated save/state experiments and action-to-event observation. Dot needs to
learn relevant phases, clocks and deferred effects as well as scenes. The
[XCOM reuse map](docs/XCOM_REUSE.md), topic `xcom`, recovers prior startup,
serializer and sparse-recognition work with its actual evidence limits.
Initial usable controls, an understood operating loop and full task completion
have separate readiness measures; complex cold preparation may need its own
declared longer bound. No event-loop analyzer or XCOM provider is added here.

[Generic event transitions](docs/EVENT_TRANSITIONS.md), topic `transitions`, put
menus, screens, rooms and local changes under one event/guard/effect contract.
Learned code patterns or table schemas can expose sibling bindings and unlock
independent analyses. The guide separates reusable rules, concrete bindings
and observed occurrences; family storage and automatic expansion remain planned.

[Behavior and entry-point guidance](docs/BEHAVIOR_AND_ENTRY_POINTS.md), topic
`entrypoints`, uses agents' coding knowledge to propose testable implementations
and recover several ways to invoke one operation. Movement grows from verified
position through coherent placement to original room entry; menus can similarly
reuse a qualified handler or loader. Isolated research and the visible player's
original route retain separate purposes. Existing fDisBull helpers are concrete
reuse candidates; this guide does not add native invocation or teleportation to DotBox.
Its multi-probe survey method uses the debugger to retain transient dispatch
evidence across comparable per-control trials, producing a useful map before
every handler is explained. An isolated [Dune batch](docs/DUNE_BATCH_PROBE.md)
now executes restore, probe setup, input, capture and timeout mechanically.
The reviewed nine-trial dispatch pass took 3.233 seconds; a separate 18.080-second
pass observed the visible effects and repeated a map action with matching
measured outcomes. Both used the retained fDisBull native runtime;
packaged original-Dot orchestration and player-facing rewind remain separate work.

The [continued Dune run](docs/DUNE_PROGRESS.md) recruits a Fremen troop and
assigns spice work through original input. Its [optimization continuation](docs/DUNE_OPTIMIZATION.md),
`dotbox guide --topic duneoptimization`, adds explicit sparse observations and
capability-gated native bounded waits. Eight paired trials retain matching
measured images/state while reducing a conversation-entry action from 227 to
56 RPCs and from 1,572,879 to 117,315 bytes read. The rebuilt headless Linux
runtime and Gurney checkpoint are qualified within the recorded research scope;
original-Dot desktop integration remains a separate gate.

The [travel-map selector](docs/DUNE_MAP_SELECTOR.md), available through
`dotbox guide --topic dunemap`, adds read-only destination preparation and a
single-use original-click action for the recorded travel-menu profile. It binds
the complete callback vector and current rendered point, proves destination
acceptance before continuing, and reports input readiness separately from
arrival. Both full and sparse readers are supported with explicit native
bounded waiting; 124 authored protocol tests cover the action and refusal paths.
Four final-source live trials reached Harg and Timin through separate original
travel actions; stale-revision and exhausted-budget checks preserved refusal
without replay. The guide records exact identities and the limits of those results.

The [RTS primitives](docs/RTS_PRIMITIVES.md), available through
`dotbox guide --topic rts`, separate camera movement, entity/group selection,
command choice, target submission, context click and held gestures. A bounded
world observation includes NPCs, allies, distinct ownership/control, logical
groups and mission events. It projects into the existing scene/store path.
The public controller admits and dispatches one provider primitive at a time;
stale contexts and uncertain outcomes cannot silently replay input. The offline
`dotbox rts` tools and authored example ship with the kit. Game-specific live
bindings and the original Dune II held-gesture adapter remain separate work.

The [Dune II economy guide](docs/DUNE2_ECONOMY.md), available through
`dotbox guide --topic dune2economy`, records an original mission-one win and the
observed conditions for construction, harvesting, returning and result
transitions. Its source-bound findings support future provider work; the guide
does not install a live Dune II adapter or qualify a complete campaign.

The primary experience is [Dot as the game's conversational interface](docs/CONVERSATIONAL_PLAY.md):
describe the current scene, offer useful choices, interpret the player's intent
and carry it out. Autonomous play uses the same scene/action model. A small
[guide-informed opening pass](docs/GUIDE_RECONSTRUCTION.md) supplies the game's
goal and a checklist of expected objects and exits, which Dot reconciles with
the actual game. Description length, who chooses, and hints remain separate preferences.
When usage permits, Dot can spawn full cloud agents to prepare likely upcoming
scenes while Dot narrates and operates the live game. Graphical movement is
useful progress and natural preparation time. `dotbox guide --topic lookahead`
documents bounded prediction, independent worker candidates and adoption at a
fresh action boundary. These are operating requirements; this cut does not add
a cloud scheduler or qualify live movement/voice concurrency.

This development cut extracts the working transport, input validation, screenshot
handling and immutable learned controls from fDisBull. It does not import or
require an installed fDisBull package or analysis database. The package now
includes a bounded offline inspection kit, a saved next-question journal and
the play instructions, with its pinned x86 decoder as a required dependency.
It also owns the small [AGI V2 logic/resource reader](docs/ENGINE_AWARE_PREPARATION.md)
and a [state-bound walking planner](docs/NAVIGATION.md), so compatible engine
evidence and long straight route legs can be prepared without the full analyzer.
A compatible DOSBox-X native build is a separate explicit runtime input.

Start with [standalone installation](docs/STANDALONE.md), the
[native source/build recipe](docs/STANDALONE_NATIVE.md), and
[persistent controls](docs/PERSISTENT_CONTROLS.md).
For a local Apple Silicon build, use the
[Mac build-and-test helper](docs/LOCAL_MACOS_BUILD.md). It builds the pinned
native source and requires eight actual native fixture passes, with no skips.
A fresh Mac Studio build passed all eight fixtures, four headless and four
visible, on 17 November 2026. See the
[sanitized native-build receipt](https://github.com/seeker-cyber-maker/DotBox/blob/codex/local-macos-build-20261117/docs/evidence/local-macos-native-2026-11-17.json).
A separate [cloud Linux build](docs/LOCAL_LINUX_TEST.md) also passed all eight
fixtures, and an ordinary-input Police Quest run completed the locker-to-shower
controls endpoint. These results qualify the recorded developer-build fixtures
and one functional game route. Original-Dot desktop integration, reusable route
and timing qualification, and complete memory rewind remain separate gates.

For the current development slice, read [incremental play](docs/INCREMENTAL_PLAY.md)
and the [installed learning kit](docs/LEARNING_KIT.md). `dotbox guide` gives Dot a
short starting procedure; `dotbox doctor` checks offline tools and packaged
resources without launching a game. Use a known applicable control for the
selected intent now, observe
its effect and save the recipe afterward. Learn only the next missing interaction.
The current 15-second/two-probe learning allowance is an evaluation policy,
not a measured promise of seamless play.

The current scene slice renders provider-reported facts, keeps guide expectations
internal, and returns a scene-bound intent without executing input. Its
[stateful scene tools](docs/STATEFUL_SCENES.md) persist observations and flags,
reject selections made stale by offscreen updates, distinguish enabled actions
from input readiness, and separate useful suggestions from commands available
on request. `dotbox scene look` passively describes the current scene; `record`,
`present --store`, `choose --store` and internal `memory` use the saved observation
stream. `dotbox guide --topic state` explains the provider adapter contract.
The offline slice does not yet extract live game flags, recognize scenes, parse
arbitrary speech, fetch walkthroughs or connect a live voice frontend.

For development continuation, read the [current handoff](docs/DEVELOPMENT_HANDOFF.md).

The first milestone is the engine and its ownership boundary: one guest survives
client calls, frames can be observed, and stale agent input is refused after
explicit human handoff in diagnostic mode. Normal input stays on the desktop
harness path, with direct agent input RPCs disabled. Codex's **Take over / Return control** buttons belong to
the outer WebRTC harness. The optional [ownership bridge](docs/OWNERSHIP_BRIDGE.md)
uses fresh viewer observations to coordinate cooperating agent turns. Native
ownership stays separate. A coordination-only receiver can run without an
emulator. The real viewer-to-headless-receiver handoff is verified over the existing
private SSH route, using harmless data callbacks. The saved operations environment
starts. Actual desktop-tool input through the turn wrapper remains unqualified.
The [connection follow-up](docs/evidence/studio-connection-repair-2026-11-16.json)
verifies restored Studio attachment with a sandboxed default. In the checked
attachment, Dot's desktop-tool session reinitialized and its bound cloud app
variable was unavailable. The original cloud desktop and coordinator still need
a shared supported execution path for the input check.
The optional [ownership connector](docs/OWNERSHIP_CONNECTOR.md) now connects Dot
through an existing private Secure MCP Tunnel. Live reads match Dot, human after
Take over, and Dot after Return control. Paused foreground observation returns
unknown; no unattended sampler or input grant is implied. See the
[connection permissions](connectors/ownership/permissions.review.json) and
[live verification](docs/evidence/ownership-connector-live-2026-11-16.json).
The [earlier preflight](docs/evidence/desktop-ownership-preflight-2026-11-16.json)
also records the fix preventing asynchronous callbacks from being reported as
completed synchronous actions. The separate `Client.run_turn_step_async` now
awaits a cooperative Python callback between checks of one unchanged lease.
It does not expose CUA tools to Python or qualify live Dot input.

`dotbox agi inspect` produces a bounded private census for the explicit AGI
2.917/uncompressed V2 profile. It identifies conditions, state writers and
resource candidates; static references do not establish current flag meanings
or available actions. `dotbox route plan` minimizes distance, then turns, and
compresses a route into straight legs. `route check` rejects proposals made
stale by changed supplied scene/state, geometry or conditions. Both commands
are offline and send no input.

[Recovery and saved-game evidence](docs/RECOVERY_AND_SAVES.md) specifies how to
reuse native checkpoints to recover from a stall or crash, invalidate the old
timeline and learn from controlled save contrasts. The existing raw restore
primitive still needs a qualified restore transaction before DotBox can offer
live rewind. Revert restores memory; mounted files keep their current versions,
with no matching filesystem rollback. Selected long legs likewise
need integration with the existing monitored x/y and TAS control machinery.
The [recovered AITD work](docs/AITD_REUSE.md), available through
`dotbox guide --topic aitd`, supplies prior walking feedback, manipulation
planning and reference-backed menu methods. Its research helper that replaces
save files is explicitly excluded from memory revert.
The user-selected [Police Quest acceptance tests](docs/POLICE_QUEST_ACCEPTANCE.md)
are changing in the locker room and reaching the showers, then recovering from
late arrival at the first briefing. The first has one successful functional
run on the cloud Linux computer, including shower activation and cleanup through
ordinary controls. A reusable route and complete timing trace remain open;
the missed-briefing memory-recovery trial has not run. `dotbox guide --topic
policequest` supplies the EGA-specific conditions and static timer findings.
The guide itself adds no game-control or recovery operation.
Additional engines, game-specific routes, HUD and audio transport remain later
work. There is no published release or qualified Dot cloud installation yet.

[Verification](docs/evidence/standalone-engine-2026-11-16.json) · [Extraction boundary](docs/EXTRACTION.md) · [Product brief](docs/PRODUCT.md) · [Repositories](docs/REPOSITORIES.md)

See the [Codex viewer code investigation](docs/CODEX_VIEWER_CODE_ANALYSIS.md) for
ownership signals, actual-source offline checks, live viewer results and remaining
bridge boundaries. Movement through that ownership bridge, recovery and audio
still need qualification; the separate local controls run does not close them.
