# Native SMK2 cinematic framing

Start with the caller-selected tool's current catalog and reader limits:

```text
fdisbull file-identify /private/original.smk --catalog /private/formats.sqlite
fdisbull media-inspect /private/original.smk --adapter smacker
fdisbull smk-frame /private/original.smk /private/new-framed-output
```

The output directory must be new beneath an existing private parent outside Git.
The SMK adapter requires a regular non-symlink source. When intake recorded a
file alias, verify and pass its canonical regular target while retaining the
alias/provenance edge; do not duplicate a large source merely to remove a link.
The writer snapshots a bounded source, verifies supported SMK2 structure and
requires working FFmpeg/ffprobe readers. Unsupported ring, scaling, geometry or
audio profiles refuse; an SMK4 header does not select the SMK2 writer.

Default framing retains 32 opening and 32 final indexed images. Native FULL
blocks reproduce retained pixels/palettes; native SKIP blocks hold the preceding
image through the intervening positions. The writer rebuilds Huffman trees,
exact decoded-node allocations, frame-size and frame-type tables. Original
compressed audio packets remain at their original frame positions, and logical
frame counts, geometry and timing stay unchanged. Storage shrinks; playback
need not become shorter.

Every declared audio track must agree with an independently identified stream
in slot/order, codec, channel count and rate. Undeclared frame audio packets and
unsupported audio flags refuse. Before output is accepted, complete independent
video decoding checks retained images/palettes and complete decoded PCM hashes
and sample counts must match. A manifest records source/output identities,
retained positions, reconstruction policy and limits. Decoded memory and host
lifetime are bounded independently of the output-size limit.

Use `--keep-frames`, `--max-movie-bytes` and `--timeout` only within their documented
supported ranges. Existing outputs are never overwritten. Tool limits do not
replace the caller's storage admission and approved destination rules.

Hash all supplied executables before and after. Use an isolated writable runtime
with linked assets and the exact framed-file hash, then observe the original
player open it, process its logical frames without unintended skips and return
to its caller. Fixed CPU settings may matter: starvation can make the original
player skip visual frames while still returning success. A standalone decoder,
success return value or opening filename alone is insufficient native evidence.

Native screenshots can lag instruction breakpoints, and the decoder can rewind
its frame/palette at EOF. Compare actual decoded buffers and stable displayed
witnesses at meaningful boundaries; do not present a post-rewind palette as the
final displayed image. Retain failed observer routes separately from codec errors.
Prepared invocation of a late ending remains assisted; it does not qualify the
campaign route, credits, seeking, audible audio or all gameplay.
