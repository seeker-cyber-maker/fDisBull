# Zork interpreter investigation — 2026-10-28

## Question and boundary

Starting from the supplied GOG installer, identify signs of an interpreter without assuming an engine, test the proposed division between executable and story, and estimate a useful scene harness. Static analysis is supplemented by a bounded run with the locally installed fDisBull 0.20.0 release. Derived files and the fDisBull databases are in `/tmp/fdisbull-zork-analysis.rBn9QZPl` and may be removed by the OS. The original installer is unchanged.

## Source identities

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| Supplied installer | 13,847,648 | `c92fd01bd7478e92179a98fb8386e86b915e30e5f3d285638fb578a1e95f8f64` |
| `_ZORK1.COM` | 11,402 | `2a6f366349be71ef4a164e3fc9c31a4a3d8c24ee6ddac93ed345c993c3562514` |
| `DATA/ZORK1.DAT` | 92,160 | `0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd` |

`innoextract -l` enumerated the files, and selective extraction obtained the two named files and launch configuration. A different installer member, `__support/save/SAVE/ZORK1.DAT`, is a separate save-related file and was not treated as the story. The launch configuration invokes `_zork1.com` after mounting the game directory. Listing and extraction do not establish successful execution.

## From naive clues to a bounded identification

1. Inventory the distribution and launch path without naming an engine. The small executable sits beside a much larger data file. Its readable strings include `DATA\\ZORK1.DAT`, a separate save path, generic file and memory errors, and `IBM/MS-DOS 2.0 Interpreter Version M2`. This is strong evidence of a reusable interpreter architecture, but neither a filename nor a string proves execution or identifies the bytecode format.
2. Check actual instruction and file references. fDisBull imported the COM bytes as explicit 16-bit raw x86, with base and entry `0x100`, and decoded an entry jump to `0x1192`. Recursive native discovery decoded 1,175 instructions; its queue became stable within this configured static traversal, which does not mean full binary coverage. The path string starts at file offset `0x3` (declared flat address `0x103`); fDisBull reports candidate immediate references at `0x28d6` and `0x2aa5`. These are heuristics, not proven file-open calls. The separately attached story has no authored cross-reference and no runtime access evidence.
3. Inspect the data file independently. Its bytes match a coherent Version 3 Z-machine header: release 88, serial `840726`, high memory `0x4e37`, initial PC `0x4f05`, dictionary `0x3b21`, object table `0x02b0`, globals `0x2271`, static-memory base `0x2e53`, and abbreviations `0x01f0`. The header declares 84,876 bytes; summing bytes `0x40` through the declared end modulo 65536 gives `0xa129`, matching its stored checksum. The actual file is 92,160 bytes; the remaining 7,284 bytes must not be silently counted as story length. See the [header standard](https://inform-fiction.ifarchive.org/zmachine/standards/z1point1/sect11.html) and [verification opcode](https://inform-fiction.ifarchive.org/zmachine/standards/z1point1/sect15.html).
4. Inspect a discriminating program fragment. At story offset `0x4f05`, `e0 03 2a 39 80 10 ff ff 00` parses under Version 3 rules as `call` with packed routine address `0x2a39`, two large-constant arguments `0x8010` and `0xffff`, and result variable `0`. The packed address maps to `0x5472`, which begins with local count 3 and six local-default bytes. The next bytes `e1 97 00 00 01` fit `storew` with a variable and two small constants. These internally consistent checks strongly identify the data as Version 3 Z-machine code, not merely an arbitrary data blob. See [instruction encoding](https://inform-fiction.ifarchive.org/zmachine/standards/z1point1/sect04.html) and [opcode definitions](https://inform-fiction.ifarchive.org/zmachine/standards/z1point1/sect15.html).

The strongest current conclusion is that this is a DOS interpreter distribution containing a structurally valid and checksum-consistent Z-machine v3 story. The 0.20.0 run below executes the original executable and observes matching story identity and responses in a directory containing that story. The native file-open/read path and bytecode dispatch remain unobserved; observing those, correlating loaded story bytes with a changing virtual PC and checking the native dispatch cycle would establish the implementation mechanism directly. A second conforming interpreter producing matching bounded observations would be useful independent corroboration, not proof of whole-game equivalence.

## Actual 0.20.0 run

The shared installation reports `0.20.0`, located under `/Users/Shared/fDisBull/releases/0.20.0-4f7791b`. Its native macOS backend SHA-256 is `1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`. A fresh project imported the original binary with `--image com`; runtime launch verified its original source and 16 entry bytes. The extracted installer files `SETUP.INF` and `NNANSI.COM` were also present in the temporary game directory.

The captured opening frame displayed West of House and revision 88 / serial 840726, matching the story header. Queued `open mailbox` produced a frame reporting that the mailbox revealed a leaflet; `look` then reported the mailbox contains a leaflet. The move counter advanced from 0 to 1 to 2. These are observed game outputs for one run, not a full replay or VM-dispatch trace. The run closed cleanly and its owned process was reaped. Screenshot artifacts in the private project are `fae1cd98d99b4aa5bed4a41bacafdbc1`, `e4a5787fef194c7caea2010f0c065620`, and `7d531098c83548ad93014cac24beed89` for opening, action and revisit respectively. Three individual guest advances reported host elapsed 200.5, 112.872 and 111.565 ms; these are not end-to-end harness or authoring times.

## Separation and harness implications

The executable supplies the host implementation, I/O and virtual-machine operations. The story file contains virtual instructions and mutable initial state as well as tables and text: calling it only scripted data can hide that it is itself an executable program. Story offsets, native COM offsets, real-mode addresses, virtual PC, dynamic memory, and a save file are distinct identities. The Z-machine object table is a starting point for discovery, not automatically a room list; hidden objects and conditional behavior must not leak into the player view.

The older checkout initially inspected lacked COM runtime support; that conclusion does not apply to the installed 0.20.0 release. Version 0.20 requires explicit COM import and has now launched this actual game. Its normal scene API depends on screenshot/geometry-backed definitions. No character/text stream adapter for this game was demonstrated. The bounded command sequence works through the debugger; an independently usable text scene harness has not yet been built.

Two reasonable paths to a first playable slice:

- **Existing compatible Z-machine interpreter plus adapter:** launch the exact story with a selected, locally verified interpreter, expose prompt/output and command submission, retain transcripts, process and story identities, save/restore isolation, and measure startup-to-first successful `look` or other verified command. The original story still supplies game behavior. Inventory/parser/world-state access depends on the interpreter's actual API; plain text alone does not establish hidden state. This path has not been implemented or timed here.
- **fDisBull original DOS route:** reuse the verified 0.20 COM launch and keyboard path, then obtain reliable text through a qualified text buffer, output hook or OCR with explicit ambiguity, and add prompt detection plus checked outcomes. A screenshot-backed action can provide a narrower proof, but a general machine-readable transcript remains unverified.

For either route, start with one recognized prompt and one action, compare the response and actual subsequent state, then add a blocked action, movement, revisit and save/restore. Record raw output, freshness, command delivery, observed result, story and interpreter hashes, wall time and game-turn policy. An unrecognized or incomplete prompt is unknown; do not invent a scene or infer success from input delivery. A Zork prompt already provides textual play, so a wrapper may be faster than reconstructing all scenes, but room count and a complete conversion are unknown. Estimates remain hypotheses: the demonstrated keyboard and screenshots permit a narrow manually observed driver now; a robust automatic prompt/text adapter may take hours to days, depending on the available observation surface and validation. No full harness authoring time has been measured.

## Suggested fDisBull investigation-skill additions

- Begin with a format-neutral executable/resource inventory and startup configuration; report clues with competing explanations.
- Search for generic engine, file handling and error strings, then link candidate references to the actual loader/dispatcher with native control flow and runtime reads where possible. Treat heuristic references and unreachable code accordingly.
- For suspected bytecode, test header ranges, lengths, checksums and more than one decoded instruction against a documented format; distinguish structural identification from runtime confirmation.
- Track interpreter binary, story/resource, save, versions, native addresses and virtual addresses as separate hashed identities; associate changed-resource counterexamples with the relevant revision.
- Prefer the existing game's own observable text and command interface for a first harness. Only expose knowledge justified for the player; use state or verified outputs for outcomes. Add scene-specific layers incrementally and retain missing behavior as unknown.
- Include COM-versus-MZ and text-capture capability checks before estimating or promising a live fDisBull harness. Track measured setup, first useful action, revisits and failure cases rather than presenting an estimate as a benchmark.

## Reproduction notes

`innoextract` selectively extracted `_ZORK1.COM`, `DATA/ZORK1.DAT`, and the DOSBox launch configuration. `fdisbull import ... --arch x86 --bits 16 --base 0x100 --entry 0x100`, `analyze --max-instructions 1500`, `attach-file` and `xrefs` produced the static results above. Header values and checksum were calculated directly over the extracted bytes. REA was not connected: its doctor reported Codex registration drift and no native analysis provider; its setup was not applied. No result is represented as REA evidence.
