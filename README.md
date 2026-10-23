# fDisBull 0.8

Attach save files, resource tables and other data to an existing analysis. Their bytes and SHA-256 are retained in the project, so byte queries and typed fields remain available after the source file is removed. Attached files have their own **file name + byte offset** identity; they do not become executable memory or code seeds.

```bash
fdisbull attach-file analysis.fdb ./resource.dat --name resource.dat --kind resource
fdisbull files analysis.fdb
fdisbull file-bytes analysis.fdb resource.dat --offset 0 --size 64
fdisbull define-type analysis.fdb Record record.json
fdisbull apply-file-type analysis.fdb resource.dat Record --offset 0 --name record
fdisbull file-data analysis.fdb resource.dat --offset 0
```

`record.json` uses the existing scalar/array/struct type definitions; for example, `{"kind":"struct","size":4,"fields":[{"name":"count","offset":0,"type":"u16"},{"name":"flags","offset":2,"type":"u16"}]}`. Values are interpreted from retained little-endian bytes. A field name records an interpretation, not a proven gameplay meaning.

Use `file-reference` to record an explicit, evidenced relationship from a stored instruction to one file offset or a strided set of offsets. `file-xrefs` queries those annotations; subsequent disassembly and CFG exports resolve their current field names. These links do not recover runtime file I/O or establish where a loaded resource buffer lives in memory. Source-byte changes make the links stale.

Attachments and their type bindings are inherited by child byte versions, with parent state preserved. Content is immutable under a given file name in a version: reattaching identical bytes is idempotent, while changed bytes require another name. Attachments share a 64 MiB per-version budget. See [EXTERNAL_FILES.md](docs/EXTERNAL_FILES.md) for a complete example, reference evidence and limits.

Older DOS projects, including the packaged historical DinoPark analysis, need an explicit state refresh before querying affected analysis. An earlier shallow `LES`/`LDS` rule treated initial descriptor bytes as current far pointers even after possible writes; that could produce false exact memory locations. `analysis-status` now marks those legacy facts `facts_stale: true` and cannot report stable. Rebuild them with:

```bash
fdisbull refresh-dos-state examples/dinopark.fdb --max-instructions 10000
fdisbull analyze examples/dinopark.fdb --max-instructions 100000
fdisbull auto-analyze examples/dinopark.fdb --max-functions 200 --max-rounds 8
```

Repeat bounded `analyze` until native work is stable; derived `auto-analyze` work has its own pending state. Refresh preserves bytes, versions, authored names/comments/types, attachments and file references. It retains explicit seed addresses but discards their inherited register assumptions for revalidation. Read-only queries do not silently rebuild old results: raw disassembly remains available with old native references hidden. `refresh-facts` is not this repair. ELF, PE and Mach-O projects are unaffected by the DOS state revision.

Linux ELF and macOS Mach-O now feed declared library slots and code stubs into the same call, xref and conditional memory-effect passes used for Windows imports. ELF metadata includes GOT relocations, version requirements and validated PLT aliases; Mach-O includes dyld/chained bindings, indirect-symbol stubs, dependencies and export kinds. These are static file identities: runtime providers and relocated target addresses remain unknown.

```bash
fdisbull import ./program linux.fdb
fdisbull auto-analyze linux.fdb
fdisbull libraries linux.fdb
fdisbull relocations linux.fdb --limit 50
fdisbull linkage linux.fdb
fdisbull calls linux.fdb --kind library
fdisbull call-effects linux.fdb --access write
fdisbull refresh-metadata existing.fdb
```

`refresh-metadata` upgrades retained ELF/Mach-O/PE metadata and rebuilds its symbol index without changing bytes, versions or user annotations. It makes dependent derived results stale; run `auto-analyze` again to refresh them. It requires retained original file bytes. `refresh-facts` remains the separate instruction-access/fallthrough backfill.

Choose a universal Mach-O slice explicitly. `x86` means 32-bit, `x86_64` means 64-bit, and `arm64` means ARM64:

