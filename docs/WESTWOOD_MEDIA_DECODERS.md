# Westwood Kyra-family media readers: PAK, CPS, WSA, EMC2

**Status:** Bounded source-only decoder prototype built from fDisBull **0.31.1**; static input acceptance and generated pixel buffers are **not** DOS engine equivalence, native script execution, UDL recovery, gameplay, or audio/video playback proof. Source games, generated assets and original executable bytes must remain outside Git, published wheels' fixture collections and shared reports.

## Supported, explicitly selected adapters

| Adapter | Layer | Delivered result | Refused / unknown |
|---|---|---|---|
| `westwood-pak` | Resource container | Westwood DOS PAK v2/v3 member inventory, exact byte ranges, payload SHA-256, opaque tail accounting; extract selected member | No automatic nested extraction, filename-only inference, overwrite, unsafe names or ambiguous same-name selection |
| `westwood-cps` | Indexed bitmap | DOS PC compression 0/raw, 3/RLE and 4/LCW, 6-bit VGA palette if embedded, indexed pixel buffer, PNG preview if **320x200 and palette present** | Unknown geometry/palette is left unknown, other image variants unsupported, PNG is not palette cycling or video parity |
| `westwood-wsa` | Delta animation | Early, early-with-flags and coordinate-bearing late headers; bounded offsets, compressed first-frame LCW + XOR delta decode where independent | A WSA with no first-frame bytes requires caller-bound previous frame; timing, multi-asset chaining, runtime palettes and composite output unqualified |
| `westwood-emc2` | Script container | Big-endian IFF `FORM/EMC2` ORDR/DATA/TEXT span inventory, entry-list validation | Does not execute scripts or resolve syscall IDs to game behavior |
| `fdisbull.westwood.emc2` | Guest processor module | Bounded static control-flow traversal of 19 core EMC instructions, with source offsets, per-game entry convention, unresolved syscalls and stack-dependent returns | No binding to the original DOS interpreter, emulation, game logic, original-to-UIL proof or UDC realization |

All readers run without launching original game binaries. Inputs are regular files with strict per-reader size caps, outputs and hashes retain provenance. Source-controlled filenames do not authorize execution.

## Commands

This is an additive patch on the existing 0.31.1 command surface. Choose the real game-owned paths and a private output directory, **outside any Git checkout**.

```bash
# List a container and its members, without extracting or executing:
fdisbull media-modules
fdisbull media-inspect /private/kyrandia/GEMCUT.PAK --adapter westwood-pak

# The parent of the exclusive new output directory must be owned and 0700.
# Example: install -d -m 700 /tmp/my-private-intake
fdisbull media-extract /private/kyrandia/GEMCUT.PAK \
  /tmp/my-private-intake/gemcut-emc --adapter westwood-pak --member GEMCUT.EMC

# Inspect the extracted EMC2 member and disassemble one bounded entry:
fdisbull media-inspect /tmp/my-private-intake/gemcut-emc/payload.bin \
  --adapter westwood-emc2
fdisbull module-analyze fdisbull.westwood.emc2 \
  /tmp/my-private-intake/gemcut-emc/payload.bin \
  --profile kyrandia1-dos --function-index 0 --max-instructions 40

# Use --profile lol1-dos for a source-bound Lands of Lore INF script.
# First-frame and bitmap extraction use distinct adapters:
fdisbull media-inspect /private/kyrandia/SOME.CPS --adapter westwood-cps
fdisbull media-extract /private/kyrandia/SOME.CPS \
  /tmp/my-private-intake/some-cps-indices --adapter westwood-cps --member indices
# If the exact CPS includes 320x200 pixels and its own palette:
fdisbull media-extract /private/kyrandia/SOME.CPS \
  /tmp/my-private-intake/some-preview --adapter westwood-cps --member preview-png
fdisbull media-inspect /private/kyrandia/OPEN.WSA --adapter westwood-wsa
```

`media-extract` emits `payload.bin` plus a JSON source/derived-member receipt. For PAKs containing case-insensitive duplicate names, the inventory emits selectors `#<index>:<filename>`; select one such entry *exactly*. Preserve both duplicate members. `media-inspect` does not recursively open a PAK-contained WSA/CPS/EMC file; extract it to a new private directory, then select the second adapter explicitly.

