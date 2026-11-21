# Paired mode-13h source-frame qualification plan

This is an authored native qualification with separate functional and phase
results. Its ten pure device-journal oracle tests passed, the fixture was
assembled, and one finite native attempt has run. Both backends passed the
quiet completed-raster checks; all four pulse trials remained timing-unqualified,
so the overall native test failed. The exact evidence and limits are below.
It changes no emulator model or production API. A later attempt requires its
own reviewed controller and admission against exact source and artifact hashes.

## Pure oracle verification

At integrated commit `9b6ba9a36beb1ce588a5c6b8d4d92a0981145757`, all ten tests
in `tests/test_paired_video_frame_oracle.py` passed with zero failures, errors or
skips: 0.20 seconds pytest, 0.404275 seconds outer worker. All 5,679 tracked
source hashes remained unchanged and the worker/group was reaped with no
adopted children. The test imports only the pure rational PIT/VGA oracle;
neither assembler nor emulator was launched.

Evidence is retained in `frame-parity-20261120/host-paired-oracle-01`; receipt
SHA-256 `2644a251eff2ff9ef77146fda43785afa0bd14baf044d614b3b804eea6a5433a`.
This verifies the authored arithmetic and ambiguity rules. That pure gate left
both actual backend phase/complete-image outcomes pending.

## Retained assembly

One finite assembly at host `c77c68c569e948de56ca3ba9474ed237fb3cdd59`
produced the 3,883-byte COM, SHA-256
`1c31924eaabfe96dc1d8bf2869232d93478c8d78f65ee605cfb82387a506dba7`.
The receipt at `frame-parity-20261120/paired-assembly-01/receipt.json` has
SHA-256 `11320f4fcbbff6103a5a3d2106459ca4bea77c0134e2ac53eec5b119fdef9112`.
That preparation did not execute the guest. The native attempt's assembly
subsequently matched these exact bytes and the retained symbol layout.

## First native attempt

The one native attempt ran at clean host
`840e3883c9e26485f95aa921b73ec79ec8010feb`, with the producer hashes below
and the unchanged authored test, fixture and oracle. Its **overall result is
failed: one failed test, zero test errors or skips**. Setup and teardown passed.
The final phase assertion failed because all four pulse observations were
unqualified; no native dispatch error or pixel mismatch caused that assertion.
The pytest `record_property`/xunit2 compatibility warning is retained.

The worker receipt's `dispatch_failed` field records the controller's aggregate
failure flag, which also includes the final pytest assertion. It is true here,
while the case's actual dispatch latch is false, its error list is empty and
the native journal has no error event. The original receipt is preserved;
that aggregate field is not evidence of a native dispatch failure.

The independent functional evidence is narrower and positive. DOSBox and QEMU
each completed two quiet rasters and two fixed pulse rasters, in that order.
All four quiet 192,000-byte RGB arrays matched the authored palette and corner
sentinels and matched across backends, with SHA-256
`141a920ca2ecdd0d6fd7684eca3918d7d9ce66f74573266a15656dd107295939`.
All eight completed-image probe/capture observations preserved the recorded
paused CPU, guest clock and authored journal state. This concerns observations
at the completed-frame stops; it is not the separate strict immediate-pause
stability witness or atomic CPU/image equivalence.

The independent timing oracle rejected these fixed trials while constructing
the two phase predictions, before comparing their RGB arrays:

| Backend | Pulse trial | First uncertainty intersection |
| --- | --- | --- |
| DOSBox | 3 | Row 100, phase 1, intersects a DAC-write window |
| DOSBox | 4 | Row 101, phase 0, intersects a DAC-write window |
| QEMU | 3 | Row 101, phase 0, intersects a DAC-write window |
| QEMU | 4 | Row 101, phase 0, intersects a DAC-write window |

Both phase families must be unambiguous so that the fixed counterfactual can
be rejected. A refusal in either family leaves that trial unqualified. These
refusals also precede the stricter QEMU H/8 callback-lateness check, so that
check is not qualified by this attempt. Captured pulse pixels were not used
to choose a phase, shift a pulse, narrow an interval or rerun the experiment.

