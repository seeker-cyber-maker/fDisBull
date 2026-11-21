# Recovery, rewind and saved-game evidence

Decision: 17 November 2026. Dot should recover from getting stuck, dying or
crashing a car, then continue the selected playthrough with what it learned.
**Revert restores emulator memory state. It does not roll back files on disk.**
This includes the machine/device state needed to resume coherently, not merely
selected game flags or CPU registers. Saves, autosaves, configuration, reports
and learned harness files retain their current disk versions.
This document specifies the next integration. **DotBox does not yet expose a
qualified player-facing checkpoint or rewind operation.** The offline state
store and persistent controls do not restore a running game.

When the player chooses recovery, or delegates retries within an autonomous
goal, a qualified implementation should proceed within that intent without
another technical approval prompt. The remaining gate is implementation and
qualification on original Dot, including its existing ownership flow.

## Choose the right recovery unit

| Unit | Meaning and intended use |
| --- | --- |
| Game-created save | The game's loader restores a semantic play position. Useful for durable progress and discovering important state. Loading can rebuild derived values and reset transient state; this is not an exact machine/frame rewind. |
| Full native checkpoint | Compatible in-memory machine/device state plus explicit input metadata. Useful before a risky interaction. Mounted host files retain their current disk versions. |
| Frame timeline | A bounded sequence of full native checkpoints at completed renderer frames followed by safe CPU boundaries. Useful for recovering before a collision and retaining a failed attempt for analysis. |
| CPU delta, instruction trace or scene-store copy | Partial evidence/model state. None establishes full machine, device, host-file or game recovery. |

Label a recovery point with evidence that it precedes the failure and permits
useful input. The newest frame may already be inside an unavoidable crash.
Preserve the failed attempt, its input receipts and observations as immutable
history. Learned controls and the reason to try a different route survive;
inventory, flags, position and readiness must be observed again after restore.

## Learn state from saves, one change at a time

Game saves are a strong source of state hypotheses: the game deliberately
preserves values needed later. They are not a complete description of every
live variable. A loader may reconstruct derived values, and saves may omit
pending input, animations, timers or device state.

1. Bind the executable, edition and selected resources. Establish an observed
   baseline, save through the game's existing qualified control, and retain a
   private frozen copy after the write completes.
   Retain a repeated baseline save without an intended game action as a control
   for timestamps, counters and other save-time changes. Observe any autonomous
   progression during that interval; "no input" does not mean frozen game state.
2. Perform one meaningful action, such as taking a key or opening a window.
   Observe its actual effect, save again, and retain a second frozen copy.
3. Record identities and inspect bounded, aligned windows. For example, with
   an actual executable and two distinct save basenames:

   ```sh
   dotbox inspect identity /private/frozen/GAME.EXE --resource /private/frozen/before.sav --resource /private/frozen/after.sav
   dotbox inspect diff /private/frozen/before.sav /private/frozen/after.sav --length 64 --limit 16
   ```

   Choose a window within both files. The diff requires equally sized windows;
   it reads two independent files and supplies no atomic capture or causal
   interpretation. Identity's resource fingerprint covers the explicitly named
   evidence set here; retain the game's edition/resource binding separately.
   Compare logical offsets only when the container/layout makes them comparable;
   changed compression or record order may require a format decoder first.
4. Correlate changes with engine-aware hints. For AGI, logic references to
   variables, flags, inventory objects and room transitions are more useful
   starting points than disassembling the whole interpreter. A static reference
   or changed byte remains a hypothesis, not a current flag observation.
5. Using a qualified recovery path in an isolated experiment, load each save
   through the real game loader and observe the reconstructed state. Repeat a
   small contrast when needed. Separate counters, checksums, compression and
   incidental changes from the candidate meaning before promoting a binding.

Use the existing [inspection implementation](../src/dotbox/inspection.py) and
[stateful scene contract](STATEFUL_SCENES.md). Save comparison does not require
complete game reconstruction. Keep commercial saves, snapshots and raw evidence
private; published fixtures must be authored and small. Worker experiments use
their own guests and mutable files, never the player's mounted directory.

