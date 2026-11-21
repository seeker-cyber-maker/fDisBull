# Strict paired ordinary-pause witness

The original witness was proposed from `353df71e2281a4078ac5c3ff87f89cd3ccdbb17e`.
This document now records a source-only public-observation capture revision
prepared from the strict witness at `f69a946110fce16bdd3f5d00daf7ad561b374783`.
The revised source has not
been imported, collected, tested or executed and grants no new execution admission.

**Historical source precondition:** at the original base, a COM process retains its reserved
DOS parent-return breakpoint. Public `resume()` rejects any remaining machine
breakpoint, while the public delete operation correctly reserves that control
until process completion. Therefore the proposed QEMU half currently reaches
an honest public refusal. The root has been notified; a separately reviewed
host decision is needed before native admission. This fixture does not remove
the return control, edit the breakpoint dictionary, call raw QMP continue, or
substitute a raw machine session to bypass that restriction. The integrated
86a5fdb host includes the separately reviewed public asynchronous-resume fix;
its behavior still requires the strict observations below.

## Question and retained legacy evidence

Does the actual ordinary-pause boundary leave the sampled guest clock, full CPU
register object, status and selected RAM exactly unchanged until an explicit
resume? The reference is the historical strict DOSBox fixture and its retained
independent review, SHA-256
`ed49e7ca9429ab9ade790d16fcdaf4e19251351f4d4aad6b33db7984bce65dbe`, in
`pause-candidate-native-review-20261119/INDEPENDENT-NATIVE-REVIEW.md`.

The corrected legacy producer previously passed eight episodes and four
immediate timing/status/register/timing blocks per episode. Its result was
`c654c6922fd4f814ab8ebcd9169161ffff856c93181f623330d253cdc71d7c5f`, and its
170-call journal was
`c4bae356d990ee677c0ab9cdfdafea2d47db6cc20f2ddfac483f6bd443d0020a`.
Those are historical identities, not a new raw-journal audit: the original
temporary directory is no longer present in the current workspace. The prior
stock failure, with PIC ticks 9 through 20 after one stop, remains a separate
failed tuple. This new witness neither reruns nor relabels that failure.

The exact ten bytes remain `b83412bb78564043ebfc`, SHA-256
`fc98fc96de8fa01651cd36f3877242a0cc35cf306621d2236db205e9b3718d91`. They set
AX=1234h and BX=5678h, then execute INC AX, INC BX and JMP back indefinitely.
There is no assembler, code patch, memory stimulus, game, snapshot or input.

## Minimum finite selection

One node is proposed:

`tests/test_paired_pause_native.py::test_native_paired_strict_pause_keeps_immediate_clock_register_ram_brackets`

It owns at most two native lifetimes: original DOSBox first, reaped completely,
then the current source-fence QEMU. There is never more than one live native
owner, no replacement, and no restore overlap. Failure on DOSBox prevents QEMU
construction. Failure in an episode prevents all later guest work.

Each owner receives one 50-second work deadline and at most 10 seconds cleanup.
The separate controller must enforce a 120-second whole-case bound, including
private setup, plus explicitly bounded preflight/postflight. The fixture caps
each owner's public/RPC journal at 512 calls and QEMU's combined post-constructor
QMP/GDB journal at 1,024 calls. Each JSON evidence file is at most 8 MiB, each
complete native log at most 2 MiB, and the campaign output cap is 128 MiB.

### Receipt-retention revision

Strict pause attempt 02 failed during QEMU episode 5 because pretty-printed
JSON exceeded the original 4 MiB per-file cap. Its last persisted QEMU journal
is 4,164,213 bytes; the same parsed values encoded as compact JSON, including the
trailing newline, occupy 2,460,420 bytes. The complete DOSBox journal shrinks
from 247,456 to 150,288 bytes. Both conversions preserve every parsed value.

The largest of the four complete observed QEMU episodes contributes 537,618
compact bytes across its episode, public-call and native-call records. Using
that measured contribution for eight episodes, with the retained initial
metadata, projects 4,317,832 bytes for QEMU and 4,468,542 bytes for the paired
aggregate before final cleanup or failure additions. These are sizing
estimates, not observations of the missing episodes or a guaranteed maximum.
Compact encoding alone therefore does not justify retaining the old 4 MiB cap.

