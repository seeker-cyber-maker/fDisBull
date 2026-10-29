# DOS format findings and implementation follow-up

Date: 2026-10-29. This handoff records private static experiments on supplied
game packages and the resulting LE implementation. The LE feature is under
review. No supplied installer or game was executed, and no commercial bytes,
disassembly, or byte-retaining projects are included here.

The concrete Syndicate blocker was executable loading: its protected-mode
program needs LE object mapping and relocations before the existing x86-32
`NativeProcessor` can analyze it. Conventional MZ support already handles the
resident Eternam and Colonization images. None of these observations proves
that a game was written entirely in assembly or contains a particular script
interpreter.

## Sample identities and bounded results

These identities distinguish the privately tested editions; they are not
download references or claims about every release of each game.

| Sample basename | Role | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| `ETERNAM.EXE` | Eternam main | 110,888 | `1ed9504e918da578465b227fec06fd9d13fe3ffc4a0f99dbc7fee46cb9062cbc` |
| `VICEROY.EXE` | Colonization main | 494,910 | `a17ed64c27671e5e95236e54a7ddc85803a96ba822fbed05e1dad34d3917e2e3` |
| `MAIN.EXE` | Syndicate main | 518,713 | `bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078` |

Each main executable received exactly one 5,000-attempt autoanalysis call,
without manual seeds. All three exhausted that budget with `stable=false` and
`entry_complete=false`.

| Sample | Selected image | Stored instructions | Function candidates | Xrefs | Pending work |
| --- | --- | ---: | ---: | ---: | ---: |
| Eternam | Resident MZ, x86-16 | 4,542 | 193 | 5,497 | 683 |
| Colonization | Resident MZ, x86-16 | 4,009 | 85 | 5,214 | 759 |
| Syndicate | LE, x86-32 | 5,000 | 171 | 6,126 | 392 |

Eternam and Colonization used unmodified released **0.23.0**. That version
identified Syndicate's LE header but refused import. Syndicate's successful
pass used the new module on **0.24.0 source based on
`d31c1757f8e73b64783930b0e9932ecb80452eb1`**. These are format-coverage results,
not a same-version performance comparison. Counts are discoveries, not coverage
percentages; candidate functions are not recovered original symbols. Pending
totals include discovery-phase bookkeeping.

## Verified format observations

### Eternam: conventional MZ and a separate COM candidate

`ETERNAM.EXE` has a 6,144-byte header, 104,744 file-backed module bytes, 1,433
segment relocations, and no appended tail. Header entry `0000:0000` maps to
`1000:0000` / `0x10000` at the selected static load segment `0x1000`.
Compiler-runtime text suggests a Turbo C runtime; it does not establish the
source language of every routine.

The supplied 3,794-byte `tatou.com` was inspected using explicit COM selection;
it was neither imported nor analyzed. Its suffix alone does not establish a
format. Implementers should retain explicit selection for such headerless
inputs rather than promote filename guesses into signature evidence.

### Syndicate: LE objects, pages, and internal fixups

The main file's LE header starts at `0x28B8`; enumerated data starts at absolute
file offset `0x15C00`. Structural table offsets are LE-header-relative. Entry
object 1 has base `0x10000`; EIP `0x2D85C` yields linear entry `0x3D85C`.
These are declared static addresses, not observed DOS/4GW selectors or runtime
placement. The interpretation follows the pinned [definitions][1] and
[linker source][2].

| Object | Preferred base | Virtual bytes | File-backed bytes | Zero-filled bytes |
| --- | --- | ---: | ---: | ---: |
| 1 | `0x10000` | 261,620 | 261,620 | 0 |
| 2 | `0x50000` | 81,504 | 53,248 | 28,256 |
| 3 | `0x70000` | 3,072 | 0 | 3,072 |
| 4 | `0x80000` | 116,274 | 114,233 | 2,041 |
| Total | | **462,470** | **429,101** | **33,369** |

There are 105 pages under a 4,096-byte page model. The final physical page is
3,641 bytes, and its payload ends at EOF.

