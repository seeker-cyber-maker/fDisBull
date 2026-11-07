# Execution-event searches

Execution-event searches help answer questions such as “which instructions do
these two actions share?”, “which sites appear during A but also during idle?”,
and “does the same handler receive a different register value for B?” A bounded
live runner can also stop when a declared instruction or register condition is
observed. The result is a smaller set of candidates to investigate, with the
original traces retained as evidence.

Use the installed guide for the complete Python/JSON workflow:

```sh
fdisbull agent-skill --reference references/execution-event-search.md
```

## Choose the observation

| Surface | Use it for | Result boundary |
| --- | --- | --- |
| `debug-trace-until` / `DebugSession.trace_until()` | Run an owned guest until a predicate, interval budget, deadline or foreign stop | A successful match identifies the current before-instruction boundary; interrupted or unqualified intervals do not establish an exact match |
| `event-trace-query` / `Project.event_trace_query()` | Find predicate matches in a stored trace | Retrospective observations; no guest execution |
| `event-search-start/refine/results` | Intersect or subtract observed execution sites or site/register/value combinations | Persistent candidates within the supplied windows; no automatic function, cause or entry-point proof |

The first live implementation admits stopped **real-mode DOSBox** sessions.
Offline analysis can consume supported existing DOS and PE trace artifacts;
that does not qualify live Windows tracing. Protected/v86 observations retain
their recorded mode, and an unqualified selector is never converted into a DOS
paragraph address.

## Stop at an observed boundary

The example assumes `debug` is the caller's already owned, stopped DOSBox
session. The address range is illustrative: replace it with a qualified range
in that project's address space and choose an input appropriate to the target.

```python
captured = debug.trace_until(
    {"kind": "pc-range", "space": "project",
     "start": "0x10180", "end": "0x10190"},
    action={"op": "keyboard.press", "key": "enter"},
    max_steps=1000,
    timeout_ms=5000,
    name="action-a.json",
    label="A:1",
)
trace_a1 = captured["trace_artifact"]
```

`until` may be positional or a keyword. The other parameters are keyword-only:
`regions=None`, `max_steps=1000`, `timeout_ms=10000`,
`name='trace-until.json'`, `action=None`, and `label='trial'`.
The `max_steps` budget is 0–9,999, allowing the initial observation plus at most
9,999 verified later boundaries. The host deadline is 1–600,000 ms. Labels are at most 128
characters. One aggregate trace artifact records the bounded window; the runner
does not create a separate trace artifact for every interval. The artifact is
bounded to 16 MiB, so its byte budget can end capture before the interval budget.

An optional action is one queued DOS `click` or `keyboard.press`. All inputs
are validated before dispatch. A qualified initial match returns zero steps,
records `action.dispatch='skipped_initial_match'`, and queues no input.
An unmatched initial observation with `max_steps=0` also queues no input.
An accepted input is evidence of queueing, separate from guest consumption or
the intended application outcome. An uncertain input must not be retried
automatically.

| Outcome | Meaning |
| --- | --- |
| `predicate` | The current qualified boundary satisfies the condition. Inspect it before deciding to execute it. |
| `step_budget` | The allowed next-fetch intervals are exhausted; no matching boundary was established. |
| `timeout` | The shared host deadline ended the attempt. |
| `foreign_stop` | An unrelated debugger stop takes precedence over the predicate and further execution. |
| `unqualified_interval` | Native fetch evidence differs from the stopped endpoints. Execution may have occurred, but no exact match or complete window is claimed. |
| `artifact_budget` | Capture stopped before exceeding its retained-evidence budget; the window is incomplete. |
| `cancelled` | Cancellation triggered bounded cleanup and evidence retention; the Python cancellation is then re-raised with its result attached. |
| `exited` / `error` | The guest exited or an operation failed. Inspect the stop, cleanup and error evidence before proceeding. |

Advancement uses the existing native `trace.start(instruction_count=2)` and
`execution.continue`/`execution.wait` path under one owner lock and shared
deadline. This path preserves DOSBox service-callback dispatch without invoking
the high-level `run` hook dispatcher. The first native fetch must agree with the
already-tested stopped PC, mode, full register snapshot and code bytes; the
second must agree with the new stopped PC, mode, code and reconstructed general
and segment registers. Raw second-fetch FLAGS are excluded from that comparison:
DOSBox can defer their materialization and omit a change from its sparse trace.
Live predicates use the full stopped `state.get_registers` observation, marked
`observation.flags_materialized=true`. Historical DOS sparse FLAGS remain
unknown without that marker. `steps` counts intervals that pass the endpoint
checks; `attempted_steps` can be greater when an attempt fails or is interrupted.
Neither count proves architectural instruction retirement.

There is an asynchronous boundary limit: an IRQ, NMI or context change between
the stopped snapshot and continuation can redirect the first native fetch.
By the time the mismatch is detected, that unexpected instruction may already
have executed. The runner reports `unqualified_interval`, keeps `complete` and
`exact_stop` false, and retains the native endpoint evidence in
`result.native_interval`. It does not claim an exact first match or rewind the
guest.

Armed execution breakpoints guard the initial and subsequent boundaries before
predicate evaluation or further execution. Native foreign stops are also
honored. The runner does not delete those controls or dispatch their host hook
actions; inspect the backend's reported state for a native breakpoint hit.
An active native CPU trace, armed data/watchpoints or active execution-byte
layers are refused before input or execution.

In a debugger script, `trace-until` accepts literal descriptors only, including
labels, filenames and region identifiers; `$result` references in its parameters
are rejected during whole-script preflight. A following operation runs only
when the result has `complete`, `matched` and `exact_stop` all true. A failed
route preserves the stopped guest when no input was dispatched and no earlier
route input still requires cleanup. Possibly queued input receives terminal
cleanup. Persistence failures retain the result in
`ExecutionTraceError.result`, exposed as `error.result` by the JSON interface.