```bash
fdisbull inspect ./UniversalBinary
fdisbull inspect ./UniversalBinary --slice-arch arm64
fdisbull import ./UniversalBinary mac-arm.fdb --slice-arch arm64
fdisbull auto-analyze mac-arm.fdb
fdisbull analyze-module ./universal.dylib selected-library.fdb --slice-arch x86_64
```

Unselected inspection inventories FAT slices; import requires a unique explicit match. Projects retain the full original container, selected-slice metadata and global file offsets. A slice selector does not select the host CPU or execute that architecture.

PE remains the default image for a file containing a PE header. A valid preceding DOS image can be selected into a separate project:

```bash
fdisbull inspect ./program.exe --image mz
fdisbull import ./program.exe windows.fdb --image pe
fdisbull import ./program.exe dos-stub.fdb --image mz --load-segment 0x1000
fdisbull analyze dos-stub.fdb
```

The DOS view must pass normal MZ declared-size, relocation and entry validation; an `MZ` prefix alone is insufficient. It uses the declared DOS module, without guessing a stub boundary from the PE offset. Neither view executes. See [PLATFORMS.md](docs/PLATFORMS.md) for selection, linkage evidence and ABI limits.

The `auto-analyze` pipeline adds bounded indirect-target recovery, shared function membership, frame/argument observations, qualified library effects, structural data types and dependency-driven reanalysis. Shared passes consume normalized instruction semantics rather than PE structures or CPU mnemonics. Current adapters cover x86 16/32/64 and ARM64; supported containers include DOS MZ, ELF, PE, thin/selected universal Mach-O and explicit raw images. This is an extensible analysis design, not a claim that every ISA is implemented.

```bash
fdisbull auto-analyze my-analysis.fdb --max-functions 200 --max-rounds 8
fdisbull advanced-status my-analysis.fdb
fdisbull function-analysis my-analysis.fdb 0xADDRESS
fdisbull function-membership my-analysis.fdb
fdisbull call-effects my-analysis.fdb --address 0xDATA --size 2 --access write
```

`auto-analyze` resumes persistent native and derived work. Its `stable` covers both queues; `analysis-status` retains the native queue's `stable` and separately exposes `advanced` and `overall_stable`. Each function result records generation, stale state, unknown transfers, assumptions and budgets. Re-run after a limit, or raise the relevant limit when a routine itself exceeds it. `function-analysis` is read-only and never presents a stale cache as current.

Indirect transfers require finite state or a dominating index bound, exact readable table entries and valid native target decoding. Unknown indices remain proposals. Function membership is many-to-many over instruction identities: shared tails, alternate entries and noncontiguous blocks do not become exclusive address ranges. Frames retain symbolic entry-SP offsets, candidate arguments and ABI alternatives. Use `--abi x86_64_sysv`, `--abi x86_64_win64` or another documented profile when evidence supports it; file-based defaults are assumptions.

Library memory effects require import/export identity, an exact full-body signature or an explicit `set-summary` contract. A rename is never sufficient. The small bundled signature catalog consists of authored test helpers, not a comprehensive compiler library database. `call-effects` reports bulk reads/writes and unresolved buffers; combine it with `memory-accesses` for instruction-level evidence. Import effects remain conditional on the declared binding being unchanged. Their `binding_evidence` distinguishes unchanged-under-static-state (`true`), a possible intervening write (`false`), and unavailable proof (`null`); even `true` is not runtime provider verification. DOS near-pointer effects retain unresolved segment identity instead of treating offsets as physical addresses. No imported function runs.

Define a structure in a JSON file, for example `record.json` containing `{"kind":"struct","size":4,"fields":[{"name":"quantity","offset":0,"type":"u16"},{"name":"flags","offset":2,"type":"u16"}]}`, then:

```bash
fdisbull define-type my-analysis.fdb Record record.json
fdisbull apply-type my-analysis.fdb 0xDATA Record --name record
fdisbull typed-data my-analysis.fdb 0xDATA
fdisbull set-summary my-analysis.fdb 0xCALLEE memcpy --abi x86_64_sysv
```