| Retained controller evidence | Observed result |
| --- | --- |
| Complete attempt | 20.972756 seconds, including preflight and postflight |
| Pytest / owned worker | 3.30 / 4.157973 seconds |
| Native ownership | DOSBox then QEMU; both exit zero and reaped, no overlap |
| Calls | 1,120 paired attempts/results: 155 DOSBox and 965 QEMU; zero native error events |
| Complete logs | DOSBox emulator log plus QEMU and boot logs retained after reap |
| Inputs | All 11,708 file pins and nine trees matched before and after |
| Runtime closure | 209 ELF files, including qemu-img and reviewed optional Pillow loaders; actual native and Python-worker mappings checked |
| Output | 12,276,091 logical / 12,378,112 allocated bytes, plus an 8 MiB open-log reservation, below the 128 MiB cap |
| Bounds | 120-second fixture-inclusive case, 45+10 seconds per owner, 240-second inclusive controller |

The controller is `frame-parity-20261120/controller-paired-01`; raw output
is `/tmp/fdisbull-paired-raster-native-20261121-attempt-01`.
Plan SHA-256:
`24c658df65dd7a842264f9a39d3bcf49e0722d7b77ca66030c70df35d02567f5`.
Root review SHA-256:
`5a83f007d42eb7b275bb038b33606864b4c68181377482527230f1c6ca19dc9b`.
Phase receipt SHA-256:
`a88503b5309382c8240882d6f5c3f7d63443caba04585225e981fff67697b50e`.
Native receipt SHA-256:
`a8923431a354496d640132a2e7792f7b4756add7db7228b2012988eb5538fcc1`.

The failed attempt and its raw timing/pixel evidence remain unchanged. A future
phase witness needs better independently measured timing bounds before another
admission; this result does not justify relaxing the oracle or tuning from an
image. DOSBox's explicit requested profile and actual arguments were checked,
but per-setting effective runtime state and individual row callback times were
not independently observed. No retirement row, backend default or broader
parity campaign is promoted.

## Decision being tested

Functional completed-source-frame/API parity can be qualified for the admitted
320x200 chain-4 profile while each backend retains its own scanout timing.
Static prepared rasters must be byte-identical. A raster-sensitive pulse must
match an independent device-time prediction for its declared backend phase.
The experiment keeps functional evidence, phase qualification, and exact dynamic
image equivalence as separate results.

The source inference is fixed before any execution: QEMU's unchanged
`qemu-vga-chain4-scanline-v1` samples physical lines 0,2,...398 at an H/4 offset.
The pinned ordinary VGA DOSBox path, with doublescan disabled, carries
`render_step=1` after a complete frame and then samples 1,3,...399 at that offset.
It does not alternate phases on every healthy frame. Two quiet completed frames
precede the pulse, so the test does not assume that capture start or INT10h return
exposes the first fresh phase-0 DOSBox scanout.

## Exact proposed native inputs

| Input | Required SHA-256 |
| --- | --- |
| Original DOSBox producer, attempt-02/prefix/bin/dosbox-x | `bfdacbed027ae16f48256abc5d0309cc8984569a2946dabea2f4d43907d43e71` |
| Source-fence QEMU, candidate-fence-01/build/prefix/bin/qemu-system-x86_64 | `b42b624f452e19c1560f1af45712fc93f6859ac753bab73a1495c49188cca0af` |
| Matching candidate qemu-img | `b8687f147c9ac6900e840619196abdec4d5f4890d94be6876eae0c9e09985f03` |

The implementation parent is commit
`154d6659cba2211eccaeaf73505bd049ad192b20`. The independent controller must pin
the final integrated host commit, both producer receipts and complete tool/
library closures, source manifests, firmware, original boot image, NASM, mcopy,
the authored test files and the resulting COM. There is no producer fallback,
download, rebuild, original game, saved emulator state or GUI route.

The runtime environment requires `FDISBULL_REQUIRE_PAIRED_VIDEO_FRAME=1`,
`FDISBULL_PAIRED_VIDEO_QEMU`, `FDISBULL_PAIRED_VIDEO_DOSBOX`,
`FDISBULL_PAIRED_VIDEO_DOSBOX_LIB`,
`FDISBULL_QEMU_DOS_BOOT_IMAGE`, `FDISBULL_QEMU_DOS_MCOPY`,
`FDISBULL_QEMU_DOS_FIRMWARE`, `FDISBULL_QEMU_IMG` and `NASM`. These variables do
not themselves constitute admission. Missing required inputs fail the explicit
gate. Ordinary test selection skips it without the enable variable.

