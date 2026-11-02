# KQ1 bow intent verification — 2026-10-30

This follow-up to the AGI scene census executes one bounded initial-audience
bow interaction through named UIL rules and an exact UDL mapping. It preserves
the full source census and the existing Zork conversion. The parent is census
PR #60, commit `759dcdbe10a5954b359b325c79f1da757b699125`.

The date is America/New_York; some private run timestamps fall on October 31
in UTC. The [interaction contract](KQ1_BOW_INTENT.md) states admission, effects,
output, host obligations and retained work. The machine-readable
[verification receipt](evidence/kq1-bow-2026-10-30/verification.json) contains
selected aggregate results and implementation hashes, without game bytes,
message text or native snapshots.

## Three distinct verification boundaries

| Boundary | What ran | What it establishes |
| --- | --- | --- |
| Source binding | Exact-resource producer and strict package validator | The definition, 18 source witnesses, UDL and retained census match this edition |
| Executed intent | Pure UIL evaluator plus UDL adapter versus independent raw-source slice execution | Ordered requests, complete declared carrier state and modal progression agree within the qualified dispatch segment |
| Original-game reference | Fresh original KQ1 execution, then higher-level evaluation against selected observed boundaries | Selected score, flag, position and output effects agree with original observations; the renderer and scheduler remain original |

The producer's `native_execution_verified: false` is deliberate: producing or
validating a package does not run the native engine. The separate verification
receipt records model execution and its comparisons with native observations.
Neither result claims all game intent or a complete game player.

## Source execution matrix

The verifier compares **7,490 source cases**: 7,040 command cases and 450
completion/command-tie cases. The command matrix varies 88 position pairs,
both recognized command forms, invisibility, visit/reward latches, and five
score values including wraparound boundaries. Completion cases check current
position restoration and refusals before completion, with visit/reward latches
and the completion flag already set. The command matrix covers first/repeated
respect. An authored pure-model test covers new admission clearing a stale
completion event; the strict source adapter instead declines a completion flag
without a qualified outstanding bow.

| Result | Count |
| --- | ---: |
| Dispatch or resumed segments compared | 14,640 |
| Original action requests compared | 29,000 |
| Modal acknowledgements compared | 7,150 |
| Explicit unsupported-context refusals | 11 |
| `court.begin_bow` executions | 640 |
| `court.award_first_respect` executions | 320 |
| `court.finish_bow` executions | 450 |
| Mismatches | 0 |

Every comparison includes the complete declared raw carrier, ordered requests
and pause/completion status. Caller inputs are checked for mutation. Clock
variable 11 advances between source and UIL acknowledgements on both sides;
the current clock survives while protected state remains bound. Authored
regressions separately exercise all four allowed clock fields and rejection
of changed score, position, scratch, parser, control and host data.

An independent review probe also sampled 792 states. Of these, 643 were admitted
to the declared boundary and 149 explicitly declined an unqualified completion
state. All 974 admitted dispatch/resumption segments matched full carrier,
ordered requests and status. This smaller probe did not advance the clock;
it supplements the larger matrix rather than broadening its scope.

The raw-source executor shares byte-boundary qualification through `agi_layout`
with the source tooling, while its control, predicate and effect semantics are
independent. It has no dependency on the intent producer/evaluator/adapter. Unsupported
executed operations and predicates fail explicitly. Condition zero,
high-bit conditional displacements and wildcard `said` remain unsupported in
this reference; the recovered bow closure does not use them. Existing census
and legacy inspector decoding were not changed to fit this executor.

## Fresh original execution

The original COM loader and game ran through the existing native backend.
The route reached rooms 1, 2, 55, 54 and 53 using original movement and the
original door command. There were no room, position, score or flag memory
writes. Opening the castle door earned one point before the audience.

| Native observation | Score | Actor baseline | Pose or response |
| --- | ---: | --- | --- |
| Far bow refusal | 1 | `(153, 120)` | Local message 14; no reward |
| Admitted initial bow | 4 | `(63, 110)` from `(70, 110)` | Bow view 71, loop 0, cel 0 |
| Final bow cel | 4 | `(63, 110)` | Cel 8; completion flag set |
| Completion response | 4 | `(70, 110)` | Normal view 0, loop 1, cel 0; message 4 |
| Acknowledged response | 4 | `(70, 110)` | Later normal animation sample at cel 1 |
| Completed repeat | 4 | `(70, 110)` | Message 55; no second reward |

The bow therefore adds **three**, not four, points. Its reward precedes its
response. The quest dialogue is a separate talk command. All bow cels 0–8
were sampled, and subsequent original movement demonstrated that control was
restored. That movement is behavioral evidence; the native player-control
memory field has not been bound.

