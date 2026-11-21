# Bit 3 vertical-sync witness revision

Status: integrated source revision after raster attempt04. The frozen outside-main proposal remains unchanged. New host checks, assembly/listing review and separately admitted native evidence are pending; this document does not claim a measured improvement.

## Why this change is proposed

Raster03's second DOSBox pulse remains unqualified. Its row100 phase1 sampling interval overlaps the complete B-write interval by867/308 PIT ticks. The independently retained ambiguity review derives the result from raw PIT journals and immutable source, without images; the preceding result is summarized in the [timing revision](DOS_QEMU_PAIRED_TIMING_REVISION.md). The refusal is at the earliest possible sample, so reducing the H/8 latest-sample allowance would not resolve it.

The existing `new_vsync` loop uses the horizontal/vertical `sample_status` routine. That routine takes an upper PIT latch on a bit0 rise as well as a bit3 rise. A bit0-only upper latch is unused while waiting for vertical sync; its I/O and journal store can delay the next status observation. Removing that unused work is justified by the consumer's source semantics, without choosing a different image phase or pulse time.

The proposal is intentionally limited to this one change in observation policy. It does not defer the current/previous state stores into registers: doing so would require additional treatment of poll-budget and retrace-fault exits. Keeping the established store and fault order provides a smaller reviewable change. Deferred bookkeeping remains outside this proposal.

## Exact source change

The two calls in `new_vsync`, one in the wait-for-low loop and one in the wait-for-high loop, change from `sample_status` to `sample_vsync_status`.

A private sibling `sample_vsync_status` is added immediately before the existing generic sampler. Its instructions and local control flow match the generic sampler, except its selected-rise test is `test al,8` instead of `test al,9`. The generic `sample_status` source and both calibration call sites remain unchanged. No exported symbol, host operation, palette, pulse target, timer setup, journal field or finite guest bound changes.

The sibling preserves the existing register lifetimes:

| Value | Register while observations are made |
| --- | --- |
| Previous lower latch | CX |
| Previous status | BH |
| Current lower latch | SI |
| Current status | BL |
| PIT return/count scratch | AX |
| VGA status port | DX |

The inline PIT macro still changes only AX. The expression `(current XOR previous) AND current` identifies rises; masking with8 selects only bit3. A simultaneous bit0/bit3 rise therefore takes exactly one upper latch. A first high observation may receive an upper latch, but `status_valid=0` prevents it from inventing a vertical generation.

Both `new_vsync` callers consume journal fields after return and require none of these registers to survive. The clobber set is unchanged. All local labels remain under their respective global sampler or waiter labels. The additional code changes assembled addresses, so this integration requires a new emitted listing, binary and hashes; no old COM identity can be reused.

## Endpoint, state and bound preservation

Each sibling call executes `poll_budget` once before performing I/O. A refused poll increments the same counter to200001 and faults before a new latch or status read. For an admitted sample, the lower latch occurs before the actual status read. On a bit3 rise, the upper latch occurs after the high status read, and all current/previous journal stores follow it. The lower endpoint returned by the waiter remains the timestamp preceding the last low sample, not the lower latch of the first high sample.

Current/previous lower counts and statuses are stored after every completed sample. `current_after` updates only for a selected bit3 rise and otherwise retains its last value; intermediate stale upper counts are not used as new vertical witnesses. The waiter returns only after observing low and then high, so its returned `current_after` belongs to that final rise. No endpoint is interpolated or moved across a device observation.

Generation bookkeeping is deliberately unchanged even while the waiter is still seeking low. If it enters with a valid previous-low state and its first sample is high, that observed rise increments the generation; the waiter then observes low and the final high, which increments it again. If the first sample has no valid predecessor, it does not increment. The thirteenth observed rise is enclosed and journaled before the existing cap faults, preserving fault-state ordering.

The following remain unchanged:

- Channel2 mode2, divisor65536, gate high, speaker disabled; real port0x3da observations.
- The512-edge calibration buffer, four calibration retraces,200000 polls, twelve observed vertical rises, and four trial limit.
- The28-byte control and trial records, six-byte calibration record, decoder version and footer symbol names. Assembled address values will change.
- Both complete RGB triples inside their real lower/upper DAC brackets; one-tick expansion at both ends; half-wrap refusal.
- The calibrated schedule `(Vtotal-VsyncStart+200.75)*midpoint(H)` and `floor(midpoint(H))` width, reused for both pulses and chosen before images.
- The same-frame post-display vertical reference, both phase predictions, strict overlap refusal, H/8 assumption/check, calibration coarse band and128-line minimum.
- The independent integer-count work, which is not included or modified here.

## Authored source/dataflow regressions

The existing timing source test is extended to consume a finite stream of status observations and to follow calls to the new sibling. It still interprets only the actual small assembly routines and substitutes ordered PIT/status/DAC events. Unknown instructions fail review. Its finite source-interpreter instruction allowance changes from128 to512 solely to cover multiple nested samples; this is not a guest, owner or native resource-limit change.

New cases assert observable event sequences and journal state for:

- Bit0-only rises while bit3 is low or high, neither of which takes an upper latch.
- Bit3 rises and simultaneous bit0/bit3 rises, each with one lower/status/upper sequence.
- First-high initialization without a fabricated generation, and a valid previous-low entry whose first high must be counted before the later returned rise.
- A complete waiter containing repeated high and low observations, including an ignored horizontal rise; exactly one poll admission per actual sample and the correct last-low/first-high endpoints on return.
- The poll limit with no I/O after the refused admission and the last completed sample preserved in memory.
- A permitted twelfth vertical rise and a fault on the thirteenth, after its real endpoints and journal state have been retained.

The existing generic transition table, first-sample behavior, PIT byte order/register contract, full DAC triples and finite-cap cases remain present. These checks are authored only; no result is claimed.

## Limits and next decision

This source change can remove irrelevant bit0 upper-latch work. It cannot establish the width or placement of a future vertical bracket, prevent all polling alias, or guarantee that the sample and full DAC write are actually separated. Changed instruction count and layout can change polling phase under fixed icount. No old trial is repaired by this proposal, and no pixel-selected delay or phase is introduced.

Raster attempt04 now provides the integer-count evidence: QEMU calibrated a 427-line span and reached both pulses, but the full phase gate still refused. QEMU pulse4 has a row101 phase0 overlap with the C write; both DOSBox pulses have a counterfactual row99 phase0 overlap with the B write. These are independent timing-journal refusals, not grounds to change the fixed phase families. Root owns the new host checks, assembly/listing review and separately bounded native admission after independent source review. A future actual interval that still intersects a complete DAC write remains unqualified. DOSBox H/8 remains a declared assumption because individual row callback timestamps are not observed.
