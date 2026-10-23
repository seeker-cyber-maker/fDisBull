# fDisBull 0.8.2 architecture

The local engine separates decoding, recoverable facts, shared address interpretations and presentation. Imported code is never executed. Python coordinates native iced-x86, Capstone and LIEF libraries with SQLite and Pillow.

## Modules

| Module | Responsibility |
| --- | --- |
| `model.py` | Immutable image/region/seed records and retained source bytes. |
| `loader.py` | File-format routing, explicit image/slice selection and raw/ELF/PE/Mach-O mappings. |
| `inspection.py` | Header recognition, structural metadata and bounded file-backed strings. |
| `elf_metadata.py` | ELF GOT/relocation/version evidence, typed dynamic exports and native slot-proven PLT aliases. |
| `macho_metadata.py` | Mach-O dependencies, dyld/chained/indirect bindings, stub aliases and typed exports. |
| `macho_slices.py` | Validated universal/thin Mach-O inventory and explicit architecture selection. |
| `image_views.py` | Independent PE/DOS view inventory and validation boundaries. |
| `linkage.py` | Shared declared slot/stub call identities and static binding qualification over normalized flow. |
| `external_files.py` | Versioned immutable save/resource snapshots and structural types in file-offset space. |
| `file_references.py` | Authored instruction-to-file links with source fingerprints and dynamic field labels. |
| `shared_labels.py` | Evidenced byte correspondences and bidirectional labels across native/file fields. |
| `dos_state_refresh.py` | Legacy DOS fact guards and explicit bounded state rebuilding. |
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

A project has one selected image/architecture/bitness, while retaining the complete original file container. Versioned instruction facts add decode context. Non-DOS contexts remain flat; MZ contexts include actual CS, such as `x86:16:little:cs=38ff`. Two CS:IP aliases may identify the same physical bytes while retaining different relative-control-flow interpretations. Names/comments/explicit representations identify the shared physical address within the byte version.

SQLite hexadecimal address keys preserve unsigned ordering; public physical addresses are hexadecimal strings. Each byte version retains mapped bytes/permissions, parent, label, origin, timestamp and mapped-image digest. A patch creates a child without overwriting its parent. Mapped hashes include region descriptions and differ from source-file hashes.

New projects retain source bytes and parsed metadata. File offsets and virtual mappings stay distinct; strings map through actual file-backed ranges. Schema 1–7 databases migrate to schema 8 without deleting versions/annotations. Schema-1 work reopens for reference backfill. Missing original source metadata remains unavailable until a new import; migration never reconstructs missing source bytes.

## Container selection and platform linkage

Universal Mach-O selection validates the entire slice table, extents, alignment,
non-overlap and matching thin CPU/subtype headers before selecting a unique
explicit `x86`, `x86_64` or `arm64` slice. The host CPU never chooses a slice.
The loader maps only that image but retains full container bytes and separate
container/slice hashes. Disk metadata and patch translations add the selected
slice offset, so reported file offsets remain global to the original file.

For PE-bearing MZ files, automatic selection remains PE. Explicit `image=mz`
uses the ordinary DOS loader on its declared module with all extent/relocation
checks intact. `image_views.py` reports a valid PE even if its preceding DOS
view is unavailable. A magic prefix does not establish a runnable DOS image,
and `e_lfanew` does not define a guessed stub boundary. Different native views
are imported into separate projects; selection does not rewrite the container.

Platform adapters produce slot, stub, symbol-kind and dependency evidence.
ELF JUMP_SLOT/GLOB_DAT relocations identify GOT cells, while consistent verneed
indices can identify a required library/version. DT_NEEDED alone supplies only
candidates. COPY storage, TLS, object/absolute exports and IFUNC resolvers keep
their distinct roles rather than becoming automatic function seeds. PLT aliases
require decoded native slot proofs, without a universal entry stride.

Mach-O records load-library ordinals/scopes, dyld/chained binding sources,
exact indirect-symbol pointer/stub identities and export kinds/reexports.
Unsupported chains, incomplete tables and special lookup scopes remain
warned/unresolved. Neither adapter applies runtime relocations, executes a
resolver, loads a dependency or establishes the actual external provider.

`linkage.py` joins direct stub calls and normalized pointer-width loads from
declared slots into `import_call` identities. This is the same graph/data-flow
path across platforms. A declared runtime-unresolved slot is excluded from the
immutable-memory oracle, so zero/lazy/chained/planted on-disk pointer bytes cannot
become fabricated internal code targets. Captured-IAT recovery remains a
separate explicitly supplied snapshot/export-map evidence source.

