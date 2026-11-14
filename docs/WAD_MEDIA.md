# Bounded WAD media recovery

The recovered authored readers support Doom IWAD/PWAD directories, retained
lump occurrences, linked maps and bounded palette, image, texture, sound and
music decoding. This is format recovery, not a claim of native rendering or
whole-game equivalence. Inputs and extracted bytes remain private.

`media-modules` advertises `doom-wad`. `media-inspect --adapter doom-wad` provides
a bounded first inventory page; `media-extract --adapter doom-wad --member all`
exports into a new private directory. The Python API
`fdisbull.wad_media.inspect_wad_media` accepts `start`, `limit` and an explicit
`base_wad`; `extract_wad_media` accepts `wad_mode` (`raw`, `decoded`, `both`),
`palette`, output budget and an optional base. Duplicate names remain separate:
use `lump:N` when `name:NAME` is ambiguous. Unsupported decodes keep raw records
and explicit errors; no source is rewritten.

Recovered source provenance: `73ec8dfc`. The adaptation is checked with authored
lumps and existing structural fixtures. Historical game/corpus observations in
adjacent recovery documents are retained as historical reports and do not
qualify the current release or caller inputs.