**10,060 fixup records represent 10,055 unique four-byte writes.** All observed
source types are offset32 (`0x07`). Target flags `0x00` occur 6,710 times and
encode 16-bit target offsets; `0x10` occurs 3,350 times and encodes 32-bit
offsets. Both forms write four bytes, and every observed object ordinal is
one byte; see the [definitions][1] and [dump reader][4].

Five writes cross page boundaries and occur twice in the records. The first
uses page offsets 4,095 and -1 for the same pointer at `0x10FFF`, targeting
object 2 plus `0xE555`. The resulting value is `0x5E555`. Signed source offsets
and duplicated records follow the [linker writer][3]; the loader retains both
records, performs one write, and rejects conflicting overlaps.

The supplied expansion `MAIN.EXE` also loads: four objects, 112 pages, 10,470
fixups, entry `0x3F16C`. Launcher `SYND.EXE` loads with two objects, 11 pages,
1,029 fixups, entry `0x138F8`. These two checks are loading surveys only.

### Colonization: resident MZ plus unresolved appended data

`VICEROY.EXE` declares an MZ extent ending at byte 132,709: a 9,216-byte header
and 123,493 file-backed resident bytes. The loader provides a 171,776-byte
minimum static allocation and applies 2,260 segment relocations. Entry
`110D:071D` maps to `210D:071D` / `0x217ED` at load segment `0x1000`.

The remaining **362,201 bytes are preserved but unmapped**. An RTLink/Plus
marker at file offset 107,101 lies inside the resident extent. It supports an
overlay-manager investigation; it does not establish a parsed overlay catalog,
load addresses, or that every appended byte is executable code.

The 89,178-byte `OPENING.EXE` illustrates another tail purpose: its declared MZ
extent ends at 67,271, followed by 21,907 bytes with NB02 markers at the start
and trailer and a matching trailer distance. This is CodeView debug-data
evidence, separate from the RTLink lead. No overlay mapper or symbol importer
was implemented.

## Implemented LE contract

The [LE guide](dos4gw-le.md), [loader](../src/fdisbull/le.py), and
[authored tests](../tests/test_le_loader.py) define the supported profile:

- Bare LE or an independent MZ secondary LE header; little-endian byte/word
  order, format level zero, i386/486 CPU, 32-bit objects, and 4,096-byte pages.
- Enumerated pages, explicit zero-fill pages, and BSS. Preferred object ranges,
  ownership, table bounds, and file backing are validated before acceptance.
- Internal offset32 source `0x07`; only target width bits `0x10` and `0x40`
  are accepted, selecting 16/32-bit offsets and 8/16-bit object ordinals.
  Signed source offsets span -3 through 4,095. Object-end target pointers are
  allowed; entry must identify an executable, file-backed byte.
- Limits: 64 MiB source and total mapped bytes, 4,096 objects, 16,384 pages,
  and 100,000 fixup records.

Explicit refusals include LX; other byte orders, levels, CPUs, or page sizes;
imported modules; selector/far/self-relative fixups; lists/chains/addends;
16-bit, resource, invalid, alias, or privileged objects; iterated/invalid/
compressed pages; and DLL, driver, or link-error modules. Unsupported means
outside this implementation, not necessarily malformed.

Automatic selection and `--image le` use the same checks. Unsupported LE never
silently falls back to the DOS bootstrap; `--image mz` explicitly selects a
valid preceding image in a separate project. Raw `--arch` bypasses container
loading. LE import rejects `--bits`, `--base`, nondefault `--load-segment`, and
`--slice-arch`; `--module` does not waive entry requirements.

Original source bytes remain separate from relocated memory. Fixups retain
original/relocated values and file fragments; fragmented or zero-filled
backing does not claim a contiguous file offset. Child patches change mapped
memory while preserving the parent and original container. Inverse fixups,
runnable rewriting, and LE `refresh-metadata` are unsupported. Status stays
compact; standalone inspection previews 10,000 fixups with a warning, while
project pagination and summary counts retain all supported records.

## Verification and audit limits

