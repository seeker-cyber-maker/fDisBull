# Independent MADS media and bounded conversation model

## Delivery and scope

This follow-up extends the merged static processor from !107. The previous
media/runtime recovery ZIP contained no implementation source, so its reported
results are not acceptance evidence for this contribution. The modules below
were rebuilt and tested. A downloadable ZIP must contain these source files,
not just a recovery receipt.

This is an analysis/media toolkit plus a bounded conversation execution model.
It is **not a complete playable MADS engine**, a native ScummVM sidecar, a
qualified original-DOS emulator, or an executable UIL reconstruction of all
native scene handlers. Parser success, deterministic replay and export-format
round trips are different claims and must remain separate.

## Independent layers

| Module | Responsibility | Runtime dependencies |
| --- | --- | --- |
| `codec_fab.py` | FAB decompression, explicit expected length and consumed extent | Python standard library only |
| `codec_dcl.py` | PKWARE DCL decompression, coded/uncoded literals, three dictionaries | Python standard library only |
| `mads_resources.py` | HAG, MADSPACK 1.0/2.0, CND metadata | The two codecs, no processor |
| `mads_media.py` | Indexed sprite/tile/depth/mask/glyph planes, DSR PCM, AA records, PNG/WAV | Resource layer and standard library, no processor |
| `mads_media_adapters.py` | Catalog, selected output, standalone CLI | Media layer, existing private-output helper |
| `mads_processor.py` | Existing CNV instruction decoder and source-bound traversal | Resource layer, processor interfaces |
| `mads_runtime.py` | Bounded dialog model, explicit external variables/RNG, breakpoints/replay | Static conversation processor, no media dependency |

There are no target-controlled plugin imports and no ScummVM executable or
library dependency. The `python -S` regression verifies that media inspection
and catalog discovery do not import `mads_processor`, `mads_runtime` or a
ScummVM module. Another game can use a codec or asset reader directly.

**DCL is a genuinely separate codec**, not a MADS opcode and not PKZIP's method
6. MADSPACK 1.0 compression identifier 1 means DCL; MADSPACK 2.0 identifier 1
means FAB. Explicit identifier 3 means DCL. Identifier 2 is unsupported and
refused. Pack metadata records both the raw identifier and resolved codec.
The previous `mads_resources.decode_fab` import remains compatible.

## Discover and use

The regular projectless `media-modules`, `media-inspect` and `media-extract`
JSON/Python APIs include these explicit adapters:

`fab`, `pkware-dcl`, `mads-hag`, `mads-pack`, `mads-sprite`, `mads-tiles`,
`mads-depth`, `mads-background`, `mads-depth-map`, `mads-mask`, `mads-font`,
`mads-dsr`, `mads-animation`.

The ordinary `fdisbull media-inspect` and `media-extract` commands derive their
adapter choices from the same catalog as JSON/Python. They expose `--source-member`
or `--source-index`, `--map-path` with `--map-member` or `--map-index`,
`--expected-size`, `--width` and `--height`. Mutually exclusive selectors fail
before opening an input. `source_member` is the original resource; `member` is
the decoded output. The dedicated installed module CLI also remains available:

```sh
python -m fdisbull.mads_media_adapters catalog
python -m fdisbull.mads_media_adapters inspect /private/GLOBAL.HAG --adapter mads-hag
python -m fdisbull.mads_media_adapters inspect /private/scene.SS --adapter mads-sprite --number 0
python -m fdisbull.mads_media_adapters extract /private/scene.SS \
  --adapter mads-sprite --number 0 --member preview-png --output /private/new-frame
```

```json
{"method":"media-extract","params":{"path":"/private/SPEECH.HAG","source_member":"CONV001.DSR","adapter":"mads-dsr","number":0,"member":"audio-wav","output":"/private/new-speech"}}
```

`source_member` selects an existing HAG member by exact integer index or a
unique case-insensitive name. `member` selects the **decoded output**, not the
source archive entry. Both archive identity and selected resource identity
remain in the report. Duplicate names must be selected by integer index in
JSON/Python, or with `--source-index` / `--map-index` in the CLI. The corpus
harness separately compares all matching companion bytes:
identical duplicates retain all indices in the receipt; conflicting duplicates
refuse instead of being silently selected. No name from a resource opens a filesystem path automatically.

For a tile background, supply `map_path` and optionally `map_member` explicitly:

```json
{"method":"media-inspect","params":{"path":"/private/SECTION3.HAG","source_member":"RM301.TT","adapter":"mads-background","map_path":"/private/SECTION3.HAG","map_member":"RM301.MM"}}
```

