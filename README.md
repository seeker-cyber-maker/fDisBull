# fDisBull 0.2

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

Opening a 0.1 database migrates its schema without discarding byte versions or annotations. Run `analyze` to backfill structured references from the retained bytes. Old projects did not retain full original file bytes, so newly added header/import/export/section metadata remains explicitly unavailable there; reimport the original into a new project to obtain it. Existing byte analysis still works if the original is missing.

## Supported scope

Loaders support little-endian x86/x86-64 and ARM64 ELF/PE, plus thin little-endian x86/x86-64/ARM64 Mach-O. They use preferred static virtual addresses; they do not apply runtime relocations. A shared library without an executable entry requires `--entry`.

```bash
fdisbull import segment.bin dos-segment.fdb --arch x86 --bits 16 --base 0x100
fdisbull import arm-code.bin arm.fdb --arch arm64 --base 0x1000
```

`--arch` always selects explicit raw mode. Raw x86/16 is a flat extracted code segment. Header identification/inspection recognizes DOS MZ, NE, LE and LX, but **segmented DOS executable loading is still missing**. Recognizing DinoPark's DOS header does not mean its whole executable can yet be analyzed correctly. Fat Mach-O slices must also be selected before loading.

ELF/Mach-O import bindings are partial and use null addresses where unresolved; PE delay-load imports are not enumerated. String extraction is a bounded heuristic for printable ASCII and ASCII-range UTF-16LE, not full Unicode recovery. Function entries are candidates. Complete function boundaries/CFGs, jump-table analysis, decompilation, runtime SMC capture and a native UI remain future work.

## Verify

```bash
python -m pytest -q
```

See [VERIFICATION.md](docs/VERIFICATION.md), [ARCHITECTURE.md](docs/ARCHITECTURE.md) and [API.md](docs/API.md). Close a project before copying only its `.fdb`; active SQLite WAL state may occupy adjacent sidecars.
