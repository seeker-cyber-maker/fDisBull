# Dune: continued play and agent workload

Measured 18 November 2026 (America/New_York; raw receipts use UTC).

**Continuation:** [Sparse observations and bounded native waits](DUNE_OPTIMIZATION.md)
implements the overhead reductions identified here, records paired measurements
on a rebuilt DotBox native backend, and saves a later checkpoint after meeting
Gurney. The measurements and limitations below retain this earlier run's scope.

This continuation asks which work belongs in a deterministic tool and which
still needs Dot's interpretation. It uses the same supplied English DOS RIP
edition and retained Linux native backend as [the Dune probe batch](DUNE_BATCH_PROBE.md).
The game remains authoritative; ordinary mouse inputs perform the playthrough.
No game variable, handler address, save file or register is patched to advance it.

## Observed progression

From the opening throne room, the run heard Leto's instructions, crossed the
palace, took an ornithopter, selected Carthag-Harg, used the game's own travel
shortcut, entered its sietch and recruited the Fremen troop. Recruitment replaced
the work request with the troop-orders command. The run opened the strategic
map and occupation menu, assigned spice work, then asked for troop information.
The visible information panel reported that the troop was doing spice mining.
This establishes recruitment and the accepted activity, not a measured quantity
of harvested spice or a qualified simulation of the strategic economy.

The instructions also named Gurney as a contact among the nearby Fremen. That
is a goal for continued exploration, not evidence that this run has met him.

## Measured reduction

One bounded request to hear the chief's remaining information performed **five
ordinary conversation actions in 2.119 seconds**, advancing **1,641 guest
milliseconds**. It collected four new pages and stopped when the fifth action
closed the conversation. The declared maximum was six actions; no sixth click
was sent. No model decision occurred between those actions. The initial
input-readiness qualification took a separate **90.785 milliseconds**.

The pages described troop statistics, a game-reported production estimate,
poor local spice and nearby Harkonnens. The estimate was 2 kg/hour; this is
dialogue evidence, not an independently measured production delta.

| Measured operation | Host duration | Guest advancement | Native RPCs |
| --- | ---: | ---: | ---: |
| Earlier fixed-wait helper, median of 16 short actions | 0.835 s | About 1,800 ms per action | 173 median |
| Controlled troop-information page | 0.272 s | 100 ms | 81 |
| Controlled close of troop orders | 1.544 s | 1,427 ms | 257 |
| Controlled conversation entry | 1.303 s | 1,213 ms | 227 |
| One bounded five-action conversation | 2.119 s | 1,641 ms total | 515 total |

These are different operations, not a controlled A/B speedup measurement.
The new controller removes the guessed fixed wait and model polling. Animated
transitions can still cost more host time and RPCs than the earlier fast-forward
helper. Each measured controlled action read 1,572,879 bytes; the five-action
macro read 7,864,395 bytes. Frame-by-frame RPCs and broad memory snapshots are
the next measurable costs to reduce.

The [sanitized receipt](evidence/dune-progress-2026-11-18.json) records the 17
measured manual-helper actions, three individual controlled actions, final
conversation batch, source hashes, failures and evidence limits. The complete
gameplay-and-tool-validation interval was **1,607.207 seconds** from the recorded
run start, including recovery diagnosis, source development and reviews. Some
initial interpretation and reads preceded that clock, and later packaging and
publication followed it. The 2.119-second warm batch is not a cold harness build.

## Work split

| Work | Existing native tools | What the agent supplied | Reusable reduction |
| --- | --- | --- | --- |
| Interpret the next objective | Frames, raw memory and controls | Read instructions and choose a goal | Return compact dialogue candidates and legal current choices; keep goal selection with Dot |
| Select a menu command | Original mouse input | Read labels, locate row, select coordinates | Resolve exact labels through the current menu and active rectangle records |
| Move through known rooms | Original input and bounded execution | Choose a direction and inspect each result | Reuse qualified direction controls with fresh context, while retaining observed room transitions |
| Choose a map destination | Mouse input and memory reads | Pick a visible map point and infer its identity | Decode rendered point records and site-name candidates, keeping selection separate from arrival |
| Wait for travel or animation | Execution and frame stepping | Guess a wait, inspect again, avoid duplicate input | Observe the recurring input-loop boundary with an explicit timeout |
| Follow dialogue | Repeated ordinary clicks | Read, click, wait and compare each response | Bound a same-subject continuation by action count, time and no-progress witnesses |
| Verify a strategic order | New frames and state | Compare menu changes with the troop's information panel | Retain exact before/after evidence; do not equate a handler entry with a completed task |
| Recover a memory checkpoint | Native save/load | Diagnose rendering mismatch and choose a supported recovery path | Qualify restored rendering with a later visible action; initialization workaround retained separately from a native repair |

## New read-only observations

`scripts/experiments/dune_ui_reader.py` reads an already-frozen conventional
memory image. It performs no guest calls and needs only the Python standard
library. It resolves the active menu, row metadata, handlers, control rectangles,
label text, dialogue witnesses and bounded site/map candidates. It is bound to
the measured edition and observed data segment, not a universal Dune decoder.

The final expanded dialogue buffer is available in ordinary RAM. Reading it
avoids asking an image model to transcribe every line. Presentation is a separate
claim: the conversation and strategic-map text renderers have different state.
The buffer may retain an old line after its original text box closes, and the
strategic map may display a line without opening the conversation text box.
The reader preserves those distinctions rather than treating every readable
string as something being said now.

