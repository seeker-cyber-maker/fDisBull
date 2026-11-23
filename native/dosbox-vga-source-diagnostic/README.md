# DOSBox-X completed VGA source diagnostic

This opt-in diagnostic extends the retained fDisBull layers build at DOSBox-X
upstream revision `029bd65c5dcc7cdc7f2e14e35278620d9707d969`. Apply the historical
layers patch first, then this delta. The source manifest identifies the exact
base patch, original executable and four changed source files. Verify the
preimages and postimages before building with the original backend flags.

Use the inherited-pipe agent with a stopped target and
`video.probe {"points":[],"source_indices":true}`. The first successful call
needs an existing completed frame and arms capture for subsequent frames.
Optional `frame_id` and `mode_id` pin the request to that framebuffer. Configure
`max_message_bytes` to at least 96 KiB to carry the encoded indices.

Follow the normal frame ID from `frame.step` or `video.screenshot`. An admitted
reply has `source_indices_available: true` and a `frame_source` object bound to
the enclosing `frame_id` and `mode_id`. `latched_crtc_start` is the CRTC start
consumed when the vertical draw callback schedules its rows.
`selected_draw_address` is its renderer byte address after origin translation,
and `first_row_address` is the byte address actually passed to the first row.
`selected_ticks + selected_tick_cycles / cycles_per_tick` gives the emulated
millisecond clock at the selection callback. It marks the callback itself. The
hardware latch and first row callbacks occur at separate times.

`indices_base64` holds 64,000 original row-major VGA indices and `indices_sha256`
hashes those bytes. Collection follows the standard 320×200 VGA source reader
on every drawn row. Other renderer paths, panning, split rendering, draw effects
and incomplete source collections yield an unavailable receipt. A screenshot
encoded as indexed PNG still uses colors derived from the RGB image.

Pass `source_indices: false` with an empty point list to disarm. Unqualified
frames remain usable as ordinary RGB captures. The source receipt is retained
with its completed frame and is invalidated when frame capture is reset.
Checkpoint payloads have no source diagnostic fields.

The authored two-page fixture runs only when explicitly enabled against a
selected build. Supply `FDISBULL_DOSBOX_FRAME_SOURCE`, its exact
`FDISBULL_DOSBOX_FRAME_SOURCE_SHA256`, `NASM`, and
`FDISBULL_REQUIRE_DOSBOX_FRAME_SOURCE=1`, then run
`python -m pytest -q tests/test_dosbox_frame_source_probe_native.py`.