Call effects retain the declared binding condition and `binding_evidence`.
`binding_unchanged_under_static_state` is true when modeled writes permit the
unchanged-slot assumption, false when a may-write/taint defeats it, and null
when proof is unavailable. The reported buffer range may still instantiate a
conditional contract; it does not prove the callee or effect ran. ELF and
Darwin ABI defaults enter at the coordinator boundary. `aarch64_darwin` handles
integer register arguments while leaving Darwin packed stack/variadic placement
unknown; it is distinct from the ELF AAPCS64 profile.

`refresh_metadata` reparses retained ELF/Mach-O/PE bytes, rebuilds metadata
slot/stub/export indexes and invalidates dependent advanced jobs and owned
edges. It preserves mappings, versions, original bytes and authored labels.
Patches rebuild child metadata through known global file mappings; the parent
index and results remain unchanged. This is separate from `refresh-facts` for
stored instruction effects. See [PLATFORMS.md](PLATFORMS.md) for commands and
the interpretation of these records.

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

Classic MZ segmented disassembly is supported, including the original DinoPark image and its known `38ff:*` routines at the selected load segment. This does not establish full-game execution or every-instruction coverage. Native boundary evidence and managed CIL inspection do not establish complete function/CFG recovery or source decompilation. NE/LE/LX native-image loading, runtime overlays, arbitrary indirect-transfer recovery, runtime SMC capture, an emulator/debugger connection and a native desktop UI remain outside this build.

Other loaders cover supported little-endian x86/ARM64 ELF/PE and thin or explicitly selected universal Mach-O images. Slot/stub metadata improves declared library identities; actual external providers, unsupported dyld chains and some metadata remain unresolved. PE delay imports are not parsed. String scanning is bounded printable ASCII/ASCII-range UTF-16LE recovery. Linux Python/CLI checks and cross-platform file fixtures are exercised; native macOS host execution remains unverified. Historical DinoPark 0.6 receipts are unchanged by this platform work.

## Flow and access indexes

Every permitted ordinary, conditional and call-return continuation now persists as a fallthrough edge. A call-return continuation explicitly assumes the callee returns. DOS next addresses wrap IP within the source CS; instruction identity remains `(version, context, address)`. `refresh-facts` atomically derives missing continuations and memory effects from stored instruction bytes, never extending discovery or using candidate function ranges as boundaries.

Schema 4 adds `memory_refs(version, context, source, fact_key, detail)` and `analysis_facts_revision`. The JSON detail retains native access category, width, segment, address expression, exact/possible intervals, repetition, unknowns and assumptions. Per-source facts are replaced when state is reprocessed; representation resets clear them and patches leave the parent untouched. A current revision marks all stored instructions indexed. Migrated projects without that marker use read-only re-decoding until an explicit refresh. The original `operand_refs` table remains compatible; it is not a writer index.

The CFG query follows exact stored edges independently of function labels, keeping call targets outside intraprocedural traversal and reporting missing destinations, unresolved transfers and budget frontiers. Older missing continuations can be reconstructed with separate provenance without writing. Highlighted sites carry exact shortest paths and edge evidence. A closed static graph is neither proven function ownership nor proof that a runtime path is feasible.


## Shared derived-analysis pipeline

Schema 5 adds versioned type definitions/bindings, qualified function summaries, signature catalogs, durable advanced jobs/results, byte/context dependencies and ownership of admitted derived edges. `advanced.py` coordinates native discovery with generic `semantics.py` → `flowdata.py` → `indirect.py`/`frames.py`/`summaries.py`. CPU-specific facts enter at the adapter; pure solvers never route on PE, ELF or instruction mnemonics. `function_analysis.py` computes many-to-many membership and `membership_view.py` supplies stored context-aware graphs.

`incremental.py` follows byte-range dependencies and transitive callers. It retracts owned edges, makes cached results stale, removes orphan inferred call seeds and reopens the durable queue. Representation changes close over shared instruction owners before retracting affected slices. Incomplete dependency coverage uses the explicit full-reset fallback. `typesystem.py` resolves nested fields through shared physical addresses and applies versioned layouts without changing bytes. Byte-derived signatures are requalified after invalidation and are not inherited as established identities by patched child versions.

`auto-analyze` is the end-to-end bounded fixed-point operation. Native `analyze` remains available; its basic pointer hints use snapshot evidence and its stable flag covers native queues only. Enabling advanced analysis replaces flat legacy pointer-target promotions with normalized flow proof. Read-only reports expose stale results, missing branches, budget frontiers and unknown arguments rather than silently manufacturing information. Full API/evidence contracts are in [ADVANCED_ANALYSIS.md](ADVANCED_ANALYSIS.md).

## External files and corrected DOS pointer propagation

