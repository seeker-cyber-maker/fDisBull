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

## Paired declared pulse windows

A fresh pair ran the same authored COM on installed DOSBox-X and the
production QEMU `dosbox-mode13` profile. It used two predeclared widths,
40 PIT ticks for pulse 3 and 36 for pulse 4. The prior PIT-only record
bounded the pulse-4 C overlap and motivated advancing that write. The
guest retained the same calibrated delay for both pulses on each engine.
The runner used no candidate pixels to pick the windows and kept the
original strict oracle.

| Engine | Pulse 3 | Pulse 4 |
| --- | --- | --- |
| QEMU phase profile, delay 8,991 ticks | Full phase 1 prediction matches and phase 0 is excluded | Full phase 1 prediction matches and phase 0 is excluded |
| Installed DOSBox-X, delay 9,013 ticks | B write overlaps phase-0 row 100 by `18077/15132` PIT ticks | B write overlaps phase-1 row 100 by `849/388` PIT ticks |

All four corresponding RGB images match. The independent audit rebuilt
the line periods from native guest journals and verified each full RGB
hash. QEMU reports phase 1 and a maximum callback lateness of 124 ns
in both pulse trials. DOSBox-X remains timing-unqualified on both
windows. The newer C window separates on both engines. The remaining
DOSBox-X ambiguity is at the B-write interval, even though its schedule
uses the same nominal delay. The qualification depends on the actual
write and retrace brackets rather than nominal pulse placement.

First draw remains unqualified on DOSBox-X. In the retained producer
source, `VGA_StartResize` can schedule a later `VGA_SetupDrawing` through
the PIC, so an INT 10h return or equivalent register readback establishes
a guest programming boundary only. The completed-frame RPC records a
frame ID, renderer mode ID and millisecond `PIC_Ticks`. It supplies no
effective draw-setup timestamp or row callback time. That resolution
cannot distinguish a physical scanline of approximately 31.7 µs. A
paired first-raster proof needs an effective setup or first draw
observation on the DOSBox-X producer. A strict steady proof needs an
independent tighter DOSBox-X B-write and retrace bracket.

Both native owners closed and reaped; the boot images and producer pins
passed readback. Native receipt SHA-256
`0af70ea41d901eeeaaf2ffd79af633def57bf6d38bc5f1d20f96319ce986162e`.
Independent timing audit SHA-256
`719aed07fb57d7cca525a8ae7e2c4fda2983922f97b21273a4c94fdd40aef768`.

## Direct DOSBox-X steady row timing

The [row timing diagnostic](../native/dosbox-vga-row-timing/README.md)
records the PIC schedule and actual renderer callback clock, phase ordinals
and completed writes to the authored palette index. Its timing-only RPC
returns no image. The fixture wrote both complete timing predictions before
reading the exact same frame's RGB. The authored COM and declared pulse delay
and widths stayed at 9,013 and 40 or 36 PIT ticks on DOSBox-X. The original
PIT-only oracle and its archived results retain their earlier scope.

Both quiet and both pulse rasters recorded physical lines 1, 3, …, 399.
The scheduled line period is 31,778 ns and the largest observed callback
lateness is 1,019 ns rounded up, below the declared one-eighth-line bound.
Both pulses separated every row for both phase predictions. Row 100 is A
under phase 0 and B under phase 1. Both full images match phase 1 and exclude
both phase 0 and the final-palette-only image.

The four full RGB hashes match the retained installed DOSBox-X and pinned
QEMU observations from the preceding pulse-window experiment. The archived
QEMU producer independently passed both strict phase predictions there. The
timing probe was rebuilt from the earlier DOSBox-X source diagnostic and
verified on that derivative.

| Evidence | SHA-256 |
| --- | --- |
| Authored COM | `c2ddebd5affa489302f22c9139d354be1cb31b38d5edbe58b5e491c90ed3cb1d` |
| DOSBox-X row timing derivative | `eb13dc7cb4866ab2c182c23439cbd40d74463faafb94c173b76c38857ff33176` |
| Timing-only native receipt | `885deae5058315102ae9ee19c6ae1267eff776c043908ecd5ebfeda00f900225` |
| Previously qualified QEMU producer | `cea0a35169d6e51fafa6c32824e208ad2c14c9ec755cb9c9c005cd119c2e478f` |
| Previously paired native receipt | `0af70ea41d901eeeaaf2ffd79af633def57bf6d38bc5f1d20f96319ce986162e` |

## Direct DOSBox-X first completed mode-13h raster

The same diagnostic producer was armed against an earlier completed
320×200 mode-13h frame. A 57-byte authored COM then entered text mode and
stopped immediately before a new `INT 10h` with `AX=0013h`. At the stop the
host read the `CD 10` instruction and the guest's zero return marker. The
first newly completed 320×200 frame carried the marker set after BIOS
return. Each frame step advanced exactly one completed renderer frame.

| Completed frame | Renderer mode ID | Source extent | Selected physical rows |
| --- | --- | --- | --- |
| 3 | 5 | 320×200 | 1, 3, …, 399 |
| 4 | 6 | 720×400 | Text mode |
| 5 | 7 | 320×200 | 0, 2, …, 398 |
| 6 | 7 | 320×200 | 1, 3, …, 399 |

The producer returned the first new-mode timing from the already completed
frame, which shows that diagnostic arming survived both mode transitions.
Each graphical receipt contained all 200 callback times. The first retained
row started 7,945 ns after its frame origin. In the subsequent frame it
started 39,722 ns after its origin, one physical line later within scheduler
rounding. Maximum actual callback lateness was under 7 ns in both frames.