The last command explicitly asserts a contract; use it only when that function identity is supported by your evidence. Structure fields, arrays and pointers share physical address identity and labels. Type/summary changes queue dependent results and callers. Structural representation changes retract affected routine slices when the instruction dependency index is complete; older or incompletely indexed projects fall back to full analysis reset. Byte patches create isolated child versions, retaining user interpretations but revalidating byte-derived signature identities.

See [ADVANCED_ANALYSIS.md](docs/ADVANCED_ANALYSIS.md) for the IR, algorithms, ABI profiles and limitations. There is no new emulator, runtime watchpoint engine, C# dataflow adapter or decompiler in this release.

`cfg` follows exact stored instruction identities and control-flow edges from a chosen entry. `render-cfg` exports its basic blocks as SVG with selected sites highlighted. Straight-line and assumed call-return fallthroughs now persist in SQLite. Existing projects can explicitly backfill these and memory-access facts with `refresh-facts`.

```bash
fdisbull refresh-facts examples/dinopark.fdb
fdisbull memory-accesses examples/dinopark.fdb '4020:6f90' --size 2 --access write
fdisbull cfg examples/dinopark.fdb '38ff:2b66' --highlight '38ff:3168'
fdisbull render-cfg examples/dinopark.fdb '38ff:2b66' routine.svg \
  --highlight '38ff:2be6' --highlight '38ff:2fd6' --highlight '38ff:3168'
```

Memory queries classify reads, writes, read/modify/write, conditional writes and address-only operands, including implicit stack/string accesses and interval overlaps. Unknown effective addresses remain separate unresolved candidates. A concrete overlap establishes an address under stored assumptions; it does not establish runtime execution. The [DinoPark field audit](docs/DINOPARK_FIELD_AUDIT.md) records indexed staff-array writers, initialization and save loading without assigning a settled gameplay meaning to either field.

`analysis-status` reports the current persisted queue and seed states. New disassembly JSON and PNG/SVG exports include this state, so an earlier budget-limited receipt is distinguishable from a later fixed point. See [QUERYING.md](docs/QUERYING.md) for hexadecimal address queries and evidence limits.

`calls` groups stored function and library call targets with incoming call-site xrefs. Try `fdisbull calls examples/dinopark.fdb --limit 50` or `fdisbull calls examples/windows.fdb --kind library`. Shared renames resolve when queried. Unresolved indirect calls remain visible; DOS compiled-in library helpers retain their current function labels until independently identified.

A local, agent-first disassembler with a persistent SQLite database and GUI-free image export. iced-x86 decodes x86, Capstone decodes ARM64, and LIEF reads executable metadata. The project owns its analysis order, annotations and byte versions. Python coordinates the native libraries.

## Start

Requires **Python 3.12 or newer**. Python/CLI checks run on Linux; native macOS host execution has not been verified. Parsing Mach-O fixtures on Linux does not establish a macOS host run.

```bash
cd fdisbull
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
fdisbull info examples/demo.fdb
fdisbull analyze examples/demo.fdb
fdisbull functions examples/demo.fdb
```

Bundled examples include a compiled ELF with C source, a constructed Windows PE with imports/exports, and a synthetic captured-IAT snapshot with an export map. Saved projects and PNG/SVG exports are included. The tool can inspect an ELF file on another supported host without running that file.

`examples/dinopark.fdb` contains the prior native static fixed point for your original DOS executable: the original analysis plus an explicitly seeded save-loading wrapper across 31 CS contexts. Query it immediately with `fdisbull code-regions examples/dinopark.fdb` or `fdisbull disasm examples/dinopark.fdb --address '38ff:53fd'`. Its analysis receipt and PNG/SVG exports are included alongside it. The 0.6 package also retains two targeted derived function results; 650 other derived jobs remain pending. `function-analysis` and `advanced-status` expose that distinction.

Those DinoPark 0.6 receipts remain historical evidence and are unchanged by the 0.7 platform metadata work.

## Inspect a file, then build a project