Schema 6 adds `external_files`, `file_type_bindings` and `file_references`.
An external address is `(version, file name, byte offset)`, independent of every
CPU memory address. Attachments retain complete source bytes, SHA-256, kind and
author. Snapshot content is immutable for a given name/version; structural
interpretations can change. Native patches inherit attachments and authored
links without mapping those bytes into the executable.

The existing layout validator supplies scalar, array, pointer and nested
structure views. File queries return bounded values and compact one-level
layout descriptions. Type changes validate all native and file bindings before
committing. Labels resolve when queried, so changing a field updates file data,
cross-references, disassembly and graph exports without rewriting instructions.

Instruction-to-file relationships are explicitly authored and retain evidence,
CS context, widths and bounded strided spans. They never create native xrefs or
runtime heap objects. Native instruction fingerprints distinguish active,
awaiting-decode and stale links after patches. Previews have explicit counts
and truncation; file-xrefs supplies the separate paged relationship index.

DOS pointer revision 2 removes unsound LES/LDS promotion from immutable initial
descriptor bytes. DOS memory is mutable: even a nonzero initialized descriptor
can be overwritten before a load. Without reaching-value proof, the destination
register/segment stays unknown. Byte queries and descriptor-cell references
remain available. This does not add allocator, emulator or runtime file-I/O
semantics.

Legacy DOS projects expose `facts_stale` and hide obsolete native references in
raw disassembly. Dependent queries require explicit `refresh-dos-state`, which
resets native/derived facts, preserves authored interpretations and bytes, and
re-admits registered manual roots without their old register assumptions.
Rebuilding runs within a native instruction budget; derived jobs remain a
separate queue. Opening a project never silently discards its old analysis.


## Bidirectional field identity

Schema 7 adds `label_links` and `shared_label_names`. A link declares a pair of
native/file intervals and a one-to-one relative-byte mapping, with evidence and
author. File identity remains `(version, file name, offset)`; native data uses
physical address identity. Range links compose through other files or memory
buffers, so a block link also connects its interior fields. The mapping engine
has no ISA/container branches beyond the existing native address parser.

`link-labels` validates interval bounds, explicit-name conflicts and contradictory
offset cycles atomically. Resolution traverses the correspondence component
with explicit limits: 4096 retained links per version (including removed history),
256 corresponding locations per
field, 1 MiB per range, 100,000 validation location visits and 10,000 native name
annotations. A budget failure rejects an operation instead of returning a
partial shared identity. An explicit `name` can resolve the starting field's
conflicting names; interior conflicts remain independent.

`rename-file` and native `rename` write the shared explicit name for the selected
corresponding field. Presentation resolves that name on demand; no instruction
operands, bytes, semantic summaries or type definitions are rewritten. Without
an explicit shared name, current structural names provide the fallback.
Native/file typed leaves retain structural `path` and expose canonical `name`.
File references, native operands/xrefs, disassembly and graph/image exports use
the same resolution path. Instance-level renaming does not affect unlinked
instances of a type. A patch clones label interpretations into an isolated
child; parent names and mappings remain intact.

Instruction-to-file references remain distinct from field correspondence: an
instruction identity is not the field identity it accesses. Source fingerprints
continue to govern whether its authored file reference is active. Shared label
links are authored interpretations, not inferred byte equality, runtime I/O,
register/pointer values or native xrefs. A shared name never qualifies a library
contract or establishes a gameplay meaning.


## Correcting correspondence edges

Schema 8 adds `label_link_removals`, a per-version soft-removal record keyed by
link ID. `label-links` inventories active edges by default and optionally
includes removed history. Each edge keeps its original endpoints, size,
evidence and author; removal adds a reason, author and timestamp. IDs are
never reused, including when the same endpoints are linked again. All retained
records count toward the per-version link quota.

`unlink-labels` deactivates one complete range edge. Resolution, duplicate
matching and validation ignore removed edges, while the original relationship
remains auditable. The receipt captures starting-endpoint labels/members before
and after removal and reports alternate connectivity with
`connectivity_scope: "starting_endpoints"`; interior fields require their own
queries. It does not remove other
paths automatically. Repeating removal keeps the first removal metadata and
returns `removed: false`. Unknown IDs are rejected. Byte-version inheritance
copies removal state into the child; later corrections remain version-local.

Removal does not reverse rename history. Existing schema-7 shared-name rows
record a canonical storage anchor, not the original endpoint at which the
analyst chose the name. Keep each name at its existing anchor when an edge is
removed. Detached components resolve their local shared names, native
annotations and type paths; copying a prior shared name into every split
component would manufacture provenance. Before/after receipts expose the
actual outcome for review. `label-info.label_anchor` exposes the stored marker
location without pretending to recover its historical rename origin.
Attachments, type bindings, source file-reference
annotations, authored native annotations, bytes and analysis facts are retained.