`number` selects a zero-based sprite frame, tile, sound sample, pack section or
HAG directory entry. It selects character code **1..127** for a font. HAG
inspection without `number` inventories the directory but exports no resource.
Sprite/tile/sample inspection defaults to item 0; font inspection defaults to
code 1. Reports retain full set metadata and only prepare selected output.

The raw FAB adapter requires `expected_size` from an identified owning
container. It does not guess a length. DCL optionally accepts `expected_size`.
Mask decoding requires explicit `width` and `height`. Unrelated options refuse.

Selected outputs are `decoded`, `resource`, `section`, `indices`,
`palette-rgb`, `preview-png`, `pcm-u8`, `audio-wav` and `timeline-json`, as
appropriate. Inspect first. Extraction uses the existing exclusive private
folder contract: 0700 directory, 0600 payload/manifest, no Git ancestry or
symlink output, no overwrite. Output filename is `payload.bin`; metadata says
which format it contains. Input bytes remain unchanged.

## Media contracts

SS decodes both scanline-RLE and per-frame FAB forms, retains origin offsets,
local palettes and transparency 255, and represents empty frames explicitly.
PNG uses local resource colors, not the game's live palette allocator.

TT offsets refer to the appended payload after MADSPACK sections. MM is a
separate source. Repeated tile references are allowed. A full canvas is
reconstructed separately from the stored viewport. Depth tiles use high-nibble
first four-bit values and remain uncolored. WW/PP masks use high-bit first
one-bit planes with explicit geometry. Neither kind establishes collision or
walkability semantics merely by decoding.

Zero-tile resources have no frame to export. In the inspected corpus RM920.TT
has zero tiles, and its MM has a `0xffff` entry. The reader reports an empty
resource; it does not turn inactive serialized workspace into artwork or
manufacture a black image. Rendering that resource refuses explicitly.

FF returns two-bit glyph planes without inventing runtime-selected colors.
Original fonts and decoded glyph files must remain private and are not included
in source packages or public test fixtures.

DSR retains sample rate and unsigned-eight-bit mono PCM. WAV is a lossless
container conversion. The inspected channel layout is mono; other layouts
refuse. No MP3 conversion is performed because it would lose source samples.

AA yields timeline, sprite references, positions, signed frame selection,
message metadata and timing records, including the interface variant. It does
**not** execute the scheduler, open referenced assets automatically, composite a
whole animation, assign a tick frequency, or synchronize speech/music.

FAB/DCL decompression, selected PNG/WAV generation and all inspection paths
are in-process and bounded. HAG inputs are limited to 128 MiB; pack input and
codec input to 16 MiB; total unpacked pack data to 32 MiB. Raster dimensions
are at most 4096 each and 16 Mi pixels per image, with a 64 MiB aggregate indexed
plane or PCM budget per set. DCL output is at most 32 MiB. Unknown variants,
back-reference underflow, truncated streams, overflowing dimensions and partial
resource overlaps refuse. Consumed sizes and trailing data remain visible.

## Conversation model

```python
from fdisbull.mads_runtime import ConversationRuntime
model = ConversationRuntime(cnv_bytes, cnd_bytes,
    external_values=explicit_vm_values, random_tape=recorded_draws)
model.start_dialog(dialog_index)
model.breakpoint(dialog_index, model.pc)
assert model.run()["stop_reason"] == "breakpoint"
model.step()
checkpoint = model.snapshot()  # private target-derived state
result = model.run(max_steps=10000, timeout_ms=1000)
model.restore(checkpoint)
```

The profile is `mads-conversation-model-1`. Commands 1..5 and 7..9 execute under
explicit model semantics. Arithmetic is signed-16, including wrapping;
division truncates toward zero, remainder follows that quotient, and zero
divisors yield zero in this selected reference profile. Operand flag 2 means
logical inversion of a variable value. Unknown operand flags refuse.

Commands 0, 6 and 255 have conflicting historical decoder/runtime interpretations
and are deliberately not executable here. They did not occur in the inspected
conversation corpus. This guard is not a claim that every theoretical MADS
program is implemented. The older static decoder's terminal-edge interpretation
must not be used as independent runtime evidence for those commands.

CND imports, host control variables 2..22 and serialized pointer/placeholder
markers require explicit values. They are **model values**, not recovered live
host pointers or alias relationships. Unbound access refuses transactionally.
RNG uses caller-provided inclusive draws, not a presumed seed-equivalent stream.
The model implements bounded message/speech selection queues and variable/flag
updates, not a text UI or audio player. It does not infer speech-bank names from
host execution or restore native engine globals.

