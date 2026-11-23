# DOSBox-X steady VGA scanline phase diagnostic

## Source timing

The existing QEMU model samples mode 13h source row `r` at
`frame_start + floor(H/4) + 2*r*H`, with `H` the physical line period.
The chain-4 source admits a 320×200 image with two physical lines per
logical row. [Native frame source](../native/qemu-video-frame/qemu-video-frame.patch)

Retained DOSBox-X `src/hardware/vga_draw.cpp` initializes `render_step` to
0 during draw setup. In ordinary VGA mode with doublescan disabled and
two physical lines per logical row, setup halves the output height and sets
`render_max=2`. The timed draw starts at `H/4` plus the top blank skip.
`VGA_DrawSingleLine` draws when `render_step=0`, advances the step even on
a skipped line, and ends after the 200th drawn row. With no top blank
skip, the first completed raster therefore ends on physical line 398
and leaves `render_step=1`. A later healthy raster starts with a skipped
line, samples physical lines 1, 3, …, 399, and again leaves
`render_step=1`. This source inference applies to the timed renderer
under this geometry and profile. It does not identify the installed
binary's exact source tree. The retained source file SHA-256 is
`6c1cbe3db39828bc5c9d634aba494951f390c3ee41b3d742a8458635ad0ccb1d`.
[Historical Native07 qualification](DOS_QEMU_PAIRED_SOURCE_FRAME_PLAN.md)

## Current macOS arm64 witness

The diagnostic QEMU producer used `frame_start + floor(H/4) + (2*r+1)*H`
and reported its own model, `qemu-vga-chain4-dosbox-steady-diagnostic-v1`.
The sealed Native07 test and oracle were untouched. A private runner reused
the authored COM and both independent PIT/DAC predictions. Its diagnostic
host adapter checked the distinct native model and intended row deadlines.
The pulse parameters came from guest device timing before any image was read.
Both guests ran the same COM and reported 400 displayed physical lines,
449 total physical lines and VSYNC starting on physical line 412.
The diagnostic QEMU line period was 31,700 ns.

| Observation | Installed DOSBox-X | Diagnostic QEMU |
| --- | --- | --- |
| Two quiet rasters | Full authored RGB equal | Full authored RGB equal |
| Two pulse rasters | Same RGB as diagnostic QEMU | Matches the fixed phase-1 oracle on both trials |
| Independent pulse timing | Unqualified on both trials | Phase 0 and final-palette-only predictions rejected |
| Row callback lateness | H/8 allowance assumed | 4–124 ns observed, within H/8 of 3,962.5 ns |

All four actual RGB pairs matched byte for byte. DOSBox-X's PIT-only
row-100 phase-1 band still crosses the C-write bracket on trial 3 by
`53603/60242` PIT ticks and the B-write bracket on trial 4 by `55/91`
PIT ticks. Those trials cannot independently identify the installed
DOSBox-X sampling phase. The earlier Native07 qualification remains tied
to its original pinned producers.

The diagnostic QEMU refused native checkpoint export with
`Diagnostic VGA sampling cannot be checkpointed` while the raster stream
was owned. The runner propagated that expected native refusal as a
`ValueError` in the raw record. Both guests exited zero and were reaped.
The boot images and pinned executables passed identity readback. No
diagnostic build or runtime setting was installed.

| Evidence | SHA-256 |
| --- | --- |
| Authored COM, 4,358 bytes | `c2ddebd5affa489302f22c9139d354be1cb31b38d5edbe58b5e491c90ed3cb1d` |
| Installed DOSBox-X | `df2080bcd2e65aa8a8511ca0692d45d9b9f5355d673a83967c4abdab9672c47e` |
| Diagnostic QEMU | `5ecf3194f0fea0bccc616ba5623dc450c6fc45da8c1b9d88b6cfadb5cba482c2` |
| Diagnostic qemu-img | `414fba3a549725b9cee8cd32f43f7bdbfbea26efb0c31f1a7024dbc391a1cab0` |
| Private raw witness | `770e4342c145a2451c173511526a50033d1484113345600c1ad694280cae5b09` |
| Quiet RGB, both backends | `141a920ca2ecdd0d6fd7684eca3918d7d9ce66f74573266a15656dd107295939` |
| Pulse RGB, both backends | `ea3c07508b70c79784eeffab0106e1345771f9dc35c218cd3584ffefde7b5d23` |

## Translated-pulse follow-up on macOS arm64

One new paired run reused the same pinned producers, authored COM and
strict PIT/DAC oracle. The prior raw timing intervals, before image
comparison, allowed shifting the first scheduled DAC write by −1 PIT tick
and the second by +2 ticks. The runner declared that single change before
starting either guest. It did not alter the geometry, full-write uncertainty
rule, H/8 allowance, phase models or historical runner. Actual writes were
bracketed afresh because nominal waiter changes do not translate all
observed write windows by the same amount.

All four pulse RGB images now match the complete, timing-separated phase-1
prediction and reject a final-palette-only image. Both quiet raster pairs
also retain their exact RGB identity. The strict paired gate still refuses
three trials because phase 0 has an ambiguous row. The separate
[phase witness](../tests/support/paired_video_phase_witness.py) compares
only independently determined counterphase rows and can positively exclude
phase 0 where such a row differs from the captured RGB.

