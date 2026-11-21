# Vertical-sync witness with state held in registers

Status: **implemented and separately executed at
`0ff9383caaa374558ca3fc15e2b4ed3d826423ac`; paired native attempt06 failed**.
All 48 focused host cases passed. Fresh assembly05 and an independent complete
emitted-code review accepted the 4,146-byte fixture. Native06 then qualified
both QEMU pulse trials at the fixed source phase 0, while both DOSBox pulse
trials remained timing-unqualified. All four quiet RGB comparisons passed.
The full result and limits are recorded below. Earlier failed attempts and
the frozen source proposal retain their original bytes and dispositions.

## Source reason and exact scope

The earlier bit3-only waiter removed upper PIT latches for unused bit0 rises.
It still called a sampler and a poll-budget routine for every observation,
stored current/previous state after every sample, and reloaded that state on
the next call. Those stores and calls lie between the last low observation
and the first high observation used by a vertical bracket.

This proposal keeps that state in registers inside `new_vsync`, with an inline
poll admission and a common commit path on normal return or either finite
fault. The complete previous/current lower counts and full status bytes, last
selected upper count, validity byte and poll count are written back before
return or the existing `timing_fault` path. The now-unused private
`sample_vsync_status` is removed. The generic `sample_status`, calibration,
DAC triples, `wait_offset`, journal declarations and decoders are unchanged.

This removes source-observable work without selecting a new delay, phase or
threshold from pixels. It does not guarantee narrower native brackets or a
qualified pulse. Instruction changes can alter polling phase, including under
the fixed-instruction-clock profile.

## Register and state invariant

| Value | Location inside `new_vsync` |
| --- | --- |
| Total fixture poll count, inherited at entry | EBP, all 32 bits |
| Previous completed sample's lower count | CX |
| Current completed sample's lower count | SI |
| Last selected bit3 upper count | DI |
| Previous/current complete status bytes | BH / BL |
| Exact `status_valid` byte | EBX bits16..23 |
| A fresh low was observed during this call | EBX bit24 |
| Exit must continue to the original timing fault | EBX bit25 |
| VGA status port | DX = 03DAh |
| PIT and I/O scratch; validity extraction during commit | AX / EAX |
| Vertical-generation count | Existing memory field; updated only on valid observed rises |

Entry loads both previous and current states separately. It clears the flag
register, places the exact validity byte in bits16..23, and then loads BH/BL.
The fresh-low flag always starts clear, even if the previously stored current
status was low. A nonzero validity byte is preserved exactly; zero becomes
one only after the first completed sample.

At the next poll boundary, the cached fields describe the last completed
sample and its actual predecessor. The first operations are `inc ebp`,
`cmp ebp,200000` and the refusal branch. Only a successful admission rotates
`CX <- SI` and `BH <- BL`. Therefore a refused first poll cannot replace the
initial previous fields with copies of the current fields, and a later refused
poll cannot erase the predecessor of the last completed observation.

After admission, the lower PIT latch occurs before the status read. The lower
count is retained in SI and the full status in BL. The unchanged rise expression
`(current XOR previous) AND current`, masked with 8, selects only bit3 rises.
On a selected rise, the upper PIT latch follows the actual high read and its
count is retained in DI. The PIT primitive still changes AX only. A sample
without a selected rise leaves DI unchanged.

An observed valid rise increments `vertical_edges` only after that upper
count is retained. The existing comparison with 12 then decides whether the
thirteenth rise must fault. The generation field remains an event-only memory
update; it is not rewritten for unchanged or falling status.

After a completed sample, zero validity becomes one. A low status sets the
fresh-low flag and polling continues. A high status can finish the wait only
after that flag was set by an actual sample during this call. Consequently,
normal return still has a last low followed by the first high, and its upper
count belongs to that final transition.

## Return and fault boundaries

The shared commit writes `current_after`, `previous_before`, `current_before`,
`previous_status`, `current_status`, `poll_count` and the exact validity byte.
It then either returns or branches to the original `timing_fault`, which sets
the existing fault code. There is no additional I/O in the commit path.

| Boundary | Preserved behavior |
| --- | --- |
| Valid stored low, first new sample high | Count the observed rise and retain its upper; keep waiting for a fresh low before returning on a later high |
| Invalid first sample high | Retain the selected upper latch, suppress only generation increment, then mark the sample valid |
| Sample 200000 | Complete it normally; it may provide the returning high |
| Poll 200001 before any sample | Commit the untouched entry observation pair and upper, plus the refused poll count, then fault without I/O |
| Poll 200001 after samples | Commit the last completed observation pair and latest selected upper, including an upper from an earlier rise, then fault without new I/O |
| Twelfth valid observed rise | Retain its bracket and permit normal continuation/return |
| Thirteenth valid observed rise | Retain the new upper and generation 13, commit all completed observation state, then take the original fault |

