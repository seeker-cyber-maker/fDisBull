# Paired raster timing witness revision

This source revision reduces observer work inside the authored guest's timing
measurements. It has **not yet been assembled or executed**. Its source tests
are authored for separate admission; their presence does not establish a pass.
The first paired native attempt remains failed and phase-unqualified, with its
independently verified quiet-raster facts and original evidence unchanged.

The fixture is [paired_video_frame_fixture.py](../tests/support/paired_video_frame_fixture.py).
The independent [timing oracle](../tests/support/paired_video_frame_oracle.py)
and [native test](../tests/test_paired_video_frame_native.py) are unchanged.
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