```bash
fdisbull identify /path/to/program
fdisbull inspect /path/to/program
fdisbull import /path/to/program my-analysis.fdb
fdisbull header my-analysis.fdb
fdisbull sections my-analysis.fdb
fdisbull imports my-analysis.fdb
fdisbull exports my-analysis.fdb
fdisbull strings my-analysis.fdb --limit 100
fdisbull libraries my-analysis.fdb
fdisbull relocations my-analysis.fdb --limit 50
fdisbull linkage my-analysis.fdb
fdisbull analyze my-analysis.fdb --max-instructions 10000
fdisbull functions my-analysis.fdb
```

`identify` and `inspect` need no database. Identification uses header bytes rather than the filename. `inspect` adds sections, imports, exports, strings and available platform linkage metadata, with warnings where recovery is partial. Section records distinguish **file offset/size** from **virtual address/size**. PE imports identify preferred-VA IAT slots; exports retain ordinals and forwarder information.

Importing a new project stores the source bytes and parsed metadata automatically. Project information remains available after the original file disappears. `info` gives the summary; the individual information commands support version selection and list pagination.

Analysis starts with recursive traversal from the entry point, then investigates mapped data references and admits disconnected symbol/export seeds. Pointer values become candidates; corroborated indirect control-flow references can supply further code work. Facts and tasks are deduplicated. Repeat `analyze` after a budget stop until it reports `stable: true`. Stability means the implemented rules have no remaining queued work, not that every function or indirect target has been recovered. `queue`, `items` and `issues` expose the remaining evidence and uncertainty.

## Analyze the original DOS DinoPark executable

Classic DOS MZ loading now applies the executable's relocation table and retains real CS:IP contexts. This is static disassembly of the original bytes; it does not run the game.

The following uses the original file location in this workspace. After extracting the package elsewhere, replace `../dino-check/DINOPARK.EXE` with the path to your own original file:

```bash
fdisbull identify ../dino-check/DINOPARK.EXE
fdisbull import ../dino-check/DINOPARK.EXE dinopark.fdb --load-segment 0x1000
fdisbull header dinopark.fdb
fdisbull analyze dinopark.fdb --max-instructions 100000
fdisbull analyze dinopark.fdb --max-instructions 100000
fdisbull segments dinopark.fdb
fdisbull code-regions dinopark.fdb
fdisbull disasm dinopark.fdb --address '38ff:53fd' --lines 35
fdisbull xrefs dinopark.fdb '38ff:53fd'
fdisbull render dinopark.fdb loan-function.png --address '38ff:53fd' --lines 35
```

Repeat the bounded `analyze` command until its receipt reports `stable: true`; two calls above are an example, not a guarantee of completion. `stable` concerns the implemented static rules. Unknown indirect targets, jump tables and external overlays can still remain.

With the chosen load segment `0x1000`, the previously investigated `38ff:53fd` loan routine is addressable directly. Changing the load segment changes relocated selectors. To add a targeted seed and explicit register assumptions:

```bash
fdisbull analyze dinopark.fdb --start '38ff:53fd' --ds 0x4020 --max-instructions 10000
fdisbull disasm dinopark.fdb --address 0x3e3ed --cs 0x38ff --lines 35
```

Here `0x4020` is DinoPark's statically established startup data segment at that load address, not a universal DOS default. `--cs`, `--ds`, `--es` and `--ss` let the caller provide analysis assumptions. Unknown segment/register values remain unresolved. The MZ project `header` includes fixed DOS header fields, relocation count, load segment and initial CS:IP; `segments` lists inferred segment roles/bounds. `code-regions` reports only contiguous stored instruction runs within a CS context and does not declare whole candidate segments to be code.

DOS analysis follows the entry first, then admits relocation-backed far-call patterns, callback pointers in observed data segments and corroborated paired literal far-pointer stores as **candidates**. It does not treat every relocated word as code. Multiple CS:IP aliases may share a physical address; their instruction interpretations remain separate while a rename or explicit representation belongs to that shared physical location.

