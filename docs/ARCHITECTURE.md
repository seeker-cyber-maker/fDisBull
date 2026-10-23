# fDisBull 0.5 architecture

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
| `boundaries.py` | Read-only byte-span ownership and candidate native prologue/epilogue evidence. |
| `modules.py` | Explicit offline DLL/shared-library selection and bounded analysis roots. |
| `managed.py` | Dependency-free CLR recognition; optional metadata and method-local CIL decoding. |
| `decoder_check.py` | Non-executing iced/Capstone comparison at bounded proposed x86 starts. |
| `memory.py` | Native read/write effects, exact/possible intervals and read-only cross-context queries. |
| `facts.py` | Persisted access facts and explicit backfill of stored control-flow continuations. |
| `cfg.py` | Exact-entry, context-sensitive reachable slices and evidence paths; calls kept separate. |
| `cfg_render.py` | Basic-block SVG export with highlighted instruction sites. |
| `project.py` | SQLite lifetime/migration, persistence, annotations and byte versions. |
| `chimprec.py` | Offline candidate-slot/export matching and bounded IAT expansion. |
| `cli.py` | CLI/JSON-lines dispatch and public response/address normalization. |
| `render.py` | Stored-snapshot SVG/PNG export without a graphical desktop. |

## Identity and persistence

A project has one binary/architecture/bitness. Versioned instruction facts add decode context. Non-DOS contexts remain flat; MZ contexts include actual CS, such as `x86:16:little:cs=38ff`. Two CS:IP aliases may identify the same physical bytes while retaining different relative-control-flow interpretations. Names/comments/explicit representations identify the shared physical address within the byte version.

SQLite hexadecimal address keys preserve unsigned ordering; public physical addresses are hexadecimal strings. Each byte version retains mapped bytes/permissions, parent, label, origin, timestamp and mapped-image digest. A patch creates a child without overwriting its parent. Mapped hashes include region descriptions and differ from source-file hashes.

New projects retain source bytes and parsed metadata. File offsets and virtual mappings stay distinct; strings map through actual file-backed ranges. Schema 1/2/3 databases migrate to schema 4 without deleting versions/annotations. Schema-1 work reopens for reference backfill. Missing original source metadata remains unavailable until a new import; migration never reconstructs missing source bytes.

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

Address labels resolve from user names and discovered/default identities. Structured operand references point to physical targets; queries resolve current names/representations into `display_operands` without rewriting numeric operands. A rename therefore updates all referring views. Explicit representations reset derived facts and trigger bounded reanalysis, or leave work queued with `defer`, while retaining annotations and the same byte version. An explicit `unexplored` definition holds a range out of automatic code/data work until it is reclassified; held ranges do not prevent stability of the remaining implemented queue. Inherited interpretations require revalidation after byte changes.

Disassembly selects one stored CS interpretation, exposes alternatives and reports nearest-row fallback when applicable. Xrefs retain source/target CS. Rendering consumes the same stored snapshot; it does not decode bytes or elevate candidates. A future native UI should use these interfaces.

## Byte ownership and candidate function boundaries

`BoundaryMixin.locate` queries all stored instruction/data/definition spans containing a physical byte. Instruction contexts remain independent, including overlapping x86 streams and MZ aliases. Each owner reports byte offset and `begin`/`part`/`end`/`single`; its inclusive final-byte `end` and following-address `end_exclusive` make representation selection unambiguous. The query decodes no new instructions and can expose conflicting ownership instead of choosing silently.

`function_patterns` examines native frame-setup/teardown patterns, returns and possible tail jumps. The default evidence comes from stored instructions and current snapshot bytes. An optional bounded raw scan proposes patterns only in unclassified executable mappings, excluding explicit definitions and known data/instruction spans. Raw DOS interpretations carry candidate CS windows. Neither path changes function facts or queues work. Function starts and ends remain hypotheses; frame omission, shared exits, internal jumps and matching data prevent universal signature-based boundaries.

## On-demand modules and managed assemblies

`modules.analyze_module` imports one requested local module into a new project, validates an optional export name/ordinal or preferred virtual entry, and runs one analysis budget. Selection happens before database creation. Forwarded exports are rejected and other modules are not loaded. A selected root set persists in metadata so later representation resets and deferred phases preserve the requested scope. Module mode permits files with no executable entry; an absent entry is not silently treated as executable code.

