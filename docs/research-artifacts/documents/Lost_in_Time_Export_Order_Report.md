# Lost in Time: joint versus staged representation exports

Experiment date: 29 October 2026. This is a measured local rebuild experiment,
not a measurement of an agent discovering unknown game logic.

## Result

No robust total-time winner was established on this small corpus. Completing one
representation at a time produced the lowest in-memory median, but paired
uncertainty intervals include zero. Joint export made the first Z action available
earlier; representation-first made the complete bounded outline available earlier.
A short shared-overview pass followed by end-to-end action slices is the practical
compromise to try for investigation. Its improvement to analyst reasoning remains
an untested hypothesis, not a result of the machine timing.

## Matched experiment

The inputs are the retained English Lost in Time hold/bilge recovery package.
Seven previously recovered executable branch models link to eleven source action
IDs. These are bounded branches, not seven rooms or a whole-game reconstruction.
The surrounding retained catalog has 51 action rules, 23 targets and 36 distinct
storage-field entries; it is not all implemented behavior.

For each branch the experiment actually generates six artifacts: an investigator
outline, UDL, UIL, an executable partial Z package, model-state HUD/agent JSON,
and source-derived harness target bindings. All 42 outputs are identical across
all schedules and handoff modes, including their source evidence and limitations.
They contain 307,935 bytes per run. No original game files or project databases
are modified.

The three schedules are:

- **Joint:** outline, UDL, UIL, Z, HUD and harness for one branch, then the next.
- **Staged:** every outline, then every UDL model, every UIL model, every Z
  package, every HUD and every harness binding. Each stage reuses prior results.
- **Hybrid:** every bounded outline first, then all remaining outputs per branch.

This is export scheduling on one worker, not parallel model workers. Both
primary approaches share the same source cache, reusable lowering implementation,
entry witnesses, schemas, output writes and final verification budget. Neither
is artificially made to redo reverse engineering. The bilge builder is factored
for on-demand branches; every result is checked against the retained model.

There are 21 paired repetitions for each of three schedules and two handoff
modes: 126 successful fresh-worker runs. Schedule execution order and branch
order are randomized deterministically; the same branch order is used for every
strategy within a repetition. Application caches are fresh; operating-system
page caches are not flushed. The JSON-handoff mode reopens exact intermediate
artifacts instead of retaining only in-process objects. Imports and interpreter
startup are excluded from internal timing and included in process-wall timing.
One earlier unlogged batch was terminated by a tool timeout; it contributed no
samples. The retained run log contains all 126 reported successful trials.

## Timings

Medians, milliseconds, with in-process handoff:

| Schedule | Complete bounded outline | First successful Z test action | All exports and final checks |
| --- | ---: | ---: | ---: |
| Joint | 59.0 | 18.0 | 157.4 |
| Staged | 13.0 | 31.7 | 141.3 |
| Hybrid | 14.0 | 21.6 | 165.4 |

The first Z time is a schema-valid model-backed action smoke pass, not completion
of the final exhaustive counter checks or a new native-game qualification.

The in-memory total-time interquartile ranges are joint 137.4–174.0 ms,
staged 131.2–161.1 ms and hybrid 140.8–176.3 ms. For staged minus joint,
the paired median total difference is -11.6 ms; a 10,000-resample percentile
bootstrap interval for the paired median is [-35.4, +2.1] ms. This is insufficient
to declare a reliable total-speed improvement. Conversely the paired first-Z
difference is +14.4 ms, with interval [+9.8, +20.2] ms: delaying executable work
until all earlier stages finish consistently delayed that milestone here.

With serialized JSON handoff, total medians are joint 157.0 ms, staged 163.0 ms,
and hybrid 169.7 ms. The ranking changes; total-time paired intervals again include
zero. Do not make a workflow policy out of the fastest isolated median.

Per run, the shared cache records 19 source reads, 9 JSON parses and 12 hashes.
These counters cover that cache, not every file operation: the retained poster
builder also performs the same direct source reads in every strategy. JSON
handoff adds 43 intermediate reads totaling 384,788 bytes. It does not redo source
lowering. Exporter-phase changes are 41 joint, 5 staged and 35 hybrid; these are
software scheduling counts, not measured human/agent cognitive costs.

