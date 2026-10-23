# fDisBull 0.3

A local, agent-first disassembler with a persistent SQLite database and GUI-free image export. iced-x86 decodes x86, Capstone decodes ARM64, and LIEF reads executable metadata. The project owns its analysis order, annotations and byte versions. Python coordinates the native libraries.

## Start

Requires **Python 3.12 or newer**. Linux execution is verified in the supplied receipt; macOS execution has not been independently run.

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

`examples/dinopark.fdb` contains the completed static analysis of your original DOS executable: 46,294 instructions across 31 CS contexts. Query it immediately with `fdisbull code-regions examples/dinopark.fdb` or `fdisbull disasm examples/dinopark.fdb --address '38ff:53fd'`. Its analysis receipt and PNG/SVG exports are included alongside it.

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
fdisbull analyze my-analysis.fdb --max-instructions 10000
fdisbull functions my-analysis.fdb
```

`identify` and `inspect` need no database. Identification uses header bytes rather than the filename. `inspect` adds sections, imports, exports and strings, with warnings where recovery is partial. Section records distinguish **file offset/size** from **virtual address/size**. PE imports identify preferred-VA IAT slots; exports retain ordinals and forwarder information.

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

`represent` accepts `code`, `byte`, `word`, `dword`, `qword`, `pointer`, `ascii` and `utf-16le`. Strings require an explicit byte size, for example `represent my-analysis.fdb 0xADDRESS ascii --size 12`. Fixed-width numeric types require their matching width. Definitions must fit within one region and may not overlap another explicit definition. Changing a representation resets derived analysis and runs it again within the supplied budget; the response reports whether more work remains. This is a data/code interpretation, not a byte patch.

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

Schema 1 and 2 databases migrate to schema 3 without discarding byte versions or annotations. A schema-1 project needs `analyze` to backfill structured references from retained bytes. Its original full-file metadata remains unavailable unless it was retained; reimport the original into a new project to obtain that information. Migration does not reconstruct missing source bytes. Existing byte analysis still works if the original is missing.

DOS patches apply to relocated memory bytes. For a stored child file version, all relocation fixups are undone in reverse order before rebuilding the file-backed module; the parent remains unchanged. Allocation-only/BSS edits stay in the child memory snapshot and have no disk counterpart. Patching does not execute or save a runnable DOS process.

## Supported scope

Loaders support classic DOS MZ, little-endian x86/x86-64 and ARM64 ELF/PE, and thin little-endian x86/x86-64/ARM64 Mach-O. MZ applies its segment fixups at the chosen load segment. Other executable loaders use preferred static virtual addresses without applying runtime relocations. A shared library without an executable entry requires `--entry`.

```bash
fdisbull import segment.bin dos-segment.fdb --arch x86 --bits 16 --base 0x100
fdisbull import arm-code.bin arm.fdb --arch arm64 --base 0x1000
```

`--arch` always selects explicit flat raw mode. Use automatic MZ import for DOS segmentation and relocation; raw x86/16 is only an extracted flat segment. NE/LE/LX secondary headers can be recognized but are not loaded as classic DOS MZ. Fat Mach-O slices must be selected before loading.

ELF/Mach-O import bindings are partial and use null addresses where unresolved; PE delay-load imports are not enumerated. String extraction is a bounded heuristic for printable ASCII and ASCII-range UTF-16LE, not full Unicode recovery. Function entries and inferred segment bounds are candidates. Complete function boundaries/CFGs, general jump-table analysis, dynamic overlay recovery, decompilation, runtime SMC capture and a native UI remain future work. A decoded original-game function does not establish full-game execution or complete instruction coverage.

## Verify

```bash
python -m pytest -q
```

See [VERIFICATION.md](docs/VERIFICATION.md), [ARCHITECTURE.md](docs/ARCHITECTURE.md) and [API.md](docs/API.md). Close a project before copying only its `.fdb`; active SQLite WAL state may occupy adjacent sidecars.
