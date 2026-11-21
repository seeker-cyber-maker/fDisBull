# Vertical-sync witness with state held in registers

Status: **source integrated after independent review; execution gates pending**.
No project import, source-test execution, assembly or native execution has been
performed for this change. This source commit does not admit native attempt 06.
Root owns each later finite gate. Attempt 05 remains failed; its retained
quiet-frame facts and unqualified pulses are not reinterpreted here.

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
counter operations; actual emitted operand widths still require a fresh
assembly/listing review.

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

The additional code and removed sibling change assembled addresses. No old
COM size, bytes, listing or footer address can stand in for a future assembly
of this source.

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
hand-calculated register-alias behavior. Source AST counting declares 48 timing
cases. They have not been collected or executed.

## Next decision

Independent source review accepted the exact guest changes, caller lifetimes
and commit semantics. Host checks, a fresh finite assembly and independent
emitted review remain separate gates. Any later native
attempt needs fresh explicit admission and outputs. This proposal neither
repairs attempt 05 nor promises that the remaining pulse uncertainty will pass.
