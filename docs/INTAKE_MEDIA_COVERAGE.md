# Media coverage at intake

The catalog covers observed media families through two different kinds of record:
self-identifying headers with bounded field/extent checks, and explicit
consumer-context profiles for resources without a safe global signature. A
context profile has no magic bytes and never decides the recognized format.
Intake preserves these as candidates and queues the missing reader or decoder.

The private 2026-11-03 census covered 6,698 accessible file paths across 46 target
directories (45 maintained executable-roster sets), plus the separate original
DinoPark directory. It found 96 media-context cohorts among 286 filename-suffix
cohorts. Those 96 cohorts have explicit catalog descriptions. This is coverage
of observed directory resources, not an assertion that every archive, ROM,
resource fork or program's embedded media was expanded or decoded. Code-only
selections and hidden members remain recovery obligations.

| Family | Recognized structure / context candidate | Qualification boundary |
|---|---|---|
| DinoPark | `UNC2`/`UNCS` actors, `UNCP` picture directories, IFF XMIDI; context ABT delta audio | Header/directory facts; private recovered sprite/picture/ABT readers are not shipped codec support. Preserve external palettes, six-bit palette scaling, even row stride, raw versus compressed rows and sequence control semantics. |
| Civilization DOS | PIC/PAL chunk families, CV/CVL fonts/graphics | Consumer/edition context; short E0/M0/X0/X1 tags alone are not global signatures. Recover complete chunk/LZW/RLE and palette obligations. |
| Civilization Amiga / Atari | IFF ILBM/PBM, platform PIX/PAL/fonts | IFF top-level extents/subtype recognized. Packed PIX and raster/font semantics remain separate; palette-only IFF need not contain a bitmap. |
| Civilization Mac / Windows; Colonization Windows | Resource forks, NE/PE resources, bitmap/icon/font/sound payloads | Native executable/header mapping is not a resource or media decode. Traverse resource maps and member extents before codec selection. |
| Colonization DOS | `MADSPACK 2.0` PIK/SS/font resources; WAVE; MOV/ANM control data | Packed marker and WAVE envelope recognized. Packed block/consumer codecs need recovery. `.MOV` here does not establish QuickTime. |
| Eternam | PAK/CC4/CC1/CC!/NAR and companion data; shared MP3 | Consumer-bound offset tables, compressed graphics/narration and audio placement remain explicit. AVE is a script/state candidate rather than proven video. |
| Lost in Time | ITK/STK directories, LTK caches and embedded IMD; shared MP3 | Context-qualified archive/member recovery. Italian CD IMD rewriting requires paired LTK cached headers/index/boundaries/metadata; it is not generic English-floppy support. |
| AGI | LOGDIR/PICDIR/VIEWDIR/SNDDIR, VOL resources and interpreter assets | Existing bounded AGI2 resource readers and picture decoder linked separately; sound synthesis, view pixels and AGI3 compressed variants need qualification. |
| SCI | RESOURCE.MAP/volumes and script/heap/message patches | Version-specific map/compression/resource recovery; AGI readers are incompatible. Do not confuse code resources with pictures/sound. |
| Syndicate / Syndicate Wars | SMK2, compact Bullfrog FLIC, IFF XMIDI; DAT/TAB, WAD/IDX, ANI, RAW/PAL | SMK2 framing is independently validated and separately native-qualified. FLIC structure is inspected; packed sprites, raw geometry and index consumers remain recovery tasks. |
| X-COM / TFTD | Standard FLI, custom TFTD VID/IDX; MIDI/IFF; PCK/TAB, SPK/SCR, CAT | FLIC packet/index extents checked without pixel/audio decoding. Palette/geometry, sprite offsets and CAT member codecs remain consumer-specific. |
| Console ROMs, Saturn, Civ64, small fixtures | Cartridge/native wrappers with embedded data | Directory inventory establishes no complete embedded-media census. Queue consumer/bank/resource recovery and preserve exact input identity. |

## FLI/FLC structural reader

```text
fdisbull media-inspect /private/intro.fli --adapter flic
fdisbull media-inspect /private/movie.vid --adapter flic --index-path /private/movie.idx
```

The bounded reader distinguishes standard 128-byte FLI/FLC from Bullfrog's compact
12-byte envelope and TFTD's audio-bearing VID packets. It inventories packet and
subchunk extents/types, declared versus physical frame counts, ring-frame
candidates, opaque prefixes/tails and unknown chunks. An explicit TFTD IDX can be
cross-checked against audio-plus-visual group lengths and its sentinel. Successful
structure or index correspondence does not establish index seeking/timing.

A private read-only qualification covered 219 actual movies: 213 Bullfrog compact
files, one standard UFO intro, and all five TFTD VID/IDX pairs. It inventoried
18,467 top-level packets and 16,037 frame packets while preserving all hashes.
Authored tests cover malformed boundaries and unsupported cases. The reader does
not decode pixels/audio, shorten files, patch programs or launch a game. The SMK
writer cannot frame FLI/FLC. Unknown chunks and delta dependencies must be
recovered before any future FLIC media edit.

DinoPark is the useful counterexample: none of its 183 original intake files is
FLI/FLC. It has 57 UNC2/UNCS actors, 25 UNCP picture containers, 44 headerless ABT
sounds and seven XMIDI files. Its `.PIC` suffix also differs from Civilization's
picture family. The private census rechecked all 183 original file hashes.

## Recovery rather than guessed support

Use each queue item's stated missing boundary: container traversal, decoder,
resource consumer, companion index, size/layout variant or runtime behavior.
Retain private recovered reader locations and source hashes as evidence; code
which exists in a research directory is not automatically a shipped module.
Port it into a bounded production API with authored fixtures, then compare its
results with the original consumer or an independent reader to the promised
scope. Preserve missing observations as unknown and keep licensed bytes outside
source/tool packages.
