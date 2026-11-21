# Dune travel-map selector

This research adapter continues [the sparse-reader/native-wait work](DUNE_OPTIMIZATION.md).
The continuation is dated 19 November 2026 (UTC) and is available as
`dotbox guide --topic dunemap`.
It selects a destination through the original game's mouse callback and records
three separate facts: the selected callback was reached, the intended site was
accepted, and the interface became ready again. Actual arrival is a later
observation.

The supported profile is the recorded English DOS RIP executable, real 16-bit
mapping at CS `0824` / DS `16F3`, and its travel map (menu `2794`, mode `1`,
gate `04`). Strategic troop maps and other callback profiles are outside this
adapter. The original game remains authoritative.

The pointer at `DS:2A5C` must name vector `2176`, and all seven callback words
must match the observed profile, in order:

```text
4D9F, 4D4E, 133D, 133D, 133D, 4D9F, 4D9F
```

Pinning only the left-click callback `4D4E` is insufficient. Idle polling can
call slot 0 at `D27C`, and held-left movement can call slot 5 at `D2C1`, before
a new press reaches the selected callback at `D2FE`. Binding an initially
unknown callback value across two observations would not qualify that behavior.
The normal rectangle path also requires byte `DS:4235 == 0`.

## Prepared choices

`scripts/experiments/dune_map.py` supplies `MapSelector` over the caller's
already-owned `ProgressController`. The controller must explicitly use the
qualified native bounded-wait capability. Both full and sparse scene readers
are supported.

```python
selector = MapSelector(controller)

# Choose an identity from the current observed map points.
prepared = selector.prepare(
    controller.ready_token,
    site_record=selected_observed_record,
)
if prepared["outcome"] == "prepared":
    result = selector.select(
        prepared["selection_token"],
        max_frames=600,
        max_stops=12,
        max_guest_ms=5000,
        host_budget_ms=15000,
        hold_ms=40,
        stable_frames=2,
    )
```

Preparation reads the current stopped map; it does not run the guest or inject
input. A generic scene observation alone is insufficient. Preparation requires
the same controller's current input-loop token, a matching stopped revision,
neutral input, the qualified code/data mapping, and no foreign probes.

The private selection token binds the chosen site and pixel to the current map
meaning: callback pointer and vector, gate, viewport, map mode, current site,
normal rectangle-table route, terminated point table, eligibility bytes, names
and active control bindings. Live code ranges must match the qualified
executable. The selector retains its own copy; changing the returned packet
cannot change the pending selection.

Creating another preparation invalidates the previous pending token. Selection
consumes its token before any native admission. An absent, mismatched or reused
selection token is refused locally without native calls. If a once-valid token
names a native revision that has since changed, the stopped-state admission
fence refuses it before input or execution. A new controller or process cannot
inherit another selector's pending intent.

The point comes from the current rendered table, not a saved coordinate. The
adapter rejects a missing, duplicate, ineligible or current-site target, an
ambiguous nearest point, coordinates outside the frame or viewport, and overlap
with an active rectangle. The viewport includes its lower bounds and excludes
its upper bounds. Rectangle testing retains the original
`x0 < x < x1, y0 < y <= y1` rule.

## One click, two dispatch checks

Selection revalidates the prepared binding before input and consumes the token.
It queues one ordinary left click, then observes the following boundaries:

| Boundary | Required proof | What it does not establish |
| --- | --- | --- |
| `0824:D2FE` | The non-rectangle callback, SI vector, DX/BX pixel, and current map binding match the prepared choice | Destination acceptance |
| `0824:4D74` | Both DI and `DS:4258` identify the intended site | Travel completion or arrival |
| Recurring input loop `0824:D214` | Released input, completed frames and stable controls at a fresh qualified loop | Completion of every deferred world effect |

An owned guard at the rectangle dispatcher `0824:D326` stops an unexpected
menu route before its callback. The normal rectangle-table path must also
remain applicable; the adapter does not silently enter an override-table path.
The queued-click acknowledgement must advance the final armed revision by
exactly one, match a fresh stopped status, and preserve the prior stop reason.
An unowned intervening revision prevents any execution wait.