Python interfaces include `fdisbull.westwood_media.inspect_pak`, `decode_lcw`, `decode_rle3`, `decode_cps`, `encode_cps_png`, `inspect_wsa`, `decode_wsa_frames`, `parse_emc2`, and `fdisbull.westwood_emc2.EMC2Processor`. `media-inspect`/`media-extract` use the existing `fdisbull.media` API and JSON protocol. `module-analyze` uses the existing `fdisbull.decoder_modules` registry. `module-lift` is **not available** for EMC2: this patch does not claim UIL semantics.

## Formats and provenance boundaries

**PAK.** Read a little-endian `u32` member offset and a null-terminated ASCII member name for each directory entry, followed by the next offset. Two observed terminal shapes are supported: v2 zero DWORD and v3 explicit empty-name terminal offset. The v3 terminal offset can occur before EOF; remaining bytes are an opaque tail, not part of the last named member. Every index is preserved, including duplicate names. A matching archive shape does not prove all its members are data, executable or equivalent across titles.

**CPS.** DOS PC CPS has a compact little-endian header, optionally followed by a 768-byte 6-bit VGA palette. Supported bitmap methods are literal, Format3 RLE and Format4 LCW. Inside Format3, **the 16-bit long repeat count is big-endian** even though the CPS header is little-endian. Indexed pixel geometry is recognized as 320x200 only when the decompressed size is exactly 64,000 bytes. An unpaletted file may depend on the current game palette; don't fabricate RGB from its indices. `preview-png` converts an actual embedded 6-bit VGA palette to an indexed PNG for inspection, not proof of palette cycling or native display parity.

**WSA.** There are three distinct observed header layouts: 8-byte early, 10-byte early-flags, and 14-byte coordinate-bearing later WSA. Each contains a frame offset table and compressed delta records; the late version adds signed XY coordinates, while palette and XOR flags are distinguished. The compressed delta has an LCW envelope; decoded delta commands perform XOR/skip over a retained frame. A zero first offset means the initial frame must come from prior animation state. `decode_wsa_frames` raises until that state is explicitly provided. Do not zero-fill or infer a first frame. Frames are indexed byte arrays, not timestamps, rendered sprites or verified engine playback.

**EMC2.** An IFF-style script contains `ORDR` function entry words, `DATA` big-endian 16-bit instruction words, and optionally `TEXT`. Its generic core has **19 opcode IDs**, including stack/register operations, conditional/unconditional flow, evaluation and syscall. `kyrandia1-dos` starts at the ORDR word; `lol1-dos` starts at the following word. Syscall indices are **game-specific**. E.g. table entry zero is an item operation in Kyrandia but a wall operation in Lands of Lore, so no generic mapping from syscall number to UIL intent is safe. Static returns or dynamic calls remain open work, not implicit fallthrough.

## Evidence and verification

- The source-only implementation is based on pinned fDisBull 0.31.1 source. Its four GitLab interface files were compared byte-for-byte to `main` at `242e5343f5aa55dec95af3a49668a71ae14982c6` before patching. GitLab main may change after this check.
- Authored positive, malformed and bounded tests exercise read APIs, byte integrity, duplicate members, decoding, snapshot privacy and CLI/processor integration. No copyrighted game bytes are in the tests.
- Real-file smoke scans were made privately from a supplied Kyrandia v1.0 floppy ZIP, Kyrandia GOG CD DAT, and an English-only Lands of Lore 1.02d CD ISO. The table in the separate evidence report records counts and incomplete WSA chains. A valid static image or parse is not a runtime outcome.
- Native original-EXE interpreter matching, decoded WSA frame timelines, audio formats (TLK/ADL/XMI), VRM/APK, original versus reconstructed video raster comparison, and UDL→UIL→UDC equivalence are outside this prototype.

### Upstream reference implementations (for hypothesis tracing, not original-source evidence)

- [ScummVM indexed image and LCW/RLE implementation](https://github.com/scummvm/scummvm/blob/master/engines/kyra/graphics/screen.cpp)
- [ScummVM first/second generation WSA header readers](https://github.com/scummvm/scummvm/blob/master/engines/kyra/graphics/wsamovie.cpp)
- [ScummVM generic EMC interpreter](https://github.com/scummvm/scummvm/blob/master/engines/kyra/script/script.cpp)
- [Kyrandia-specific syscall table](https://github.com/scummvm/scummvm/blob/master/engines/kyra/script/script_lok.cpp)
- [Lands of Lore-specific syscall table](https://github.com/scummvm/scummvm/blob/master/engines/kyra/script/script_lol.cpp)

This reference code is from ScummVM's reimplementation and should not be mistaken for the original proprietary Westwood source or automatic behavioral equivalence.