This measures the first completed source raster on the authored text-mode
reentry. It leaves the internal draw-setup instruction time, equivalent
same-mode BIOS reapply, and other BIOS or programming sequences open.
The earlier pinned QEMU mode-13h producer has independent first/steady
checkpoint evidence from its own fixture.

Authored COM SHA-256
`360506d4851aaae7f9bdc328c4b4c66f067789a3704ba3791608ea03ea9577b6`.
Private native receipt SHA-256
`3ed410e1480886007bdf1a5c912bcdc096580d1cfb9bb32804ab7971984cf031`.

## Current QEMU counterparts

An [opt-in native test](../tests/test_qemu_mode13_paired_phase_native.py)
ran both exact authored COMs on the read-plane candidate. The fresh QEMU
warm trial used the previous guest-calibrated 8,991 tick delay and fixed
40 and 36 tick pulse widths. Both strict phase predictions were written
from the guest's PIT and VGA journals before export. Both quiet and both
pulse rasters matched the DOSBox-X derivative byte for byte. Both pulses
excluded phase 0 and the final-palette-only image. All 200 row receipts per
frame matched the independently calculated 31,700 ns line schedule within
124 ns.

For the text-mode reentry, the fixture read the preceding VGA geometry and
held the guest in its text loop until one sixteenth into the next VGA
period. The second `INT 10h AX=0013h` used the original BIOS memory clear.
QEMU recorded effective setup at virtual time 1,496,075,514 ns and return
at 1,500,299,514 ns. The first phase-0 row was due at 1,508,737,725 ns,
8,438,211 ns after return. The next frame was phase 1. Both completed
raster schedules matched all 200 expected deadlines within 125 ns.
This pairs the phase order on the same authored guest mode edge. The two
engines have distinct measured physical line periods.

| Evidence | SHA-256 |
| --- | --- |
| QEMU read-plane candidate | `2ac168a830ada1b61c17a6fef87ddb40ae71479be48a2dd3e229247183d6eac0` |
| QEMU warm native receipt | `99f8f58bdef6927bb08d0744d1a933733fe589fe7069def7af4d5c33b691a11e` |
| QEMU text reentry native receipt | `06cf6732870ba3aca35bffb525aa77b10c1cb21d8d7eefd3f3e10f1a3c2489cd` |

## Equivalent BIOS mode reapply

A [same-byte native fixture](../tests/test_paired_mode13_reapply_native.py)
entered and held mode 13h on both engines. It detected leading vertical
retrace at port 03DAh, waited 2,300 channel-2 PIT ticks, then stopped at an
authored `INT 10h AX=0013h` edge with the normal BIOS clear. Actual PIT
entry intervals were 2,303 ticks on DOSBox-X and 2,300 on QEMU. The BIOS
return brackets were 3 and 5,933 PIT ticks respectively. All 17 guest-read
VGA census bytes were identical before and after on both engines. The QEMU
setup stamp advanced and the old source stream invalidated. Neither run
read a raster image.

| Producer and completed raster | Physical phase | Scheduled interval between drawn rows |
| --- | --- | --- |
| DOSBox-X first after BIOS, frame 5 mode 5 | 1 | 31,777–31,778 ns |
| DOSBox-X second, frame 6 mode 5 | 0 | 63,555–63,556 ns |
| DOSBox-X frames 7 through 11, mode 5 | 1 | 63,555–63,556 ns |
| QEMU first after setup | 0 | 63,400 ns |
| QEMU second after setup | 1 | 63,400 ns |

The first DOSBox-X frame started from a recorded nominal 31,778 ns
physical-line schedule. Its row zero was 14,005 ns early relative to that
initial lattice and its final row was 6,337,915 ns early. All actual
callbacks remained within 7 ns of their dispatched event times. The first
full-spacing DOSBox-X frame used even physical lines. The next frame
restored the steady odd sequence and four further frames repeated it.

In the retained DOSBox-X source, `VGA_SetupDrawing` resets the carried
render step, and `VGA_DrawSingleLine` reads the current delay each time it
schedules a line. A setup that changes effective FPS can call
`VGA_VerticalTimer` before replacing `singleline_delay`. These separate
setup and callback operations allow a retained raster to straddle a
timing change. The diagnostic observes those row events and the return
to the steady cadence. The exact setup call that preceded each event
remains unobserved. QEMU's mode-13h source sampler uses one whole-frame
line period and one phase. Pairing this transition would require modeling
and preserving a schedule with changing row intervals.

| Evidence | SHA-256 |
| --- | --- |
| Authored reapply COM | `1742f5a2317b70365de38404732ad04128976543e862e0a913f38d3b02db2c9b` |
| DOSBox-X reapply receipt | `2affe690f6bb629f7b5465fd25686ec79cd302a74bb0b311018ce9a616cd3667` |
| QEMU reapply receipt | `11433f30a5ca553d3640a0fd279341c59256e755f627377b8598c37658cd205c` |

## Remaining qualification

- Qualify a transitional schedule if equivalent mode reapply must reproduce
  the first mixed-cadence DOSBox-X raster. Qualify additional programming
  sequences and modes separately.
- Exercise both engines through the same protected game's palette/origin
  changes and replay its dynamic raster after a native checkpoint.
  [Current QEMU frame contract](QEMU_FRAME_CONTRACT.md)