An independent reader derived from pinned Open Watcom sources before examining
the implementation, importing no fDisBull code, matched every mapped and
relocated byte of all four main-game objects. That sample does not exercise
16-bit ordinals or explicit zero-fill page records; authored fixtures cover
those forms separately.

The earlier module preview passed **132 focused tests**, including adjacent
loaders, native processing, restart, patch isolation, SVG export, and complete
relocation pagination. All **142 fDisBull wheel payload files** matched that
checkout. The installed wheel analyzed an authored two-instruction fixture and
reopened the existing real project without another game-analysis pass. These
receipts qualify that preview.

For PR preparation, the same nine focused test files passed **132 tests in
7.09 seconds** after rebasing onto upstream
`031b53eb953bfdc1d0e23c0ed49441031bad6e06`, at local code commit
`52f3792e47bd86cfdee583a1e29a7ae82f4db1e7`. Subsequent changes are documentation.
No game analysis was rerun. Neither qualification establishes native execution
or full-game behavior; the earlier wheel check is not a new wheel build for
the rebased commit.

Two private audit limits remain explicit: the initial public inspection
returned an incomplete `output_unavailable` delivery despite execution success;
a separate read-only API export captured its inspection document, still with
the preview warning. The original call log retained nine of eleven entries.
Saved final relocation/render outputs support the missing entries, but their
durations remain unavailable. No main-game analysis was repeated to repair
either record.

## Prioritized follow-up acceptance criteria

These are investigation gates, not commitments to implement an assumed format.

1. **Identify Colonization's RTLink structure before mapping overlays.** Establish
   directory boundaries, record grammar, payload extents, relocation rules,
   and dispatch references from independent evidence. Require authored valid
   and malformed fixtures, bounded parsing, and explicit overlay identities
   for reused address windows. Preserve unknown load order and unmapped tails;
   an RTLink marker alone cannot authorize guessed addresses.
2. **Qualify native DOS/4GW separately.** Establish backend capabilities and a
   reproducible authored executable first. Demonstrate entry transfer,
   selector-to-linear mapping, relocated memory, breakpoint identity, and
   restart behavior. Bind observations to input and memory versions. Only then
   assess a supplied game's bounded startup; static preferred bases cannot
   substitute for observed runtime mappings.
3. **Test resource-interpreter hypotheses.** Identify a concrete resource reader
   and candidate fetch/decode/dispatch path. Require evidence connecting file
   offsets, loaded bytes, opcode boundaries, control flow, and effects before
   defining a guest processor. Distinguish native routines and data tables from
   bytecode; retain compiled C, assembly, and mixed implementations as unresolved
   alternatives where evidence does not discriminate.
4. **Optionally import NB02 symbols.** First validate the opening program's debug
   directory and record types with primary documentation or an independent
   reader. Require bounded malformed-input tests and explicit segment/address
   translation. Preserve debug provenance and candidate status; do not treat
   debug records as loadable overlays or assume they describe `VICEROY.EXE`.

The earlier no-CD/media-size investigation remains separate in
[PR #21](https://github.com/seeker-cyber-maker/fDisBull/pull/21). A valid one-frame
music replacement can provoke rapid end/restart loops if the player immediately
replays it; neither an infinite loop nor CPU load was measured here. Locate and
qualify the actual playback loop before relying on that substitution. This LE
work changes no game code or media.

## Primary encoding references

All four references are pinned to Open Watcom commit
`5474be3542af05eee71be05fafc31bbe11f1415b`:

1. [exeflat.h][1]: LE headers, objects, pages, and relocation flags.
2. [loadflat.c][2]: object-relative entry and physical page writing.
3. [obj2supp.c][3]: internal targets and duplicated cross-page source records.
4. [wdfix.c][4]: independent fixup-record decoding grammar.

[1]: https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/watcom/h/exeflat.h
[2]: https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/wl/c/loadflat.c
[3]: https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/wl/c/obj2supp.c
[4]: https://github.com/open-watcom/open-watcom-v2/blob/5474be3542af05eee71be05fafc31bbe11f1415b/bld/exedump/c/wdfix.c
