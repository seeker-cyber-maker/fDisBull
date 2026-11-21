# Calibration polling with observation state in registers

## Current result and historical proposal

The source-only design below was integrated at
`2cb275edd852f73ee1440f9ee48e5f6bb71ed0ad`. It subsequently passed all 87 focused
host cases, fresh assembly06 and the emitted-instruction review. Native07's
controller reports success and one passed paired test: both DOSBox phase-1 and
both QEMU phase-0 pulse trials are observed. The [result below](#native-attempt07-result)
keeps the numerical calibration, unchanged acceptance rules and remaining scope
explicit. The original proposal and failed native06 evidence remain historical.

The independent retained-data audit accepted this finite result with no
discrepancy. Audit JSON SHA-256:
`1427c8db3f1e1e494adb45b271bc1cbc2b7ab4c1eeaaeb1558030f726fa966c0`.
The result does not admit another native attempt or broader parity promotion.

## Historical source-only proposal, before integration

Status: **source-only proposal; no new execution or phase qualification**.
The published baseline is `ea222ede008ef78359c46f4df9bc8b46abedf56c`.
Its fixture and timing checks have the same bytes as the previously exercised
register-waiter source. Main, earlier controllers and raw results are unchanged
by preparing this proposal. Native06 remains a failed paired gate; its two
observed QEMU pulses do not qualify the unobserved DOSBox phase.

The proposal removes between-sample calls and repeated observation-state
loads/stores from the active calibration path. It does not claim that every
PIT bracket will shrink, that numerical H uncertainty will improve, or that a
future native attempt will qualify. Required device I/O, quantization and the
existing phase assumptions remain. No native07 is admitted here.

## Narrow source change

After the unchanged `setup`, one `collect_calibration` call replaces the former
seed call and outer calibration loop. The new routine samples, records and
returns to the same exported `calibration_done` NOP. The former generic
`sample_status` body is retained byte-for-byte as the existing reference/test
body; the active entry no longer calls it. New tests target the actual collector
and explicitly check that entry routing.

Removing the new routine and restoring the old entry reproduces the complete
baseline fixture source exactly. In particular, the current `new_vsync`, PIT
latch primitive, complete DAC triples, absolute `wait_offset`, palette/setup
code, fault stops, data initializers, exported symbol list and Python decoders
remain unchanged. The oracle and native collector are outside this patch.

## Entry and observation contract

The original program takes one complete, unrecorded seed observation, then
unconditionally takes another observation before checking the four-retrace
calibration limit. The new seed flag preserves both facts. Even if a valid seed
raises the generation to four, a second sample still occurs unless a global
fault intervenes. The seed can take an actual upper latch and count a valid
vertical rise; it simply does not participate in horizontal record selection
or the outer four-retrace check.

Fresh authored globals start with zero validity and counters. Characterized
boundary entries also preserve distinct previous/current fields, the retained
upper timestamp and the complete validity byte. A zero validity byte becomes
one only after the first completed sample. Any nonzero byte, including `0xfe`,
survives exactly; it is not normalized.

Each attempted poll increments the full 32-bit counter and checks 200,000
before state rotation or device I/O. The refused 200,001st attempt therefore
retains the last completed previous/current observations, or the distinct entry
fields when no sample was admitted. Sample 200,000 may complete and return if
it satisfies a normal exit; the seed alone does not introduce a new exit.

The lower latch remains before the actual status read. An upper latch occurs
exactly when `((previous XOR current) AND current AND 9) != 0`, once even for
simultaneous bit-0/bit-3 rises. This includes an invalid first high and a bit-0
rise while bit 3 is already high. A no-rise sample preserves the last selected
upper. Full status bytes remain available, not only the two selected bits.

A valid bit-3 low-to-high observation increments the vertical generation only
after its actual upper latch. Generation thirteen faults before outer record
or four-retrace handling, including on the seed. The completed thirteenth
observation and its updated generation are committed before `fault_stop`.

## Record selection and exit order

A later sample is eligible exactly when previous bit 0 is low, current bit 0
is high, and current bit 3 is low. Previous bit 3 is deliberately unrestricted:
`8 -> 1` remains eligible. Every eligible observed rise is recorded; there is
no thinning, alignment observation or nominal timestamp. Actual poll timing
may change as the observer changes; every endpoint still comes from ordered
device observations.

The three little-endian journal words remain the previous sample's lower
latch, the current selected upper latch, and the current generation. Only after
all three writes does the record count increment. A count of 512 returns
immediately with `calibration_limited` unchanged. Otherwise generation four or
more sets `calibration_limited=1` and returns. The record-cap exit therefore
wins the characterized coincident boundary, as before.

## Register allocation and caller proof

| State | Location |
| --- | --- |
| Full cumulative attempted-poll count | EBP |
| Previous / current lower latch | CX / SI |
| Retained selected upper latch | DI |
| Previous / current complete status byte | BH / BL |
| Exact validity byte | EBX bits 16..23 |
| Unrecorded seed pending / fault exit | EBX bits 24 / 25 |
| Status port outside an append | DX = `0x3da` |
| Latch and record scratch | AX; full EAX during final validity extraction |

An eligible append temporarily copies DI's retained upper into DX, derives
`DI = calibration + 6*count`, and writes lower/upper/generation in that order.
It then restores DI from DX and DX to `0x3da` before any next poll, device I/O,
normal return or fault branch. No observation or fault branch occurs while
those registers hold temporary append roles. CX, SI, BH, BL, EBX and EBP remain
intact across the record.

The append uses count 0..511; the multiplication produces 0..3066. The existing
fresh assembly gate must re-establish the COM size and footer layout. Under its
unchanged 16 KiB COM cap, the final six-byte record remains inside the reserved
3,072-byte journal and below a 16-bit address wrap. No old COM offset or hash
is asserted for this proposal.

The collector clobbers full EAX, EBX and EBP; the low 16 bits of CX, SI, DI and
DX; and arithmetic flags. It leaves segment registers untouched. Upper halves
of ECX/ESI/EDI/EDX are not used as hidden state. No caller after calibration
requires preserved volatile values: dispatch reads commands from memory, and
`new_vsync` reloads its observation state and cumulative count from the committed
fields.

Normal completion balances the single entry CALL with RET before the
`calibration_done` NOP. The collector uses no stack scratch. **Fault stack and
scratch-register bytes are not promised identical to the old program.** The
former nested `sample_status -> poll_budget` fault path carried an additional
return address; the new fault retains its actual collector call state. No old
stack image is synthesized.

## Committed boundaries and diagnostic stops

The shared exit writes the retained upper, previous/current lower timestamps,
full statuses, cumulative poll count and exact validity byte before either
returning or branching to the unchanged `timing_fault`. Record count, generation
and completed journal entries are already written at their original event
boundaries.

While calibration is running, the cached observation fields and memory poll
count may lag the registers. A stop inside an append may expose a partially
written record before its count increment; a stop during the multi-store exit
may expose a partial commit. No atomic memory snapshot is claimed. Such stops
must retain actual memory, registers and stack as diagnostics, not substitute
those memory fields for a successfully completed calibration.

Both native owners park at the exported `calibration_done` before reading the
28-byte control, 12-byte VGA register journal and exactly `count*6` calibration
bytes. Faults, timeouts or other stops fail that park before semantic calibration
parsing. Frame capture starts afterward. This boundary-specific consumer proof
does not grant general meaning to a mid-loop control snapshot.

## Focused source checks and modeling limits

The declared inventory is 87 cases: all 48 previous cases, 30 collector cases
and 9 new model-boundary cases. This is an AST-only declaration count, also
independently checked by root; it is not a collection or execution receipt.
The original 16 test function bodies and their decorators remain unchanged.

Collector cases cover the unrecorded seed, selected latches, complete validity,
last-low endpoints, consecutive records, `8 -> 1` eligibility, a seed reaching
generation four, 512-before-four-retrace exit priority, 65,535 counter carry,
last-admitted sample, immediate/late poll faults, the thirteenth rise, and fresh
state reaching four actual retraces. Actual source dataflow checks restore the
port and retained upper across appends. They do not simulate CPU timing.

The source interpreter's 512-operation bound is unchanged. Its only new memory
support is a 3,072-byte bytearray for DI-addressed 16-bit stores at offsets 0/2/4,
with little-endian writes and range/width rejection. A representative base
`0x1000` is a model address, not an assembled symbol claim. New word ADD and
signed IMUL operations retain register alias semantics; JA/JB require a current
unsigned CMP relation. Dedicated checks cover wrap, negative multiplication,
low-DI addressing, byte order, out-of-range/non-word stores, equality and stale
comparison flags. Unknown operations still fail explicitly.

A source-only acyclic control-flow count gives 11 prologue operations and a
conservative 62-operation envelope from a poll to its backedge or exit. The
longest declared eight-status stream fits `11 + 8*62 = 507`, below 512 even
with an intentionally loose path envelope. This counts substituted source
operations, not emitted instructions or elapsed time. Full 512-record behavior
is tested at the characterized count-511 boundary rather than by expanding the
interpreter limit or inventing 512 device samples.

All endpoint rules, half-wrap checks, coarse band, complete integer counts,
128-line minimum, all long pairs, fixed phase/counterfactual families, H/8,
same-frame reference, schedule formulas, record ABI and native bounds remain.
Independent source review, root integration, finite host checks, fresh assembly
and emitted review are separate pending gates. Any later native admission is
also separate; no prior failed evidence is promoted.


## Native attempt07 result

The integrated fixture SHA-256 is
`1774766ef45b483a403589d314668f4312ad822395c8bddb1787a858b964fe51`.
The host gate at that commit executed all 87 declared cases with no failures,
errors or skips; receipt SHA-256:
`b942903f2ea8faa2cd3a6c16a52226dcb0e899dba3696bdb16e1e5e111b4f770`.
Fresh assembly06 and emitted review checked the actual 4,358-byte COM,
SHA-256 `c2ddebd5affa489302f22c9139d354be1cb31b38d5edbe58b5e491c90ed3cb1d`,
including the collector branches, restored append registers, committed exit
state, journal and footer layout. The earlier source-only paragraph describes
what was pending when the proposal was prepared, not the current gate status.

The native07 controller completed in 40.97446353000123 seconds, with one passed
JUnit case and zero failures, errors or skips; the `record_property`/xunit2
warning is retained. All 11,775 pinned files and nine trees were unchanged.
DOSBox owner 38 and QEMU owner 52 ran serially, exited zero and were reaped;
1,121 paired journal calls comprise 155 DOSBox and 966 QEMU calls.

DOSBox retained 512 calibration records from 4,059 polls and one vertical rise,
with admitted spans 146 and 364 and H in `[13606/359, 13164/347]` PIT ticks.
QEMU retained 410 records from 12,362 polls and four rises, with spans 364,
431, 426 and 424 and H in `[1550/41, 15667/414]`. The unchanged pulse formula
produced delays 9,015/8,992 and width 37 for DOSBox/QEMU; images were not an
input to that selection. The [timing result](DOS_QEMU_PAIRED_TIMING_REVISION.md#native-attempt07-calibration-registers-complete-the-authored-phase-gate)
records all-row clearances for both unchanged phase families.

All four quiet rasters pass. Both DOSBox pulses match fixed source phase 1 and
both QEMU pulses match fixed source phase 0, rejecting their counterphase and
final-palette-only images. QEMU native callback lateness is 0–120 ns, below the
unchanged H/8 = 3,962.5 ns. The backend phases and pulse RGB hashes differ;
there is no exact dynamic-image-equivalence claim. Source phase models, full
DAC brackets, quantization, H/8, coarse band, 128-line minimum, all long pairs,
same-frame reference, schedule formulas and native bounds remain unchanged.

Phase receipt SHA-256:
`0396de542532b62430252d3f131d59eb847845f92e8cc2cb5e66629f85df73e0`.
Paired native receipt SHA-256:
`d0114685dc162d3625483e1555c9b75a0078eef8f9c8a09422d2c9a9da999e11`.
The full independent raw-control audit accepted this result without discrepancy.
Its exact JSON identity is recorded above and binds all original native evidence.

This is a successful fixed authored witness, not causal isolation of the
collector or general phase qualification. DOSBox per-row times and effective
per-setting runtime configuration remain unverified. Application drawing
completion, atomic CPU/image correspondence and frame/input state equivalence
remain unknown. Earlier failed evidence remains failed. Production source is
unchanged from `86a5fdb`; all 143 surface, 18 workgroup and seven campaign
promotion obligations remain open, with DOSBox default and no native08 admitted.
The next [coherent-frame obligation](DOS_QEMU_PARITY_WORK.json) is a typed
source-raster/stopped-state observation with actual mutation authority, clock
and independently observed input ownership; legacy aliases cannot manufacture
those facts.
