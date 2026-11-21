# Paired raster timing witness revision

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

## Complete integer-count source proposal (2026-11-21)

The oracle now has a staged source correction for the candidate-count cutoff.
It has not been imported or tested, and no native attempt has been admitted for
this revision. The preceding diagnosis describes the unchanged oracle used by
attempt03; that failed result and every earlier raw receipt remain unchanged.

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
Their execution remains pending under a separately reviewed finite host gate.
Any future native run still needs its own clean source identity and fresh
admission. This source correction neither selects a count from captured pixels
nor guarantees that QEMU calibration or the separate DOSBox pulse ambiguity
will qualify.
