# fDisBull 0.3 architecture

The local engine separates decoding, recoverable facts, shared address interpretations and presentation. Imported code is never executed. Python coordinates native iced-x86, Capstone and LIEF libraries with SQLite and Pillow.

## Modules

| Module | Responsibility |
| --- | --- |
| `model.py` | Immutable image/region/seed records and retained source bytes. |
| `loader.py` | File-format routing and raw/ELF/PE/thin Mach-O mappings. |
| `inspection.py` | Header recognition, structural metadata and bounded file-backed strings. |
| `decoder.py` | Flat x86/ARM64 decode and structured operand references. |
| `dos.py` | Classic MZ validation, relocated real-mode image and minimum allocation. |
| `dos_decoder.py` | CS-relative iced16 decoding and conservative register transfer. |
| `dos_analysis.py` | CS-keyed DOS states/edges, segment evidence and recursive candidate discovery. |
| `dos_views.py` | Physical aliases, segmented views, inferred segments and decoded runs. |
| `analysis.py` | Non-DOS code/data queues, metadata indexing, shared representations and recovery. |
| `project.py` | SQLite lifetime/migration, persistence, annotations and byte versions. |
| `chimprec.py` | Offline candidate-slot/export matching and bounded IAT expansion. |
| `cli.py` | CLI/JSON-lines dispatch and public response/address normalization. |
| `render.py` | Stored-snapshot SVG/PNG export without a graphical desktop. |

## Identity and persistence

A project has one binary/architecture/bitness. Versioned instruction facts add decode context. Non-DOS contexts remain flat; MZ contexts include actual CS, such as `x86:16:little:cs=38ff`. Two CS:IP aliases may identify the same physical bytes while retaining different relative-control-flow interpretations. Names/comments/explicit representations identify the shared physical address within the byte version.

SQLite hexadecimal address keys preserve unsigned ordering; public physical addresses are hexadecimal strings. Each byte version retains mapped bytes/permissions, parent, label, origin, timestamp and mapped-image digest. A patch creates a child without overwriting its parent. Mapped hashes include region descriptions and differ from source-file hashes.

New projects retain source bytes and parsed metadata. File offsets and virtual mappings stay distinct; strings map through actual file-backed ranges. Schema 1/2 databases migrate to schema 3 without deleting versions/annotations. Schema-1 work reopens for reference backfill. Missing original source metadata remains unavailable until a new import; migration never reconstructs missing source bytes.

## Classic DOS loading

MZ load segment defaults to `0x1000`. The loader validates page/header/relocation extents, copies only the declared module, applies each segment fixup in loader order and zero-fills paragraph padding plus minimum allocation. Header/trailing overlays remain source-file evidence, not executable mappings. Initial CS:IP, SS:SP, PSP segment and all relocation records are retained.

This is a deterministic static image, not DOS memory emulation: PSP bytes, allocator maximum/heap contents, interrupt effects, devices and external overlays are not fabricated. Images requiring A20 wrapping or unsupported address ranges are rejected. A relocated segment word remains an unknown-role candidate until stronger evidence exists.

DOS patches operate on relocated memory. Rebuilding retained child file bytes undoes all relocation additions in reverse order, including duplicate/overlapping records. Allocation-only edits stay in child memory with no disk counterpart. Parent source/mapped bytes and annotations remain isolated.

## Analysis order and evidence

Analysis starts recursively from entry. Flat analysis follows direct branches/calls and permitted fallthrough, investigates mapped data references, then admits disconnected symbol/export seeds. Raw pointer/immediate matches remain candidates until corroborated.

DOS near targets retain CS and wrap the IP offset; direct far calls use the relocated selector plus offset. Known segment/register constants produce effective-address references. Unknown index/segment values stay unresolved. Caller-owned bytes resolve bounded LDS/LES and near/far pointer descriptors without simulating the whole machine. Instructions retain their state assumptions and CS context.

DOS entry work precedes relocation-backed far-call-pattern seeds. Statically observed data segments can reveal relocation-backed callback-pointer candidates. Paired literal stores that initialize offset/relocated-segment words can supply additional candidate seeds. This is not a linear sweep or a rule that every relocation is code. Provenance distinguishes decoded control-flow edges from candidate discovery.

State merging keeps bounded segment alternatives and drops unsupported/unknown constants. Call fallthrough assumes conventional DOS C preservation of DS/SS/BP/SP while general registers and ES become unknown. Deferred candidates may assume startup DS or a unique observed data segment. Interrupt handling is conservative and explicitly limited. These policies aid static investigation; none proves runtime behavior.

Persistent uniqueness keys deduplicate facts/work. Budgeted calls resume until implemented queues drain. `stable` means this rule set has no pending work, not complete reverse engineering. Unknown indirect flow, dynamic pointers, jump tables and external code can remain. Function entries are candidates, not established boundaries or complete CFG ownership.

## Segment inventory and presentation

`segments` reports candidates with inferred bounds, roles, provenance and decoded counts. These are not section permissions recovered from MZ, which supplies none. `code-regions` independently reports only contiguous stored instruction runs per CS, with exclusive ends; gaps remain unclassified.

Address labels resolve from user names and discovered/default identities. Structured operand references point to physical targets; queries resolve current names/representations into `display_operands` without rewriting numeric operands. A rename therefore updates all referring views. Explicit representations reset derived facts and trigger bounded reanalysis while retaining annotations. Inherited interpretations require revalidation after byte changes.

Disassembly selects one stored CS interpretation, exposes alternatives and reports nearest-row fallback when applicable. Xrefs retain source/target CS. Rendering consumes the same stored snapshot; it does not decode bytes or elevate candidates. A future native UI should use these interfaces.

## Agent and recovery seams

CLI and local stdin/stdout JSON-lines requests use shared project operations. There is no MCP/JSON-RPC or listening socket. Identification/inspection can run without a project. Caller filesystem permissions apply.

`chimprec.py` adapts the pinned CHimpREC slot/export-resolution methodology. Supplied export addresses anchor bounded captured-IAT recovery with aliases, ordinals and unknowns retained. Project candidate discovery uses recursive decoded references; lower-level pattern discovery stays heuristic. No live Windows attachment, module discovery, forwarder traversal or executable rebuilding occurs.

## Remaining boundaries

Classic MZ segmented disassembly is supported, including the original DinoPark image and its known `38ff:*` routines at the selected load segment. This does not establish full-game execution or every-instruction coverage. NE/LE/LX loading, runtime overlays, general jump-table recovery, complete function/CFG recovery, decompilation, runtime SMC capture, an emulator/debugger connection and a native desktop UI remain outside this build.

Other loaders cover supported little-endian x86/ARM64 ELF/PE and thin Mach-O variants. ELF/Mach-O import binding and some metadata remain partial; PE delay imports are not parsed. String scanning is bounded printable ASCII/ASCII-range UTF-16LE recovery. Linux is exercised by the verification receipt; macOS runtime verification remains open.