The higher-level evaluator was executed against four native boundaries:
admission, completion, distant refusal and completed repeat. Admission and
completion use directly observed parser/completion flags. The other two start
from an earlier observed state and explicitly bridge ready/unconsumed input
for the typed command. They are not presented as exact captured dispatch-entry
states. The word groups are source-correlated with the original parsed buffer;
the general parser remains outside the model.

Each boundary was evaluated with both Boolean values for the unbound incoming
player-control field. Comparisons include variables 3, 6, 31, 60 and 61;
flags 4, 21, 22, 24, 98 and 168; and actor x/y. Unobserved native fields are not
filled in and claimed as measurements. Printed message requests and source
text hashes agree with visually inspected native frames. No OCR or byte-exact
native text-channel comparison is claimed.

Native normalization is checked against hashed raw snapshots. An initial
private probe decoded flag bits in the wrong order. The canonical receipt
re-derives them as `0x80 >> (index % 8)` from unchanged raw bytes, and the
public verifier independently repeats this derivation. It also re-derives
actor view, loop and cel from the raw actor record. Earlier derived flag
lists are not accepted as reference evidence.

| Pinned input | SHA-256 |
| --- | --- |
| Original `KQ1.COM` | `1a5fef60e521d1e30498c6883c89e3cc6d72c5591117eafd8c94d9669f9bdf86` |
| Native backend | `45fb6ffebe01de70599403a10a4a7d4a3b003621e910c36cc63449846ad3d346` |
| LOGIC53 payload | `672b526d9606dbc59221c96b95f56556da581a5db1c1b73b8761e1c860d7f3bd` |

Missing native runtime libraries were staged privately from official Ubuntu
packages with their published hashes checked. Original game files were
unchanged, and native processes were closed after capture. No backend or game
files are included in this change or its packages.

The final bow-cel observation was at guest time 116,837 ms and the first
restored-actor sample at 116,969 ms in this run. These bracket restoration;
they do not identify an exact animation cycle count, duration or general
speedup. The higher-level evaluator does not reimplement host timing.

## Reproduce and regression-check

With your own qualified resources and private original-run receipt:

```sh
PYTHONPATH=src python scripts/verify_kq1_bow.py /private/kq1 \
  --native-receipt /private/native/native-reference.json \
  --output /private/kq1-bow-verification.json
```

The optional native receipt requires its hashed source snapshots beside it.
Omitting it runs source-only comparisons and labels the result accordingly.
The script does not launch a native game. It hashes the relevant implementation
before and after execution and refuses a run whose code changes midway.
The output is created exclusively, preserving previous receipts.

- Full repository suite: **2,463 passed, 119 skipped** in 150.53 seconds with
  `PYTHONPATH=src:player python -m pytest -q` and a private temporary directory.
  This includes all 223 newly authored slice, intent, binding and adapter/CLI
  cases. No existing test was removed or weakened. The skipped checks remain
  outside this local result; fresh KQ1 observations are recorded separately.
- Core and standalone-player wheels pass archive policy with 177 and 14
  entries. All 172 core package/resource files and nine player files match
  both the checkout and their installed copies.
- Eight isolated installed-core CLI commands pass: help, exact-resource export,
  admission, completion, acknowledgement with clock advance, repeat, distant
  refusal and an unrelated command retained as IR. These use declared states
  and establish interface/package behavior, not additional native observations.
- Both installed bundled-skill gates pass: the investigation skill has
  11 references and 30 local Markdown links; the guide skill has eight and 13.
  The isolated player imports and displays help with the core package absent.
- The source distribution and tool ZIP pass archive policy with 616 and 608
  entries. Their selected source files are compared byte-for-byte with the
  final checkout, including this report and the aggregate evidence receipt.
  Only the source distribution's expected generated metadata is additional.

These local source, regression and packaging results are distinct from GitHub
CI on the published head. That status is reported on the follow-up PR. There
is no version bump, release publication or system-installation change.

## Remaining work

This change preserves all 90 LOGICs as low-level IR. The treasure-return bow,
talk/dialogue, endings, other parser commands, save behavior, general parser,
renderer and complete scheduler remain outside the recovered interaction.
Source comparisons are not a claim that every fabricated state is reachable
in normal play, and selected native observations are not whole-game equivalence.

The reusable next step is to qualify host contracts for completion events and
modal ownership, then apply the same source-to-intent process to another full
interaction. The investigation skill records the rules learned here: trace
state writers and consumers, preserve stateful admission, separate visit and
reward latches, test competing events, and bind only state owned by a suspended
interaction while explicitly retaining unknown behavior.
