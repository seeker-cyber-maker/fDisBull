# Selected SB16 DMA on the virtual audio frontier

This incremental QEMU 10.0.13 patch follows the exact
[SB16 checkpoint package](../qemu-sb16-checkpoint/README.md). Its adjacent
manifest pins the prerequisite binary/source and all four before/after hashes.
Keep the old runtime for its own checkpoints. No cross-binary state loading is
claimed. The corrected tool also pins `base=utc,clock=vm,driftfix=none` in the
virtual clock profile; the initial calendar is seeded at fresh launch, then
follows VM time. Earlier implicit host-RTC states require their original policy.

## Fault and correction

The prior selected SB16 channel was repeatedly serviced by an idle bottom half
on the host event loop. Guest-generated auto-init ring data and IRQ delivery
could therefore depend on host service ordering, even when the full saved
CPU/RAM/device stream, virtual time and instruction count matched. Equal PCM
frame counts alone did not prove equal samples or callback frontiers. The
[dated qualification](../../docs/evidence/qemu-history-cpu-timing-2026-11-16/README.md)
retains the old counterexamples and separates the independent RTC leak.

The selected `fdisbull-sb16` channel now consumes each audio-free callback's
credit synchronously before the mixer consumes its output. Exact card,
controller, channel and registered-handler ownership are checked. The narrow
helper services one channel, honors its mask/DREQ and refuses work while paused
or inside instrumented restore. Guest I/O still services requested channels at
its normal deterministic instruction boundary. Host idle callbacks skip the
selected channel and rearm only for nonselected work. A single-cycle DREQ
release may reenter the controller; that path avoids selected-only idle work
while preserving requests and already pending callbacks for other channels.

Other audiodevs and DMA channels retain their ordinary service path. Concurrent
mixed-device scheduling beyond the observed boot/preservation cases is not
qualified. A transient reentrancy flag is valid only while DMA is running;
capture already refuses that state. Ordinary and scoped VMState field lists,
SB16 audio-core format 2, PC-speaker format 1 and outer ownership formats stay
unchanged. Snapshot authorization, fresh owner/epoch checks and passive restore
remain required. This changes no decoder, layer, hook, history or trial API.

## Build and qualification

Verify each prerequisite and `before_sha256`, apply the pinned patch with
`patch --batch --forward -p1`, and verify every `after_sha256`. Use a separate
source/build copy. The accepted same-Mac recipe regenerates existing trace
sources, recompiles the retained 30-object dependency closure (including all
23 recorded affected ABI-header consumers), updates the copied archive and
replays the 782-argument link and signing commands. It is an incremental macOS
arm64 TCG build, not a clean portable build or CI result.

The new mutable 11,025 Hz stereo auto-init ring test requires exact CPU, guest
report/ring, device, PCM/chunks and time/count across repeated explicit/root
restores. It supplements the actual original-Doom counterexample; it also passed
the old backend and must not be represented as that backend's failing test.
The RTC guest regression independently detects host time advancing a stopped
calendar. Existing mono/stereo, auxiliary timer, initial and draining audio
checks retain their strict signal/state assertions. The draining fixture uses
ordinary guest controller I/O to create genuinely queued PCM between mixer
callbacks; all five default waveform fixtures remain byte-identical.

Fresh acceptance and remaining gates belong in the dated receipt. Matching a
bounded continuation does not enable QEMU record/replay, prove retired
instruction counts, general deterministic replay, ideal audio amplitude or
DOSBox-X parity. DOSBox-X remains default and retained. No CI, release or shared
installation is performed. Commercial payloads and raw states/media stay private.
