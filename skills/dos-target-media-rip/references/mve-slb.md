# Old Interplay MVE and Castles II SLB

Start with the selected tool's catalog and explicit adapters:

```text
fdisbull media-inspect /private/movie.mve --adapter mve
fdisbull mve-frame /private/movie.mve /private/new-framed --keep-frames 32
fdisbull media-inspect /private/SND190.SLB --adapter castles2-slb
fdisbull media-inspect /private/SND190.SLB --adapter castles2-slb-playback
fdisbull media-decode /private/SND190.SLB /private/new-sample \
  --adapter castles2-slb --slot 515 \
  --playback-profile castles2-ail-sb-mono-v1
```

The supported MVE profile is old indexed 0x06/0x10 with one homogeneous video
family per movie. Later codecs, unexplained operations/maps, changed geometry,
other audio modes and invalid extents refuse. Framing retains first/last N
images and original logical presentations, audio, palette and timer/control
operations. A deterministic bounded original-tail search restores reference
state. Read the manifest's pure-hold, warm-up and exact-ending ranges; warm-up
frames are modified transition imagery, not promised originals.

Keep the source codec family. A 0x10-to-0x06 substitution can violate the original
player's buffer representation despite correct FFmpeg images. Also retain the
original maximum chunk-size bound: a synthetic image can fit a 16-bit container
length and still fail the original player's reader. The supported writer keeps
original ending packets and refuses an unqualified ending or no-saving variant.
Independent video/PCM checks are required before output is accepted.

For native acceptance, bind the actual changed file hash, count real completed
presentations, compare promised images/palettes and captured sound, then verify
return to the expected caller. One prototype returned success while omitting its
final presentation; successful open/return alone would have missed it. Stored
screenshots may lag decoder RAM. Keep normal menu paths distinct from prepared
aliases and keep private diagnostic failures out of preferred target selections.
Do not infer that castle/reference movies are expendable from their names.

SLB has no global signature. Its recovered footer/directory preserves repeated
keys and original slot identities. Native selection can randomize variants, so a
selected export uses an explicit directory slot rather than guessing from a key.
Footer selectors 11/22 bind discrete Sound Blaster time constants 166/211. They
are not literal 11,000/22,000 Hz. Exact rational device timing stays separate from
the integer WAV adapter and from setup/refill/DMA drain/caller completion.
Unknown selectors stay structural; selector 5 remains outside the qualified
playback profile. Do not replace SLB libraries with MP3 files by renaming them.

Preserve canonical game/driver bytes. Keep media variants, catalogs, native
captures and full manifests private. A media-only change needs an integrity
check of the maintained executable ZIP, not a new executable roster version.
See the selected source/package's `docs/CASTLES2_MEDIA.md` for APIs, budgets and
original-runtime qualification boundaries.
