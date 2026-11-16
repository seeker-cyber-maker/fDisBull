# RTC and SB16 continuation timing — local qualification

Two independent faults explained why equal stopped CPU/media observations did
not ensure equal later execution. The corrected candidate now passes a strict
**hot and separate-process cold Doom checkpoint/history matrix**: all six
selected restores and all four 600 ms continuations match full exposed CPU,
complete SB16 query, stored PNG, PCM bytes/chunks, virtual time and instruction
count. **2,138 host preservation cases and all 23 native cases pass**: 10
authored audio/RTC/ring cases plus 13 existing preservation cases, counted once.

This extends the [earlier SB16 checkpoint gate](../qemu-sb16-checkpoint-2026-11-16/README.md).
DOSBox-X remains default and retained. No CI, release, shared activation or
system installation change occurs. These are bounded continuation results,
not general record/replay or paired DOSBox-X parity.

## Two faults, separately demonstrated

**Stopped RTC drift.** The virtual profile set fixed instruction counting but
left QEMU's RTC on its default host clock. The native RTC pre-save hook updates
CMOS time, so captures separated only by host work could differ while virtual
time and instructions stayed frozen. Extracted old explicit/root snapshots
differed in exactly one of 14,516,408 native state bytes: CMOS seconds. Their RTC
interrupts were disabled; this alone did not establish the later CPU cause.

A genuine guest calendar test fails on the old prefix after a bounded 2.2-second
host pause: the guest observes two extra calendar seconds. It passes with the
explicit virtual-only RTC policy `base=utc,clock=vm,driftfix=none`. That policy is
part of launch/checkpoint compatibility. Legacy or forged policies refuse
before replacement or old-owner retirement. Standard and instruction-only
profiles retain their original descriptors and arguments. A fresh machine
still seeds its calendar from current UTC; no fixed fresh-start date is claimed.

**Host-polled SB16 DMA.** RTC correction removes that saved-state difference,
but strict Doom still fails full CPU continuation and differs in 7,732 PCM
bytes. Its explicit/root native streams are now completely identical. A
separate retained six-route old-runtime matrix restores each selected state
exactly but fails every later full-CPU comparison, including repeated use of
the same saved artifact. This eliminates a history-wrapper-only explanation.

Selected SB16 DMA was rearmed on host idle bottom halves. The new scoped path
services only the exact owned SB channel synchronously when its virtual audio
callback supplies credit. Host idle callbacks skip that selected channel;
guest I/O, unrelated DMA channels and ordinary audiodevs keep their existing
paths. Masks, DREQ and real IRQ acknowledgement remain active. Paused/busy
snapshots perform no selected transfer, and single-cycle completion does not
create selected-only idle work through reentrant DREQ release. Existing pending
nonselected work is retained. Bounded boot/preservation checks pass; broader concurrent mixed-device DMA
stress remains open. No NONE-backend rate-control patch or IRQ-mask
substitution supplies the result. Ordinary/scoped VMState layouts are unchanged;
the new native identity fences earlier states to their retained old runtime.

## Corrected hot and cold Doom acceptance

The [native source package](../../../native/qemu-sb16-dma-service/README.md)
records the exact patch and build scope. The tuple is tool commit `ee9694ca5f2e22997d98eb2dabec143085e7a0e3`, wheel
`c4d1b8ec796d…` with 713 exact production files, and native build `9be74ad11dd0…`.
The unchanged original EXE/WAD start in a fresh FreeDOS/CuteMouse guest with
11,025 Hz unsigned 8-bit stereo SB16 SFX, captured as 32 kHz U8 mono.

- One physical 500 ms left-button hold is observed across a 600 ms virtual
  interval: ammo **50 → 49 at A**, and **49 at B**. An old raw observation note
  saying 48 is incorrect; the retained HUD images control this claim.
- Explicit LE checkpoint A, history root A and capture node B restore exactly,
  hot and in a separate Python process:
  full exposed CPU, device state, canonical source site/instruction hash, PNG,
  PCM/chunks, virtual clock and instruction counter. Source/clock/audio owners
  and capture epochs are fresh; original MZ ownership remains retired.
- A retains **18,958 PCM samples/61 chunks**; B and the original future retain
  **37,916 samples/122 chunks** with the saved A prefix unchanged. All four hot/cold
  600 ms futures—explicit A and history root A—match **every strict field,
  including full CPU**, rather than accepting only media equality.
- Cold history attachment has no live cursor or source authority before
  explicit selection. The six companion/linked-machine exports match hot and
  cold. All **eight** QEMU handles close with return code 0, no owned group
  members remain, and immutable inputs/payloads match before and after. No
  guest memory/register writes or IRQ-mask changes are used. Closing QEMU is
  not a DOS guest-exit claim.

An independent closed-evidence audit verifies the six restores/four futures,
twelve export copies across six companion/machine artifacts, and a two-node
history charged at **103,462,938 bytes**. Explicit A and root A have identical
**14,516,408-byte native streams**, including RTC and all serialized CPU/RAM/
device/timer sections. Their guest disk and instrumented data also match. The audit verifies the exact
713-file prefix, 93-file native kit, 16 absolute Homebrew libraries and 497
referenced file pins. Known Doom guest/controller groups are absent; unrelated
process groups were not examined. The closed FDB/CAS is unchanged. Only its
sanitized findings and audit receipt hash are published here.

## Retained failures and completed preservation

The first new-native selection passes eight cases, then fails the old draining
fixture: the new synchronous service frontier had already captured its tail.
The assertion requiring a real nonconstant future tail correctly failed. A first revised guest variant issued programmed-I/O unmask every loop and
timed out. The corrected opt-in variant unmasks only when the sampled remaining
DMA counter falls below 80, creating a genuine queued tail. Its standalone
native run passes the original nonconstant-tail and exact hot/separate-process
cold assertions. The five default COM byte streams and offset dictionaries
remain identical. These failed attempts are retained; the complete native
selection subsequently passes; that result is recorded separately from the
standalone pass.

The authored mutable 11,025 Hz stereo auto-init ring passes even on the old
runtime. It adds useful guest-producer coverage but **does not reproduce the
Doom defect**; its retained “red” filename is not a failing-regression claim.
**2,138 installed host cases pass**, with zero failures/errors/skips and only
the expected duplicate-ZIP-member warning from an existing malformed-archive
negative. The final combined selection passes **10 authored cases**—the eight retained
SB16 cases, one RTC calendar case and one mutable stereo-ring case—plus **13
existing native preservation cases**, with zero failures/errors/skips and no
remaining owned members. Payloads, selected tests and dependencies stay
unchanged. Earlier partial/standalone runs are retained and are not added again
to this 23-case count.

The foreign mixer's amplitude/clipping laws remain unchanged. OPL/FM, broader
device configurations, paired DOSBox-X audio comparison and general replay
remain separate gates. LE history stays capture-only across unobserved
intervals; it does not qualify task/allocation lifetime, instruction completion
or LE trials. Original game bytes, audio, images, states and FDB/CAS data stay
private. The [verification record](verification.json) contains scoped findings
and receipt hashes only.