The generation rules also apply while the waiter is still seeking its first
fresh low. There is no exemption for an initial high. The validity exception
suppresses generation only for the first sample with no valid predecessor;
it does not suppress its upper-latch observation.

## Stops inside the waiter

A native frame operation can stop the CPU before `new_vsync` returns. At such
a stop, memory fields awaiting commit can still describe the previous committed
boundary, while EBP and the other registers contain the in-progress state.
In particular, memory `control.poll_count` is not asserted to be the live total
during this routine. The vertical-generation field can already include a
completed valid rise while the other cached fields await commit.

The existing native collectors retain stopped control/trial memory as raw
bytes with actual registers and clocks. Their passive-equality checks compare
those actual observations; they do not decode an intermediate memory count
as the current poll total. `parse_control` is used at `calibration_done` and
after `trial_done`, which are committed boundaries. This proposal does not
rewrite intermediate raw observations, fill their fields from registers, or
invent an atomic whole-journal snapshot. Host consumers of arbitrary mid-wait
memory must keep this distinction.

## Caller and clobber review

The clobber set expands: EAX, EBX and EBP are written as full 32-bit registers;
DI is also used. CX, DX and SI remain scratch. The flags are not preserved.
The private routine does not modify segment registers or SP, and introduces
no nested call or push/pop inside the polling loop. Its final `ret` still uses
the original caller's return address.

Both callers read the journal fields after return. Neither requires BP/EBP,
DI, upper EAX/EBX, or the other scratch registers to survive. DI's other uses
belong to earlier setup, calibration and VGA-register capture. The fixed
palette writes and `wait_offset` reload their own required registers. The
selected retained guest profile already supports the existing 32-bit poll
counter operations. The separate fresh assembly/listing review below accepted
the actual emitted operand widths.

The new local labels remain within `new_vsync`. The generic sampler keeps its
own labels and source bytes. Restoring the previous waiter and its removed
private sibling reproduces the entire baseline fixture source, so no other
guest instruction region is changed by this proposal.

## Unchanged measurement contract

- Real port 03DAh observations; lower before the last low, upper after the first
  high; no endpoint moved across I/O and no interpolated timestamp.
- Channel 2 binary mode 2/divisor 65536, original gate/speaker programming, one-tick
  endpoint expansion and the half-wrap refusal.
- 512 calibration records, four calibration retraces, 200000 admitted polls,
  twelve observed vertical rises and four trials.
- Complete B and C DAC triples inside their real brackets, with journal stores
  after the upper latch.
- Absolute `ready_hi` targets: delay, then delay plus width; unchanged overflow,
  nonzero-width and half-wrap checks.
- The predeclared calibrated delay and width formulas, same-frame vertical
  reference, complete positive-integer count inference, coarse band, 128-line
  minimum and every long-pair constraint.
- H/8, both fixed phase/counterfactual predictions and every overlap refusal.
- Journal widths, decoder version, footer symbol names and all native
  ownership, input, output and deadline requirements.

The additional code and removed sibling change assembled addresses. Assembly05
supplies this source's new COM size, bytes, listing and footer addresses; no
earlier fixture identity was substituted.

## Authored source/dataflow checks

The bounded interpreter now represents full 32-bit registers with correct
16-bit and byte aliases, and recognizes the needed logical shifts, OR and
unconditional jumps. Its 512-instruction source-check limit is unchanged.
The PIT primitive remains separately checked; no instruction timing, devices
or native producer are modeled.

The existing generic sampler and DAC contract tests remain. The former
single-sampler vertical cases now exercise the actual whole waiter with one
admitted sample followed by a refused poll, so they observe the real shared
commit path rather than an unused helper. Existing whole-waiter cases retain
their device-event and end-state expectations, with the memory poll counter
now committed once at exit.

Additional cases cover distinct entry previous/current state on an immediate
fault, a retained upper from an earlier rise on a later fault, valid versus
invalid initial-high generation 13 behavior, an exact nonzero validity byte,
the 65535/65536 counter boundary, a normal return at poll 200000, and independent
hand-calculated register-alias behavior. All 48 declared timing cases passed
under the separately admitted finite host gate at the exact integrated source.

## Executed host and assembly gates

Independent source review accepted the exact guest changes, caller lifetimes
and commit semantics. The host gate passed 48 cases with no failure, error or
skip in 0.405140337 seconds, with all 5,691 tracked inputs unchanged. Its owned
worker exited zero and was reaped; no timeout or cleanup error was recorded.
Host receipt SHA-256:
`b18e48fbc1dbeaf171c04a6f37de54f12375851de9aeab2579f2698b8493b75b`.