DOSBox uses normal CPU, fixed 157600 cycles, frameskip0, doublescan=false,
scaler=none, scanline-render-on-demand=false, skip-unchanged=false and vsync=off.
QEMU uses its existing virtual clock and precise retrace profiles. The test
records the actual profile; it never tunes it after viewing an image.
The admitted private DOSBox library directory is passed only to that producer's
`execve` environment. The wrapper uses the current admitted Python interpreter,
preserves the inherited RPC descriptors, and explicitly fixes the VGA profile
and DAC6/full-triple palette settings. Host Python and QEMU do not inherit the
DOSBox library path.

## Finite ownership and output plan

One native test is proposed:

`tests/test_paired_video_frame_native.py::test_native_paired_mode13_completed_rasters_have_independent_phase_witness`

- Exactly two successful VM lifetimes at most: DOSBox first, fully reaped, then
  QEMU. Maximum one live native owner, no replacement or restore overlap.
- Each owner has one 45-second work deadline and at most10 seconds cleanup.
  Launch and all commands consume that same work interval. A controller must
  additionally enforce120 seconds for the whole native case, with separate
  finite preflight/postflight bounds and owned TERM/KILL/reap behavior.
- Each owner performs at most four completed-frame advances: two quiet, then
  two fixed pulses. There are no hidden alignment advances. Explicit breakpoint
  continuations reach authored calibration, pre-arm and post-display labels.
- Calibration records at most512 horizontal rising edges and at most four
  observed vertical retraces. All phases together admit at most12 observed
  retraces and200000 guest polling iterations per owner. The COM stops at an
  authored fault label on a command/poll/retrace violation.
- A phase ambiguity is retained. It does not trigger another calibration,
  another VM, a changed pulse, another clock profile or a retry.
- All outputs, authored binary/listing, projects and the private DOS baseline
  belong under one fresh private `/tmp` campaign directory without Git ancestry.
  Total output cap128MiB; native logs2MiB each; source COM16KiB; RGB192000 bytes;
  PNG2MiB per capture; calibrated edge journal3072 bytes. The external controller
  must enforce live growth and retain/re-hash complete logs after process exit.
- Test-local logs are explicitly before-close snapshots, not complete-log
  claims. Process receipts are also checked by the independent owner controller.
  The test cannot self-admit a controller, start a build, or bypass its pinning.

If calibration is ambiguous, the two quiet frames still run and their complete
pixel/control evidence remains available. The two pulse calls are omitted for
that owner, and the separate phase gate fails explicitly at the campaign end.

## Authored guest and independent expected pixels

Both owners execute the same newly assembled COM bytes. The guest selects BIOS
mode13h, fills exactly64000 pixels with palette index1, and places four distinct
corner sentinels. The palettes use non-endpoint DAC6 values:

| Palette | DAC6 | RGB888 |
| --- | --- | --- |
| A | 1,21,42 | 4,85,170 |
| B | 42,21,1 | 170,85,4 |
| C | 21,42,1 | 85,170,4 |

The reference conversion is bit replication `(v << 2) | (v >> 4)`. The ordinary
QEMU renderer conversion is an explicit wrong-color control. Full192000-byte
RGB arrays and all four sentinels are checked, along with an ordered sparse probe
covering every row. A final VRAM/palette snapshot and completion-time palette
expansion cannot pass the A→B→C pulse oracle.

Host memory writes target only authored command, pulse-mode and calibrated
delay/width fields. They do not patch pixels, executable instructions, VGA
registers, timestamps, native receipts or expected images. The only timing
adaptation is one predeclared formula from the calibration journal, computed
before any image observation. Both pulse trials reuse those same parameters.

## Device-time and phase oracle

PIT channel2 is explicitly programmed in binary mode2 with divisor65536, gate
high and speaker output disabled. It is a linear countdown, unlike the default
BIOS channel0 mode3 count. The guest journals raw latched counts before and after
status samples and whole DAC triples. Modular unwrapping rejects a gap of half
the16-bit count range or more; it never fills a missing interval from host time.

Horizontal timing H is constrained by same-polarity port3DA edges. An initial
±5% band from the guest's raw standard VGA clock/register selection is used only
to disambiguate the integer number of physical lines between observations. Each
gap must have a unique count in1..8 to remain in a fit segment; ambiguous gaps,
long gaps and vertical-generation changes end a segment and are retained in the
receipt. The final H interval comes from every admitted long pair separated by
at least128 independently counted lines. Without such a segment, phase remains
unqualified. No candidate frame timing fields or screenshots enter this oracle.