The original map hover code updates the selected-site word and cursor state.
Those expected changes are distinct from a moved point, a different callback,
a changed gate or viewport, or a rebound control. Comparing the entire
conventional-RAM hash across queued input would reject legitimate execution.
The adapter instead rechecks explicit route dependencies under stopped-state
revision fences.

The original nearest-point routine dereferences each nonzero site's type before
filtering the map mode. The adapter therefore bounds every pointer and binds
every referenced eligibility byte, including points for a different mode. It
retains only used table entries and their terminator as dependencies; unused
prefetched bytes do not become map meaning. The routine skips type `FF`, matches
the map mode and accepts distances below nine. It retains the first point on
equal distances.
The selector conservatively refuses ties, retaining an unambiguous intended
destination rather than depending on table order.

## Results and failure handling

`destination_accepted` becomes true only after the second observed boundary
matches both site identities. `input_ready` becomes true only after the
separate readiness procedure succeeds. `arrival` and `story_commit` remain
`"unknown"`; inspect the later current site and location after ordinary travel.

Frame, guest-time, stop-count and cooperative host-admission bounds cover the
whole selection, including both dispatch checks and readiness. The receipt
retains actual counts, bytes, ticks, code identities and private evidence. The
default limits are 600 completed frames, 12 observed stops, 5,000 guest
milliseconds and 15,000 host-admission milliseconds; callers can declare a
different admitted bound. A limit is a maximum for the complete action, rather
than a fresh allowance for each callback phase.

Host time is a cooperative admission limit, not a hard wall-clock deadline for
an RPC already in flight. As with the base controller's observer cleanup, the
single stopped-status fence for an already acknowledged observer creation may
finish after host admission expires. This bookkeeping exception admits no new
input or execution. The selector restores the original deadline before either
can be admitted, counts the bookkeeping in its actual host/RPC metrics, and
makes no follow-up call after an uncertain reply. An observer revision is
adopted only when the old owned stop matched exactly, the acknowledgement
advances the revision by one, and the stop reason remains unchanged.

A timeout before target acceptance cannot be bypassed through a generic
input-free wait: the remaining callback might still choose a different target.
A known stopped timeout after proven acceptance may be reconciled without
another click, using the same controller's explicit partial-action procedure.
For `outcome == "timeout"`, `destination_accepted == True` and
`continuation_allowed == True`, the caller may use
`controller.await_ready(reconcile_partial=True, ...)` with new declared wait
bounds. Successful reconciliation retires the partial action; it does not
prove arrival or replay the prepared choice.

Foreign or wrongly attributed stops, wrong target identity, failed cleanup and
uncertain transport forbid continuation. A lost native reply permits no further
native calls from the controller, including cleanup.

A selection token is single-use. Preparation, selection and recovery never
replay an earlier click. State restore creates a new observation timeline;
reacquire ownership generation and input readiness and prepare a new token.

## Authored protocol validation

The final selector source is covered by **124 passing authored protocol tests**
with no failures, errors or skips. These tests use generated source bytes,
authored site records and labels, the real full/sparse readers and the actual
`ProgressController`, with a deterministic native-protocol peer. They do not
execute the commercial game or qualify a native runtime.

The suite covers selected-site eligibility and geometry, all seven initial
vector slots, stopped binding changes, current and consumed tokens, private
prepared copies, callback coordinates and registers, both acceptance identities,
rectangle interception, complete routine-byte checks, foreign stops, uncertain
RPCs, aggregate execution budgets and input-free recovery after acceptance.
It also checks that declining a selection cannot remove another operation's
observers and that queued-click acknowledgement provenance is enforced before
execution. Both host-deadline edges around the readiness observer's creation
and fresh status fence retain the correct known-stop identity.

Failed cases and focused red/green receipts were retained privately while the
implementation was corrected. In a repository checkout, the focused suite is
`python -m pytest tests/test_dune_map.py`. The final module SHA-256 for these
124 cases is:

`050891678c92052d5466e8f4f5340152bf9597d3d39b3b048db1026638a11b95`

## Final live evidence

