# Mixed OPL2 and SB16 checkpoints — local qualification

The explicit `sb16-opl` profile now captures and restores a mixed YM3812 OPL2
and SB16 graph. Authored tests qualify tone pitch, octave/key-off behavior,
register/status observations and exact hot/separate-process cold continuation.
Original Doom also passes all **six selected LE checkpoint/history restores**
and **four strict 600 ms continuations**, including full exposed CPU, both
native device queries, stored PNG, PCM/chunks, virtual time and instruction
count. **2,149 host cases and 26 distinct native cases pass.** An independent
closed-database/input audit verifies the stored artifacts, inputs and cleanup.

This extends the [RTC/SB16 timing qualification](../qemu-history-cpu-timing-2026-11-16/README.md).
DOSBox-X remains default and retained. No CI, release, shared activation or
system installation change occurs. Exact continuation under this tuple does
not establish hardware fidelity, general replay or paired DOSBox-X parity.

## Bounded native graph

The [source package](../../../native/qemu-opl-checkpoint/README.md) adds audio
core format 3 only for `fdisbull-sb16-opl`. It retains one 32 kHz mono U8 capture
path, a mandatory 32 kHz signed-16 mono AdLib voice and an optional SB16 voice
within the existing unsigned-8 mono/stereo scope. Stable card/voice identities
and the saved callback order distinguish the two voices. Existing PC-speaker
format 1 and SB16 format 2 remain separate and unchanged.

The checkpoint retains the synthesizer's nine channels/eighteen operators,
envelopes, phase, feedback, rhythm/noise, address latch, register shadow,
lookup-table selectors and actual cached LFO depths. Pointer-free state is
validated before adoption; fresh lookup tables and callbacks are reused without
replaying guest register writes. Wrapper buffers, pending samples, timer state,
shared mixer rings, per-voice resamplers and capture state also persist. A
contradictory shared mixer deadline refuses instead of selecting one silently.

The accepted tuple is tool commit `8e1c9c8cbc1a0314a18a6d533a51ed9fd36814d2`,
wheel `902bf97034e6…` with 713 exact production files, and native build
`01773e0f8e49…`. Its incremental macOS arm64 TCG build uses a separate source
copy and the retained dependency/link recipe. It is not a clean portable build
or a CI result. Earlier native binaries and their producer-bound states remain
available; cross-binary state compatibility is not claimed.

## Authored acceptance and retained counterexample

One combined native case checks independently predicted YM3812 pitch within
1.5%, an octave ratio, release to silence, guest timer/status behavior and
passive stopped queries. It captures active rhythm/noise, both armed OPL
timers and a pending DATA-only register write together with a guest-produced
11,025 Hz stereo auto-init SB16 ring. Explicit and history-root restores,
both hot and in a separate Python process, retain exact CPU, guest report/ring,
OPL/SB16 state, PCM/chunks and virtual time/count; each then matches the same
600 ms future. The real guest exits through its normal completion path.

Two additional native parameters save at source entry before any guest device
programming: idle observer and armed empty capture window. Both restore the
inactive AdLib voice with no SB16 voice, then reproduce the actual tone future
with exact CPU/device/PCM/chunks/time and fresh observer ownership. The first
attempt failed a test assumption after a successful save: the guest's later
DSP reset legitimately creates an inactive 11,025 Hz mono U8 SB16 voice. The
corrected test requires that exact future graph while retaining the absent-voice
save/restore assertion. No production or binary change supplies the correction;
the failed attempt remains recorded and is not counted as an accepted case.

A separate synth harness exercises all nine channels/eighteen operators,
rhythm/noise, deliberately divergent cached/per-chip LFO depths and a pending
DATA-only write. Hot and fresh-process cold recovery each reproduce all 2,287
future S16 samples and the complete final state. Each rejects 18 malformed
states without changing synth state or external timer-callback observations.
Valid restore invokes no timer callback. This is checkpoint/corruption coverage,
not an independent sound-fidelity oracle, and is separate from the native count.

The accepted native count is **23 retained preservation cases + one combined
OPL case + two initial-graph parameters**, with zero failures/errors/skips and
no remaining owned members in those runs. Host preservation also has zero
failures/errors/skips. Payload, selected test and dependency identities remain
unchanged within each accepted run. These totals evaluate the selected gates;
they do not measure completion of the migration.

## Original Doom hot and cold acceptance

The unchanged original EXE/WAD run in a fresh FreeDOS/CuteMouse guest using
SB16 SFX and OPL2 music. The mixed capture is nonconstant. Physical fire input
is observed as ammo **50 → 49 at A → 48 at B**; no guest memory/register writes
or IRQ-mask changes are used.

- Explicit LE checkpoint A, capture-history root A and node B restore exactly,
  hot and in a separate Python process. All six comparisons retain full exposed
  CPU, canonical source site/instruction hash, full OPL/SB16 queries, PNG,
  PCM/chunks and virtual time/count. Replacement owners, source bindings and
  observer epochs are fresh; original MZ ownership is not resurrected.
- A retains **38,390 PCM frames/122 chunks**. B and the original future retain
  **57,400 frames/183 chunks**, preserving the entire saved prefix. All four
  explicit/root-A 600 ms continuations match full CPU and all media/device/time
  fields, including instruction count.
- Cold history attachment has no live cursor/source authority before explicit
  node selection. The same six companion/linked-machine exports match hot and
  cold. All eight owned QEMU handles close with return code 0, no owned group
  members remain, and recorded immutable input/payload checks pass. Closing
  QEMU is not a guest DOS-exit claim.

The retained probe metadata still uses its inherited SB16-only format/scope
label. Its actual `sb16-opl` configuration and stored OPL query/state hashes,
not that old label, define the mixed-device observation. The independent
closed SQL/CAS/input audit verifies all six artifacts/twelve exports, nine
creation joins, three save chains and six adjacent atomic load-completion pairs.
The database and all 588 CAS files (161,450,545 bytes) remain unchanged. It
rehashes all 713 tool files, 93 runtime-kit files, sixteen external libraries
and the declared input identities; known Doom processes/groups are absent.

Explicit A and history root A retain byte-identical 14,534,202-byte native
VMState streams across 37 decoded sections, including AdLib; guest disks and
instrumentation also match despite the host-time pause. This keeps the previous
RTC/timing correction under the expanded device graph. Pre-fire FM operators
and nonconstant output are observed, but individual device PCM is not isolated.

## Claim limits

This is YM3812 OPL2 support. OPL3, MIDI, broader device graphs and electrical or
analog sound fidelity remain unqualified. The stock AdLib behavior that expires
an armed timer on the next guest OPL port access is retained; no hardware timer
accuracy is claimed. The explicit profile uses private checkpointed xorshift32
noise, not a qualified hardware noise generator. Ordinary AdLib noise behavior
is unchanged. The foreign mixer's amplitude/clipping laws also remain unchanged.

LE history remains capture-only across unobserved intervals. This gate does
not qualify task/allocation lifetime, LE trials or instruction retirement.
Commercial game bytes, register/memory dumps, audio, images, states and FDB/CAS
contents stay private. The [verification record](verification.json) publishes
only bounded findings and receipt hashes.
