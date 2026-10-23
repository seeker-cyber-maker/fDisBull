# Verification receipt — fDisBull 0.7.0

Final integrated `python -m pytest -q`: **635 passed**, exit 0, **42.16 seconds**.
`python -m compileall -q src/fdisbull` also passed. Qualification ran on Linux
x86-64, CPython 3.12.14, iced-x86 1.21.0, Capstone distribution 5.0.9, LIEF 1.0.0,
Pillow 12.3.0 and pytest 9.1.1. No imported program, native library or managed
assembly was executed. Native macOS host execution remains unverified.

## Linux and macOS linkage

Actual GCC-produced ELF files exercise ordinary PLT calls, CET split PLTs,
`-fno-plt` GOT calls, symbol versions, dependency requirements, COPY storage,
ELF32 implicit REL addends and code/data/IFUNC export distinctions. Public
project tests establish library-call grouping, import-call xrefs and qualified
`memcpy`/`memset` buffer effects. A planted on-disk GOT pointer does not become a
resolved external callee. Unversioned imports retain unknown provider identity.

Mach-O tests use authored file-format records with actual x86-64/ARM64 code,
load commands, dyld binding streams, indirect-symbol tables, export tries,
relocations and chained fixups. These are not Apple-compiled application tests.
Both CPU workflows recover declared stub/slot calls and conditional library
effects through the same normalized analysis. Tests distinguish loaded-library
ordinals from LC_ID_DYLIB, data/TLV/absolute/reexport identities from code,
section-relative relocation offsets and widths, and unresolved/encoded pointer
contents from external code addresses. Data exports in executable segments
remain excluded from deferred function seeds and selected module exports.
Nonzero binding addends cannot supply a function-entry contract.

Mach-O ARM64 selects the separate Darwin integer-register ABI profile. Packed
stack and variadic placement remain unknown without type evidence. Current
adapters are x86 16/32/64 and little-endian ARM64; this is not every ISA or every
platform instruction/ABI rule.

## Explicit container selections

Universal Mach-O tests cover FAT32/FAT64 tables in both byte orders, thin CPU
matching, full-table extent/alignment/overlap validation, unsupported CPU
inventory, ambiguous subtype rejection and explicit `x86`, `x86_64`, `arm64`
selection. Public import/module/CLI/JSON tests retain the full original file,
use original-container file offsets and decode only the selected image. Child
patches preserve the parent and unselected sibling bytes, including after
deleting the input and reopening the database.

A dual PE/MZ fixture has an actual valid DOS header, segment relocation and
16-bit stub before its native PE header. Default/native PE and explicit
`--image mz` produce independent projects with different entries and contexts.
DOS patches undo/reapply its relocation without modifying the PE overlay.
Malformed DOS page counts or relocation extents reject the DOS choice while
leaving a structurally valid native PE view available. Both views render and
reopen without the input path. An MZ prefix alone is not a loadable DOS image.

## Identity, refresh and evidence regressions

Recovered imports supersede original metadata when selecting contracts.
Unknown, ordinal-only, incompatible and non-callable alternatives prevent a
contract; ELF version normalization cannot erase a competing unknown identity.
Shared import binding records preserve `identity_basis`, unresolved external
target and static binding-history qualification. Real PE tests include an
intervening XOR of the IAT cell: the declared request remains visible, while
its conditional effects explicitly retain the failed unchanged-binding proof.
Buffer `resolved` never means a runtime provider was observed.

Metadata refresh reparses retained source bytes, preserves versions, mappings
and authored labels, retracts stale derived facts and does not revive orphaned
jobs. Reanalysis, explicit candidate restoration, source deletion, restart and
child-version symbol reindexing are exercised through public APIs.

## Bundled projects and wheel

`examples/platforms-v07.json` records fresh public import/auto-analysis and
separate-process restart for five projects:

| Project | Source | Stored instructions | Conditional bulk effects |
| --- | --- | ---: | ---: |
| `platform-linux.fdb` | Compiled `platform-linux.c` / ELF shared library | 18 | 3 |
| `platform-mac-x86_64.fdb` | Authored universal Mach-O, x86-64 slice | 6 | 2 |
| `platform-mac-arm64.fdb` | Same container, ARM64 slice | 8 | 2 |
| `platform-pe.fdb` | Authored dual PE/MZ file, native view | 3 | 0 |
| `platform-mz.fdb` | Same file, DOS view | 4 | 0 |

All reach their implemented fixed points, retain exact original bytes and
reopen in a separate process after deletion of the imported temporary paths.
Individual receipts, closed portable SQLite projects and PNG/SVG exports are
included. All SVGs parse; the ARM64 disassembly PNG was visually inspected for
labels, operand rendering and clipping.

`dist/fdisbull-0.7.0-py3-none-any.whl` SHA-256:
`f10afe72f62aeb8ec4cd34d31e0a3c44128f9d898dc5c5a4a07f4ea8d50ff012`.
All **39** packaged Python modules exactly match the final source. Imported
directly from the wheel outside the source working directory, all five public
workflows, library effects, full-source retention, separate-process restarts,
zero-work repeat with unchanged options and CLI DOS selection pass.
`examples/wheel-v07-check.json` retains the result.

## Retained work and limits

The original DinoPark project and its 0.6 targeted-analysis receipts are
unchanged. Its database SHA-256 remains
`2e8824f8d92df587f41104a63edf4992d656688119a39fa6816f00b2ef2358b9`.
That receipt still has two derived jobs done and 650 pending; this platform
release does not claim a new whole-game completion or settle gameplay fields.
See `VERIFICATION-0.6.md` for those measurements and limitations.

No runtime relocations, dyld slides, library loading, debugger/watchpoints,
emulator, Wine/Apple-container backend, CIL dataflow or decompiler is added.
Unsupported PLT forms, fixups and metadata remain explicit. A static fixed
point describes the implemented bounded rules, not complete binary coverage
or observed behavior. See `PLATFORMS.md` for operating examples and limits.
