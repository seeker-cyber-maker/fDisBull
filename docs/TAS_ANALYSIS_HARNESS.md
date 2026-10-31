# TAS routes as an analysis and test harness

Status: **capability map and proposed workflow**, 31 October 2026. This document
uses existing fDisBull APIs where identified. The timestamped replay scheduler,
synchronized capture sidecar, automatic route minimizer and coverage scheduler
below are proposals, not implemented interfaces.

A useful TAS harness lets an investigator reach a known interaction repeatedly,
pause at the relevant boundary, collect evidence, and branch from the same
checkpoint. An agent can use that route to inspect a writer, compare an execution
layer, test a recovered UIL rule, or reproduce a failure. A full speedrun is one
possible workload; a short, well-qualified interaction is already useful.

The current debugger supplies most components for **bounded, observed
automation**. It does not yet supply general deterministic movie replay. Keep
the recorded physical inputs, decisions, observations and any interventions
together so that a successful bot loop can become a reviewable test procedure.
The [KQ1 investigation](VERIFICATION-KQ1-TAS-2026-10-31.md) records the concrete
input-timing, capture and short-route comparison findings motivating this work.
The [capture auditor](TAS_CAPTURE_AUDIT.md) now implements the offline recording
check: it hashes every decoded frame, retains exact video timestamps, and exports
every Nth frame for slower review through the CLI, JSON protocol or Python API.

## 1. Choose the execution contract

| Contract | What determines the next input | What a repeat can establish |
| --- | --- | --- |
| Exact timed replay | A fixed sequence of physical key edges at exact guest-clock deadlines, under a pinned initial machine state and execution profile | Fidelity to that schedule, if actual deliveries and the relevant machine behavior are verified. General imported-movie execution is not implemented here. |
| Observed automation | A bounded script or agent chooses an action after qualified observations; `wait` or `move` decides when a condition has been reached | A repeatable procedure and its observed outcomes. Polling, execution overshoot and decisions can differ between trials. |
| Assisted experiment | Either procedure includes explicitly declared actor edits, layers or derived checkpoints | Behavior under those interventions. Its lineage and performance category remain separate from ordinary player input. |

For exploration, feedback is useful: wait for the actual modal, stop after the
transition, and inspect an unexpected result. For exact replay, feedback must
not silently postpone the next input or substitute a different action. A
recovery decision starts a new branch with a new identity. A successful
feedback route can later be frozen into a candidate timed schedule, but
executing that schedule and verifying it are separate work.

Likewise, two routes that reach the same room are not necessarily equivalent.
State, output, timers, animation, queued input and the chosen finish boundary
can differ. A room crossing does not establish that a full game or a published
TAS has been completed.

## 2. Components available now

The table concerns the native DOS workflow used in the KQ1 investigation.
Other backends have different capabilities and observation boundaries. Inspect
the selected backend's capabilities and the session's `script_operations`
property before dispatch; a shared method name does not establish identical
semantics.

