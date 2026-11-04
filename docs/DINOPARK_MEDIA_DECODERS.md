# DinoPark ACT, PIC and ABT decoder modules

These are shipped bounded byte decoders for the supplied DinoPark resource
profiles. They do not execute an ACT sequence, play a sound, launch a game or
rewrite an input. Header recognition, complete byte decoding, authored PNG/WAV
export and original-game agreement are separate qualifications.

For recovered sequence interpretation, an explicit original sound timing profile
and normal-gameplay observations, see [animation and playback](DINOPARK_ANIMATION_PLAYBACK.md).
The sprite/sample APIs described here retain their narrower byte-decoding contract.

## Discover and inspect

```text
fdisbull media-modules
fdisbull media-inspect /private/scene.ACT --adapter dinopark-act
fdisbull media-inspect /private/scene.PIC --adapter dinopark-pic
fdisbull media-inspect /private/sample.ABT --adapter dinopark-abt
```

Inspection completely decodes the admitted resource and reports dimensions,
counts, source/decoded hashes, limits and unresolved semantics. Reports contain
no source streams, pixels, palette buffers, sample bytes or ACT script bodies.
The pure Python APIs return immutable decoded buffers to an authorized caller:

```python
from fdisbull.dinopark_images import decode_act, decode_pic, describe_act, describe_pic
from fdisbull.dinopark_audio import decode_abt

actor = decode_act(original_act_bytes)
picture = decode_pic(original_pic_bytes)
audio = decode_abt(original_abt_bytes)
```

ACT `UNC2` and legacy `UNCS` preserve each sprite's indexed pixels, independent
opacity mask, declared bounds, commands/colors and original offsets. Palette
index zero can be opaque: transparency follows the mask. Sequence bodies and
the established trailer are preserved as opaque data rather than executed or
claimed as recovered animation behavior. Palettes belong to the game consumer.

UNCP PIC decoding preserves every frame's six-bit palette, exact padded raster
in `row_data`, logical cropped pixels in `indices`, geometry and even row stride.
Narrow frames use raw rows; wider frames use the recovered run encoding. A
control of `0x80` repeats 129 samples in this consumer; a generic PackBits library
with a different interpretation cannot be substituted blindly.

ABT has no safe global magic. The caller explicitly selects the DinoPark
consumer profile. The decoder preserves native literal/repeat/delta-table wrap
and sample saturation, checks complete source consumption, and returns an
unsigned eight-bit sequence in `pcm_u8`. Its raw rate field and three opaque
header bytes do not establish playback Hz, channels or sound-device behavior.
Metadata exposes only lengths/hashes for opaque bytes.

## Selected PNG/WAV exports

```text
fdisbull media-decode /private/scene.PIC /private/new-picture --adapter dinopark-pic --index 0
fdisbull media-decode /private/actor.ACT /private/new-sprite --adapter dinopark-act --index 0 --palette-path /private/scene.PIC --palette-index 0
fdisbull media-decode /private/sample.ABT /private/new-audio --adapter dinopark-abt --sample-rate 11025 --channels 1
```

The last example authors a WAV adapter at the explicitly selected timing; it is
not a claim that the ABT header establishes that rate or channel count. Both
values are required. Source bytes must divide into complete caller-selected
channel frames. No sound is played.

PIC output is an indexed PNG. ACT always exports exact index and opacity PNGs;
without a palette these are diagnostic planes, with no invented colors. A
caller-selected PIC frame can additionally bind ACT to an RGBA preview. Palette
policies `shift2` and `replicate6` explicitly choose six-to-eight-bit host color
expansion. Native six-bit palette agreement does not establish host RGB display
calibration. Export manifests record the source/palette identities and adapters.

Output must be a new directory under an existing private parent outside Git,
without symlink traversal. Decode and source/palette rechecks precede creation.
The output-byte budget includes all files and the manifest. Existing inputs,
outputs, programs and resources are never patched or overwritten.

## Bounds and catalog integration

Image decoders preflight an 8 MiB source, record/directory extents and cumulative
geometry/work before allocating pixel buffers. Default decoded admission is
16 Mi pixels with at most 1 Mi pixels per frame and 128 Mi work units. ABT admits
at most a 1 MiB source, 65,535 expanded bytes and two million work units. Truncated,
overlapping, contradictory, unsupported or over-budget profiles refuse explicitly.

The format catalog links `dinopark-actor` and `dinopark-picture` headers to the
pixel decoders. The ABT context profile links its explicit audio decoder while
remaining a context candidate. Intake now reports reader validation rather than
a missing pixel decoder for recognized ACT/PIC, and a separate context-decoder
validation task for ABT. It never invokes the decoders just to identify a file.
ACT sequence control, palette selection, clipping/composition, playback timing
and audible output remain consumer obligations.

## Verification boundaries

Authored tests cover opacity versus color zero, row padding, run and delta
branches, mutable-input ownership, truncation, contradictory extents and budget
admission. All 57 supplied ACT files (1,514 sprites), 25 PIC files (166 frames)
and 44 ABT files (636,978 expanded bytes) match the retained recovered readers.
Those comparisons share transcription lineage and are not independent native
proof. Fresh original-DOS comparison receipts bind the production module hashes,
original executable/backend identities, invocation profile and exact observed
buffers. Prepared routine calls and natural consumer witnesses are labelled
separately. A bounded codec comparison does not establish whole-game behavior.

Licensed inputs, output images/audio, native states, original-code maps and raw
comparison logs remain private. Only authored decoder code, fixtures, methodology
and sanitized verification descriptions belong in the repository/tool package.


## Fresh original-DOS qualification for the supplied corpus

| Decoder | Corpus | Original routine calls | Exact compared output |
|---|---:|---:|---:|
| ABT | 44 files | 44 | 636,978 expanded bytes |
| PIC | 25 files / 166 frames | 166 | 6,551,922 padded raster bytes |
| ACT | 57 files / 1,514 sprites | 3,028 | 6,994,714 dual-background composite bytes plus exact reconstructed opacity |

These are fresh processes loading the supplied original DOS executable normally,
then using assisted argument/stack/register preparation through an existing
original return instruction. No stubs or instruction patches are installed.
Scratch, descriptors and the fixture stack are disjoint from the complete
file-backed image and bounded by its verified DOS-owned allocation. The original
ABT decoder's data lookup table and the ACT raster's disassembly-established
cursor/pitch/geometry/flag words are explicitly saved/restored. Whole loaded-image
hashes are identical after cleanup. All 183 original file hashes and copied
runtime inputs remain unchanged, and all owned guests are reaped.

Four passive startup ABT consumers additionally matched without guest memory,
register or input edits: MECCHARP, CLAPPER, CRASHSYM and COMET. Natural ACT/PIC
consumers were unobserved in the bounded startup, so their corpus result remains
prepared original-codec qualification. ACT comparison covers unclipped,
unmirrored raster/opacity; sequence behavior is not tested. PIC raw palettes
match the file bytes; native host RGB expansion/palette timing is not established.
ABT rate/channel interpretation, audible output, malformed native inputs and a
whole-game playthrough remain outside this evidence.

The private acceptance selector is `NATIVE-CODEC-SUMMARY.json`, SHA-256
`cc34e1de1e675358b1ba5337d01bd74404478c5194369e995c21c9f837bebc23`.
It selects corrected ABT/PIC full-06 and ACT full-07 receipts and excludes the
earlier scratch-overlap/state-restoration diagnostic attempts. The original
executable identity is
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`;
hashes establish byte identity, not publisher authenticity or other editions.
