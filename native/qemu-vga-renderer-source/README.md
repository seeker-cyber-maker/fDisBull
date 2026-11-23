# Native renderer source for standard VGA

Apply after [the stopped unchained probe](../qemu-vga-unchained-probe/README.md)
to the exact QEMU 10.0.13 source preimage in the manifest. The diagnostic
requires explicit virtual/precise profiles, primary standard VGA and
`-global VGA.x-fdisbull-raster-proof=on`.

`x-fdisbull-render-raster-proof` runs one synchronous headless renderer
update with the guest stopped. It returns the byte origin consumed by
that draw and SHA-256 digests of all 64,000 selected palette indices,
the native-expanded palette, the logical RGB raster and the doubled
renderer surface. Each output pixel is checked against the selected
page. A pending screendump or unsupported console refuses admission.
The existing passive `x-fdisbull-query-raster-proof` returns the latest
attempt without refreshing it.

The unchained profile admits a 320 × 200 page at a nonwrapping CRTC origin.
Both the stopped row probe and renderer proof use the same layout
validation. The renderer proof uses the actual drawing parameters.
The chain-4 path retains its zero-origin profile. The new command has no
timed publication ID and produces no scanout or hardware latch timestamp.

The authored fixture checked full index and surface digests on two
distinct pages, refused a wrapping page and recovered the previous page.
The chain-4 renderer, stale-frame and checkpoint cases passed on the
same Darwin arm64 QEMU SHA-256
`e4749458abc2365fff1489d71166e51aa870ee8d95bf26b516dc072a706474f0`.
Native receipt SHA-256
`f4066f1c57c97c1919a5a544161085fcabf2c9478636d0143fe88e39bf5e34bc`.