The receipt-retention revision changed only JSON whitespace and the finite evidence-file
limit to 8 MiB (8,388,608 bytes), including the final paired aggregate. It keeps
sorted keys, strict non-NaN encoding, the trailing newline, the pre-write byte
check, atomic replacement, every raw field, every duplicate observation and
all error-retention behavior. It introduces no compression, interning,
truncation, abbreviated replies or reconstruction format. Ordinary JSON
parsing recovers the same complete value structure.

The eight running intervals, four immediate brackets per stop, clocks, call
limits, deadlines, qualification checks and 2 MiB native-log limit remain
unchanged. The controller keeps the 128 MiB total output cap and additional
256 MiB free-space reserve. Both earlier failed attempts remain failed and
immutable. The revised source requires independent review, exact integrated
host pins and a separate fresh native admission.

### Public-observation capture revision

Strict pause attempt 03 retained the full compact paired aggregate of
4,467,660 bytes within the 8 MiB cap. Both eight-episode bodies completed, but
the independent final checker failed with
`QEMU public control results differ from actual dispatch replies`. The attempt
remains failed; completed bodies do not qualify the whole gate.

The public-call journal already deep-copies each immediate dispatch reply.
`_Qemu.call` returned the original result, and the episode/control/block records
kept its nested `mapping.process` reference. Session cleanup subsequently
changed that shared object. All eight stored resume results, eight first-stop
results and 32 stopped-status blocks then differed from their original public
replies in the same six process fields. The drift consists of capture epoch,
`machine_closed`, source live flag/ranges/status and process state; it is
confined to `mapping.process`. Every other block field remains equal.

The proposed correction is one line: `_Qemu.call` returns a `deepcopy` of the
result from its existing journal call. This captures every public result at
return, including each block status, while leaving the journal's own copy and
every native wrapper untouched. Exact equality checks remain unchanged; no
field is ignored, repaired or normalized. No additional guest operation is
introduced, and future capture or oracle failures still fail the attempt.

Compact JSON, the fixed 8 MiB evidence-file limit, 128 MiB total output cap,
256 MiB reserve, eight waits, four brackets, clock rules, deadlines and all
other bounds remain as reviewed. Original attempts 01, 02 and 03 and their
source/controllers/raw receipts remain immutable failures. The new controller
must retain a pending host identity until root integrates and reviews the
complete proposed source. Separate fresh admission is still required.

The controller must pin the clean integrated host, this file, the existing boot
preparation helper, current Python/interpreter dependencies, firmware, media,
mcopy, producer manifests, binary/library/source closures and generated wrapper.
It must enforce live output/log growth, capture every native spawn, retain logs
after exit, prove reaping even on construction failure, and fail on every skip.
The test's own successful owner assertions supplement that independent policy.

## Exact input tuple and profile

| Input | SHA-256 |
| --- | --- |
| Original corrected DOSBox | `bfdacbed027ae16f48256abc5d0309cc8984569a2946dabea2f4d43907d43e71` |
| Current source-fence QEMU | `b42b624f452e19c1560f1af45712fc93f6859ac753bab73a1495c49188cca0af` |
| Matching qemu-img | `b8687f147c9ac6900e840619196abdec4d5f4890d94be6876eae0c9e09985f03` |
| Original FreeDOS boot image | `552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc` |

The opt-in variable is `FDISBULL_REQUIRE_PAIRED_PAUSE=1`. The controller also
sets its private pytest marker `_fdisbull_paired_pause_owned_gate` to
`fdisbull-paired-pause-owned-gate-1`, requires maxfail=1 and serial execution,
and supplies `FDISBULL_PAIRED_PAUSE_DOSBOX`,
`FDISBULL_PAIRED_PAUSE_DOSBOX_LIB`, `FDISBULL_QEMU_DOS`, `FDISBULL_QEMU_IMG`,
`FDISBULL_QEMU_DOS_BOOT_IMAGE`, `FDISBULL_QEMU_DOS_MCOPY` and
`FDISBULL_QEMU_DOS_FIRMWARE`. Setting these names alone is not admission.

The generated wrapper uses the current admitted interpreter and execs exactly
the pinned DOSBox binary. Its selected private library directory is supplied
only to DOSBox via `LD_LIBRARY_PATH`, with dummy SDL drivers and an explicit
environment whitelist; the host and QEMU do not inherit it. The legacy profile
is copied from the historical strict test: svga_s3, normal core, fixed 157600
cycles, frameskip=0, doublescan=false, scaler=none, scanline render on demand=false,
full-triple palette updates and DAC6. `fast_forward=false` is explicitly set
and checked. Full effective-profile verification remains false as in the prior
receipt. QEMU selects its actual virtual-clock and precise-retrace profiles.

