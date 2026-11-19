# Opt-in standard-VGA raster proof prerequisite

This private increment reports evidence about the latest actual synchronous
renderer attempt. It adds no frame ID, mode ID, guest-frame capability,
video-cadence timer, frame-step operation or legacy scene adapter. Existing
retained-display commands and their response schemas are unchanged.

The source manifest pins the exact prerequisite files from the b077 SB16-count
producer and each changed file. Build in a private QEMU 10.0.13 tree after those
prerequisites; do not patch or overwrite a qualified producer in place.

## Admission and query

The optional property is off by default. Select it together with the existing
native virtual-clock and precise-VGA profile:

```text
-vga std,retrace=precise
-global VGA.x-fdisbull-retrace=on
-global VGA.x-fdisbull-raster-proof=on
```

`x-fdisbull-query-raster-proof` has no arguments. It uses the existing stopped
clock, exact primary VGA and ownership admission. It never renders, runs guest
instructions, reads a guest I/O port, changes a timer, hashes pixels or creates
a file. Querying empty or invalid evidence cannot repair it.

The result distinguishes these outcomes:

| Outcome | Meaning |
| --- | --- |
| `unavailable` | No admitted complete-raster proof exists for the latest attempt, or no attempt has occurred since reset/load/invalidation. |
| `valid-unchanged` | The renderer considered the full admitted extent, reused its previously valid cache without redrawing rows, and every resulting pixel was verified again. |
| `updated` | One or more rows were redrawn and the entire admitted raster was verified. This does not require the visible colors to differ. |

A successful result records actual native attempt time, a frozen producing VGA
configuration and the native source descriptor. It does not describe a BIOS
mode number or application completion. `current-configuration-matches` compares
only the current configuration generation with the producing generation.
Palette/VRAM writes can leave that comparison true while changing future pixels.
The result always remains the latest attempt's evidence, not a fresh memory read.

## Exact initial source profile

`qemu-vga-chain4-320x200-raster-v1` admits only:

- Exact primary standard VGA, explicit precise profile and headless synchronous
  owned console zero/head zero.
- Legacy graphics with VBE disabled, chain-4 addressing, shift mode 2 and the
  native `vga_draw_line8d2` interpretation.
- A 640×400 allocated packed native XRGB32 renderer surface, a 320×200 palette
  index source, and exact 2×2 duplication.
- Zero VRAM origin/bank, 320-byte source pitch, no panning or visible split, the
  selected ordinary address/attribute/plane interpretation and sufficient VRAM.

The renderer must visit all 400 rows. A fresh or configuration-changed cache
forces a complete redraw before success. Unchanged cache reuse requires an
already valid cache; it still undergoes a full per-pixel verification.

Every surface pixel is compared against its actual source palette index and
native-expanded DAC entry. The verifier then owns canonical RGB888 copies of
the complete source and surface, and hashes those copies without alpha/padding.
It also records hashes of all source indices and all 256 expanded palette entries.
The six-bit conversion is the pinned QEMU `c6_to_8` implementation, not a newly
invented conversion: the authored native oracle deliberately uses DAC values
1/21/42, whose native expansion is 7/87/168. Eight-bit DAC conversion is recorded
explicitly when selected; native qualification must state which modes ran.

Unsupported text, blank, VBE, origin/pitch/panning/split or extent changes produce
unavailable evidence. In particular, an invalid text update may preserve an old
surface for existing display consumers, but it does not retain a current raster
proof. Reset, renderer invalidation and native load clear evidence independently
of restored counters. The process-local proof is not serialized and is freed by
the PCI VGA instance finalizer.

## Verification and limits

`tests/test_qemu_raster_proof_source.py` compiles the exact new helper extracted
from the hashed patch. It checks source admission, full per-pixel copy, final-row
and duplicate-pixel corruption, stale source/palette, invalid extents, null and
truncated buffers. These are source probes, not native integration evidence.

`tests/test_qemu_raster_proof_native.py` uses an authored 403-byte DOS COM and
independent pixel/index/palette expectations. It checks actual renderer updates,
palette-only change followed by unchanged cache reuse, the last source row,
invalid-text stale surfaces, blank/panning refusal, configuration A→B→A before
query, passive query stability, hot-load proof invalidation, opt-in refusal and
reset. Tests add the native property explicitly through a test-only launch hook;
there is no new public fDisBull launcher option in this prerequisite.

The native producer for these tests is the existing fixed-period retained-display
timer. Its cadence remains caller-selected sampling. Successful raster evidence
does not establish DOSBox scanline sampling, a native video-period completion,
application drawing completion, input consumption/readiness, frame-state atomicity,
frame-1 compatibility or full migration parity. A separately reviewed native
video-cadence stream and host identity/consumer work remain outstanding.

Build and native receipts are local, source/producer-bound evidence. A native skip
or an unrun counterexample remains an open gate; no campaign or default is promoted.

## Local qualification for this increment

`verification.json` pins the exact source patch, candidate executable, image tool,
runtime files, test sources and retained receipts. The final Linux gate passed
9 compiled source probes, 4 authored native cases and 9 unchanged adjacent native
cases. All final cases ran without skips or failures, and all owners were reaped.
The opt-in refusal case and adjacent cases keep the new property disabled.

The first failures are preserved. Build registration needed the new QAPI module
in Meson's explicit list. Three test setup assumptions were then corrected:
the initial full redraw can leave one dirty-bitmap drain; the hot-load witness
must explicitly enable the existing checkpoint tool; and a surviving-reset
negative control must override production's exit-on-reboot policy. The final
reset case observes the changed native epoch with passive queries, verifies
unchanged stopped virtual time, and refuses the old proof. The native C patch
did not change during these test corrections.

The native empty-proof and invalid-mode cases do not inject a zero-bpp surface.
Null, invalid and truncated verifier buffers are compiled source probes. Native
eight-bit DAC, native video cadence, raster scanline sampling and frame consumers
remain separate qualification work.