The same raster's post-display bit3 rising edge supplies V. A source row r is
predicted directly as

`V + (2*r + phase + 1/4 - VsyncStart)*H`.

Keeping this expression correlated avoids counting the uncertainty in B and H
twice. In particular, the oracle never divides inter-vsync duration by Vtotal:
the pinned DOSBox vertical timer can adjust the next frame interval independently
of H. PIT quantization, edge brackets, complete DAC-write windows and a declared
H/8 sampling-lateness allowance are included. Overlap with either DAC write, or
identical predictions for both phases, is an explicit unqualified witness.

H/8 is an experimental admission stricter than QEMU v1's unchanged H lateness
contract. Native row-time receipts may only disqualify this stricter trial; they
never choose expected pixels or shift an expected row. DOSBox has no individual
row-time receipt: its H/8 allowance remains a declared experimental assumption,
not independently observed callback timing. Its phase result means that the
complete observed pulse agrees with that fixed source-derived image family and
rejects the other family. Millisecond `captured_ticks` is retained for
order/identity only. The test does not infer timestamps for every legacy row.

The actual pulse is scheduled from the preceding vertical edge using
`(Vtotal - VsyncStart + 200.75) * midpoint(H)` and a width of`floor(midpoint(H))`
PIT ticks. Its observed write windows, rather than the nominal delay, generate
both fixed phase predictions. Two trials use the same rule and parameters.
Unexpected images do not alter the rule or select a better phase after the fact.

## Image identity and stopped boundary

Each owner first parks in an authored vertical-sync setup interval. QEMU must
also report zero partial source rows. The existing frame controller advances
exactly one accepted raster from that baseline and reports its own actual safe
stop. DOSBox must report completed=true, stop kind frame, matching stopped state
revision, and frame ID baseline+1. QEMU must report its completed target,
stop_consumed=true, and clean source-fence completion. This does not imply guest
input consumption, application drawing completion, or simultaneous CPU/pixels.

Image/probe reads occur at that stop and must preserve CPU, native guest clock,
authored journal and frozen image identity. Host clock-observation sequence and
wall timestamp are not guest-state equality predicates. The original completed
image is exported before any continuation to the post-display journal marker.
The later CPU revision is retained separately and is never attached to the
earlier image as if simultaneous.

## Required source review before any execution

1. Inspect the NASM program and footer addresses without assembling it. Confirm
   its setup, exact four sentinels, only index1 pulse writes, full DAC brackets,
   mode2 PIT programming, modulo arithmetic, poll/retrace caps, fault stop and
   control/journal extents. Only then admit one finite assembly and inspect its
   emitted layout/hash before the native campaign.
2. Check the pure oracle against the hand-calculated tests: PIT wrap; missed and
   ambiguous edge counts; vertical-origin discontinuity; row100 at11530 versus
   11570 ticks; color replication; overlap refusal; fixed pulse parameters.
   These ten pure tests passed in the host gate above.
3. Verify no actual frame, renderer query, screen pixel or native row deadline
   enters `horizontal_interval`, `pulse_parameters` or `phase_predictions`.
   Both phase arrays must be determined solely from the logged guest state.
4. Inspect both real adapters' frame-stop predicates, public image metadata,
   repeated passive observations, captured-owner cleanup and the one-owner-at-a-
   time transition. A QMP/RPC acknowledgement is never treated as a completed
   frame or a completed job.
5. Review a new controller's complete closure and finite two-owner policy,
   producer pins, source snapshot, fresh private outputs, complete-log capture,
   live caps and deadline behavior. Do not reuse or mutate the sealed stream or
   fence controllers and their receipts.

## Result interpretation

The campaign writes `paired-video-result.json` even on failure. Functional quiet
facts are recorded as soon as their two real advances and full RGB comparisons
finish. Phase outcomes are observed, unqualified, or mismatch. A timing ambiguity
fails the overall phase gate while preserving independently successful quiet
facts. Source-phase0 for QEMU and steady phase1 for DOSBox resolves the expected
backend model difference. It does not promote exact raster-effect equality or
another mode. Other consumers may use the separately qualified complete-image
and safe-stop contract without pretending both emulator clocks are identical.
