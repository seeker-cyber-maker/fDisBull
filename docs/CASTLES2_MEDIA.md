# Castles II SLB playback and bounded Interplay MVE framing

The tool exposes an explicit SLB reader/playback profile and a bounded MVE writer.
Inputs are data, never executed by these methods. Native game qualification is a
separate experiment using the user's original executable and private resources.
The source distribution and tests contain no original game payloads.

## Discover and select a format

```text
fdisbull format-modules --catalog /private/formats.sqlite
fdisbull file-identify /private/movie.mve --catalog /private/formats.sqlite
fdisbull media-inspect /private/movie.mve --adapter mve
fdisbull media-inspect /private/SND190.SLB --adapter castles2-slb
fdisbull media-inspect /private/SND190.SLB --adapter castles2-slb-playback
```

The format catalog recognizes the canonical Interplay header and first chunk
extent. That recognition does not decode a movie. Its linked `mve` module admits
an explicit old indexed-video profile; later codecs, unknown operations and
unsupported layouts refuse. SLB has no global magic. Its catalog entry is a
filename/game-context candidate, and calling the decoder requires explicit SLB
selection. A successful query never marks the current input native-tested.

## SLB directory and selection

`fdisbull.castles2_audio.decode_slb(data)` accepts bounded immutable bytes and
returns an immutable library. `inspect_slb(data)` returns metadata and hashes.
The recovered layout is:

```text
sample payloads
slot_count * {u32le key, u32le offset, u32le length}
{u32le selector, u32le slot_count, u32le table_offset}
```

The complete directory must terminate exactly at its footer. Empty records are
all zero. Occupied records have nonzero key/length, bounded extents, and their
sorted ranges partition every payload byte without gaps or overlaps. Source and
slot counts are bounded at 64 MiB and 65,536 slots. Reports retain original slot
identity and hashes, with no sample bytes.

The original consumer hashes `(key * 73) % slot_count`, probes with wrap until an
empty record, and can choose `rand() % matching_count` among repeated keys.
`library.lookup_slots(key)` returns matching slots in probe order without
inventing RNG state. It refuses an unqualified signed-overflow key domain or an
unterminated probe cycle. `library.sample(slot)` selects one occupied original
slot explicitly. Physical payload order is not directory order.

## Playback profile and selected WAV export

```text
fdisbull media-decode /private/SND190.SLB /private/new-sample \
  --adapter castles2-slb --slot 515 \
  --playback-profile castles2-ail-sb-mono-v1
```

The explicit `castles2-ail-sb-mono-v1` profile admits the original AIL/Sound Blaster
unsigned-8 mono route. It maps selectors to DSP time constants, not literal kHz:

| Footer selector | DSP time constant | Ideal device rate | Integer WAV rate |
| --- | ---: | --- | ---: |
| 11 | 166 | 1,000,000 / 90 Hz | 11,111 Hz |
| 22 | 211 | 1,000,000 / 45 Hz | 22,222 Hz |

`bind_slb_playback(library, profile=...)` returns exact rational device timing.
`sample_report(slot)` separately records ideal payload duration and integer-WAV
duration. The WAV adapter floors ideal Hz; this is not exact hardware timing.
Setup, refill, DMA drain and caller polling add separate completion latency.
Selector 5 exists in the original code but remains outside this qualified profile.
Unknown selectors remain inspectable as opaque structural metadata.

An export requires a slot and explicit playback profile, excludes sample-rate or
channel overrides, and writes a new private directory with `samples.wav` and a
hash-bound manifest. It rejects existing outputs, sources/parents with forbidden
links or Git ancestry, changing inputs and output-budget overflow. Images and
palette options cannot silently select a sound variant. The earlier DinoPark
adapters retain their own explicit rules.

All 42 supplied libraries pass directory and native lookup-order checks: 8,492
slots, 2,123 occupied entries and 339,240,448 payload bytes. At most five variants
were observed for one key. This does not establish every sample's original use.

## MVE framing contract

