# Execution-event searches and bounded trace-until

## Contents

- [Choose the question and window](#choose-the-question-and-window)
- [Capture a live window](#capture-a-live-window)
- [Define predicates and regions](#define-predicates-and-regions)
- [Join native source clocks](#join-native-source-clocks)
- [Query an existing trace](#query-an-existing-trace)
- [Narrow A against controls](#narrow-a-against-controls)
- [Follow the candidate and preserve scope](#follow-the-candidate-and-preserve-scope)

## Choose the question and window

Use this workflow to connect a declared action with candidate execution sites
or register values, or to stop at a specific observed instruction condition.
Start with the smallest discriminating question: repeated A versus idle,
A versus B, the same handler with a changed argument, or the first observed
boundary satisfying a bounded predicate.

Retrieve installed `methods` and `capabilities` before planning execution.
The initial live `debug-trace-until` backend is owned, stopped real-mode
DOSBox. Retrospective queries/searches also accept supported existing PE traces;
they do not add live Windows support. Source version, runtime code bytes,
CPU mode and qualified address context belong to each candidate's identity.

The native `qemu-dos` process adapter also supports initial real-mode COM/MZ
source boundaries. Its virtual profile adds clock-qualified source observations;
see [native QEMU migration](dos-qemu-migration.md#relate-source-boundaries-to-virtual-time)
for its distinct debugger-step and input contracts.

Reuse an existing named scene action or known input route to establish the
starting situation. Keep the action label, input receipt, observation window
and semantic outcome distinct. A queued click does not prove the game consumed
it. Use existing checkpoints for comparable starting states when appropriate;
restoring a machine does not restore mounted host files.

Use [DESQview and memory searching](desqview-and-memory-search.md) when the
unknown is a stored data value. Use execution events when the unknown is where
the program went or which register values it exposed at an instruction site.

## Capture a live window

The Python method is:

```python
captured = debug.trace_until(
    until,
    regions=None,
    max_steps=1000,
    timeout_ms=10000,
    name="trace-until.json",
    action=None,
    label="trial",
)
trace_id = captured["trace_artifact"]
```

`debug` is the existing owned session. `until` may be positional; all other
parameters are keyword-only. `max_steps` is 0–9,999, `timeout_ms` is 1–600,000,
and `label` is at most 128 characters. The initial observation plus the interval
budget fits at most 10,000 boundary observations in one retained trace. The
16 MiB artifact limit can end capture earlier; each stopped observation is also
bounded to 8 KiB.

For a retained `serve`/debug session, replace the run and all example addresses
with the caller's observed values:

```json
{"method":"debug-trace-until","params":{
  "run":"RUN",
  "until":{"kind":"pc-range","space":"project","start":"0x10180","end":"0x10190"},
  "action":{"op":"keyboard.press","key":"enter"},
  "max_steps":1000,"timeout_ms":5000,"name":"action-a.json","label":"A:1"
}}
```

The optional action allowlist is one `keyboard.press` or one `click`. Keyboard
keys use lowercase physical names such as `enter`, with optional `modifiers`,
`hold_ms` and `gap_ms`. A click
uses `x`, `y`, and optional `button`, `hold_ms`, `mode_id`, `frame_id` fields;
bind frame-sensitive coordinates to an actually observed frame when available.
This is input queueing, not arbitrary script or host-code execution.

For a mouse-triggered trial, replace `action` with a descriptor such as
`{"op":"click","x":160,"y":100,"button":"left","hold_ms":80}`. These are
illustrative coordinates; use the selected control's observed location and
frame identity in the actual experiment.

All options are checked before input or advancement. The runner checks the initial
boundary first. A true initial predicate returns zero steps and records
`action.dispatch='skipped_initial_match'`; no input is queued. Repeating the
same predicate at that stop can therefore return immediately again. Choose the
next boundary deliberately instead of assuming an implicit advance. An
unmatched initial observation with `max_steps=0` queues no input either.

Each advancing interval uses native `trace.start` with `instruction_count=2`,
followed by callback-safe `execution.continue`/`execution.wait`. One owned lock
and shared host deadline cover the operation. This uses DOSBox's existing
service-callback path and does not invoke the high-level `run` hook dispatcher.
The first native fetch must match the already-tested stopped PC, mode, full
register snapshot and code bytes. The second must match the new stopped PC,
mode, code and reconstructed general and segment registers before the runner
evaluates the next predicate. Raw second-fetch FLAGS are excluded from that
comparison because DOSBox can defer their materialization and omit a change
from the sparse trace. Live predicates instead use the full stopped
`state.get_registers` snapshot, marked `observation.flags_materialized=true`.

`steps` counts verified next-fetch intervals; `attempted_steps` can be greater
after an interrupted or unqualified attempt. `max_steps` bounds advancement,
not an architectural retired-instruction count. A successful matching
observation is the current **before-instruction** boundary. The aggregate
`trace` metadata and `trace_artifact` retain the window without a separate child
artifact per interval.

Interpret the outcome before issuing another action:

- `predicate`: a qualified current observation matched; the matching
  instruction remains unexecuted by this result.
- `step_budget`: the next-fetch interval budget ended without an established match.
- `timeout`: the shared host deadline ended the attempt.
- `foreign_stop`: another debugger stop won; preserve it for its owner.
- `unqualified_interval`: native fetch endpoints did not match the stopped
  snapshots; execution may have occurred, but `complete` and `exact_stop` remain false.
- `artifact_budget`: the evidence budget ended capture; the retained window is incomplete.
- `cancelled`: bounded cleanup and evidence retention ran, then the Python
  cancellation was re-raised with its `.result` attached.
- `exited` or `error`: inspect the guest stop, error and cleanup evidence.

An IRQ, NMI or context change before continuation can redirect the first native
fetch. The unexpected first instruction may already have executed when the
two-fetch interval stops and its endpoints are compared. In this case inspect
`native_interval` and `current_stop`; do not claim the first match was caught,
assume the earlier predicate was evaluated in the intervening context, or
report a rewind. The runner makes none of those claims and returns an incomplete
`unqualified_interval` result.

Existing execution breakpoints guard the initial and subsequent boundaries
before predicates or further execution. Native foreign stops also win. The
runner does not delete controls or dispatch host hook actions; a native hit
retains the backend's reported breakpoint semantics. Active native CPU traces,
armed data/watchpoints and active execution-byte layers refuse before
input/execution. Inspect returned action evidence after a failure; never
automatically repeat uncertain input.

### Use a bounded script route

`trace-until` is also a declarative script operation:

```json
{"format":"fdisbull-script-1","steps":[
  {"op":"trace-until","until":{"kind":"register","register":"ax","equals":7},
   "max_steps":100,"timeout_ms":5000,"label":"argument check","as":"found"},
  {"op":"registers"}
]}
```

Every trace-until parameter must be literal. `$result` references are rejected
even in labels, filenames and nested region names/IDs during whole-script
preflight, before an earlier operation can mutate the guest. A result alias such
as `found` remains available to later operations. The script advances past this
step only when `complete`, `matched` and `exact_stop` are all true; a budget,
foreign stop or unqualified interval prevents the following operation.

On route failure, conclusive `not_requested`, `not_dispatched` or
`skipped_initial_match` receipts preserve the stopped guest unless earlier route
input still requires cleanup. Queued or uncertain mouse/keyboard input triggers
terminal cleanup. If trace or journal persistence fails, inspect
`ExecutionTraceError.result`; JSON exposes the retained evidence under
`error.result`, and script failure records preserve it. Evidence failure must
not become an automatic retry of the input.

## Define predicates and regions

The same predicate vocabulary applies to live capture and retrospective trace
queries. A value can be an unsigned integer or an explicit hexadecimal string.
Register comparisons use the width of the named register; `ax` and `eax` are
different selections. Missing observations remain unknown.

| Question | Predicate |
| --- | --- |
| AX equals 1 | `{"kind":"register","register":"ax","equals":1}` |
| Masked EAX differs | `{"kind":"register","register":"eax","not_equals":0,"mask":"0xff"}` |
| One of selected registers equals 42 | `{"kind":"any-register","registers":["eax","ebx","ecx"],"equals":42}` |
| PC enters a project range | `{"kind":"pc-range","space":"project","start":"0x10120","end":"0x10140"}` |
| PC enters a runtime linear range | `{"kind":"pc-range","space":"linear","start":"0x30120","end":"0x30140"}` |
| PC enters an explicit segment range | `{"kind":"pc-range","space":"segmented","segment":"0x3000","start":"0x120","end":"0x140"}` |
| Leave the initial logical region | `{"kind":"region-change"}` |
| Encounter a string move | `{"kind":"mnemonic","equals":"movsb"}` |
| Observe a non-fallthrough transfer | `{"kind":"nonsequential"}` |

Single-register comparisons also support `lt`, `le`, `gt` and `ge`; choose one
comparison operator. A mask applies to the observed value before comparison.
Explicit register lists contain 1–32 distinct names. `all` and `any` contain
predicate arrays, with at most 64 nodes and depth eight:

```json
{"all":[
  {"kind":"pc-range","space":"project","start":"0x10120","end":"0x10140"},
  {"any":[
    {"kind":"register","register":"ax","equals":1},
    {"kind":"register","register":"ax","equals":2}
  ]}
]}
```

PC ranges are half-open. Project addresses require a qualified source mapping;
linear addresses describe the observed runtime space; segmented ranges require
the explicit segment. Protected/v86 historical observations with unknown source
mapping remain unknown for project-address predicates. Do not use
`selector * 16` to manufacture a protected-mode source address.

Mnemonic predicates decode the observed bytes and compare the canonical
operation, preserving prefixes without treating `rep` as the mnemonic.
`nonsequential` requires contiguous same-context observations and a decoded
preceding instruction. The first event, a trace gap or a context change cannot
establish it. A jump, return or interrupt transfer is not by itself a function
boundary or an unpacked original entry point.

For `region-change`, define useful logical regions when the image's default
region is too broad. DOS COM/MZ commonly has one `loaded_image`; it is not a
catalog of logical handlers. For example:

```json
[
  {"id":"menu","name":"menu dispatch","space":"project","start":"0x10100","end":"0x10200"},
  {"id":"handler","name":"selected handler","space":"project","start":"0x10200","end":"0x10300"}
]
```

Pass this array as `regions` to capture, query or search start. Up to 64
regions in `project` or `linear` space are allowed; ranges in the same address
space cannot overlap. The
optional `name` is display text. Identity is the stable `id`, address space
and numerical bounds. A region change compares the event with the initial
event's region; an unmapped endpoint is unknown. Search refinement retains the
original region definitions.

## Join native source clocks

The optional `virtual-time-range` predicate has exact fields `kind`, `run`,
`epoch`, `native_epoch`, `start_ns` and `end_ns`. Its integer interval is
half-open, with `0 <= start_ns < end_ns <= 2**63`. Obtain the run, 32-hex host
epoch and positive native epoch from the same session's `clock_observe()`;
the native epoch is `virtual_clock.native.epoch`. This predicate is admitted
live only by the initial native DOS process adapter under its explicit virtual
profile, and can be combined with other predicates through `all` / `any`.

Qualified event rows and search samples retain a `fdisbull-source-clock-1`
object with native nanoseconds, a separate instruction counter and unchanged
before/after samples around the full stopped source read. A count trace's
final `endpoint_clock` is returned separately by the query API. It does not
add an event, match or candidate beyond the trace's N preceding snapshots.
Candidate source-site keys remain independent of clocks.

Missing clock evidence or another run/epoch is unknown offline. Malformed
clocks reject the artifact regardless of the chosen predicate. Live requests
check every nested clock leaf before stepping; saved scripts check literal
identities before earlier writes, then recheck at trace admission. `$` result
references inside trace-until parameters remain unsupported. Clockless
historical traces and search artifacts remain readable.

A time predicate can match an observed unbound final boundary; its source site
remains unknown and `source_window_closed=False` prevents search narrowing.
A future interval may also be skipped between debugger stops. This predicate
does not install a timer cutoff. Use finite `max_steps` and `timeout_ms`.

Within one run and both epochs, these observations can be ordered with input
dispatch or media publication receipts. Equal timestamps do not identify
callback order. Temporal joins do not prove input consumption, input causation,
completed guest frames or natural instruction latency; the observed IRQ/timer
stepping policy still applies. No automatic synchronization is introduced.

## Query an existing trace

This operation is offline and does not resume a guest:

```json
{"method":"event-trace-query","params":{
  "project":"/private/game.fdb","trace":"TRACE_A1",
  "predicate":{"kind":"any-register","registers":["eax","ebx","ecx"],"equals":42},
  "offset":0,"limit":32
}}
```

The Python equivalent is
`project.event_trace_query(trace, predicate=predicate, regions=None, offset=0, limit=64)`.
Query pages allow 1–256 rows. Inspect `matched_count`, `unknown_count`,
`unknown_examples`, `rows`, `next_offset` and `window.closed`; query `complete`
describes that window. Sparse DOS register updates
are reconstructed within their qualified context; unobserved values are not
invented. Historical DOS sparse FLAGS remain unknown without
`observation.flags_materialized=true`; carrying an earlier FLAGS value forward
would conceal deferred flag updates. PE full-register observations retain
their existing contract. A match in a historical trace does not establish that
the live guest is still at that boundary.

Existing DOS traces can end with a pending fetch rather than a completed
instruction. PE native traces may use confirmed completed-step semantics.
Retain those observation contracts and code bytes when describing a result.
Do not equate trace row counts with completed instructions across backends.

## Narrow A against controls

Capture A at least twice, plus an idle window and a contrasting B window when
useful. Close each at a declared bounded condition. Search start/refinement
require `window.closed=true`; sequence gaps prevent closure. Retrospective
queries remain available for incomplete windows. Preserve early timeouts or
foreign stops as incomplete action observations rather than pretending they
covered the intended route. Even a closed instruction window does not prove
the whole action completed.

Start with instruction sites:

```json
{"method":"event-search-start","params":{
  "project":"/private/game.fdb","trace":"TRACE_A1","feature":"site","label":"A:1"
}}
```

The returned `artifact` is the immutable search ID. Refine it with the second A
window, then remove sites observed during idle and B:

```json
{"method":"event-search-refine","params":{
  "project":"/private/game.fdb","search":"SEARCH_1","trace":"TRACE_A2","mode":"retain","label":"A:2"
}}
{"method":"event-search-refine","params":{
  "project":"/private/game.fdb","search":"SEARCH_2","trace":"TRACE_IDLE","mode":"exclude","label":"idle"
}}
{"method":"event-search-refine","params":{
  "project":"/private/game.fdb","search":"SEARCH_3","trace":"TRACE_B1","mode":"exclude","label":"B:1"
}}
{"method":"event-search-results","params":{
  "project":"/private/game.fdb","search":"SEARCH_4","offset":0,"limit":32
}}
```

Always feed the new returned `artifact` to the next refinement. `results`
returns a bounded preview at creation/refinement; `event-search-results`
provides pagination and names its source as `search_artifact`. The old states
remain available after refinement and project reopen. Neither operation
executes the target or changes its bytes.

Searches are bounded to 32,768 candidates, 128 trials and 10,000 retained
witness samples, with at most eight samples per candidate. Result pages accept
1–4,096 rows; use `next_offset` rather than repeatedly requesting the first
page. Each retained trace/search artifact is limited to 16 MiB. Budget exhaustion
is a refusal, not an undocumented truncated candidate set.

The Python methods are:

```python
search = project.event_search_start(
    trace_a1, feature="site", registers=None,
    predicate=None, label="A:1", regions=None,
)
narrowed = project.event_search_refine(
    search["artifact"], trace_a2, mode="retain", predicate=None, label="A:2",
)
page = project.event_search_results(narrowed["artifact"], offset=0, limit=64)
```

`retain` keeps only existing candidates observed in the new filtered window.
`exclude` removes those observed there. Candidates cannot be reintroduced by a
later refinement. Source/version, observed instruction bytes, mode and
qualified address are retained; byte changes at a reused address cannot
silently become the same instruction identity.

For one shared handler with different argument values, use a separate search:

```json
{"method":"event-search-start","params":{
  "project":"/private/game.fdb","trace":"TRACE_A1",
  "feature":"register-value","registers":["eax"],"label":"A:argument"
}}
```

Now the candidate is a site/register/value combination. If EAX is 1 for A and
2 for B at the same site, excluding B's observed combination can preserve A's
candidate. Site-only subtraction would remove the shared site. Choose the
feature and register list at start; refinement does not change them. Optional
predicates filter each window before extracting its features.

## Follow the candidate and preserve scope

Inspect the candidate's original events, instruction bytes, context and
registers. Use qualified source breakpoints or a short additional trace to
separate input dispatch, guard evaluation, state write and visible outcome.
Keep unsupported mapping or missing registers unknown. A positive observation
is stronger than a non-hit, and every non-hit is limited to its declared
bounded window. Do not label a routine dead, unused, causal or a complete
handler from set subtraction alone.

The maintained !82 workflow separately defines flat32 E8 native-call capture,
serializer candidates and record frontiers. Feed qualified candidate callsites
and trace references into those existing contracts when that workflow is
available. General DOS16 discovery does not establish a flat32 call ABI and
does not require importing that MR or introducing another call-contract schema.

The supplied EPF `strings.cpp` source, SHA-256
`7e077f1b64e7480298c1c75e7884e62a2c18eaffe3a61ccbc4f32c3be3ab9117`,
informed the stop-condition comparison. Its PE-only IDA step callback uses
segment names, inclusive EIP bounds and literal mnemonic/register matches;
it lacks bounded action comparisons and trustworthy missing-register/thread
handling. This implementation retains explicit evidence and budgets and does
not redistribute EPF code or claim live IDA qualification.

Return artifact IDs, the declared action/window, outcome, bounded candidate
pages and the next discriminating observation. Keep originals, raw traces and
byte-containing project stores private. Publish authored findings and sanitized
receipts separately from target payloads.
