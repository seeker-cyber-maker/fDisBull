# Z batch recovery and shared action continuations

`BatchSession` runs an ordered public Z command plan against a session-bound
provider. It retains per-step effects and makes interruption recovery explicit.
DinoPark's original-backed provider and the typed-IL example provider advertise
the required opaque `session_token` and certified live-checkpoint capability.
Existing `Player.execute` and `execute_structured` return formats are unchanged.

## Python interface

```python
from fdisbull_player import BatchSession, Player

plan = [
    {"id": "enter", "command": "go park", "expect_context": "park",
     "continuations": {
         "park-entry.parking-notice": "acknowledge notice",
         "park-entry.quarter-notice": "acknowledge notice"
     }},
    {"id": "finances", "command": "check status"},
    {"id": "inventory", "command": "inventory"}
]
batch = BatchSession(Player(backend), "/private/existing-folder/batch.json", plan)
result = batch.run()          # Stops at an accepted partial action or uncertainty.
result = batch.resume()       # Only a provider-authorized declared continuation.
batch.checkpoint("operating") # Only at a verified boundary.
# After further testing, explicitly return to that boundary:
batch.recover("operating")
batch.run()                  # New branch; superseded results remain in history.
```

`run(max_steps=N)` can return control at a completed step without closing the
guest. Reopening the same journal with a new `BatchSession` reads the fixed plan
and executes only pending steps in the same provider session. Changing the plan
or attaching a different native guest is refused. A verified public native-load
handoff can change the session token; prior live checkpoints then cease to apply.

`resume()` observes the fresh public context and may execute a continuation only
when the original provider result and the plan both name that context and exact
command. A plan alone does not certify that an action is safe. The player also
compares the resolved verb and stable target/item IDs against the original action
immediately before dispatch, refusing the same action even through an alias.
If the original action identity or provider authorization is unavailable, the
batch remains paused and sends no continuation. Each declared continuation
command can run once per step; its result remains a separate attempt.

A successful continuation or matching `expect_context` does not certify an
original action whose effects were partial or unknown. Such a step remains
paused or unknown, preserving its original result and preventing later batch
steps. The current providers do not issue an original-intent completion
certificate, so this batch interface cannot upgrade those partial outcomes;
inspect and reconcile them through the provider's qualified evidence. A
previously confirmed effect with a destination mismatch remains a separate
case. The plan must explicitly authorize any additional travel as a new intent.

Count continuations and superseded branches when applying an external benchmark
action budget. Serialize batches sharing a provider; a journal lock does not
make a shared backend connection safe for concurrent use.

Pause reasons distinguish `continuation-required` from `destination-mismatch`;
the latter can retain a confirmed effect even though the requested scene goal
was not met. An interrupted dispatch is `unknown`, never a pending notice.

`Player.execute_result(command)` exposes `status`, `complete`, `effects`,
`action_sent`, public text and optional provider continuation/session-handoff
details. A confirmed purchase with a failed follow-up retains
`effects: applied-confirmed` while the batch step remains unknown. A passive
read is distinguished from an unsupported command that sent no input.

## Read-only reconciliation after a readback error

`batch.reconcile()` reads the durable journal and one fresh provider observation.
It sends no action, checkpoint save/load, notice acknowledgment or execution-time
request. It can update local journal bookkeeping; "read-only" refers to the
original guest. It never executes later plan steps. Use a separate explicit
`run` or `resume` after inspecting the result.

Reconciliation requires an already durable, complete provider reply with a
`witness` containing exactly `session_token`, `context_id` and `context_token`.
The fresh qualified observation must match all three. DinoPark and the typed-IL
provider issue this witness after qualifying the resulting public context.
The state token prevents accepting an old reply after an intervening action,
even when the scene name is unchanged. Older providers/journals without a
witness remain conservatively unresolved.

- An action whose complete reply survived but whose following read failed can
  be classified from that reply. Its original effect and readback exception
  remain recorded. An accepted purchase with a pending notice becomes paused;
  an explicit authorized continuation is still required. Partial/unknown
  original effects cannot be promoted to confirmed completion.
- `recover` persists its returned provider certificate before the following
  observation. If only that read fails, reconciliation can finish the local
  rewind using the bound certificate, actual checkpoint handle and fresh
  qualified context. It does not load the checkpoint again. Superseded attempts
  and the original receipt are retained together in history.
- A completed restore can be verified again without adding history or loading
  again. This supports a caller whose own result reader failed after `recover`
  had already finished. `inspect(include_history=True)` exposes detached copies
  of history and the current recovery record; default inspection stays compact.
