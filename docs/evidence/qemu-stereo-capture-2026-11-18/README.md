# Native stereo capture: macOS and Linux

The opt-in `s16-stereo` observer passed **nine native cases on macOS and nine
on Linux**, with no failures, errors or skips in the accepted runs. The same
three test files cover the legacy mono paths, asymmetric stereo, active and
initial checkpoint graphs, malformed core4 rejection, and hot and separate
Python-process cold continuations. The machine-readable
[verification record](verification.json) pins the exact sources, native
binaries, installed macOS wheel, tests and private receipt identities.

## Observed contract

The authored asymmetric program runs on both QEMU and DOSBox-X. Its independent
left/right tone checks distinguish the intended channels; swapped channels and
duplicated mono output fail the negative controls. Those observations establish
channel separation and the tested pitches. They do not establish waveform
identity between different emulator audio implementations.

The active combined SB16/OPL2 witness compares 600 ms futures after explicit
hot restore, history restore and a separate-process cold restore. It checks
CPU state, complete PCM, chunk accounting, native device/mixer state, virtual
time and instruction-count position. Initial idle, armed-empty and stopped-empty
observer cases cover the graph before an ordinary SB16 stream has started.
Legacy unsigned8 mono remains covered by the same selection.

Corruption cases reject truncated or inconsistent capture geometry and the
wrong core version for an attached stereo tap. Failed fresh destinations are
closed. A stale nested payload hash is refused before replacing the original
owner, whose future remains reproducible. These checks preserve the existing
exact-native-producer restore boundary.

## Build and execution

| Host | Native build | fDisBull source and delivery | Accepted native run |
| --- | --- | --- | --- |
| macOS | Isolated copy of the pinned mixer parent; regenerated QAPI; 30 affected compile steps followed by archive, link and signing | `8b828a4be2411d3bbec265972eaccb787813b9e6`; fresh private wheel/prefix, 714 production files equal to source | 9 passed, 0 failures/errors/skips; controller 48.739 s |
| Debian 13, Linux x86_64 | Fresh headless PC/TCG build from reconstructed QEMU 10.0.13 and pinned incremental packages; 4 compile jobs, 86.08 s | `cfe53a7ffd2a1e5fdd8f094921867818b1dfdbce`; exact source package path propagated to the cold child | 9 passed, 0 failures/errors/skips; 37.49 s |

The macOS archive step initially failed to create a temporary file. Replaying
the remaining archive/link/sign plan with a private `TMPDIR` succeeded; all
completed compile outputs and original inputs were pinned before continuation.
The earlier failure receipt remains retained. A mistyped launch checksum was
also refused before execution, then corrected without changing test or runtime
inputs.

The first Linux run passed seven cases and failed the two separate-process
cold children because the child interpreter could not import `fdisbull`.
Declaring the same exact source package path in `PYTHONPATH` corrected that
environment error. The complete nine-case repeat passed without source or
native changes; both attempts are retained. The Linux runtime was separately
relocated and smoke-tested with no `LD_LIBRARY_PATH`. This establishes the
tested Debian 13 environment, with a GLIBC 2.38 symbol floor, rather than broad
distribution portability.

All builds, private prefixes, states, raw media and bulky logs remain outside
Git. There was no hosted pipeline, release publication, shared installation
activation or change to the installed DOSBox-X baseline.

## Limits

The new capture converts the internal mixer channels to 32 kHz signed16 PCM.
It does not change guest device formats, gains, OPL synthesis, DMA/IRQ timing,
headless output or clock policy. No 48 kHz, MIDI, OPL3, audible-playback or
generic hardware-fidelity qualification follows. Actual game workloads and
the remaining source, input, frame, workflow, driver and installed-package
campaigns retain their own acceptance gates. All 141 migration surfaces and
seven campaigns remain formally unqualified; DOSBox-X remains selectable and
the default.