## Predicates and address regions

Predicates include register comparisons, any-of-an-explicit-register-list
equality, PC ranges, region changes, decoded mnemonics and nonsequential
transfers. Compose them with bounded `all` and `any` arrays. For example:

```json
{"all":[
  {"kind":"pc-range","space":"project","start":"0x10120","end":"0x10140"},
  {"kind":"register","register":"ax","equals":1}
]}
```

Ranges are half-open: the start is included and the end excluded. Register
comparisons are unsigned at the named register's width, with optional masks.
Missing register or mapping evidence is unknown, not zero or a false match.
DOS sparse register updates are reconstructed within their qualified trace
context. Mnemonics come from the observed instruction bytes; `movsb` can match
a prefixed string instruction without confusing `rep` with its operation.

`region-change` compares against the initial observed numerical region identity.
For DOS COM/MZ images, a single `loaded_image` region is often too coarse to
answer a control-flow question. Supply explicit logical ranges when needed:

```python
regions = [
    {"id": "menu", "name": "menu dispatch", "space": "project",
     "start": "0x10100", "end": "0x10200"},
    {"id": "action", "name": "action body", "space": "project",
     "start": "0x10200", "end": "0x10300"},
]
```

Names are display labels. Identity includes the region ID, address space and
bounds; equal names do not establish equal regions. `nonsequential` compares
contiguous same-context observations against the preceding instruction's
decoded fallthrough. A gap, unknown decode or context change remains unknown.
A nonsequential transfer alone does not identify a function or an unpacker's
original entry point.

## Narrow repeated actions

Capture comparable, bounded windows for A twice, an idle control, and B. Use
the same qualified starting situation where practical; retain the checkpoint,
input and observed-outcome evidence separately. These identifiers are existing
trace artifacts in one private project:

```python
from fdisbull.project import Project

with Project("/private/game.fdb") as project:
    search = project.event_search_start(
        "TRACE_A1", feature="site", label="A:1"
    )
    for trace, mode, label in [
        ("TRACE_A2", "retain", "A:2"),
        ("TRACE_IDLE", "exclude", "idle"),
        ("TRACE_B1", "exclude", "B:1"),
    ]:
        search = project.event_search_refine(
            search["artifact"], trace, mode=mode, label=label
        )
    page = project.event_search_results(search["artifact"], offset=0, limit=32)
```

`retain` intersects the existing candidates with the new window; `exclude`
removes candidates observed there. Every refinement creates a new immutable
private search artifact, retaining the earlier state and trace references.
Results survive project reopen. Candidate identity includes qualified source,
version, code bytes, CPU mode and address context; a bare PC is insufficient.

For a shared handler receiving EAX=1 for A and EAX=2 for B, site subtraction
would discard the shared location. Start a separate search with
`feature='register-value', registers=['eax']` to distinguish the observed
site/register/value combinations. A start/refine `predicate` filters that
window's events before comparison. It does not alter an existing search's
feature or register selection.

Start and refinement require a closed, bounded trace window; retrospective
queries can still inspect incomplete evidence. Check the reported window
status rather than inferring completion from the number of rows. A candidate
absent from one trace is “not observed in that window,” not globally
unreachable. A timeout, foreign interruption or missing observation cannot
establish that a complete action lacked the candidate. Repeated controls reduce
noise; they do not independently prove semantic causation.

## Relationship to the supplied EPF plugin

The supplied `strings.cpp` snapshot, SHA-256
`7e077f1b64e7480298c1c75e7884e62a2c18eaffe3a61ccbc4f32c3be3ab9117`,
was reviewed as source. It implements a PE-only IDA step-trace callback with
tests for a changed starting segment name, an inclusive EIP interval, an exact
case-sensitive mnemonic, one register equality, or any-register equality over a
fixed nine-register set. Those are useful stopping ideas; they are not differential
action analysis or proof of an original entry point.

The source also shows relevant limits: segment comparison uses a 16-byte name
buffer; register-read success and event thread/phase are not checked; and the
any-register loop can toggle repeatedly when several registers match. It has
no bounded execution/evidence-receipt contract. fDisBull uses explicit numerical
regions, typed unknown-aware predicates, a single bounded stop result and
retained trace evidence. Its implementation is independently authored; the EPF
code and binary are not redistributed. No live IDA qualification is implied by
this source review.

## Integration and qualification

[MR !82](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/82)
owns the independent flat32 E8 call-capture, serializer-discovery and
record-frontier contracts. General DOS16 event searches can supply candidate
sites and evidence for that workflow after the required address, instruction
and ABI qualification. This feature adds no competing native-call schema and
has no hard dependency on that MR.

Existing scene/action receipts, normalized trace semantics and private artifact
storage remain the integration points. For data-value narrowing rather than
execution events, use [persistent memory searches](DESQVIEW_AND_MEMORY_SEARCH.md).
Raw captures and original program bytes remain private.

Qualification results must identify the exact source and backend. Authored
predicate fixtures, original-program observations and native backend tests have
different scopes; offline PE support does not establish a live Windows runner.
The authored native regression is `tests/test_execution_event_native.py`. Its
four cases cover stop-before-write predicates, region/branch/mnemonic boundaries
and hook precedence; repeated mouse A/A/B/idle trials and the shared handler's
AX value; BIOS keyboard status without fabricated input; and terminal DOS exit.
The qualified DOSBox executable has SHA-256
`795df754019b5e9876d68067cb8d91314b001f28c9c6964502dd57ef21adf79d`.
Exact-source test and package receipts accompany the integration MR. These
authored fixtures do not qualify an original game, QEMM/DESQview, or live PE.
