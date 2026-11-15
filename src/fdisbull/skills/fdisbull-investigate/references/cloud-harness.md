# Continuous play and cloud harness building

Use this reference when Dot plays with a user while the harness grows, or when
a cloud worker is assigned part of that harness. The goal is a usable current
scene with the next useful controls ready before they are needed. This is an
operating procedure over existing capabilities, not a new scheduler or a promise
that background workers survive after their task/process ends.

## Start from the current frontier

Reuse the selected executable, project, live owner, policies and action file.
If the environment is new, check only the required capabilities and keep private
databases, object stores, outputs and saves outside Git ancestry. In a cloud
checkout, `$HOME` can itself be inside the repository; choose an actual private
writable location and set `FDISBULL_TARGET_STORE` and
`FDISBULL_OUTPUT_ARTIFACT_DIR` there when needed. Ephemeral `/tmp` is useful for
scratch work but is not a persistence guarantee. Preserve the required private
workspace through the environment's supported storage mechanism.

Retain the process and open JSON stream that own the guest. Use the environment's
supported long-lived process/session facility; do not pipe each command into a
new `z-controller`. `close`, EOF and transport failure close its guest. Saved
run history cannot reconnect it. A fresh controller starts with empty `ctx.state`;
restored artifacts are evidence to revalidate, not a live attachment.

The single play lead owns requests to that controller. Coordinate the actual
desktop input owner separately when a user can take over. A chat/thread handoff
does not establish a WebRTC input lease. Use a supported ownership signal/API
when available, otherwise coordinate explicitly. Before a planned handoff, while
still owning input, settle movement and release controller-owned holds through
the qualified input recipe. If ownership is lost abruptly, do not inject releases
during the user's turn; reconcile owned holds on safe return. While the user owns input, do
not send game input, run/step, restore, or apply live edits. Offline analysis can
continue. On return, observe the current scene, release only controller-owned
inputs where applicable, retire queued scene-specific intentions and refresh
bindings. Never rewind the user's progress to fit a worker's checkpoint.

## Prepare a small opening buffer

Choose a short recon budget appropriate to the game and available startup time.
Keep it internal unless the user needs a real timing decision. Use the opening
menus and first playable state to retain:

- A bootstrap from launch to the actual opening scene, with a visible/readable
  readiness check. Controller `ready` means command-channel readiness only.
- The basic movement or selection action and its stop/release behavior; primary
  interaction, back/cancel and menu/pause controls when present. A turn-based or
  text game may need selection/submission instead of movement.
- A few useful Z scene/route definitions around the current opening and likely
  next transition, with entry/readiness, action, result and a working fallback.
- A known recovery route or qualified save/checkpoint if readily available.
  Missing save support is a local gap, not a reason to delay otherwise usable play.

These are goals to adapt, not a fixed control checklist or scene-count quota.
Stop buffering when current play and the next likely transition can proceed
through a verified action or ordinary input. If the recon budget expires, publish
what works and address only an actual blocker; do not claim the buffer is ready.
For an existing session, start from its current scene instead of replaying launch.

## Build where the player is going

Keep a short ordered frontier rather than a whole-game implementation plan:

| Priority | Work to do | Publish |
| --- | --- | --- |
| Current play | The missing control, stalled movement, modal exit or interaction needed now | Smallest working named action or authentic input route |
| Immediate continuation | Next likely room, encounter, menu or turn boundary; a cheap alternative when choices branch | Entry check, short route and usable resulting state |
| Reuse along that path | A repeated global control, observation, navigation helper or serializer that removes near-term effort | Shared verb behind the existing interface |
| Later research | Distant levels, exhaustive engine recovery or a replacement implementation | Park until requested or brought to the frontier |

Reprioritize at scene transitions, player choices and user takeover/return.
Stop speculative work that has lost its near-term consumer. A bottleneck on the
immediate path receives the worker before interesting endgame research does.
Batch compatible observations while the relevant scene is available; do not
hold the live guest in a research screen for unrelated experiments.

Learn through ordinary play, retain the input recipe immediately, then compose
routes. Record an already-performed action with `capture-action` without
`execute:true`; execution would repeat it. A newly tested sequence may use
`execute:true` to retain its before/after frames. Metadata (`entry`, `next_state`,
`observation`) records a claim; it does not enforce live readiness. Use a real
predicate where a stale label could cause an incorrect effect. `expect-frame`
checks the last stored frame and does not wait for redraw.