Fresh assembly05 completed in 0.117575721 seconds. The resulting COM is
4,146 bytes, SHA-256
`fc210fae31c7bec5d24f5899348865478e0947aa73e61335830522de0025487d`.
Independent static review reconstructed all 4,146 bytes from 389 emitting
listing rows, covering 341 instructions, 102 absolute relocated words,
50 direct control transfers, nine PIT macro expansions, both complete DAC
triples and all twelve footer symbols. All 63 changed waiter instructions
were checked, including the 15 new operand-size prefixes. The whole code has
17 such prefixes, including two in the retained generic sampler. This review
did not execute the guest or rebuild either emulator producer.

Assembly receipt SHA-256:
`ff1408b4824155e7c0170b7e04867ecaee40576f6fb62a1ac17d8d738b3b86ba`.
Independent emitted review SHA-256:
`e48d001e5020e531a0513f24e89b263ee82b7a862589386d02e307cc7d4dfb25`.

## Native attempt06: QEMU pulse phase observed, paired gate still failed

The one admitted native phase used the exact source commit above and the
same retained producers. It completed in 40.894148974 seconds. Both serial
owners exited zero and were reaped. The owned pytest worker returned one
because the final paired phase assertion failed; setup and teardown passed.
The existing `record_property`/xunit2 warning was retained and did not cause
the failure. All 11,768 pinned files and nine trees matched before and after.
No timeout, adopted child or cleanup error was recorded. The normal final
process-group cleanup signal remains in the ownership receipt.

| Observation | Attempt06 result |
| --- | --- |
| Four quiet rasters | Full authored RGB and cross-backend equality passed |
| DOSBox calibration | Spans of 158 and 352 lines; H in `[6329/167, 6525/172]` PIT ticks |
| QEMU calibration | Spans of 192, 416, 416 and 405 lines; H in `[7522/199, 15745/416]` PIT ticks |
| Both DOSBox pulses | Unqualified: row 100 phase 1 intersects a complete DAC-write interval |
| Both QEMU pulses | Fixed source phase 0 observed; counterfactual phase 1 and final-palette-only predictions rejected |
| QEMU native row timing | 200 rows in each pulse receipt; callback lateness 6–126 ns, all strictly below H/8 = 3,962.5 ns |

Each owner executed two quiet and two pulse captures in the fixed order. The
calibrated delay/width remained 9014/37 PIT ticks for DOSBox and 8992/37 for
QEMU, selected before images and reused for both pulses. All four quiet RGB
hashes are
`141a920ca2ecdd0d6fd7684eca3918d7d9ce66f74573266a15656dd107295939`.
Both QEMU pulse RGB hashes are
`6ac6ee1c5e63281ab20344aa0ed251a2d10288ffa2c5248c242c21d74e90c2fa`.
The latter match both independently fixed source-phase predictions; the
opposite phase and a completion-time palette expansion produce different
images. Native row times check the declared lateness bound after prediction;
they do not choose pixels or shift a predicted row.

The exact DOSBox refusals remain informative:

| Pulse | First fixed-phase refusal | Exact overlap in PIT ticks |
| --- | --- | --- |
| 3 | Row 100 phase 1, upper endpoint reaches the C-write interval | `159843/229792`, approximately 0.695598628 |
| 4 | Row 100 phase 1, lower endpoint reaches the B-write interval | `703/688`, approximately 1.021802326 |

Pulse3's overlap includes the declared H/8 allowance. Without that allowance,
the upper endpoint would precede C, but individual DOSBox callback times are
not observed and the allowance remains part of the fixed experiment. Pulse4's
overlap is at the lower endpoint and is independent of H/8. Neither observation
authorizes weakening the bound, moving a pulse or selecting a phase from its
captured image.

Phase receipt SHA-256:
`9223a1da9379b9acfbf5b9295de490ed288a1707633953a2f62a19839a01523e`.
Paired native result SHA-256:
`0913e53af7f00d9c695c291b3247c9056c1de4b80ac36ef72a5f4c6c3a3c3326`.

## Remaining decision

Native06 provides two qualified authored QEMU pulse observations under the
unchanged measurement contract. It does not establish general raster parity
or isolate the register change's effect from changed instruction layout and
polling phase. The full paired phase gate remains failed because DOSBox still
has two timing ambiguities. The next step is an independent uncertainty and
measurement review; this checkpoint admits no native07 or automatic retry.
Production source, defaults, all 143 surface, 18 workgroup and seven campaign
promotion obligations remain unchanged. Earlier failed attempts stay failed.