| Need | Existing interface | Limit relevant to a TAS harness |
| --- | --- | --- |
| Physical keyboard input | `keyboard_press`, `keyboard_type`, `keyboard_state`; held-key leases through `keyboard_key_down` / `keyboard_key_up` | Atomic press/type durations are integer guest milliseconds. Queue acceptance does not prove game consumption. This is not an arbitrary timestamped physical-edge movie importer. |
| Bounded guest execution | `run(guest_ms=..., timeout_ms=..., fast_forward=...)` | Guest time and host budget differ. Host polling can overshoot the requested guest interval; retain the measured result. |
| Observed completion | `wait(observations, until, ...)` | Explicit memory/register/status observations, bounded polling, and mandatory captures. It requires the measured DOS guest clock. |
| Reusable input vocabulary and movement | `macro`, `move`, immutable source-bound macro sets | A name expresses an authored control contract. Movement additionally verifies progress, stop consumption, settling and retained destination; it is not an automatic world planner. |
| Stored routes | `script`, `project.debug_save_script` | Bounded declarative `fdisbull-script-1`, immutable source and results. No arbitrary embedded host-language bot, rollback or deterministic replay is implied. |
| Checkpointed comparisons | `save_state`, `load_state`, `save_experiment`, `restore_experiment`, `compare_experiment` | Native identity checks and mounted-file manifests apply. Experiment restore rearms owned controls; plain state restore has different control semantics. |
| Focused execution evidence | `breakpoint(access="x"/"r"/"w"/"rw")`, `trace`, `capture_code` | Watch/trace stage is backend-specific. A captured code span does not establish that it executed. |
| Pixels and scene recognition | `screenshot`, `frame_probe`, scene checks/actions | The agent framebuffer is a latest-snapshot cache, not an all-frame queue. A frame identifier is not a video-frame count. |
| Finalized recording audit | `capture-audit`, `fdisbull.capture_audit.audit_capture` | Decodes/hashes every recorded AVI frame and optionally samples PNGs. Segment clocks remain independent; guest time and input alignment remain unknown. |
| Explicit assisted branches | `assisted_travel`, execution layers, `project.debug_fork_state` | These retain intervention evidence. A derived checkpoint is not evidence that ordinary input reached that state. |

Detailed contracts are in [guest keyboard input](GUEST_KEYBOARD.md),
[bounded runs](DOSBOX_DEBUGGER.md), [observation waits](OBSERVATION_WAIT.md),
[semantic input and movement](SEMANTIC_INPUT_MACROS.md),
[scripts](DEBUGGER_SCRIPTS.md), [experiments](DEBUGGER_EXPERIMENTS.md),
[runtime code](RUNTIME_CODE.md) and [assisted travel](ASSISTED_TRAVEL.md).

### A bounded action using existing APIs

The following is an integration fragment, not a KQ1 route. It assumes one
owned, paused DOS session named `debug`, a verified starting condition and a
command of at most 63 supported ASCII characters. `probes` and
`finished_predicate` are caller-qualified descriptors in the existing wait
schema; they must establish the action's completed boundary, including its
relevant output/modal state. They are not inferred from the command string.

```python
route = {
    "format": "fdisbull-script-1",
    "steps": [
        {"op": "keyboard.type", "text": command + "\n",
         "hold_ms": 40, "gap_ms": 40},
        {"op": "wait", "observations": probes,
         "until": finished_predicate, "guest_ms": 11000,
         "slice_ms": 20, "timeout_ms": 30000, "fast_forward": False,
         "timeout_screenshot": None},
        {"op": "keyboard.state", "as": "keys"},
        {"op": "assert", "value": "$keys.keyboard.pending_events",
         "equals": 0},
        {"op": "assert", "value": "$keys.keyboard.owned_keys",
         "equals": 0},
        {"op": "screenshot", "name": "action-end.png", "hooks": False},
    ],
}
report = debug.script(route, timeout_ms=60000)
if not report["ok"]:
    raise RuntimeError("Action failed; retain the saved script report")
checkpoint = debug.save_state("after-action.sav")
```

The 11,000 ms guest budget includes delivery of the bounded command and a
completion allowance; keyboard delivery itself consumes guest time. Adjust
the allowance to the qualified interaction rather than assuming queue
acceptance means the game has already received Enter.

A wait can match immediately if its predicate was already true. Choose a
postcondition that distinguishes this action from the starting state, or use
a separately qualified transition witness. Do not add an arbitrary delay to
make an ambiguous predicate look like success. The keyboard assertions also
prevent a matched observation from hiding outstanding input. A movement action
needs the stronger stop/settle/retained-destination contract provided by `move`.

This fragment disables the wait's automatic timeout screenshot and uses raw
final capture with `hooks=False`: screenshot
preparation can execute guest work or change layers. If preparation is part of
the experiment, declare its effects and timing instead. Missing framebuffer
evidence remains a failed capture; a stale or fabricated image cannot replace
it. Saving the resulting checkpoint does not roll back host files written by
the game.