The loader excludes the MZ header and trailing overlay bytes from executable memory. It zero-fills only paragraph padding and the declared minimum allocation, not a guessed DOS heap. Initial PSP segment values are recorded, but PSP bytes are not fabricated. A20 wrapping, DOS allocation, runtime overlays and device behavior are not emulated.

Static propagation preserves DS/SS/BP/SP across call fallthrough by a conventional DOS C calling assumption, while general registers and ES become unknown. Deferred candidate seeds may inherit the startup DS or a unique observed data segment. Receipts and disassembly expose assumptions; these facts are not runtime execution observations. See [VERIFICATION.md](docs/VERIFICATION.md) for measured original-binary results.

## Name and interpret addresses once

Replace the example addresses below with addresses returned by your project:

```bash
fdisbull disasm my-analysis.fdb --address 0xADDRESS --lines 40
fdisbull rename my-analysis.fdb 0xADDRESS park_name --author TiGa
fdisbull comment my-analysis.fdb 0xADDRESS 'Evidence and interpretation' --author TiGa
fdisbull represent my-analysis.fdb 0xADDRESS qword --author TiGa
fdisbull xrefs my-analysis.fdb 0xADDRESS
fdisbull render my-analysis.fdb function.png --address 0xADDRESS --lines 40
```

Names and representations are shared by address and resolved when queried. Disassembly retains numeric `operands` and adds structured `references` and `display_operands`; image export uses the latter. Renaming a referenced address therefore updates its label in callers and exported views without editing every instruction.

`represent` accepts `code`, `byte`, `word`, `dword`, `qword`, `pointer`, `ascii`, `utf-16le` and `unexplored`. Strings require an explicit byte size, for example `represent my-analysis.fdb 0xADDRESS ascii --size 12`. Fixed-width numeric types require their matching width. Definitions must fit within one region and may not overlap another explicit definition. Changing a representation invalidates dependent analysis, using a full reset if the dependency index is incomplete, and runs native reanalysis within the supplied budget; `--defer` leaves reanalysis queued instead. The byte version and its digest stay unchanged.

## Locate instruction bytes and inspect function patterns

```bash
fdisbull locate examples/dinopark.fdb '38ff:53fd'
fdisbull locate examples/dinopark.fdb '38ff:5401'
fdisbull function-patterns examples/dinopark.fdb --limit 30
fdisbull function-patterns examples/dinopark.fdb --scan-unexplored --limit 30
```

`locate` identifies every stored instruction/data span containing the byte, including CS aliases and overlaps. Each span reports `begin`, `part`, `end` or `single`, its byte offset, shared representation and exact bytes. Here `end` is the final included byte; `end_exclusive` is the following address. A one-byte instruction is `single`. The query does not decode new bytes.

`function-patterns` reports native frame-setup/teardown evidence, returns and possible tail exits for supported x86/ARM64 code. A pattern remains a candidate: optimized functions may omit it, and the same sequence may appear inside a function or in data. The optional bounded unexplored-byte scan adds proposals with separate provenance; it neither queues analysis nor creates functions/instructions. Candidate DOS contexts remain explicit.

Hold a range for later interpretation, then release the same range as code:

```bash
fdisbull represent my-analysis.fdb 0xADDRESS unexplored --size 32 --defer
fdisbull locate my-analysis.fdb 0xADDRESS
fdisbull represent my-analysis.fdb 0xADDRESS code --size 32 --defer
fdisbull analyze my-analysis.fdb --start 0xADDRESS
```

An explicit `unexplored` range blocks automatic code/data investigation until its representation changes. A drained queue can therefore coexist with intentionally held bytes. Names and comments survive reanalysis; use `patch` only when changing the bytes themselves.

## Analyze a DLL or shared library on demand

```bash
fdisbull analyze-module library.dll library.fdb
fdisbull analyze-module library.dll selected-export.fdb --export ExportName
fdisbull analyze-module library.dll ordinal-export.fdb --export '#7'
fdisbull analyze-module library.dll selected-entry.fdb --entry 0x180001000
fdisbull analyze selected-export.fdb --max-instructions 10000
```