An exact UI-admission digest and a separate dialogue-progress digest serve
different purposes. A hover highlight does not create a new choice. Conversely,
the same row can acquire another label or handler when state changes. Dialogue
comparison ignores stale bytes following the terminator; it is evidence of
measured text/context change, not a complete plot-progress measure.

## Continued-control contract

`scripts/experiments/dune_progress.py` accepts the caller's already-owned,
session-bound native adapter. It does not launch a guest, choose a story goal,
take ownership, restore a checkpoint or call a model. It retains private
screenshots, RAM and action receipts outside both the repository and game mount.

The selected-control dispatch at `0824:D326` and recurring input-loop head at
`0824:D214` provide different evidence. Dispatch identifies the selected record
before its callback executes. The loop head says the original interface is
polling again; it does not prove every deferred world effect is complete.
`D209` is an initialization entry and is not the recurring boundary.

Admission must include current input-loop readiness, neutral input and fresh
observations. An active rectangle alone is insufficient. At the pre-call
dispatch stop, the selected row binding must be checked again: a stable record
address and stable row wrapper do not prevent a changed label or handler.
Unexpected stops and uncertain transport results are preserved. An incomplete
attempt is not automatically replayed.

The controller records underlying RPC counts, bytes read, completed guest frames
and host duration separately from agent selection requests. Moving a loop into
Python removes repeated model decisions but does not remove native execution
or evidence collection. Full conventional-RAM reads are deliberate research
overhead here; sparse reads are a possible later improvement after the readers'
dependencies are explicit.

The research API is a small composition over the existing native adapter:

```python
controller = ProgressController(
    call, describe, private_evidence_directory,
    session_id=owned_session_id, source_path=dune_executable,
)
ready = controller.await_ready(max_frames=1800, host_budget_ms=30000)
if ready["outcome"] == "input_boundary":
    result = controller.perform(
        ready["after"]["scene_token"], label="ASK FOR MORE INFORMATION"
    )

# Only in the observed conversation context, for an explicit intent to listen:
dialogue = continue_conversation(
    controller, controller.latest["scene_token"],
    max_actions=6, max_frames=720, host_budget_ms=15000,
)
```

The example operations require their corresponding current scene; they are not
a single generic route. Reuse the successful `after.scene_token` directly for
the next selected action in the same controller. `observe()` alone does not
authorize input. A replacement controller cannot silently inherit another
controller's stop: the first attempted source-upgrade handoff was correctly
refused before advancement, and the owner explicitly reconciled the prior
successful loop boundary before the final live batch.

The controller, reader and existing probe suites passed **72 authored tests**.
Independent review also ran four additional cases for unchanged dialogue and
changed current site, selected site or local location; each stopped after one
action. Review exposed and fixed the pre-call rebind and unsafe wait-resume
cases described above. The final source was then exercised in the live batch.

## Failures that changed the implementation

### A valid-looking menu during flight

After selecting a destination, the ornithopter takeoff animation still exposed
the old palace menu and active rectangles. An attempted palace command received
an input receipt but never reached the selected-control dispatch within its
120-frame bound. The script reported timeout and did not resend it. Later
ordinary execution showed the flight and its travel commands.

This is why observation and readiness must be separate. The destination click
had worked; repeating it or treating the retained menu as a new ready scene
would have confused an in-progress transition with failed navigation.

### Restored game state with broken graphics writes

Loading the old graphics checkpoint into a fresh process still in DOS text mode
restored the old throne image. Subsequent clicks advanced game RAM and dialogue,
and frame counters advanced, but the pixels remained the old throne image.
Two bounded probes preserved this mismatch before the run fell back to a fresh
original launch. The 180-second warm-recovery target was missed; the recorded
usable state arrived 419.777 seconds after the run-start record.

Inspection of the checkpoint and corresponding native source found unregistered
VGA handler IDs in the graphics aperture. Restore preserved the new process's
existing text-mode memory handlers there. Frame-cache invalidation and restored
VRAM alone therefore did not restore later guest graphics writes.

The narrow workaround was executed successfully: normally initialize Dune's
graphics in the destination process, load the old memory checkpoint, perform
the ordinary Leto interaction, and verify agreement between changed pixels and
game state. This qualifies that edition/backend path only. Rebuilding the VGA
memory handlers after state load, followed by a fresh-text-mode-to-graphics
restore-and-mutate regression, remains a native repair proposal.

The prior probe batch's CPU/RAM comparisons remain scoped as recorded. They
did not establish that later graphical writes work after every cross-process
restore. Memory rewind continues to preserve the current mounted files.

## What to optimize next

1. Return a compact changed-scene packet by default, with full evidence available
   on demand. Avoid retransmitting identical controls, stale dialogue and RAM.
2. Compile explicit short intentions into bounded operations: hear the current
   speaker, wait for arrival, or traverse a previously observed local route.
   Stop on a changed subject, unavailable action, repeated witness or timeout.
3. Reuse a qualified event-family adapter across its siblings. Keep scene- and
   state-dependent bindings fresh instead of investigating every button again.
4. Request background analysis only when a new observation breaks the current
   contract. An unknown map hit-test or text renderer is a bounded question;
   neither requires reconstructing the whole game before continuing.
5. Measure remaining polling and memory-read costs separately from model work.
   A larger tool that merely returns larger logs can still increase agent load.

## Qualification limits

This is an isolated continuation using DotBox's Python transport and the retained
fDisBull 0.34.1 native executable. It is not qualification of the current
DotBox-owned native build, the original-Dot ownership/takeover bridge, macOS,
arbitrary Dune editions, or a complete strategic simulation. The new source and
guide are packaged research resources; player-facing integration remains a
separate gate. Commercial assets, raw RAM and emulator checkpoints stay private.