## Invoke original Save/Load at a qualified entry

Once its contract is known, an original Save or Load operation can have a
programmatic invocation route alongside its menu route. Choose the cheapest
applicable qualified route for the task and retain the working input fallback.
Record the required caller preparation, slot/path arguments, current state,
effects and continuation using the [behavior and entry-point contract](BEHAVIOR_AND_ENTRY_POINTS.md).
Knowing a reader's address alone does not qualify a whole-game Load operation.

An original Save still writes the selected current game state to disk; an
original Load still reads the selected current file and reconstructs the game's
state. Bypassing menu navigation does not remove these intended effects or turn
either operation into memory-only rewind. Distinguish a low-level file transfer
from the encompassing loader, authoritative adoption, required initialization,
completed presentation and usable controls. Observe the boundary needed by the
consumer and retain partial successes or failures without automatically retrying.
The [XCOM reuse evidence](XCOM_REUSE.md) demonstrates why a working single-file
call cannot inherit a complete Save/Load claim from another prepared run.

The inspected fDisBull [direct native-call helper](https://github.com/seeker-cyber-maker/fDisBull/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/z_native.py)
requires a qualified flat32 near-return callee, argument contract and compatible
non-reentrant boundary. Its [captured-call helper](https://github.com/seeker-cyber-maker/fDisBull/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/z_call_contract.py)
can replay an observed original call in the same live owner, with a bounded
captured continuation. Both restore only their temporary execution machinery
while retaining the callee's game/file effects. Neither establishes arbitrary
scene entry, a general ABI, or full machine restoration. These are integration
references; DotBox has not added a public native Save/Load or rewind API here.

A helper may use qualified loaders or entry operations to construct a research
state beyond the player's current story progression, following the
[movement investigation stages](NAVIGATION.md). Keep imposed inventory, flags,
location and other prerequisites explicit, with scoped coherence checks and
remaining unknowns. Observe resulting effects in that helper's isolated branch;
do not merge its position, inventory or completion flags into player progress.
Any research save-file perturbation/restoration belongs to that separate
experiment, never to the player's memory-only revert transaction.

## Required restore transaction

The single live controller owns the complete operation, coordinated with the
supported outer Dot ownership flow. Background workers can suggest a recovery
point but cannot restore the player or publish their clone's facts as live.

1. **Preflight before effects.** Verify checkpoint bytes/hash, source, edition,
   selected immutable resources, emulator build and runtime profile/load identity.
   Check current ownership, expected generation and the stopped safe
   point. Resolve unsupported or incompatible state before loading anything.
2. **Fence old work at native admission.** On the emulation thread, validate
   the expected control generation and advance it before uncertain restore
   effects. Preserve the current owner rather than restoring an old owner or
   lease from a snapshot. Clean held/queued keyboard and mouse input, including
   pending host events. Outer action checks alone cannot make this atomic.
3. **Restore the declared memory scope.** Do not replace mounted files with
   earlier versions. Reconstruct frame-key state only
   under an explicit policy. Exact TAS playback may require the saved keys;
   interactive recovery should use a neutral checkpoint or release restored
   keys as a separately recorded input before continuing. Old steering must
   never resume silently. Ambiguous or partial restoration ends in an
   incomplete stopped/closed state, with no automatic replay or resume.
4. **Establish a fresh timeline.** Assign a new restore epoch, provider context
   and `branch_id`; create a new `SceneStore`. Invalidate old selection tokens,
   routes, coordinate observations, pending actions and worker candidates.
   Retain the earlier branch as history without copying its reports into
   current facts. A restore epoch complements input generation fencing.
5. **Verify, observe, continue.** Check the native register/input result and
   obtain a newly completed frame plus a coherent provider observation.
   Historical screenshots are not fresh restored observations. Reevaluate
   action readiness and the selected goal, then continue through the qualified
   controller with a revised route or action.

Do not use `state_revision` as the ownership epoch: it changes on ordinary
keyboard/mouse mutations, execution transitions and even `state.save`.
Doing so would invalidate normal turns. A restore-specific identity and a
native generation bump are required.

## Existing seams and the extraction boundary

The following fDisBull references are package-relative paths in the studied
**0.34.1** offline package. They describe reusable behavior, not a requirement
for users to install fDisBull or proof of DotBox runtime qualification.

| Source seam | Existing behavior / integration requirement |
| --- | --- |
| `fdisbull/debugger.py`: `DebugSession.save_state`, `_capture_native_checkpoint`, `load_state`, `_restore_native_checkpoint` | Full native bytes, hash/compatibility checks, bounded mounted-file manifest, input/register verification, runtime-binding invalidation and close on partial restore. `disk_restore=False`; changed mounted files are refused. |
| `fdisbull/debug_timeline.py`: `FrameTimelineSessionMixin.timeline_start`, `timeline_advance`, `timeline_rewind`, `timeline_pin` | Bounded RAM history, frame input edges, explicit branching and durable pinning. Delta retention still captures full native state at each point. |
| `fdisbull/player_checkpoints.py`: `save`, `load`; `debug_experiments.py`: `save_experiment`, `restore_experiment` | Durable private slots, provenance, projection/binding checks and incomplete-state handling; useful for durable player recovery. |
| `fdisbull/runtime_observations.py`: `_invalidate_runtime_bindings`; `text_projection.py`: `TextProjectionHandle._read` | A new `_runtime_epoch` invalidates prior runtime bindings and participates in projection freshness tokens. |
| [Native state RPC base](../native/dosbox-x/headless-agent.patch): `state.save`, `state.load` | Stopped-target serialization and frame-key sidecar exist. The base alone lacks a restore ownership fence; DotBox's overlay adds it. Raw load remains an incomplete recovery primitive. |
| [Native input control](../native/dotbox_input_control.h); [input patch](../native/input-control.patch) | `FenceRestore` requires the current expected generation, preserves owner and advances generation before cleanup/load effects. The separate `dotbox-restore-control-1` capability advertises this fence only. It does not assert neutral restored input or complete memory-only recovery. |
| [Native session](../src/dotbox/native_session.py), [backend](../src/dotbox/backend.py), [service](../src/dotbox/service.py), [client](../src/dotbox/client.py) | Existing transport, single backend owner and cooperative outer turn checks. No public recovery API; service bridge identity currently uses run/session/generation/owner. Wire successful and failed restore invalidation through these layers. |
| [Scene store](../src/dotbox/scene_state.py): `SceneStore` | Existing branch/context binding rejects mixed histories; a restore must create a new store. Persistence of this store or control recipes is not native checkpoint persistence. |

The smallest executable recovery slice is one explicitly captured, verified
full checkpoint and one fenced restore through the controller, with fresh
observation afterward. Qualify this before adding a rolling frame buffer.
Authored isolated native tests can verify mechanics; they cannot substitute
for the original-Dot desktop/ownership qualification.

### Implemented control fence, remaining recovery transaction

The `0.1.0.dev6` native source overlay makes `expected_generation` mandatory for
raw `state.load`. A missing/malformed generation is rejected at parsing; a stale
one is rejected on the emulation thread before input, target-identity, frame or
serializer mutation. Successful admission preserves the current owner and
advances generation once before uncertain effects. A successful reply contains
the new owner/generation and `input_reset:true`. `state.save` keeps its existing
contract and does not advance control generation.

An admitted failure cannot revive old generation-tagged input. This is only the
native control boundary: the Python service still exposes no checkpoint/revert
operation, and existing offline scene stores are not automatically rebound.
The later recovery controller must distinguish preflight rejection from an
admitted failure, close on an unverifiable partial load, create a fresh branch
and obtain coherent new observations before accepting another action. Never
automatically retry with a freshly queried generation.

The existing serializer can restore keyboard FIFO/typematic and mouse device
state after the pre-load reset. Therefore `input_reset:true` records cleanup,
not proof of a neutral restored machine. Interactive recovery needs neutral
capture and post-load verification; explicit TAS held-key restoration is a
different policy. Do not announce a `memory_checkpoint` capability from this
control-fence change alone. The [native protocol](../native/README.md) states the
raw RPC compatibility change and qualification boundary.

## Current disk versions survive revert

A checkpoint archive may itself be stored in a private file outside the mounted
game directory. Reading it into the emulator does not roll back the game
directory. DotBox must not take a matching filesystem snapshot or restore older
save, configuration or analysis-file contents as part of revert.

fDisBull's existing mounted-directory hash check refuses any changed file. That
historical restriction is not DotBox's desired contract. A changed, closed
autosave or new report alone must not block recovery. Bind selected immutable
executable/resource bytes and mount configuration separately from mutable saves,
even when they share a directory. An actual incompatible immutable dependency
remains a preflight refusal.

After recovery, the machine has returned to the checkpoint while external files
retain their current versions. A subsequent original game Load reads the current
save on disk. Save contrasts remain read-only research evidence, not rollback
instructions. Invalidate observations that assumed an earlier file version and
reobserve file-dependent behavior before describing it as current.

The bundled native `AGENT_StateFile` disables the serializer's historical file
backup/restore path. It still reconstructs DOS handles and saved seek positions.
Reopening a local file can flush a currently open writer to that file. Such a
flush persists current pending writes; it is not restoration of old file bytes.
Do not turn the user's no-rollback rule into a blanket prohibition on every
filesystem write, or claim that raw load leaves all bytes/timestamps untouched.

Qualify an explicit I/O boundary before exposing interactive recovery. A small
first scope can require no active writable DOS handles, pending writes or mutable
disk-image mounts at capture and restore. Closed saves may still differ freely.
An alternative may explicitly drain current writes before the safe point; it
needs its own evidence. Missing required saved-handle dependencies must be
reported instead of silently skipped or recreated from history. Do not omit
the DOS-files component while restoring guest handle tables: that would leave
guest and host handle state inconsistent. Normal writes after resumed play are
new game effects, separate from the restore operation.

## Bound capture cost

Bound retained frames, bytes, capture count, per-state size and wall time.
Measure pause, serialization, immutable-dependency checks, compression and fresh-frame costs
on the intended runtime. Delta storage reduces retained bytes, not necessarily
capture time. Select sparse useful checkpoints before promising continuous
rewind; ordinary movement must not be extended to hide capture work.

## Acceptance cases for implementation

The user's selected first live recovery trial is [missing Police Quest's first
briefing, then rewinding and attending it](POLICE_QUEST_ACCEPTANCE.md). The
inspected EGA edition has separate late-arrival and briefing-start mechanisms;
closing the newspaper accelerates the latter without resetting the former.
Bind the checkpoint to the actual predeadline guest clock, reproduce the late
outcome, restore memory while preserving a newer closed disk file, then observe
successful attendance. Static logic inspection has established candidate test
conditions, not a measured host duration or a passed rewind trial.

- Ordinary input advances state revisions without invalidating an unchanged
  ownership turn; a restore rejects all old-generation input and old choices.
- A held steering key cannot survive as an unowned or implicit resumed input.
  Explicit TAS restoration and neutral interactive recovery have tested receipts.
- Source/build/selected immutable-resource mismatch fails before native load;
  a changed, closed autosave does not. A partial/unknown load cannot be retried
  or resumed automatically.
- With no pending file writes, restore preserves newer mounted-file contents,
  including a file created after the checkpoint. A later game Load reads the
  newer save. No matching filesystem rollback is performed.
- Restoring after a simulated collision produces a new branch, fresh frame and
  verified playable state. The failed attempt remains immutable knowledge.
- Old inventory/door reports, routes and worker results cannot be presented as
  current; learned control recipes remain available after rechecking applicability.
- A save-file contrast yields only a candidate state meaning until real loader
  observations corroborate it. Derived and transient state remain distinguished.
- Capture/restore limits and measured latency cover the actual native path;
  authored offline checks and original-Dot integration results are reported
  separately. Recovery within an already selected intent needs no extra prompt.