Each first command creates a new project from a local module snapshot. Without an explicit root it uses available entry/export seeds; an export name, `#ordinal` or preferred virtual entry address selects a narrower root. Repeat ordinary `analyze` to resume its budget. Forwarded exports require selecting their destination module explicitly. The operation does not load the DLL into a process, run its initializer, download dependencies or recursively load imported DLLs. `import --module` can also retain a library that has no executable entry.

## Inspect managed .NET assemblies and CIL

```bash
python -m pip install -e '.[managed]'
fdisbull managed assembly.dll
fdisbull managed assembly.dll --token 0x06000001 --max-instructions 1000
```

The optional extra pins **dnfile 0.18.0** and **dncil 1.0.2**. Start with the method list and select an actual MethodDef token from that assembly. The tool reports CLR metadata, names, signatures, RVAs/file offsets and method-body CIL, with token/call references and method-local branch targets. Tokens and `IL_` offsets have their own identity; they are not x86 addresses. Recognized CLR payloads are guarded from accidental native entry analysis, and invalid CLR metadata stays explicit.

This is metadata/CIL analysis. It does not reconstruct C# source, verify the IL type/stack rules, interpret exception-handler sections or execute .NET. NativeAOT/native-only files need native analysis; absence of a CLR directory does not establish NativeAOT origin. Mixed native/managed payloads retain their limits. Actual Godot ALD assembly qualification remains pending the matching assembly; a Godot native executable alone is not its C# game assembly.

## Compare alternative x86 decodings

```bash
fdisbull decoder-check 0f0dc0 --bits 64
fdisbull decoder-check 554889e5c3 --bits 64 --scan-offsets
```

This read-only comparison records iced/Capstone validity, lengths, text and backend versions for bounded proposed starts. It never executes bytes or promotes a proposal to stored code. Text differences can be aliases or formatting; agreement does not prove hardware semantics. [DECODER_RESEARCH.md](docs/DECODER_RESEARCH.md) connects this surface to Sandsifter/Battelle and the proposed SNO x86 adapter. [WINE_DEBUGGER.md](docs/WINE_DEBUGGER.md) describes a future isolated Wine execution backend; it is not delivered or macOS-qualified here. [CORPUS.md](docs/CORPUS.md) records the difficult-binary collection search and current fixture coverage.

Try the Windows example directly:

```bash
fdisbull info examples/windows.fdb
fdisbull imports examples/windows.fdb
fdisbull disasm examples/windows.fdb --address 0x140001000
fdisbull recover-imports examples/captured-iat.fdb examples/module-exports.json
```

These are deterministic fixtures, not observations from a live Windows process.

## Agent interface

No API key or built-in model is required. Use CLI commands or keep a local session:

```bash
fdisbull serve --project my-analysis.fdb
```

Send one JSON request per line:

```json
{"id":1,"method":"analyze","params":{"max_instructions":2000}}
{"id":2,"method":"queue","params":{"limit":100}}
{"id":3,"method":"rename","params":{"address":"0x401106","name":"transform","author":"TiGa"}}
{"id":4,"method":"render","params":{"address":"0x401106","lines":25,"output":"function.png"}}
```

Every response has `id`, `ok`, and `result` or `error`. `fdisbull methods` lists the operations. This is **JSON lines, not MCP or JSON-RPC**. It opens no listening socket. Commands use the caller's normal local filesystem access.

## Offline import recovery

`recover-imports` adapts CHimpREC's candidate-slot/export-resolution method to captured bytes. Supply a JSON list of module exports with addresses that match the pointer values in your snapshot:

```json
[
  {"address":"0x7ffb12341000","module":"KERNEL32.dll","name":"Sleep","ordinal":null},
  {"address":"0x7ffb12342000","module":"KERNEL32.dll","name":null,"ordinal":123}
]
```

```bash
fdisbull recover-imports my-analysis.fdb module-exports.json --max-slots 4096
fdisbull imports my-analysis.fdb
```