For a writer investigation, set a qualified execution breakpoint or data watch
before saving an experiment. Its route can run to that stop, read registers and
the relevant fields, remove the owned stop, and collect a bounded trace. Use
the captured control keys supplied by `restore_experiment`, rather than
assuming native breakpoint IDs survive restoration. The
[existing experiment example](DEBUGGER_EXPERIMENTS.md#capture-and-restore-controls)
shows that complete sequence.

`run()` normally dispatches hooks and may resume after them. Set
`stop_on_hook=True` when each hook must terminate the observation interval;
`wait` already preserves such stops. A DOS data watch means that an access was
observed, with whole-instruction completion unknown. A DOS trace records
before-fetch observations, and its final budget record is pending. Use the
[normalized semantics](DEBUGGER_SEMANTICS.md), not an assumption that every
record represents a completed instruction or game action.

## 3. Capture a route as evidence

Reuse the existing script, experiment, artifact and event records. A proposed
analysis manifest can connect them; it should not replace their native receipts
or introduce an undocumented extension to an existing format.

| Evidence group | Minimum information to retain | Why it matters |
| --- | --- | --- |
| Source and execution identity | Executable/resource inventory hashes, mapped source version, emulator binary/configuration, CPU/timing profile, tool and harness revisions | A game title, movie title or filename does not identify a reproducible execution environment. |
| Starting boundary | Checkpoint artifact/hash, mounted-file closure, owned controls/layers, relevant state, guest-clock endpoint, input state and any warm-up | Restoring the same checkpoint does not imply identical state after different preparation. |
| Input and decisions | Immutable script/macro hashes, expanded physical operations, requested timing, queue responses, releases, observations that selected each branch | An agent's semantic command is insufficient to reconstruct its actual input. Existing queue receipts are not a full per-edge delivery log. |
| State and execution | Explicit before/after fields, source-qualified bindings, stop/trace stage, unresolved observations, completion/continuation boundaries | A final screenshot or score alone can conceal different conditions and side effects. |
| Frames | Capture segment, source frame/PTS identity where available, dimensions/mode, image hash, sampling rule, capture errors and known gaps | “Every fifth sample” is different from “every fifth guest video frame.” |
| Completion and timing | Success conjunction, start/end guest clocks, host timer endpoints, measured overshoot, timed preparation/cleanup policy | Reported elapsed time must have an auditable boundary. |
| Interventions and failures | Parent branch/checkpoint, authorized intervention kind, exact declared edits/layers, expected values/readbacks, partial effects, failed attempts | Later arrival must not erase an earlier blocked or incomplete action. |

Current APIs retain substantial parts of this evidence in separate artifacts.
A uniform manifest, synchronized input/frame sidecar and per-edge native
delivery receipts remain proposed work. Capture unavailable fields as unknown;
do not reconstruct an exact delivery time from queue acceptance or a PNG time.

After the owning guest exits, reopen the closed project or a sealed copy to
check that referenced events and artifact bytes are durable and hash-matched.
Do not inspect a database concurrently in a way that competes with its live
owner. Publish a selected receipt and generic reproducer; original game assets,
native states, target-derived bytes and byte-retaining databases stay private.

### Frames and slower host processing

The practical requirement is to slow **host-side processing** while preserving
the guest schedule. Processing an already captured image while the guest is
paused can satisfy that requirement: record guest clocks before and after, and
verify no guest progress occurred. Changing emulated CPU speed or stretching
input deadlines changes the experiment. `fast_forward` is not a lossless
frame-stepping or arbitrary slow-motion interface.

Current RPC screenshots expose the latest accepted cached snapshot. Polling
cannot recover overwritten intermediate frames. The KQ1 investigation also
found snapshot-cache starvation in its tested backend, so an advancing native
display did not guarantee that every completed render became a new cached
snapshot. This change carries a source correction, tracked in the linked
verification report; acceptance on a rebuilt native backend requires the PR's
native CI jobs and their backend identity receipts. The historical measurements
do not qualify that corrected source. Treat `frame_id` as an accepted snapshot-refresh
sequence, not a count of all video frames. CPU instruction stepping is not frame
stepping.

Native video recording provides an independent capture path in the tested
setup, with zero frameskip and unchanged frames retained. Record those settings
and the capture's actual timebase; do not substitute a published movie's frame
rate. Its video timestamps and segment-local frame indices still need an
explicit relationship to guest-clock/input/checkpoint events. Mode changes may
split captures; checkpoint restores create timeline discontinuities. A decoded
AVI's frame count does not by itself establish exact input-to-frame alignment.
The present fDisBull API has no synchronized all-frame sidecar.

For short regression runs, capture the complete native video when feasible,
decode and hash every available frame, and derive every-Nth-frame analysis
offline while preserving original frame indices and timestamps. For agent
snapshots, label the samples honestly and retain every
capture failure. A proposed native capture queue with backpressure would pause
or throttle host execution before losing a requested frame, while keeping guest
deadlines unchanged; that requires implementation and timing verification.

Use `capture-audit` for that offline step. Its compact receipt reports success or
failure and references the complete per-frame records; agents must check the
audit outcome before using exported samples. The optional HTML viewer changes
only inspection playback speed. Known-color real-codec tests verify that all
frame hashes and original timestamps survive different sampling intervals,
including duplicate frames. See [the command and API guide](TAS_CAPTURE_AUDIT.md)
for budgets, failure handling and the boundary between video and guest clocks.

## 4. Use the route to answer an analysis question

### Find the committing operation

Reach the interaction with ordinary input, save a drained checkpoint, and
watch the smallest relevant state range. Repeat the action once with the watch
armed. Inspect the causing instruction, resume location, raw registers and
memory effects at their actual observation stage. Then collect a bounded trace
around the writer or a source-qualified engine entry. This narrows analysis to
the operation that changes state rather than tracing the entire trip to it.

Separate admission from completion. A score increment may occur before an
animation finishes; a modal may suspend dispatch before a later write; a room
number may change before entry initialization has completed. The stopping
condition must match the question being investigated.

### Branch from a checkpoint

Use `save_experiment` / `compare_experiment` for a baseline and an explicit
alternate layer stack. Both trials restore the saved setup, and the comparison
attempts to restore the baseline afterward. Inspect procedure success and
`observed_difference` separately. Failed or incomplete trials cannot establish
equality, and positional trace comparison is not alignment after a divergent
loop.

For alternative ordinary inputs, restore the compatible checkpoint and execute
separate immutable scripts, retaining a parent-child record in the investigation
manifest. Native restore invalidates runtime bindings and cached framebuffer
evidence; resolve and verify the required addresses again. Do not carry an
old actor pointer or input lease into a restored epoch.

An explicitly edited fork through `project.debug_fork_state`, or an
`assisted_travel` action, is a diagnostic/assisted branch. It is useful for
testing a condition or reaching a bounded interaction, but it does not prove
player reachability. Do not invent inventory, quest or ending writes to make
an ordinary route appear successful. Preserve the original failed attempt and
record assistance as a separate child operation.

### Turn a failure into a small regression

First reproduce the same failure from the same qualified starting boundary.
Define its signature: for example, the same semantic mismatch, wrong writer,
unreleased key or destination lost during cleanup. A timeout from a different
cause is not the same reproduction.

A proposed minimizer can then remove action groups, shorten a prefix by using
an already captured compatible checkpoint, and reduce observation/trace scope.
Preserve key-down/key-up pairing, modal acknowledgements, required state and
the failure boundary. Timing changes are separate candidates with new hashes;
deleting a delay can change timers or random draws. Keep the original full
input record beside each reduced candidate and stop reducing when the signature
no longer reproduces.

No automatic minimizer is implemented. Existing saved scripts, checkpoints,
experiments and explicit assertions are enough to perform these reductions
under one controller today. A regression should assert the investigated effect
and its relevant side effects, not merely that the script returned successfully.

## 5. Back recovered UIL with the same interaction

A native route is valuable as an input and event fixture for semantic recovery.
It does not turn every visited instruction into game intent. Begin with one
complete interaction whose entry, conditions, state changes, output, temporal
effects and return/continuation boundary are defined.

Use three comparisons where the project supports them:

1. **Original execution:** qualify the actual entry state, inputs, engine events,
   ordered effects and completion boundary. Memory bindings and output/event
   identities require source evidence.
2. **Preserved reference:** execute the retained low-level IR or an independent
   source-slice reference against the same admitted state and event sequence.
   Keep its original behavior and tests intact.
3. **UIL plus UDL:** execute named semantic rules through their source-bound
   adapter, compare the ordered effects and resulting state, and account for
   every retained IR segment or unsupported-path fallback.

Compare conditions/refusals, all relevant writes, output order, input
consumption, animation/timer events and continuation state. The next command
can be part of the fixture when an effect concerns pronoun resolution or later
progression. Do not erase a difference simply because the final picture matches.
Unknown facts remain unknown, and unmodeled operations remain explicit IR.

The existing [Zork intent runtime](ZORK_INTENTS.md) already separates the
mailbox interaction and action counter from retained parser/scheduler IR, with
source-specific UDL and existing reference checks. Its input-to-prompt boundary
includes turn effects; one command does not necessarily equal one turn.

The earlier [KQ1 bow interaction branch](https://github.com/seeker-cyber-maker/fDisBull/blob/0b7f258cc0fa71daef5c60c068ade42904c5d1c6/docs/KQ1_BOW_INTENT.md)
demonstrates a different boundary: command admission, a one-time reward, an
animation completion event, response and modal acknowledgement. That is
branch-scoped prior work; its evaluator is not supplied by this PR or its
current-main base. In that implementation, the evaluator accepts a declared
state and qualified host events; it does not drive a native guest or manufacture
animation completion. A harness must supply those observations rather than
guessing them from an elapsed delay. Returning all treasures and ending the
game remain outside that recovered interaction.

An automatic bridge from arbitrary native checkpoints to complete semantic
state is not available. First add and verify only the state/event projection
needed by the chosen interaction; unrelated uncertainty need not block an
already qualified slice.

## 6. Measure scene coverage without overstating recovery

The earlier [AGI census branch](https://github.com/seeker-cyber-maker/fDisBull/blob/0b7f258cc0fa71daef5c60c068ade42904c5d1c6/docs/AGI_SCENE_CENSUS.md)
illustrates how to inventory scene elements and source obligations before short
routes collect targeted runtime evidence. That separate branch's `agi-scenes`
implementation is not added by this PR or present in its current-main base.
Room visits, decoded LOGIC resources, accepted interactions and proved
conditions remain separate coverage measures.

For each source-bound interaction revision, track:

- Candidate entry/exit and the source conditions controlling them.
- Observed admissible, refused, repeated and interrupted cases.
- State and output changes, asynchronous completion and acknowledgement paths.
- Native commit evidence versus source-only/model-only checks.
- Whether the tested state was ordinarily reached or explicitly assisted.
- Missing dependencies, unobserved branches and residual low-level IR.

A proposed coverage scheduler can prefer the next cheap route that resolves an
important unknown, reuse a compatible checkpoint, and share immutable evidence
with analysis workers. One controller still owns each guest. Workers can inspect
source and completed captures in parallel; they cannot independently advance,
restore or type into the same session. The
[progressive scene workflow](SCENE_STREAMING_WORKFLOW.md) and
[requirements-first recovery pass](SCENE_RECOVERY_FAST_PATH.md) describe the
semantic qualification work surrounding that controller.

## 7. Timing, completion and failure gates

Before comparing routes, define a common starting checkpoint and a common
finish condition. Account for any preparation after restore and record actual
start states and clock endpoints. Equal checkpoint hashes alone do not prove
equal timer or RNG phase at the timed start. Include stop-key consumption,
settling, transition initialization and required output acknowledgement in the
chosen boundary.

Report guest elapsed time separately from host elapsed time. State whether
checkpoint loading, warm-up, observation, video encoding, screenshot export and
cleanup are inside each interval. Prefer recorded host monotonic endpoints in
addition to the elapsed value, so an independent verifier can subtract them.
Do not add component times and assume they equal an outer measurement when
unmeasured gaps remain.

For an observed movement or assisted route, success requires the conjunction of
the declared operation result, complete observations, the correct destination,
retained landing after cleanup, settled actor/control state, drained input and
any required fresh scene evidence. An operation can modify state before failing.
Generic script completion is not a universal checker for every operation's
semantic success; inspect the relevant receipt fields explicitly.

Preserve unexpected breakpoints, watches, hooks, timeouts, missing captures and
unknown write outcomes as failures or incomplete results. A blocked attempt
that later arrives during cleanup stays blocked. Keep failed tuning attempts
beside successful trials, with their source/harness identities. Repeat trials
characterize variation; retrying until one passes does not clear the failure.

An assisted route can fairly demonstrate a speedup within its declared
intervention category and matched boundary. It cannot claim an unassisted
record or full-game improvement from a single short room crossing. A full-game
comparison requires original interaction conditions and the actual ending
boundary, not only coordinate or room writes.

## 8. Smallest implementation path

| Stage | Reuse or add | Acceptance gate |
| --- | --- | --- |
| Bounded analysis harness | Reuse scripts, waits, movement, checkpoints, experiments and retained artifacts; add only a manifest/orchestrator where the investigation needs it | One short interaction repeats, failure receipts survive, input is drained, and a closed-project verifier checks identities and referenced artifacts. |
| Recorded-frame audit (implemented) | Reuse `capture-audit` on finalized native AVI segments before pixel analysis | Independent decoding, every-frame hashes, timestamp provenance, corruption/budget failures and sampling invariance are checked. A successful video audit does not certify guest timing or game completion. |
| Reliable capture | Correct and independently test the agent snapshot path; keep native video as an independent observation; add an explicitly versioned synchronization sidecar | Changed and unchanged frames, restore, mode changes, capture failure and slow processing are characterized. No stale snapshot is counted as an unseen frame. |
| Exact input replay | Add a native guest-clock physical-edge scheduler and an importer for one pinned movie format/profile | Preserve timestamp precision and simultaneous-event order, physical key identity, make/break polarity and final held state; record requested and actual delivery deadlines. Reject unsupported precision or mapping before execution. |
| Reusable analysis tools | Add checkpoint branch manifests, failure-signature minimization and targeted coverage selection | A reduced failure reproduces for the same reason; an assisted branch cannot be reported as ordinary input; unknown coverage remains explicit. |
| Semantic regression fixtures | Bind one route's native state/events to an existing UIL/UDL interaction and its independent reference | Conditions, ordered state/output effects and completion/turn behavior agree in the declared domain; unsupported behavior stays IR. |

For exact replay, scheduling must happen against the guest's native clock, not
a series of host sleeps or rounded `run(guest_ms=...)` calls. The first format
adapter must state its hardware/emulator assumptions and key mapping. It must
refuse an input interval that the backend cannot represent instead of rounding
sub-millisecond edges into the existing millisecond press API. Actual delivery
and late/drop behavior need native receipts; nominal deadlines alone are not
verification.

Checkpoint policy also needs an explicit decision: stop only at drained-input
boundaries, as today, or add fully serialized replay-scheduler state with a
verified restore contract. A new scheduler must not silently reuse today's
input cancellation behavior and claim uninterrupted movie replay.

The useful first deliverable is a reliable short investigation route with
auditable state and timing, followed by the smallest native additions needed
for exact input and frame correspondence. Every later scene or semantic
interaction can reuse those contracts without claiming complete game recovery.