## The larger picture must survive the representation

A separate executed test supplies two valid typed poster-model witnesses with
counter values -2 and 2. Their public Z observations are identical after removing
the opaque freshness token. The same inspect action then produces counters -1
and 3; the former hides the poster and the latter keeps it visible. Both actions
succeed. These are isolated model witnesses, not claims about ordinary original-
game reachability.

Consequently the public Z description is not a lossless intermediate source for
later behavior recovery. A private Z blueprint can still be useful if it retains
the typed source facts, guards, state and evidence. Reuse that investigation
knowledge rather than reconstructing rules from the player-facing narration.
The same distinction applies to a selected HUD snapshot versus a complete save.

The audit also found a concrete information-reuse issue in the existing packet
merge: equal-type fields sharing an offset use the first field description. The
bilge packet's generic poster-state label therefore hides the later hold packet's
more specific counter/removal-sentinel description in that merged field list.
This does not prove an existing executable-model bug; the poster model already
has the correct counter semantics. The new research catalog retains both
annotations and their packet provenance. Eight field entries have annotations
from both packets. These are pinned-profile/bank-local identities, not globally
interchangeable numeric addresses.

## Verification

All 126 retained trials passed the same checks: seven lowerings equal their
retained source-backed models, seven actual Z-player action invocations succeed,
seven HUD JSON round-trips preserve values, 256 poster counter cases and two
poster guard refusals pass. UDL-to-UIL remains a checked role metadata change,
not a separate semantic compiler. All schedules emit the same 42 file digests.

Additional audit: all 51 broad unresolved action descriptions still refuse with
no effects; seven harness artifacts explicitly retain unknown live readiness;
the public-Z information-loss probe passes. HUD values come from isolated UIL
witness execution, not new native memory captures. No graphics are invented or
presented as native screenshot evidence. No native walkthrough or save/reopen
was repeated. No whole-project pytest or CI result is claimed for this experiment.

Runtime: Python 3.13.5 and fDisBull 0.22.0 from the preserved offline kit. The
Z backend is exactly the PR #18 file at commit
`c107d1576d46d7dc353c8043cb81be5005e8926b`, Git blob
`9f349892065a6fd3e5ac026956899970d9fd3173`, loaded beside the installed runtime.
This is a pinned test combination, not a new installed fDisBull release. The
backend file was retrieved through the GitHub connector and its copied bytes
matched that blob because direct container network access was unavailable.

## Proposed workflow and follow-up requirements

Start with one compact private scene/dependency outline for the next useful
area. Preserve field meanings, types, aliases, sentinels, side effects, source
bindings and unresolved helpers in a shared record. Then complete one action
slice end-to-end and emit its supported Z, UDL, UIL, HUD and harness views.
Expand the outline as new facts arrive. Do not wait for the entire game to be
reconstructed in one representation, and do not maintain six independent
accounts of its behavior.

The exporter should support both action-major and representation-major schedules
from one dependency graph. Reuse decoded facts and qualified primitives in either
order. Persist that graph across agent handoffs. Preserve contextual annotations
rather than using first-description-wins merges. Keep public projections separate
from private recovery data. Invalidate only dependent outputs when facts change.

To test whether the *investigation* itself is faster, use unseen, matched scene
sets and isolated investigators with equal starting tools, prior knowledge,
information permissions and acceptance scope. Counterbalance order and include
guide reading, source interpretation, corrections, tool calls and token usage.
Measure first useful action, completed scope, contradictions, failed actions and
rework. Replaying this already-understood corpus cannot establish that result.

## Files

`results/benchmark.json` contains summaries and all timings; `results/runs.jsonl`
contains the append-only trial receipts. `results/audit.json` contains paired
comparisons and semantic probes. `results/shared_knowledge_catalog.json` is the
private source-fact catalog. `results/examples/joint/memory` contains one canonical
set of the 42 generated outputs. The other schedules emit identical bytes.
The retained archive's original scene scripts and game resources are prerequisites
for reproduction and are not duplicated in this experiment package.