```text
fdisbull mve-frame /private/original.mve /private/new-framed \
  --keep-frames 32 --timeout 120
```

Use a regular canonical source and a new private output directory. The writer
requires FFmpeg for complete independent source/derived video and audio decoding.
It admits a homogeneous old 0x06 or 0x10 indexed-video family, bounded geometry,
fixed initialization, unsigned-8 mono PCM, known operation versions and complete
container extents. Unsupported later 0x11, extra/true-color buffers, unexplained
maps, subrectangles or unknown controls refuse.

A framing variant retains opening and ending images while replacing a declared
middle interval with native holds. It keeps source codec family, geometry,
logical presentations, original audio, palettes, timers, control operations and
chunk positions. Original ending packets restore the needed reference state;
the manifest distinguishes pure holds, any bounded reference-recovery transition,
and the exact retained ending. Storage reduction does not shorten the wait.
The writer refuses an ending it cannot qualify within its declared work budget.

No output chunk may exceed the source's original maximum. A container's 16-bit
length field alone does not establish the original player's input-buffer capacity.
A synthetic full image may decode with FFmpeg while failing the original player.
Likewise, changing old codec families midstream can invalidate native reference
buffers even when an independent decoder produces the intended pixels.

Before accepting output, the writer completely decodes both streams, compares
all promised retained indices/palettes, validates the held interval, and checks
complete PCM identity. It checks original nonvisual operations at their original
chunk positions and refuses source changes, unsupported budgets or a variant
that does not reduce storage. Result flags describe decoder qualification only;
`native_runtime_tested` stays false.

