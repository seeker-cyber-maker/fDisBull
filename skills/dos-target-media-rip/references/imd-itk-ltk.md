# Coktel IMD, ITK and LTK framing

This procedure is grounded in a particular Lost in Time Italian CD dataset.
Check the actual version and layout before reusing it. Other versions, including
the English floppy LTK, can differ.

## Three linked formats

- IMD contains the movie header, palette and frame packets. The version-4
  examples also have an absolute frame-position table.
- ITK contains named members, byte lengths and archive offsets.
- LTK caches IMD headers and frame boundaries; rebuilding only ITK leaves stale
  information in its companion.

The inspected Italian LTK files have a leading record count. A record consists
of a 32-byte prelude, the cached IMD header, `4 * native_index_count` bytes,
`4 * (logical_frame_count + 1)` frame-boundary bytes, and one metadata byte per
logical frame. Keep native index count distinct from logical frame count;
version-2 examples disambiguate them.

The general meaning of the final metadata byte is unresolved. In this dataset,
all 703 genuine exact two-byte `00 00` holds had metadata byte `02`. Preserve the
original metadata for exactly retained packets, and use `02` only for that
established native hold. Refuse arbitrary new packet encodings whose metadata
cannot be justified.

## Conservative framing

1. Keep the first frame and find a later independent full-frame packet.
2. Keep that last full frame and all following delta frames needed for the end.
3. Replace eligible intervening packets with native holds, preserving numbering.
4. Rebuild IMD header/index, ITK member sizes/offsets, and all affected LTK caches.
5. Reparse everything and verify that unchanged members are byte-identical.
6. Completely decode original and framed versions independently. Compare frame
   count, geometry, first/final pixels and palettes.

Do not automatically alter interactive movies, short assets, inventory or
subrectangle images, unsupported versions, anomalous indexes, or clips without
a qualified final independent frame. A one-frame prefix can be valid media yet
change script frame ranges and the final image, so it is a separate diagnostic.

## Existing private evidence

The current package contains
`analysis/lost-in-time/pro-handoff-validation-v1/`: a byte-exact round trip of six
original ITK/LTK pairs and a DESCC-only framed pair. DESCC kept frames 0 and 24,
used 23 holds, and shrank from 364,749 to 24,864 bytes while retaining 25 frames.
An independent C++ decoder compared endpoints with zero differing pixel/palette
bytes. That modified pair has not been exercised by a new original-game run.

The supplied Pro account reported a larger 20-movie compact ISO. Its complete
artifact was not imported or independently accepted locally. Do not cite that
report as evidence that the local package contains or qualifies that full build.

Reuse the private `audit_ltk.py`, narrow decoder, manifests and original sources
when present. Keep copyrighted game bytes outside the local skill itself.