Use bounded guest time and stop conditions. For user-paced controller execution,
pass `fast_forward:false` explicitly; `ctx.run` otherwise defaults to true.
Retain the acquired input fallback when an optimized handler is unfinished or
inapplicable. Before a same-name Python handler shadows a captured recipe,
retain a separately callable input verb such as `open-door-input`; the optimized
`open-door` can invoke that alias when its precheck declines before any effect.
Invoking `open-door` from its own handler would recurse. Merely retaining the
shadowed recipe on disk is not a callable fallback. Explicit restoration of the
prior action module is another option. A failed action may have partial effects: inspect those effects
before retrying or choosing recovery. Never automatically repeat a purchase,
submission, turn, save overwrite or other effect after an ambiguous response.

## Give a worker one useful slice

Delegate only work that can proceed independently. A compact brief is enough:

```text
Role/question: prepare the next-room exit action.
Consumer/priority: play lead, before leaving the current opening area.
Inputs: allowed scene snapshot/revision, relevant evidence IDs, current action
        contracts and input recipe, target/source identity, user clues.
Policies/ownership: physical/assisted/story and information policy; shared live
                   controller is read-only evidence, with no direct worker input.
Output: separate candidate file/recipe, applicable entry and result, tests or
        observed evidence, unknowns, and working fallback.
Bounds: one scene transition, explicit time/probe limit; return a useful partial
        early and stop if superseded or the declared limit is reached.
```

Workers normally inspect immutable captures, supplied files or authored code.
If a supported isolated guest is available and its use is in scope, it needs its
own controller, project, action files and writable game/save directory. An emulator
checkpoint does not isolate mounted host files. Do not start a duplicate guest
merely because a worker exists, or let an experiment overwrite the player's saves.
If isolation is unavailable, return a candidate and one bounded probe for the lead
to perform during ordinary play or an agreed safe boundary. Never seize the guest.

Keep worker results small: usable candidate, applicability, decisive evidence,
unknowns and next action. `work-queue`/`run-work` can track and execute dependencies
in the controller, but they are single-owner operations, not background agents.
When parallel execution is unavailable, follow the same priority order serially
and keep using working input routes between short authoring steps.

## Promote without disrupting play

Workers write separate candidates. Only the lead publishes the selected action
module or capture store. Retain the known working revision; review the candidate
and syntax-check it without importing it into the live owner. Top-level code and
imports must have no guest effects: even `list` executes the selected module.
Promote a complete file atomically between controller requests. Sibling imports
have normal Python caching; explicitly reload reviewed helpers or keep evolving
handlers in the selected file. One composed route pins one handler generation;
promote after it finishes, not in the middle of its input sequence.

Check the candidate against current source/scene and assistance policy. Evidence
from an isolated scene is not a live readiness check. Preserve verb names and
parameter contracts used by current routes; adapt the candidate or defer a breaking
change. Use a side-effect-free `list` for discovery, then validate the smallest
applicable effect at a safe opportunity. `list` metadata alone does not qualify
the effect. For destructive or unavailable cases, keep the candidate unpublished
and continue the working fallback. A reload error preserves the guest but does
not automatically reuse stale handlers: explicitly restore the known working
file, inspect state and resume without replaying ambiguous effects.

Use a small task note to distinguish candidate, tested scope and published
revision; these are authoring labels, not built-in controller status fields.
An action is currently usable only when its applicable context is available.
Return the immediate state and available choices to the player. Interrupt only
for an actual blocked action, a consequential choice or control ownership; routine
harness progress belongs in the background dossier.

## Keep blind play blind

Apply the selected information policy to worker inputs, outputs and the play
lead's observations. Investigative access to full memory, source, a map, saves or
an isolated future scene does not make that knowledge player-visible. In blind
play, keep generic control mechanics separate from hidden game facts; give the
lead only allowed observations and action contracts. Do not leak unseen units,
objectives, random outcomes or spoilers through scene names, readiness metadata,
logs or fallback explanations. If a worker cannot separate a useful control from
forbidden facts, defer it or use an allowed input-backed action.

For exact controller JSON, recipe fields, scene guards, input handling and native
helper contracts, read [runtime navigation](runtime-navigation.md). Read
[scenes](scenes.md) for persisted scene definitions. These operations remain
backend- and target-specific; a notebook plan is not an executable Z scene.