The JSON protocol also accepts `module_exports` directly and optional `candidate_slots`, the virtual addresses of pointer cells. Without candidates, the project runs recursive analysis and proposes slots from its decoded pointer-width memory operands. The standalone Python recovery helper also offers CHimpREC-style `FF 15/25` pattern discovery for captured images; the project command uses recursive code evidence. Matched exports anchor bounded range expansion. Aliases, ordinal-only exports, padding, unresolved cells and exhausted budgets remain explicit. Resolved labels appear in shared address views; the latest recovery receipt is returned by `imports`.

This is offline recovery, **not Windows process attachment, runtime DLL discovery or executable/import-table rebuilding**. An ordinary on-disk PE often holds unresolved import descriptors rather than runtime function pointers; its normal imports are parsed by `inspect` and do not need this recovery step. See the pinned source reference in [THIRD_PARTY.md](docs/THIRD_PARTY.md).

## Byte versions and existing projects

```bash
fdisbull patch my-analysis.fdb 0xADDRESS '90 90' --label experiment --origin 'manual patch'
fdisbull analyze my-analysis.fdb
fdisbull versions my-analysis.fdb
fdisbull disasm my-analysis.fdb --version 1 --address 0xADDRESS
```

A patch preserves the parent snapshot and creates fresh child analysis. Operations default to the newest version; use `--version` to select another. Names, comments and explicit representations inherit and require semantic revalidation after changes. Source-file and mapped-snapshot digests are distinct: mapped hashes include region descriptions and bytes.

Schema 1–4 databases migrate to schema 5 without discarding byte versions or annotations. A schema-1 project needs `analyze` to backfill structured references from retained bytes. Its original full-file metadata remains unavailable unless it was retained; reimport the original into a new project to obtain that information. Migration does not reconstruct missing source bytes. Existing byte analysis still works if the original is missing.

DOS patches apply to relocated memory bytes. For a stored child file version, all relocation fixups are undone in reverse order before rebuilding the file-backed module; the parent remains unchanged. Allocation-only/BSS edits stay in the child memory snapshot and have no disk counterpart. Patching does not execute or save a runnable DOS process.

## Supported scope

Loaders support classic DOS MZ, little-endian x86/x86-64 and ARM64 ELF/PE, and thin or explicitly selected universal little-endian x86/x86-64/ARM64 Mach-O. MZ applies its segment fixups at the chosen load segment. Other executable loaders use preferred static virtual addresses without applying runtime relocations or dyld slides. Use `analyze-module`/`import --module` for a library without an executable entry, and `managed` for CLR metadata/CIL.

```bash
fdisbull import segment.bin dos-segment.fdb --arch x86 --bits 16 --base 0x100
fdisbull import arm-code.bin arm.fdb --arch arm64 --base 0x1000
```

`--arch` always selects explicit flat raw mode. Use MZ image loading for DOS segmentation and relocation; raw x86/16 is only an extracted flat segment. NE/LE/LX native images remain unsupported; a valid preceding DOS image can be selected explicitly with `--image mz`. Universal Mach-O import uses `--slice-arch`; it never guesses from the host architecture.

ELF GOT and Mach-O dyld addresses identify slots, not resolved external code. Unknown slots stay null; on-disk lazy/chained pointer values are not used as runtime targets. ELF version requirements can establish a requested library, while unversioned names retain candidates. Unsupported dyld/chained cases stay explicit. Darwin ARM64 describes integer register arguments only; packed stack, variadic and authenticated-pointer behavior is not fully modeled. PE delay-load imports are not enumerated. String extraction is a bounded heuristic for printable ASCII and ASCII-range UTF-16LE, not full Unicode recovery. Function entries and inferred segment bounds are candidates. Proven function ownership, arbitrary indirect-transfer recovery, dynamic overlay recovery, decompilation, runtime SMC capture and a native UI remain future work. A decoded original-game function does not establish full-game execution or complete instruction coverage.

## Verify

```bash
python -m pytest -q
```

See [VERIFICATION.md](docs/VERIFICATION.md), [ARCHITECTURE.md](docs/ARCHITECTURE.md) and [API.md](docs/API.md). Close a project before copying only its `.fdb`; active SQLite WAL state may occupy adjacent sidecars.
