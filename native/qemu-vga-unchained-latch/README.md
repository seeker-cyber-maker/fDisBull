# Timed unchained VGA page selection

Apply this delta to the exact QEMU 10.0.13 source after the
[stopped renderer-source patch](../qemu-vga-renderer-source/README.md).
The manifest records the previous native producer and every changed source
file's preimage and postimage.

For a native DOS process, select `--qemu-video-source-profile vga-unchained-latch`
with virtual clock and precise retrace. The launch passes
`VGA.x-fdisbull-unchained-latch=on` to the primary standard VGA device.
The reported model is `qemu-vga-unchained-320x200-latch-v1`.
It admits the same nonwrapping four-plane layout as the stopped source probe.
The timed stream selects the page once at the precise model's leading vertical
retrace boundary before the frame. Each timed row reads that selected page and
the palette in effect at its sampling time. A late latch may run less than one
line after its deadline. A CRTC origin change at or after a pending latch
deadline invalidates the stream if the callback has yet to select the page.

The frame retains its layout identity and a separate `page-latch` receipt
with intended and actual virtual time, byte origin and the live VGA census
generation at selection. Start-address and CPU write-plane changes continue
to advance the general VGA generation. Other effective configuration changes,
timing changes and reset retire the source stream.

The selected profile uses `fdisbull-instrumented-qemu-state-6`. Its source
sidecar records either the pending latch or the selected page and sampled
prefix, with the next deadline and exact native timer expiry preserved. A
retained completed frame keeps its own page receipt. Format 6 imports require
the same selected profile and validate the page generations against the
restored VGA census. The existing chain-4 and mode-13 profiles retain their
own checkpoint formats.

The receipt describes the timed source sampler. Stock screenshots and the
stopped renderer proof still use the renderer's own display parameters. This
profile supplies a boundary that can be tested against DOSBox-X independently.

The authored native test programmed one page before the latch and the next
page after the latch. A same-session restore preserved the pending write
before selection. A new session preserved the selected page and 65 sampled
rows even though the guest had already programmed another page. Both full
frame futures matched the authored RGB oracle. The existing Mode 13h restore
and renderer tests passed on the same native producer.

Darwin arm64 QEMU SHA-256
`aad47cf70c912a4c95ec4236f4fa1c6f032e5bbe33c2c3e671fcfc2fb5821001`.
Native validation receipt SHA-256
`00853176b3862b5380a858bb670c31c1ed778cddcd8bf8400bbea57c671b05a0`.