The published-format references are pinned to FFmpeg commit
`7aab64c1f2187a3d4607b699eb18810bbd806387`:
[demuxer](https://github.com/FFmpeg/FFmpeg/blob/7aab64c1f2187a3d4607b699eb18810bbd806387/libavformat/ipmovie.c)
and [video decoder](https://github.com/FFmpeg/FFmpeg/blob/7aab64c1f2187a3d4607b699eb18810bbd806387/libavcodec/interplayvideo.c).
The implementation is authored Python; it does not embed those C files or game
resources.

## Original-DOS acceptance

Keep immutable originals, separate derived media, exact source/implementation/
backend identities, and fresh owned runtimes. Bind passive instruction probes to
relocated original bytes. Show the exact altered member being opened, every
promised presentation, appropriate pixels/palettes and captured mixer sound,
completion and return to the expected caller. A successful filename open or AX
return is not sufficient. Stored screenshots can lag a decoder breakpoint;
compare completed display checkpoints and keep screenshot/VRAM timing separate.

Normal UI or supplied tutorial routes must remain distinct from prepared media
aliases, data/register edits or direct routine invocations. A prepared alias can
qualify an original decoder/driver path without proving natural story selection.
Capturing stock mixer PCM with dummy host output does not establish physical
speaker audibility. Preserve failed candidates and wrong-rate controls rather
than rewriting those observations as source corruption.

### Bounded original sound evidence (2026-11-04)

The unchanged DOS engine and its original SBDIG driver were observed through the
supplied tutorial-43 argument path. Passive probes verified complete source PCM
slices, 15,000-byte refills, mode zero, DSP time-constant writes, buffer release
and normal caller continuation. No host guest-RAM/register writes or instruction
patches were used.

| Arm | Input association | Source bytes / buffers | DSP TC | Ideal payload | Observed start to cleanup |
| --- | --- | --- | ---: | ---: | ---: |
| Natural tutorial | Original SND190 key/slot | 158,720 / 11 | 211 | 7,142.40 ms | 7,185 ms |
| Prepared media substitution | Complete original SND263 sample, remapped into a new one-variant SLB for the tutorial key | 30,208 / 3 | 166 | 2,718.72 ms | 2,762 ms |

The second arm qualifies the selector-11 decoder/driver route; it does not prove
that the tutorial naturally selects that later-story sample. Canonical libraries
were unchanged, and the fixture is not selected into the preferred game variant.
The roughly 43 ms difference is setup/refill/drain/polling overhead in these
observations, not a universal latency constant.

Both complete captured windows are nontruncated stock 48 kHz stereo PCM. Dense
source-derived waveform comparisons remain approximate. Natural selector 22 has
global correlation 0.72686; the wrong literal 22,000 Hz control gives 0.10219.
Per-buffer comparisons cover all expected payload frames with independently
observed device-write anchors and a declared ±4 ms alignment bound, giving
0.97227–0.99895 across all 11 buffers. These local alignments are not global phase
parity and do not replace the retained global result.

The prepared selector-11 global correlation is 0.99870, versus 0.19920 for a
literal 11,000 Hz control. Its two informative full buffers correlate
0.99859–0.99929; the final 208 bytes are constant silence, so their correlation is
unknown rather than reported as success. Full PCM source identity, device timing
and captured waveform similarity are separate checks. Physical speakers, other
drivers, stereo modes, loops and interruption behavior remain unqualified.

### Bounded original movie evidence (2026-11-04)

Two ordinary menu paths were compared in fresh original-DOS runs: Reference →
Intro to Castles (`REF1`, old 0x10) and Designs → Beaumaris → Movie (`BEAU`, old
0x06). Both original and derived media were mounted through the original DOS CD
path with the same complete music track and data-track length. The exact derived
member bytes match the final production writer. No executable, guest-RAM,
register or instruction edits were used.

| Movie | Original bytes | Framed bytes | Presentations per arm | Retained images |
| --- | ---: | ---: | ---: | --- |
| REF1 | 22,379,772 | 4,167,665 | 1,571 | First 32 and last 32 |
| BEAU | 15,404,072 | 5,333,270 | 779 | First 32 and last 32 |

Both writers selected an original 128-presentation tail after shorter candidates
failed ending-image checks. REF1's pure holds are indices 32–1442, with declared
reference recovery 1443–1538 and exact retained ending 1539–1570. BEAU's pure holds
are 32–650, recovery 651–746 and exact retained ending 747–778. The recovery images
are intentionally modified transition imagery; they are not claimed as original
images. Every modified presentation was compared with the fully decoded variant.

The two original/derived pairs cover **4,700 native presentation boundaries**.
REF1's complete original and framed rasters/palettes match their respective
independent outputs. For BEAU, direct native original-to-derived comparisons
verify the retained prefix/ending and every held image; all modified indices 32–778,
including the recovery interval, agree with the independent decoder. Six unchanged
BEAU prefix frames 2–7 disagree with the modern decoder identically in both native
arms. Their native original/derived images match, and their cause remains unknown.
This is bounded native transformation evidence, not general decoder parity.

Each movie completed every expected presentation, returned AX=0 and restored the
ordinary menu. A prior candidate also returned success but missed the final
presentation; that failed gate is preserved. Earlier cross-codec holds and large
synthesized endpoints are excluded. The final writer preserves source codec and
original ending packets, without increasing the original maximum chunk size.

Dense mixed-audio windows through presentation 96 compare without a gain/DC fit.
REF1 covers 467,420 stereo 48kHz frames at lag −4 frames, correlation 0.999998948;
BEAU covers 622,943 at lag −26 frames, correlation 0.999999999. Lag selection was
bounded to ±100ms, chosen on the left channel and applied to both. Incorrect 100ms
lag and 13% rate controls give correlations near zero. This qualifies the captured
windows, not the entire emitted soundtrack or physical audibility. Full source
and derived movie PCM is independently identical at the codec layer.

The accepted corpus scan admits 21 of 22 movies, reducing 255,831,840 accepted source
bytes to 115,301,234; it preserves the refused THRN source, whose ending cannot be
qualified within the bounded tail search. All 21 outputs were reconstructed and
fully redecoded using the final source with exact retained images, explicit
transition hashes, PCM/control identity and original chunk bounds. Only REF1 and
BEAU have the separate native qualification above. Keep other candidates distinct
from the preferred game layer until their consumers are tested. A whole-game
playthrough, arbitrary seeking and all playback environments remain unqualified.