Each instruction is transactional on failure. Breakpoints bind to a dialog's
known instruction boundaries; resume passes a stopped breakpoint once.
Execution is synchronous with cooperative instruction-boundary deadlines.
Traces have fixed capacity and dropped counts. Checkpoints bind CNV, CND,
profile and RNG tape; invalid schema, dimensions or source identity refuses
before applying state. Restore advances the revision and clears transient trace
and resume state. No portable native save-state equivalence is asserted.

## Verification and unimplemented engine work

Authored tests cover both compression literal modes, all supported dictionaries,
the published DCL reference vector, malformed data, overlapping copies,
transparency, empty resources, geometry, output privacy, public JSON and the
standalone CLI. They exercise arithmetic, refusal rollback, weighted RNG,
breakpoints, bounded loops, stale revisions and checkpoint replay.

Private corpus validation decodes media and runs selected conversation scripts
with explicitly **synthetic** external values and RNG draws. Its source-free
aggregate receipt is separate from authored tests. Exact PNG/RGBA and WAV/PCM
round trips validate serialization, not original scene rendering or sound timing.

Still separate: native x86/RTLink scene handlers, a real ScummVM MADS sidecar,
original-interpreter differential tests, animation composition/scheduling,
FM/MIDI/native music-driver synthesis, interactive conversation UI, native
save/load, a complete executable UIL lifter, and wider games/variants. DAT/HH/INT
scene tables and other resource classes may be unpacked as containers but are
not falsely advertised as completed semantic decoders.

The test environment overlays exact relevant release interfaces on the supplied
c80 source. It is not a full checkout or full-suite qualification of the current
release tree. A locally built wheel is a test artifact, not a release. Combined
source/native/macOS/CI acceptance remains required before release.

## References and provenance

This is source-assisted work, not a clean-room claim. ScummVM GPL source informed
format and behavioral models; license/provenance review remains required before
integration or distribution. No ScummVM runtime or game assets are bundled.

- ScummVM v2.8.1 `engines/mads/assets.cpp`, `sprites.cpp`, `palette.cpp`,
  `scene_data.cpp`, `font.cpp`, `audio.cpp`, `animation.cpp` and `animation.h`:
  https://github.com/scummvm/scummvm/tree/v2.8.1/engines/mads
- Current core format/model references inspected by immutable Git blob identity:
  `core/pack.cpp` `19d2907ab5719409b17b0ca10bdb90f3cb13a58c`,
  `core/pack.h` `1614eedb81d90871996cc5a5c23f235da739ae6b`,
  `core/tile.cpp` `9e344f0f6fbb0d4ffaddfc38d5824c2d5e330f5c`,
  `core/attr.cpp` `20d77e18bad344f1775ff3a97c073a3b573dbcb7`,
  `core/conv.cpp` `bb69c6933867c713b3ffba9255aa0485b31c8ff3`,
  `core/conv.h` `7a30da678979b89c4fd27cdf965166313653e850`.
  https://github.com/scummvm/scummvm/tree/master/engines/mads/core
- Mark Adler, blast 1.3, pinned zlib v1.3.1:
  https://github.com/madler/zlib/tree/v1.3.1/contrib/blast
  DCL tables/format notes informed an explicitly altered Python implementation;
  the upstream notice is retained in codec_dcl.py. DCL is not PKZIP method 6.

## Integration audit (7 November 2026)

`codec_profiles.py` links signature recognition for FAB, MADSCONCAT and MADSPACK
to these independent media adapters through `file-identify` / `format-modules`.
Recognition never decompresses. PKWARE DCL has no distinctive magic, so it is
cataloged but not automatically guessed from its two option bytes. An SS/CNV/FF
filename does not turn a generic MADSPACK container into a qualified subtype.

The reusable corpus validator is installed as `fdisbull.mads_validation`:

```sh
python -m fdisbull.mads_validation --resources /private/resources \
  --synthetic-model --output /private/new-receipt.json
```

Tests import this installed module, not a pruned `examples/` path. The example
is only a thin convenience wrapper. Immutable CNV/CND parsing is reused across
dialogs, with the same explicit initial checkpoint restored before every dialog.
A regression compares resulting state digests with fresh-runtime construction.
This improves the validation harness, not the interpreted program's semantics.

The codecs remain individually importable in a Python `-S` process without any
MADS or processor imports. Media set/PNG/WAV APIs do not import the conversation
runtime or ScummVM. No shared native installation or binary is required.

The audit does not remove any engine-completeness restrictions above. Public
integration must run the final combined tree and its installed artifacts.
