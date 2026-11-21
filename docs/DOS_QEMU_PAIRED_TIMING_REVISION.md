# Paired raster timing witness revision

## Current native07 result

The [dedicated calibration register collector](DOS_QEMU_PAIRED_CALIBRATION_REGISTER_PROPOSAL.md)
at `2cb275edd852f73ee1440f9ee48e5f6bb71ed0ad` passed 87 focused host cases and
fresh assembly06. Native07's controller and one authored paired test passed:
both DOSBox source-phase-1 pulses and both QEMU source-phase-0 pulses are
observed, with counterphase and final-palette rejection. The exact result is
[appended below](#native-attempt07-calibration-registers-complete-the-authored-phase-gate).
These fixed phases differ; no general phase equivalence, application-frame
completion or full parity claim follows. Earlier failed attempts remain failed.

The independent retained-data audit accepted this finite result with no
discrepancy. Audit JSON SHA-256:
`1427c8db3f1e1e494adb45b271bc1cbc2b7ab4c1eeaaeb1558030f726fa966c0`.
The result does not admit another native attempt or broader parity promotion.

## Historical initial timing revision and subsequent attempts

This source revision reduces observer work inside the authored guest's timing
measurements. Its bounded host selection passed 33 cases, and assembly02 produced
the reviewed 3,959-byte COM. The second actual paired native execution,
controller attempt03, **remains failed and phase-unqualified**. Four quiet rasters
matched exactly; DOSBox's second pulse was ambiguous and QEMU calibration could
not establish a 128-line span. Original attempts and raw evidence remain unchanged.
See the recorded results below; completed source rasters do not establish paired
pulse-phase parity or `completed_guest_frames` qualification.

The fixture is [paired_video_frame_fixture.py](../tests/support/paired_video_frame_fixture.py).
The independent [timing oracle](../tests/support/paired_video_frame_oracle.py)
and [native test](../tests/test_paired_video_frame_native.py) were unchanged for
the timing-witness revision and attempt03. The separate integer-count proposal
below changes the oracle and its host tests; the guest fixture and native test
remain unchanged.
The previous result is recorded in the
[paired source-frame plan](DOS_QEMU_PAIRED_SOURCE_FRAME_PLAN.md#first-native-attempt).

## Reason for the change

In attempt 01, both producers completed two quiet and two pulse rasters. All
four quiet images matched the independent authored RGB oracle. The four pulse
observations were refused while constructing their two timing predictions:
some possible row sampling times intersected whole-DAC-write uncertainty
windows. The refusal occurred before pulse RGB comparison and the subsequent
QEMU callback-lateness check.

The row interval contains the post-display vertical-edge bracket, accumulated
horizontal-period uncertainty, and the existing H/8 allowance. At the first
failed rows its width was approximately 28.75 PIT ticks on DOSBox and 25.21 on
QEMU. The original observer performed two PIT reads on every status poll and
included extra bookkeeping and calls inside its write brackets. Removing that
avoidable observer work is a measurement change justified by the journal
semantics. No pulse image was used to choose a new phase or timing parameter.

Narrower measurement code does not guarantee a qualified next observation. A
real sample and a write can still be too close. Only fresh independently
admitted device journals can establish the resulting intervals.

## Status-edge measurement

`sample_status` still takes a channel-2 lower-latch timestamp before each read
of VGA input status register 1. The revised routine retains the previous
lower count/status in `CX`/`BH`, and the current lower count/status in `SI`/`BL`.
It takes a second PIT reading only when bit 0 or bit 3 has changed from low to
high. The current status is retained across that reading, and bookkeeping is
performed afterward.

The two existing consumers use exactly those transitions:

- Horizontal calibration consumes a bit-0 rise while the current vertical-sync
  bit is clear. The preceding observation therefore saw bit 0 low, and the
  upper count was captured after the new high observation.
- `new_vsync` first observes vertical-sync low, then returns on the first
  observed high. That bit-3 rise receives an upper count even if bit 0 changes
  at the same time.

An unused bit-0 rise during vertical sync can also receive an upper count.
It does not create a horizontal calibration record or an extra vertical
generation. A first sample with either selected bit high can receive an upper
count, but `status_valid` still prevents a fabricated initial vertical edge;
the calibration loop starts only after that first sample.

The retained edge bracket remains:

1. The PIT latch before the last observed low status.
2. The last low status read.
3. The unobserved device edge.
4. The first observed high status read.
5. The PIT upper latch after that high read.

In particular, `previous_before` is not replaced with a timestamp after the
last low read, and `current_after` is not replaced with the current lower
timestamp. Those substitutions would exclude possible transitions. A poll
without a selected rise leaves `current_after` unchanged; no consumer uses
that stale value as a new edge witness.

Each call still invokes `poll_budget` exactly once before performing I/O.
Every observed bit-3 low-to-high transition still increments `vertical_edges`
once, followed by the original cap check. Lower-count and status fields are
updated on every completed sample, including falling or unchanged status.

The routine now clobbers `AX`, `BX`, `CX`, `DX`, and `SI`. Its only callers are
the initial sample, the calibration loop, and `new_vsync`; none requires those
registers to survive the call. `wait_offset` continues to use `BX` as its
absolute target and does not call `sample_status`. No exported symbol or host
register convention is changed.

## Complete-DAC-write measurement

For both fixed writes B and C:

1. Select palette index 1 and position `DX` at the DAC data port before the
   lower timestamp. This does not write a palette component.
2. Latch channel 2 and retain its full count in `SI`.
3. Write all three fixed palette components to port `0x3c9`.
4. Latch channel 2 again.
5. Store the retained lower count and new upper count in their original
   `b_before`/`b_after` or `c_before`/`c_after` journal fields.

Both complete RGB triples remain inside their measured brackets. The witness
does not assume that the final component alone describes palette commit
semantics. No journal memory write or PIT-helper call/return lies between
these two DAC latch events. Component loads and the `SI` retention instruction
still take time inside the bracket; their time is measured, not subtracted.

The shared zero-argument NASM macro `latch_pit2` uses the same six instructions
as the previous PIT helper: channel-2 latch command `0x80` to port `0x43`, then
low and high bytes from port `0x42`, yielding the 16-bit count in `AX`. It
preserves the other registers. `pit_read` retains its call interface for
`wait_offset` and expands that same primitive before returning. Inlining only
removes helper call/return overhead around the affected device observations.

## Unchanged experimental contract

| Contract | Retained value or rule |
| --- | --- |
| PIT configuration | Channel 2, binary mode 2, divisor 65,536, gate high, speaker disabled |
| Status observations | Actual reads of port `0x3da`; no predicted edge timestamps |
| Endpoint uncertainty | One PIT tick on each side of every admitted bracket |
| Time unwrapping | Unique adjacent descending-count gap below 32,768 ticks |
| Calibration | At most 512 records, four calibration retraces, uniquely counted same-polarity horizontal gaps, at least one 128-line span |
| Total finite guest bounds | At most 200,000 polls, 12 observed vertical rises, four trials |
| Phase families | QEMU phase 0 and DOSBox phase 1, with both complete counterfactual predictions required |
| Pulse schedule | Existing device-calibration formula and width; fixed before pulse images |
| Row reference | The same raster's post-display vertical-sync observation |
| Callback allowance | Existing H/8 assumption and subsequent stricter QEMU check |
| Refusal | Any sampling/write interval intersection leaves the trial unqualified |
| Owner experiment | Two quiet frames followed by two pulse frames; no alignment frames or automatic retry |
| Image role | Compare only after independent predictions are available; never select or tune timing from pixels |
| Journal ABI | 28-byte control, 28-byte trial, six-byte calibration record, existing footer symbols and bounds |

The journal format and endpoint meanings are unchanged, so its decoder version
remains `PVF1` version 1. The modified assembly must nevertheless receive its
own exact source/COM identities. The old 3,883-byte COM and its hash cannot be
used as evidence for this revision.

## Source checks and required next evidence

[test_paired_video_frame_fixture_timing.py](../tests/test_paired_video_frame_fixture_timing.py)
checks the actual assembly source's small measurement routines against ordered
PIT/status/DAC events. It covers the selected status-bit transition table,
generation accounting, first-high initialization, the last-low/first-high
bracket, unchanged poll/retrace limits, the PIT byte-order/register contract,
and both complete DAC triples with post-bracket journal stores.

These are source/dataflow checks with a deliberately limited instruction
interpreter. Unknown instructions require explicit review. They neither
assemble machine code nor model instruction timing or an emulator's devices.
The independent pure timing-oracle tests remain a separate check. Their
expected values and ambiguity rules are unchanged.

Before another native attempt, review the fixture and these tests, run the
bounded host checks, and assemble once under a separately reviewed finite
controller. Verify the new COM size/hash, footer addresses, journal extents,
register use, and actual assembled instruction ordering. Freeze the exact
integrated host, test, fixture, oracle, producer, loader, and controller inputs.
Any native admission then uses new output paths and preserves attempt 01 in
full. Acceptance still requires both complete phase predictions, correct raw
RGB, the stricter QEMU timing check, and the original ownership/log/input
integrity conditions.

## Recorded host, assembly and native results (2026-11-20)

At `86a5fdb49d17452f9eda8af9380897f4a92ea7cc`, the separate bounded host selection
passed 33 cases: ten unchanged oracle cases and 23 witness source/dataflow cases.
Assembly02 used the retained NASM once and produced 3,959 bytes, SHA-256
`f36dc2638353868da45dc924aee17cfd3ef098dbe0cbceccf0a673f4e75180bc`.
Its complete instruction listing, footer addresses, extents and register lifetimes
were independently reviewed. No emulator producer was rebuilt.

Controller attempt02 was frozen metadata only and never admitted. Fresh attempt03
used the reviewed 212-member potential loader closure and ran both original owners.
Both exited zero and were reaped; all 11,757 pinned inputs and nine trees remained
unchanged. The whole native phase failed after 56.414883888 seconds, receipt
`a8f3268066fbc3c040bcb8562e4a38784fcb6c6a4f34919b18694cdfe49f3155`.
The 1,665,160-byte native witness has SHA-256
`5b228cb28ce00e734533becd078588b75fc11344a7ca591b348d602359d318e0`.

| Observation | Recorded outcome |
| --- | --- |
| Two quiet frames on each backend | All four matched the authored 192,000-byte RGB oracle and public source APIs |
| Quiet RGB SHA-256 | `141a920ca2ecdd0d6fd7684eca3918d7d9ce66f74573266a15656dd107295939` |
| DOSBox first pulse | Declared source phase 1 matched, counterfactual/final-palette-only models rejected |
| DOSBox second pulse | Unqualified: row 100 phase 1 intersects a whole-DAC-write uncertainty interval |
| QEMU calibration | No uniquely counted horizontal span of at least 128 lines |
| QEMU pulse observations | None attempted after calibration refusal |

QEMU retained 205 edges and 9,856 polls, reaching the fixed fourth-retrace bound
with `calibration_limited=1` and `fault=0`. Its 204 adjacent gaps contain 151
unique seven-line choices, 50 same-generation gaps compatible with eleven lines
outside the oracle's fixed candidate set 1..8, and three vertical boundaries.
Those exclusions leave a maximum admitted span of 21 lines. This is consistent
with the unchanged oracle, not an image mismatch or a PIT unwrap error. DOSBox
retained a qualifying 397-line segment; its pulse ambiguity is a separate limit.

PIT and VGA status use the same QEMU virtual clock. With fixed `icount shift=7`,
removing guest observer instructions changes sampling phase. The revised stable-low
loop's 43 instructions correspond to 5,504 ns; narrower local edge brackets can
therefore coexist with worse edge coverage. Source-derived VGA window estimates
are corroboration only, since the fixture did not journal CR04/CR05. No pixel
feedback was used to select timing data or tune the oracle.

### Historical mathematical review, before implementation

A possible completeness correction is to consider every compatible positive
integer line count using exact interval bounds:
`n_min = max(1, ceil(delta.lo / coarse.hi))`,
`n_max = floor(delta.hi / coarse.lo)`. A unique count requires equal endpoints.
This can admit a unique count above eight and can also expose ambiguity hidden
by the old cutoff. Bounds-only evaluation avoids unbounded candidate lists.
The existing half-wrap rule bounds adjacent expanded differences at 98,303 ticks;
512 records still bound adjacent decisions and long-pair intersections.

During the attempt03 diagnosis, this mathematics was reviewed only. No revised
oracle, H estimate, pulse schedule or retrospective pass was produced then.
Any implementation needs new source review and host evidence before a fresh
native admission. Generation breaks, endpoint
brackets, quantization, 128-line minimum, all long-pair constraints, H/8, fixed phase
models, counterfactuals and execution/output limits must remain. The successful
[return/pause gates](QEMU_PAUSE_AND_RETURN_GATES.md) qualify separate contracts.

## Complete integer-count revision (2026-11-21)

The oracle now implements the source correction for the candidate-count cutoff.
All 22 focused host cases passed at `72a4975`. Fresh assembly03 emitted the same
3,959-byte guest COM as assembly02. A separately reviewed native attempt04 then
ran both producers with this exact source identity. The preceding diagnosis
describes attempt03; that failed result and every earlier raw receipt remain
unchanged.

For same-generation adjacent edges, closed overlap of the observed difference
`delta` with `n * coarse` is equivalent to the complete positive-integer bounds
`n_min = max(1, ceil(delta.lo / coarse.hi))` and
`n_max = floor(delta.hi / coarse.lo)`. The arithmetic stays exact in `Fraction`.
Equal endpoints admit one physical count; lower greater than upper means no
count, and lower less than upper means ambiguity. Both nonunique cases break
the segment. A vertical-generation change always breaks it without inferring
a count. Each decision uses the original coarse band, never a fit already
tightened by another pair. No list of candidate integers is materialized.

New successful horizontal receipts identify
`line_count_rule="complete-positive-integer-bounds-1"`. Within `excluded_gaps`,
`possible_line_count_bounds` replaces the former enumerated
`possible_line_counts` field. It is `{"min": n_min, "max": n_max}` for a
same-generation gap, including an empty range with `min > max`, and `null` for
a generation change where counting was not attempted. The existing delta,
record index and generation-change flag remain. The native collector retains
this receipt without interpreting the old list field; no existing caller in
the repository consumes that field. Historical receipts keep their original
schema and are not rewritten.

The 512-record limit and half-wrap rule remain in the parser. Three adjacent
counter steps, each at most 32,767 ticks, bound an adjacent expanded difference
above by 98,303 ticks. Candidate bounds therefore stay finite for a positive
coarse interval, while their representation has two integer fields independent
of the number of candidates. There are still at most 511 adjacent decisions
and 130,816 long-pair intersections. The 128-line minimum, every long-pair
constraint, endpoint quantization, geometry/coarse band, pulse formulas,
same-frame reference, H/8 and both phase/counterfactual models are unchanged.

Focused host regressions are authored for unique counts above eight, a false
eight-line uniqueness caused by omitting nine, closed fractional endpoints and
sub-float distinctions, empty/negative-lower ranges, generation breaks, bounded
diagnostics from half-wrap-safe raw counters, and inconsistent long spans.
These cases passed under a separately reviewed finite host gate. Every native
run still needs its own clean source identity and fresh admission. This source
correction does not select a count from captured pixels or relax the separate
pulse-phase gate.


### Native attempt04: complete counts reach the pulse gate

Attempt04 completed at `72a4975224a4eee5cf912becfeacd94d1d1c3139` in
37.277624148 seconds. Its phase receipt SHA-256 is
`96977333152afaf477d551f0f148bb88e9e8f917725c14f2916954cf75a2d16b`.
All 11,766 file pins and nine input trees were unchanged. Both serial owners
exited zero and were reaped, with no owner or adopted-child cleanup errors.
The worker returned one because the separate phase assertion failed.

| Observation | Attempt04 result |
| --- | --- |
| Four quiet rasters | Full authored RGB equal within and across both backends |
| DOSBox calibration | 399-line span; H in `[4851/128, 7473/197]` PIT ticks |
| QEMU calibration | Spans of 160, 416, 416 and 427 lines; H in `[15725/416, 16161/427]` PIT ticks |
| QEMU first pulse | Source phase 0 observed; counterfactual and final-palette-only predictions rejected |
| QEMU second pulse | Unqualified: row 101 phase 0 intersects the complete C-write bracket |
| Both DOSBox pulses | Unqualified: counterfactual row 99 phase 0 intersects the complete B-write bracket |

Each producer ran exactly two quiet and two pulse captures. No alignment frame,
extra retrace or automatic retry was added. The complete count rule resolves the
old artificial cutoff; it does not establish full raster phase parity. The
[vertical witness revision](DOS_QEMU_PAIRED_VSYNC_WITNESS_PROPOSAL.md) proposes
removing unused bit-0 upper latches while the guest waits only for bit 3. The
pulse schedule, whole-write brackets, H/8 allowance and both phase families stay
fixed. Further native evidence requires a new clean source identity and gate.


### Native attempt05: vertical-only upper latches remain insufficient

The [vertical witness revision](DOS_QEMU_PAIRED_VSYNC_WITNESS_PROPOSAL.md)
was integrated at `611a62e`, passed 38 focused timing cases, and produced a
fresh independently reviewed 4,066-byte COM. A separately admitted native05
completed both original four-frame sequences. QEMU again calibrated successfully,
this time over spans of 429, 416 and 416 lines. All four quiet captures matched
the authored full RGB image and one another. Both pulse trials on each backend
remained unqualified because a possible sampling interval intersects a complete
DAC write: DOSBox row 100 phase 1 and QEMU row 101 phase 0.

The phase receipt is
`c459afddbc16b3e09375a016756de1f69ca28d1aef804653b5352ba298c9bb6a`.
All 11,763 pinned files and nine trees were unchanged. Owners exited zero and
were reaped; no cleanup error was recorded. No producer rebuild, extra frame,
automatic retry, image-derived timing choice or relaxed acceptance rule was used.
The complete-count correction remains useful calibration coverage, while the
bit-3 change alone has not established a phase pass. Full parity remains open.

### Native attempt06: register waiter qualifies both QEMU pulse trials

The [register-state waiter](DOS_QEMU_PAIRED_VSYNC_REGISTER_PROPOSAL.md) was
integrated at `0ff9383caaa374558ca3fc15e2b4ed3d826423ac`. It passed all 48 focused
host cases, a fresh finite assembly05 and a complete independent emitted review
of the 4,146-byte COM. It preserves the full observation and finite-fault state
at return while removing per-poll memory bookkeeping from the vertical loop.
The generic calibration sampler, pulse schedule, whole-write brackets, H/8 and
both phase families are unchanged.

Native06 completed once in 40.894148974 seconds. Both QEMU pulses now have
unambiguous timing predictions and full RGB matching the fixed source phase 0;
the counterfactual phase and final-palette-only image are rejected. Each pulse's
200-row native receipt has callback lateness between 6 and 126 ns, strictly
below the declared H/8 limit of 3,962.5 ns. All four quiet captures still pass.

The overall paired gate nevertheless failed. Both DOSBox pulses remain
unqualified at row 100 phase 1: pulse3's upper interval endpoint overlaps C by
`159843/229792` PIT ticks, and pulse4's lower endpoint overlaps B by `703/688`.
H/8 contributes to the former overlap but cannot remove the latter. The fixed
allowance is retained; DOSBox per-row callback times remain unobserved.

The phase receipt is
`9223a1da9379b9acfbf5b9295de490ed288a1707633953a2f62a19839a01523e`.
All 11,768 file pins and nine trees matched before and after. Both serial
emulator owners exited zero and were reaped; the worker returned one for the
final phase assertion, with no timeout or cleanup error. This is an observed
QEMU improvement in this authored experiment, not a causal claim about every
bracket or a promotion of full parity. No later native attempt is admitted.


### Native attempt07: calibration registers complete the authored phase gate

Source `2cb275edd852f73ee1440f9ee48e5f6bb71ed0ad` integrates the dedicated
calibration collector without changing the register vertical waiter, complete
DAC triples, absolute schedule, oracle or native test. All 87 focused host cases
passed. Fresh assembly06 produced the independently reviewed 4,358-byte COM,
SHA-256 `c2ddebd5affa489302f22c9139d354be1cb31b38d5edbe58b5e491c90ed3cb1d`.

| Device-journal observation | DOSBox | QEMU |
| --- | --- | --- |
| H interval, PIT ticks | `[13606/359, 13164/347]` | `[1550/41, 15667/414]` |
| Calibration records / polls / vertical rises | 512 / 4,059 / 1 | 410 / 12,362 / 4 |
| Admitted spans, physical lines | 146, 364 | 364, 431, 426, 424 |
| Pulse delay / width, PIT ticks | 9,015 / 37 | 8,992 / 37 |
| Both pulse source phases observed | 1 | 0 |
| Minimum all-row phase-0 clearance, PIT ticks | `624/347` | `12307/1656` |
| Minimum all-row phase-1 clearance, PIT ticks | `646/347` | `3637/552` |

The delay still equals
`floor((Vtotal - VsyncStart + 200.75) * midpoint(H))`, relative to the previous
vertical-sync upper latch, and width still equals `floor(midpoint(H))`.
The changed numerical delays are outputs of that unchanged predeclared formula
and each backend's independent calibration, chosen before images. The 512-record
cap, four-retrace exit, complete positive-integer inference, 128-line minimum,
all long pairs, endpoint quantization, H/8 and both phase families remain fixed.

Both pulse trials on each backend now reject the counterphase and
final-palette-only prediction. All four quiet RGB arrays match the authored
oracle. QEMU's 200-row native callbacks on each pulse have lateness 0–120 ns,
strictly below H/8 = 3,962.5 ns. DOSBox's individual callback times remain
unobserved; its effective per-setting runtime profile is still unverified.
Positive interval clearances qualify these fixed predictions; they do not
establish general timing equivalence or causal isolation of this one code change.

The complete attempt took 40.97446353000123 seconds: controller success and one
passed JUnit case with zero failures, errors or skips. The retained xunit2
warning concerns `record_property` compatibility. DOSBox owner 38 and QEMU owner
52 ran serially, exited zero and were reaped. The external journals contain
1,121 paired calls: 155 DOSBox and 966 QEMU. All 11,775 file pins and nine trees
matched before and after.

Phase receipt SHA-256:
`0396de542532b62430252d3f131d59eb847845f92e8cc2cb5e66629f85df73e0`.
Paired native receipt SHA-256:
`d0114685dc162d3625483e1555c9b75a0078eef8f9c8a09422d2c9a9da999e11`.
The [source-frame result table](DOS_QEMU_PAIRED_SOURCE_FRAME_PLAN.md#current-native07-result-2026-11-21-utc)
records the unchanged quiet and backend-specific pulse hashes.

The independent raw-control audit accepted this result without discrepancy;
its exact identity is recorded above. Earlier failed attempts are preserved without promotion. Application
frame completion and frame/input state equivalence stay unknown;
`completed_guest_frames`, all 143 surface, 18 workgroup and seven campaign
promotion obligations remain open. DOSBox stays default. The next reviewable
[coherent-frame obligation](DOS_QEMU_PARITY_WORK.json) is explicit observation
and mutation authority; this result admits no native08 or new implementation.
