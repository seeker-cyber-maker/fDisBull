# fDisBull 0.2 architecture

The local engine separates instruction decoding, recoverable facts, shared address interpretations and presentation. Imported code is never executed. Python coordinates native iced-x86, Capstone and LIEF libraries with SQLite and Pillow.

## Modules

| Module | Responsibility |
| --- | --- |
| `model.py` | Immutable image/region/seed records and retained source bytes. |
| `loader.py` | Bounded raw/ELF/PE/thin Mach-O mapping at preferred static addresses. |
| `inspection.py` | Byte-based header recognition, structural metadata and bounded file-backed strings. |
| `decoder.py` | One-instruction decode, direct control/data targets and structured operand references. |
| `analysis.py` | Metadata indexing, recursive code/data queues, shared representations and recovery integration. |
| `project.py` | SQLite lifetime/migration, persistence, annotations, queries and child byte versions. |
| `chimprec.py` | Offline candidate-slot/export matching and bounded IAT range expansion. |
| `cli.py` | CLI and JSON-lines dispatch, public address normalization and response envelopes. |
| `render.py` | Snapshot-backed SVG/PNG export without a graphical desktop. |

## Identity and persistence

One project has one architecture, bitness and flat address space. Decoded facts and annotations carry byte version, decode context (for example `x86:64:little`) and address. Zero-padded hexadecimal SQLite address keys preserve unsigned 64-bit ordering. Public address fields use hexadecimal strings.

Each version retains mapped region bytes/permissions, parent, label, origin, timestamp and mapped-image digest. The application preserves existing byte snapshots: a patch creates a child instead of overwriting its parent. Mapped-image digests include region descriptions and bytes, so they differ from the original file digest.

New projects also retain original source bytes, inspection metadata and indexed static symbols. File offsets and virtual mappings remain distinct; runtime relocations/load bias are not applied. Strings map only through file-backed ranges. Unknown bindings are null rather than guessed.

Schema 1 projects migrate in place to schema 2 without deleting original versions or annotations. Prior work is reopened so analysis can backfill structured references. Those projects lack full original source bytes/metadata; information queries report this explicitly. Reimport into a new project to recover the new metadata. Retained mapped bytes remain usable if the source file is missing.

## Analysis order and convergence

The entry point begins the recursive code queue. Decoding follows direct branches/calls and permitted fallthrough, persists operand references/xrefs, and queues mapped memory targets for investigation. Once code work drains, data tasks classify strings, import slots, scalar values and pointer candidates. A pointer alone does not establish code. A corresponding indirect control-flow reference can corroborate a pointer target and queue it as code.

Disconnected symbol/function/export seeds enter a later recursive phase. New code/data evidence can reopen related work; persistent uniqueness keys deduplicate facts and tasks. A bounded call reports pending work and whether another call is required. `stable` means the implemented inference rules have no queued work; it does not certify exhaustive reverse engineering. Invalid bytes, blocked definitions and unresolved indirect flow remain inspectable.

Functions are candidate entries, not proven boundaries or block ownership. There is no complete CFG, general jump-table recovery, symbolic execution or decompiler.

## Shared address interpretations

Address labels resolve from user names, indexed/recovered symbols and function/default names. Explicit representations coexist with derived data items. Structured operand references point to target addresses, so callers resolve names/types when queried rather than copying annotations into instruction text. Disassembly retains numeric operands and adds `display_operands`; image rendering consumes the resolved field.

`represent` records a bounded code/data range, clears derived analysis and automatically reanalyzes within budget while retaining annotations. Explicit data definitions block overlapping decoding; explicit code definitions can admit mapped ranges as code. Parent and child byte versions remain isolated. Patches inherit names/comments/definitions with provenance; **inherited interpretations need revalidation after changed bytes**.

## Offline recovery

`chimprec.py` adapts the pinned CHimpREC candidate-slot/export-resolution method. Supplied export addresses anchor candidate pointer cells; bounded expansion retains aliases, ordinal identities, padding and unresolved values. The project command selects candidates from recursively decoded memory references. The standalone helper additionally offers heuristic x86 pattern discovery. Recovery receipts and resolved shared slot labels persist per version. This is not live Windows attachment, runtime module discovery, forwarder traversal or executable rebuilding.

## Agent and presentation seams

The stdin/stdout JSON-lines protocol routes to the same project methods as one-shot CLI commands. It is not MCP/JSON-RPC and opens no network socket. Metadata inspection also works without a project. Database-backed views return one stored snapshot and do not silently decode gaps; exports include version/hash provenance. A future native UI should consume these query/snapshot interfaces.

## Current boundaries

Decoders support flat raw x86 16/32/64-bit and little-endian ARM64. Native loading supports selected x86/ARM64 ELF, PE and thin little-endian Mach-O. DOS MZ/NE/LE/LX headers can be recognized and inspected, but segmented DOS executable loading remains missing; raw x86/16 requires an extracted flat segment. Fat Mach-O, big-endian images and relocatable object loading need further work.

ELF/Mach-O import binding and some metadata are partial; warnings identify unresolved information. PE delay imports are not parsed. String scanning covers printable ASCII and ASCII-range UTF-16LE heuristically. No runtime SMC capture, emulator/debugger connection, automatic LLM agent or native desktop UI is implemented. Linux is exercised by the verification receipt; macOS runtime verification remains open.
