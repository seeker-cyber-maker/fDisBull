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

## Remaining qualification

- Obtain independent DOSBox-X timing clearances for both pulse trials.
  Record the effective VGA renderer settings and tighten the VGA-edge and
  DAC-write brackets before any pixel read. Keep the phase families and
  overlap refusal.
- If an opt-in production profile follows, admit this geometry explicitly.
  Qualify the first raster after a real mode setup, later steady rasters and
  capture that starts after warm-up. A stream start by itself does not
  establish a guest mode reset.
- Persist the profile, current phase and pending deadlines across checkpoint
  restore. Verify restores before the first draw, between the first and
  steady rasters, and with partial steady rows. Retain the existing model
  and checkpoint formats for the default path, and reject model mismatches
  before resume. [Current QEMU frame contract](QEMU_FRAME_CONTRACT.md)
