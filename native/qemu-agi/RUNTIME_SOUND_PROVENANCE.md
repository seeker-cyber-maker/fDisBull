# Native AGI 2.917 sound sequencer

`overlay/target/agi/runtime_sound.c` is a portable, independently written sound
resource sequencer under `GPL-2.0-or-later`. It has no host mixer, device I/O,
interpreter globals, external allocations, or original game resources.

## Behavioral sources

The primary behavioral contract is Peter Kelly's
[Sound Resources and Playback](https://peterkelly.github.io/agi-re/spec/sound.html).
The reference source tree was read at commit
`d87bbb868035883d2ee899ccf3ef66069f9eda49`.
The implementation follows its four resource offsets, five-byte note records,
two-byte terminators, first-record tick, 16-bit zero-countdown wrap, f9 gate,
single/four-channel selection, speaker divisors, command ordering, attenuation
envelope, completion flags, and silence transitions. The fixed envelope table
is format/interpreter behavior, reproduced as the documented numeric data.

The prose about normal tone-byte output is abbreviated. The author's authored
examples in `tests/test_sound_resources.py` disambiguate it: ordinary four-channel
tone output emits its high byte then its low byte; a noise latch with the high
byte's top three bits set emits only that high byte. No original game resources
from that repository are used as tests here. No source from its implementation,
ScummVM, or another interpreter was copied into this sequencer.

Sound ticks are independent of actor cycles and have a nominal duration of
1/60 second. Adam Skawiński's maintained
[any2agi](https://github.com/SinusPi/any2agi) repository at commit
`4ff37066410d840e9e87721cfdf55b9fcfbf439e` documents this in its README and sets
`AGI_TICK = 1000/60` in its converter. This supports mapping one explicit 20 Hz
clock tick to three sound ticks without conflating sound and motion scheduling.
The converter is a behavioral reference only; none of its implementation is
incorporated. Sarien's SDL buffer cadence is approximate and is not used as an
exact audio timing oracle.

## Integration and observable behavior

The caller supplies an immutable SOUND resource callback. `start`, `tick`, and
`stop` update a pointer-free `AgiRuntimeSound` state and the caller's 256 flags.
Every participating channel tracks its next byte offset, next-read countdown,
remaining duration, tone word, speaker divisor, attenuation, and envelope state.
`remaining` includes the initial record-read tick, uses 64 bits, and is derived
from the participating channels.

`last_output` contains the ordered commands from the latest operation, each
with a monotonically increasing output sequence and sound tick. The optional
output callback observes those committed commands, allowing a host to retain
all outputs when advancing multiple sound ticks. Disabling that observer does
not change sequencing state or flags. The sound module itself does not drop or
coalesce its per-operation output; at most 16 commands fit one operation.

The single-channel output is an integer speaker divisor and gate state. The
four-channel output is the ordered SN76489 byte stream, including attenuation
and explicit silence. This implements the behavioral specification's output
boundary. Analog synthesis and delivery to a host audio device are external
services and are not claimed by this module.

`resync` reconstructs that output boundary after a snapshot is restored or a
device is rebound. It validates the state and its active resource, then emits
the current speaker divisor/gate or each four-channel tone and attenuation.
Finished and not-yet-read channels are explicitly silenced. An ongoing muted
note still restores its tone, because a later envelope or global attenuation
change can unmute the note without another tone latch. Resynchronization does
not advance time, notes, envelopes, or completion flags; only `output_sequence`
and `last_output` change. A null output callback stages those commands for an
atomic parent-runtime commit. The caller must supply the target device identity
even for a pristine inactive sound and retain or rebase its host journal epoch
when restoring a sequence number from an older snapshot. These are integration
requirements, not an added sound tick in the original interpreter's playback.

Starting a new valid sound completes the old flag before clearing the new
flag, including when both are the same flag. A start with f9 clear still
clears its completion flag; the next sound tick observes f9 and stops without
reading the resource. `stop` only completes an active sound, so repeating it
does not reassert a flag cleared by the program. The device selector is fixed
for a playback; the global attenuation adjustment is sampled each tick.

## Bounds, snapshots, and failure behavior

The accepted raw resource is at most 2 MiB. Stream parsing advances by five
bytes per event and terminates at an in-range two-byte terminator; the four
stream scans have finite work. Durations use a 64-bit total and bounded
1..65536 per-event countdowns. The note-output buffer has a fixed maximum;
counter exhaustion returns an explicit error.

Resource validation and failed starts preserve the old sound and flags.
Each sound tick calculates its state and output in a private candidate before
committing; a missing or malformed required resource leaves state, flags,
and external output unchanged. `sound_state_valid` checks structure bounds,
resource identity through the immutable caller bank, record boundaries, and
remaining-countdown consistency before a snapshot is admitted. The parent
runtime remains responsible for binding snapshots to their resource package.

## Authored verification

`tests/test_qemu_agi_runtime_sound.py` compiles this production C source with
strict C11 warnings and executes it directly. The initial verification passes
33 cases, covering the complete 65,537-tick zero-duration example, independent
channel termination, selector 0/8 behavior, f9 start and mid-playback gating,
per-note latch/data order, noise output, envelope deltas and termination,
global/device attenuation order, silent events, flag replacement, malformed
resources, failed-operation atomicity, snapshot boundaries, and equality with
the observer enabled and disabled. All resource bytes are authored in the tests.

The subsequent restore-output verification passes 49 cases in total. Its 16
additional cases cover sounding and silent speaker restoration, four-channel
tone/noise/volume ordering, completed-channel silence, a muted note followed by
unmute, the initial unread tick, inactive snapshots, unchanged flags and all
sequencing fields, staged output, and atomic rejection of missing/malformed
resources, invalid offsets/countdowns, or exhausted output sequence numbers.

A separate AddressSanitizer and UndefinedBehaviorSanitizer harness also passes
20,000 authored/mutated resource trials, checking validation rollback, failed
start rollback, admitted state invariants, bounded output, and subsequent
ticks. It observes 2,732,495 output commands without a sanitizer finding. Leak
detection is disabled for this sandbox's ptrace restriction; the sequencer
itself performs no allocation. The harness and exact source/test receipts are
retained outside the checkout, without game bytes.

This evidence validates the stated native sequencing boundary. It does not
establish original-DOS whole-engine parity, proprietary-game compatibility,
analog waveform parity, QEMU integration, or a host audio device by itself.
