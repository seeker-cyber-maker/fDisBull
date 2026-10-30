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
    {"id": "finances", "command": "status park"},
    {"id": "inventory", "command": "inventory"}
]
batch = BatchSession(Player(backend), "/private/existing-folder/batch.json", plan)
result = batch.run()          # Stops at an accepted partial action or uncertainty.
result = batch.resume()       # A declared continuation, then remaining steps.
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

`resume()` never resends a paused step's original command. It observes the fresh
public context and may execute only the continuation explicitly declared for
that context. Each declared continuation command can run once per step. Its
result remains a separate attempt. `expect_context` is a goal: acknowledging a
notice on the street does not complete a goal requiring arrival in the park.
The plan must explicitly authorize any additional travel as a new intent.

`Player.execute_result(command)` exposes `status`, `complete`, `effects`,
`action_sent`, public text and optional provider continuation/session-handoff
details. A confirmed purchase with a failed follow-up retains
`effects: applied-confirmed` while the batch step remains unknown. A passive
read is distinguished from an unsupported command that sent no input.

## Command-line interface

Supply the normal provider selection together with `--batch-plan plan.json`
and `--batch-journal /private/existing-folder/batch.json`. Send JSON lines:

```json
{"op":"run","max_steps":1}
{"op":"resume"}
{"op":"checkpoint","name":"operating"}
{"op":"inspect"}
{"op":"recover","name":"operating"}
{"op":"run"}
```

The control replies are small; detailed attempts remain in the private journal.
EOF closes the provider normally. A completed process/cleanup receipt is separate
from a completed batch or confirmed action. Use `inspect` to retrieve step status
through Python; CLI inspection returns only the summary and journal location is
already caller-selected. Batch mode is separate from model-turn `--live` mode.

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
  Failed recovery blocks observation/action until a new native session is opened.
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
