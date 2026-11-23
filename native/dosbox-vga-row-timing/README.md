# DOSBox-X completed chain-4 row timing

Apply this delta after the exact
[VGA source diagnostic](../dosbox-vga-source-diagnostic/README.md) preimage.
The source manifest records the earlier producer and the five changed files.

In a stopped session, use `video.probe` with an empty `points` list and
`source_timing_palette_index` in `0..255`. The first successful call needs
an existing completed frame and arms future capture. Pin later reads with
`frame_id` and `mode_id`. Timing-only requests return no image or index bytes.
An optional `source_indices` behaves as in the earlier source diagnostic.

An admitted `source_timing` describes the same completed frame. Its mode
is chain-4 320×200 source VGA at two physical lines per logical row, no top
skip, six-bit DAC and complete-color writes. It contains the initial color
and up to 16 complete commits for the selected native DAC index, the
scheduled frame start, callback start, retrace and line period, and 200
ordered scheduled and actual row timestamps with physical line ordinals.
Scheduled times are rounded to the nearest nanosecond from the producer's
PIC event clock. Actual callback and write times use the producer's exact
`ticks + tick_cycles / cycles_per_tick` emulated millisecond representation.
The renderer applies any pending palette updates just before drawing each row.

Unsupported geometry or an incomplete timing journal yields an unavailable
receipt. `source_indices: false` without a requested timing index disarms
capture. Ordinary frame and checkpoint contracts retain their existing form.

For the authored warm-phase proof, set `FDISBULL_REQUIRE_DOSBOX_CHAIN4_TIMING=1`,
`FDISBULL_DOSBOX_CHAIN4_TIMING`, `FDISBULL_DOSBOX_CHAIN4_TIMING_SHA256` and
`NASM`, then run
`python -m pytest -q tests/test_dosbox_vga_chain4_timing_native.py`.
The private receipt records the native timings even if the strict phase
comparison has overlapping rows.