| Producer and trial | Phase-0 overlap | Phase-0 rejection from a timing-separated row |
| --- | --- | --- |
| DOSBox-X pulse 3 | Row 100, B write, `129253/166616` PIT ticks | None |
| DOSBox-X pulse 4 | Row 101, C write, `4001/1412` PIT ticks | Row 100, phase 0 predicts A and the image contains B |
| Diagnostic QEMU pulse 3 | None | Row 100, phase 0 predicts A and the image contains B |
| Diagnostic QEMU pulse 4 | Row 101, C write, `941/1656` PIT ticks | Row 100, phase 0 predicts A and the image contains B |

The audit reparsed the raw PIT journals, reconstructed the line-period
bounds, checked each retained RGB hash and used no native row time to pick
a predicted color. DOSBox-X pulse 3 remains compatible with the conservative
phase-0 timing window. This is steady-mode evidence for the authored
geometry. First-raster timing and paired checkpoint behavior remain open.
The diagnostic still refused checkpoint export while its raster stream was
owned. Both guests exited zero and were reaped. Boot images and producer
identities passed readback.

Native receipt SHA-256
`4f6fdbdd9cd1b382aac632fa33a953801b5f7bbe348fd36e13242bf1bb0646bb`.
Timing audit SHA-256
`d0cf9401d35d4d784975a695c55b55505d8dd0e150ccb5589a2ff256771c0e94`.
The exact producer and COM pins are listed above.

## Guest mode-setup witness

A separate, opt-in [native test](../tests/test_qemu_vga_mode_setup_native.py)
uses the existing standard-VGA I/O trace on the pinned QEMU producer
`91321d463ad4b06e183f46cc1ab356dc4b2a23dd831531761b7f39845a835fe9`
and VGA BIOS `651513519f9e0d5b99d3b051a8f5c68db69e987339b59a441d371068c34c146b`.
The authored COM enters mode 13h from text, waits 45 ms of native virtual
time with stable VGA configuration, attaches and detaches the source
stream while stopped, and reissues the same mode set in the guest.

The two BIOS requests each emitted the same 915-write journal. The
qualifying suffix follows the retained SeaBIOS `stdvga_set_mode` source.
It writes all five sequencer and all nine graphics registers, unlocks
CRTC writes, programs CRTC 00h–18h, writes miscellaneous output and
enables display. The witness compares this ordered suffix to the raw
mode-13h configuration after the guest returns from INT 10h.

| Guest or observer event | Native evidence |
| --- | --- |
| Initial mode-13h entry | Complete setup suffix and changed effective configuration |
| Same-mode BIOS reapply | Complete setup suffix with equal final raw configuration |
| Warm attach and detach | Zero VGA I/O writes with equal configuration and stopped virtual time |
| Isolated write of the current sequencer reset value | Two index/data writes with equal configuration generation |

The BIOS mode set writes sequencer register 0 directly with `03h`.
An asserted-to-released reset transition is therefore unsuitable as the
sole setup marker for this firmware. An isolated write of `03h` also
cannot identify a mode set. The trace identifies the bracketed firmware
transaction. It does not expose a guest-virtual timestamp for each write
or establish when DOSBox-X executes its own draw setup. The evidence
therefore supports a bounded source-side witness and leaves a persistent
cross-backend phase origin unqualified.

The probe scopes logging to the disposable QEMU process and reads stopped
configuration. It uses the existing frame stream and introduces no live
phase or checkpoint state. Raw receipt SHA-256
`2b149a7b0a88fdcfee566b84a4766919b80d90153e7bc18969a140ac374bafef`.

## Persisted native mode phase

The current opt-in QEMU producer observes the completed standard BIOS
mode-13h programming transaction and uses it as the age boundary for
sampling. The first raster uses phase 0. Steady rasters use phase 1.
A warm stream attach preserves the observed mode age.

Native format 5 restores the same setup stamp and pending row schedule.
Cold witnesses passed before the first draw, at 65 initial rows, and at
65 steady rows with the preceding raster retained. Exact pixel hashes,
intended and actual row times, prefix, and armed deadline survived with
a fresh token and epoch. The public DOS process test also passed hot
and cold restore across the initial-to-steady transition. Default-off
uses the existing native model and format 4.
[Source recipe and receipt hashes](../native/qemu-video-mode13-phase/README.md)

The local paired warm-raster fixture also ran with the production
`dosbox-mode13` host profile and the installed DOSBox-X. Both quiet and
both pulse RGB pairs matched byte for byte. Pulse 3 independently
selected phase 1 and rejected phase 0 on both engines. Pulse 4 remained
timing-ambiguous because the phase-0 row 101 interval overlaps a DAC-write
window. After the QEMU comparison, public format-5 save and load reproduced
the retained phase-1 rows and pending deadline with fresh ownership.
Both original owners reaped and the pinned inputs rehashed unchanged.
Private paired receipt SHA-256
`e9e257369ae72d7843b37e9fd1328c91672a0e1d442c43a527472684cdf47d41`.

## Remaining qualification

- Obtain independent DOSBox-X timing clearances for both pulse trials.
  Record the effective VGA renderer settings and tighten the VGA-edge and
  DAC-write brackets before any pixel read. Keep the phase families and
  overlap refusal.
- Measure DOSBox-X's effective draw setup boundary and pair first rasters,
  warm attachment and equivalent reapply with QEMU over the same declared
  geometry. Qualify additional programming sequences and modes separately.
- Exercise both engines through the same protected game's palette/origin
  changes and replay its dynamic raster after a native checkpoint.
  [Current QEMU frame contract](QEMU_FRAME_CONTRACT.md)