All runtime files belong in the fresh private output directory selected and
pinned by the separately admitted controller, without Git ancestry. The
authored COM and original/prepared boot identities must survive.

## Exact episode and stop boundaries

Both backends use the historical eight predeclared running intervals, in host
milliseconds: 25, 35, 45, 55, 65, 75, 85 and 95. These intervals are not converted
to guest time, adapted to observed progress, or used after a pause.

DOSBox sends `execution.continue`, waits once for that operation for the stated
running interval, sends `execution.pause`, and waits once for the actual pause
operation. Its operation acknowledgement is retained independently of the
stopped result. The existing `TARGET_NOT_RUNNING` race path reuses the original
continue operation solely to observe the actual stop; it never retries pause
or continuation, and the actual stop must still have reason `pause`.

QEMU calls public `resume`, retains actual running status, spends the same
declared host interval running, then calls public `pause`. The real QMP
`cont`/`stop` acknowledgements are retained separately from the public result's
actual nonrunning `query-status` receipt. The native paused runstate must be
observed. QEMU is not assigned a DOSBox operation ID, stop schema or revision.
The current native source calls `vm_stop(RUN_STATE_PAUSED)` from QMP; its ordinary
main-loop path disables ticks, pauses vCPUs, and publishes STOP before returning.
That source trace is not a substitute for the strict repeated observations.

## Immediate no-drift oracle

After the actual stopped result there are exactly four fixed brackets:

1. Guest clock observation.
2. Full stopped status object.
3. Full register object.
4. The ten code bytes at the independently observed initial real-mode load site.
5. Five RAM bytes at physical 046Ch, containing the BIOS tick word and rollover byte.
6. Guest clock observation.

No sleep, extra alignment read, continuation, step, input, checkpoint, timer
budget or image call occurs between those brackets. The earliest stopped
acknowledgement contains no clock; the first immediate clock observation is the
reference. This is finite sampled no-drift evidence, not proof of an atomic
acknowledgement/clock snapshot or indefinite continuous quiescence.

Valid clock/register/status/RAM differences remain in the journal. The fixture
finishes the four admitted brackets while the APIs and stopped state remain
valid, then rejects any difference before the next resume. Invalid transport,
session, native state, clock shape or epoch terminates observation immediately
with the partial raw record. No invalid evidence is replaced by a later sample.

DOSBox compares entire clock replies, full statuses, full register objects and
full RAM replies, including session and stopped revision. Its domain is
`PIC_Ticks_milliseconds`; no positive delta is permitted. QEMU compares every
guest/owner/profile/native field from its public clock, including the complete
native virtual-clock receipt and separate instruction-counter receipt, plus
full status/register/RAM objects. Only public `sequence` and
`host_monotonic_ns` are classified separately as host observation bookkeeping.
They remain in the raw evidence: sequence must increment by one, host timestamp
must not regress, and both clock epochs stay fixed. No guest field is removed
from equality and no clocks are equated across backends.

Across each explicit running interval, the backend's guest clock must increase
and the observed low-word AX/BX pair must change. QEMU's native instruction
counter must also increase; it is an execution-model progress witness, not a
claim about architectural instruction retirement. A coincident modulo return
to the same AX/BX pair fails this finite witness; it does not authorize a longer
run or an inferred amount of progress. The original fixture writes no data RAM,
so BDA bytes are compared only for exact stopped stability, not prescribed values
or cross-backend numerical equality.

## Source review checklist

- Verify the literal ten-byte program and unchanged eight waits/four brackets.
- Trace ACK versus actual-stop handling in both real adapters; refuse a guessed
  session/operation/revision mapping or a still-running clock observation.
- Check that raw replies survive comparison failures, and that no mismatch can
  reach another resume or construct a replacement native owner.
- Inspect QEMU's two explicitly separated host clock fields; all remaining
  clock keys, nested native fields, status/register/RAM objects stay exact.
- Confirm real transport wrappers delegate actual QMP/GDB calls and do not
  fabricate responses or expected guest values. No native execution packet is
  allowed within the four passive brackets.
- Review original-owner cleanup, complete after-exit log retention, all finite
  caps, private output roots, wrapper/library isolation and input postflight.

The gate can qualify this ordinary-pause tuple and these bounded observations.
It cannot close unrelated game failures, establish other pause modes, or promote
frame/CPU-image equivalence.