CLR recognition is separate from native-machine decoding. `managed_kind` validates PE CLR/metadata structure without optional dependencies, distinguishes missing/invalid managed evidence, and protects recognized pure-IL/invalid payloads from accidental native entry analysis. Metadata/method decoding uses the optional pinned dnfile/dncil extra. `Project.managed` reads the selected version's retained source bytes, allowing method inspection after the original file disappears.

Managed method identity is the assembly's MethodDef token plus local IL offset. Native VA, RVA and disk offset stay separate. A CIL query decodes a bounded method stream and resolves available token/call names and branch targets; it does not insert x86 instruction rows. It reports partial/invalid bodies and native/runtime/PInvoke methods explicitly. Linear CIL decoding is not IL type/stack verification, full EH recovery or C# reconstruction. Precompiled mixed-mode/NativeAOT payloads require their own native evidence. Actual Godot ALD assembly qualification remains open.

## Decoder comparison and research seam

`compare_decoders` supplies the first non-executing investigation surface: iced-x86 and Capstone receive the same bytes/mode/address at up to fifteen proposed starts. Results retain both predictions and distinguish validity, length and textual differences; no decoder becomes authoritative and no candidate enters stored analysis automatically. Formatting/alias differences are not semantic verdicts. Two-engine comparison currently supports x86 only.

[DECODER_RESEARCH.md](DECODER_RESEARCH.md) relates this seam to Sandsifter/Battelle and the proposed SNO x86 candidate adapter. A physical CPU observation, translated execution and a software prediction have distinct provenance. Existing QP2A proposal/verifier machinery is useful design material; it does not establish an x86 semantic verifier. [WINE_DEBUGGER.md](WINE_DEBUGGER.md) specifies a future isolated execution backend, not an implemented/macOS-qualified debugger. [CORPUS.md](CORPUS.md) records collection discovery and fixture limitations.

## Agent and recovery seams

CLI and local stdin/stdout JSON-lines requests use shared project operations. There is no MCP/JSON-RPC or listening socket. Identification/inspection can run without a project. Caller filesystem permissions apply.

`chimprec.py` adapts the pinned CHimpREC slot/export-resolution methodology. Supplied export addresses anchor bounded captured-IAT recovery with aliases, ordinals and unknowns retained. Project candidate discovery uses recursive decoded references; lower-level pattern discovery stays heuristic. No live Windows attachment, module discovery, forwarder traversal or executable rebuilding occurs.

## Remaining boundaries

Classic MZ segmented disassembly is supported, including the original DinoPark image and its known `38ff:*` routines at the selected load segment. This does not establish full-game execution or every-instruction coverage. Native boundary evidence and managed CIL inspection do not establish complete function/CFG recovery or source decompilation. NE/LE/LX loading, runtime overlays, general jump-table recovery, runtime SMC capture, an emulator/debugger connection and a native desktop UI remain outside this build.

Other loaders cover supported little-endian x86/ARM64 ELF/PE and thin Mach-O variants. ELF/Mach-O import binding and some metadata remain partial; PE delay imports are not parsed. String scanning is bounded printable ASCII/ASCII-range UTF-16LE recovery. Linux is exercised by the verification receipt; macOS runtime verification remains open.

## Flow and access indexes

Every permitted ordinary, conditional and call-return continuation now persists as a fallthrough edge. A call-return continuation explicitly assumes the callee returns. DOS next addresses wrap IP within the source CS; instruction identity remains `(version, context, address)`. `refresh-facts` atomically derives missing continuations and memory effects from stored instruction bytes, never extending discovery or using candidate function ranges as boundaries.

Schema 4 adds `memory_refs(version, context, source, fact_key, detail)` and `analysis_facts_revision`. The JSON detail retains native access category, width, segment, address expression, exact/possible intervals, repetition, unknowns and assumptions. Per-source facts are replaced when state is reprocessed; representation resets clear them and patches leave the parent untouched. A current revision marks all stored instructions indexed. Migrated projects without that marker use read-only re-decoding until an explicit refresh. The original `operand_refs` table remains compatible; it is not a writer index.

The CFG query follows exact stored edges independently of function labels, keeping call targets outside intraprocedural traversal and reporting missing destinations, unresolved transfers and budget frontiers. Older missing continuations can be reconstructed with separate provenance without writing. Highlighted sites carry exact shortest paths and edge evidence. A closed static graph is neither proven function ownership nor proof that a runtime path is feasible.