Four controlled success trials used the final selector hash above: one sparse
and one full reader run for each of Carthag-Harg (`026C`) and Carthag-Timin
(`0234`), starting from the same neutral Carthag-Tuek travel-map checkpoint.
The complete sanitized identities, exact metrics and evidence limits are in
[the map-selector receipt](evidence/dune-map-selector-2026-11-19.json).

Every trial queued exactly one map click, matched `D2FE` and the intended
`DI == DS:4258` at `4D74`, and reached fresh flight input readiness. The selector
continued to report arrival and story commit as unknown. A separate original
`SKIP TO DESTINATION` action then produced the requested current site, matching
site/location context, ordinary outside menu `2598`, neutral input and zero
remaining observers. Both readers produced identical flight and arrival PNG
hashes and guest timing for each destination.

The following costs include **preparation plus selection** from an already-ready
map. They exclude checkpoint restoration, initial readiness, and the subsequent
travel shortcut. The success calls declared 600 frames, 10,000 guest milliseconds
and 15,000 host-admission milliseconds. This explicit guest bound is larger than
the API's 5,000-millisecond default.

| Destination | Reader | RPCs | Memory bytes read | Host elapsed | Selection frames / guest ms |
| --- | --- | ---: | ---: | ---: | ---: |
| Harg | Sparse | 191 | 216,202 | 5,247.225 ms | 348 / 4,972 |
| Harg | Full | 215 | 3,673,536 | 5,327.236 ms | 348 / 4,972 |
| Timin | Sparse | 191 | 216,202 | 5,142.519 ms | 347 / 4,962 |
| Timin | Full | 215 | 3,673,536 | 5,268.718 ms | 347 / 4,962 |

Sparse reading reduced measured memory transfer by 94.115% for these operations.
Each reader/destination combination was run once; the host timings are
observations, not a statistical speedup estimate. The controller made no model
calls internally. Restoration and other work outside its methods are not
represented by those zero-call counts.

Two additional bounded live checks exercised refusal behavior. An acknowledged
`state.save` after preparation changed the native revision; selection declined
after one status read, with no click or execution. Trying the consumed token
then declined with zero RPCs. A fresh selection with a one-millisecond guest
budget queued one click and stopped after one guest millisecond before target
acceptance. It reported no readiness or arrival and refused input-free
reconciliation with zero RPCs. No input was replayed. Recovery used an explicit
known checkpoint restore and a fresh controller.

Every map-checkpoint restore preserved the currently mounted disk, including a
closed file written after that checkpoint. These trials also left the disk
unchanged through their ordinary actions; that is an observation, not a
requirement that later legitimate game writes must be absent. Warm recovery,
including ordinary graphics initialization, checkpoint loading and a changed-pixel
Gurney interaction, took 34.95 seconds against the declared 180-second target.
Earlier analysis and coordination are outside that interval.

The final complete machine checkpoint is outside Carthag-Timin, current site
`0234`, location words `0101/0C80`, menu `2598`, and mode `0`. Its SHA-256 is
`ac8ba8e615dd20a46da9293b12751073a6fc35eedaee07b49869f3340dc85bf2`.
It was restored successfully with neutral input and zero observers before the
owned native process was closed and reaped with return code zero. The earlier
Gurney `COME WITH ME` choice remains unselected; this work makes no party-state
claim.

The exact reused native binary has SHA-256
`af4d353c128dbb58fa433a0f8601cb92d8fb93acc907e25827c038d6dea77e8e`.
No native rebuild was needed. An earlier successful Harg trial used source
`f7c2659a…`, before the complete-vector restriction; it remains historical private
evidence and is excluded from the four final-source results. Raw game files,
checkpoints, screenshots, RAM, failed test receipts and complete native logs
remain private.

## Recovery and scope

Use the same qualified native executable and graphics-initialization procedure
documented in the prior guide. Machine rewind restores memory and device state
while preserving current mounted files. The text-mode-to-graphics native
restore defect remains open.

This is a packaged research adapter for the measured edition and travel-map
profile. It does not add speech interpretation, a general game planner,
strategic-map support, original-Dot desktop/takeover qualification, macOS
qualification of this path, or arbitrary cross-build checkpoint support.