- A missing/lost reply, incomplete effect, unbound/stale witness, foreign guest
  or uncertified restore remains unresolved. Matching a destination alone is
  insufficient. A dead transport cannot be reconnected by this operation.

The return keeps the ordinary batch summary and adds `reconciliation`:

| Status | Meaning |
|---|---|
| `reconciled` | A bound durable reply repaired local action/restore bookkeeping. |
| `verified` | The already recorded restore still matches the current witness. |
| `unresolved` | Evidence is missing, incomplete, stale or unqualified; no repair. |
| `not-needed` | No eligible unresolved readback or current restore witness. |

`operation`, `reason`, and the applicable step/checkpoint identify the decision.
`not-needed` does not certify a caller-defined phase. Check `verified` for a
previous restore, or inspect the specific recorded attempt. Repeated calls do
not replay actions or duplicate restore history. The caller must serialize all
users of the same provider, including between reconciliation and later input.
Checkpoint-save failures and native-load session-handoff readbacks are not
reconciled; these retain their existing conservative recovery behavior.

## Command-line interface

Supply the normal provider selection together with `--batch-plan plan.json`
and `--batch-journal /private/existing-folder/batch.json`. Send JSON lines:

```json
{"op":"run","max_steps":1}
{"op":"resume"}
{"op":"checkpoint","name":"operating"}
{"op":"inspect"}
{"op":"inspect","include_history":true}
{"op":"recover","name":"operating"}
{"op":"reconcile"}
{"op":"run"}
```

The control replies are small; detailed attempts remain in the private journal.
EOF closes the provider normally. A completed process/cleanup receipt is separate
from a completed batch or confirmed action. Use `inspect` to retrieve step status
through Python; CLI inspection returns only the summary by default. Explicit
`include_history` can return private history/recovery data, bounded by the journal
size limit. The journal location is caller-selected. Batch mode is separate from
model-turn `--live` mode.

## Recovery guarantees and limits

- A private journal is atomically replaced, flushed and synchronized before
  every command dispatch. A filesystem lock serializes writers. A surviving
  `running` marker becomes `unknown` on reopen, even if input was never consumed.
- `unknown`, rejected and undeclared partial steps block later commands. A
  transport failure does not cause a replay. An interrupted restore latches the
  journal and cannot authorize more input.
- Recovery requires an explicit named checkpoint and a provider-certified
  restore. Superseded step attempts are retained in branch history. Commands
  after the checkpoint become pending only after successful recovery; `run`
  remains a separate explicit operation.
- DinoPark's checkpoint uses the existing native state artifact and its source,
  backend, register and mounted-file compatibility checks. Changed mounted files
  are refused. Restored native values must match all 20 saved ranges before
  presentation preparation. The provider then runs input-free 100 ms intervals,
  at most twelve, until the original frame and expected public scene qualify.
  An uncertified native recovery blocks observation/action. A successfully
  certified restore with only a failed client read can be reconciled as above.
- Preparation consumes simulation time. The field-equality proof is recorded
  before preparation; subsequent calendar/food/income changes are original game
  behavior. Recovery does not imply time or presentation equivalence.
- Live checkpoints belong to the surviving provider/native guest. A journal
  alone cannot resurrect a dead DOSBox process or reverse external effects.
  Native `save park`/named `load` remain the durable park-resumption mechanism.
  New native guests require a new batch or a verified native-load handoff.
- Limits: 128 plan steps, 16 attempts per step, eight declared context handlers
  per step, 32 checkpoints, 128 recovery-history entries, four MiB journal.

## Shared original-action continuation

`fdisbull.action_continuations.ActionContinuation` supplies one-shot input,
optional provider preparation, bounded destination observation and independent
effect confirmation. Its backing owns the actual original input, observations
and native effect predicates. Queued input, qualified arrival and confirmed
effect remain separate facts in the event record.

The DinoPark park/quarter and food-advice acknowledgments now use this common
implementation. One original acknowledgment is followed only by input-free
observation, up to twelve additional 500 ms guest intervals. Multiple recognized
destinations are ambiguous; an exhausted budget remains unqualified. Another
wait does not renew the budget. The backing confirms dismissal only after its
original scene assertion succeeds. Z consumes the resulting public action and
context; it does not implement game finances, feeding or travel effects.

This is a reusable execution seam for UDL backings. It does not establish
recovered semantic blocks, general game equivalence or automatic optimization
of animations and elapsed simulation time.
