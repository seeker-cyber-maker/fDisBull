# fDisBull 0.1

A local, agent-first disassembler with a persistent SQLite project and GUI-free image export. iced-x86 decodes x86; Capstone decodes ARM64; LIEF loads executables. Our analysis decides which addresses to follow. Python drives the native libraries in this first build.

## Start on macOS or Linux

Requires Python **3.12 or newer**. Linux/Python 3.12 is verified in this package; macOS execution is not yet independently verified.

```bash
cd fdisbull
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
fdisbull status examples/demo.fdb
fdisbull render examples/demo.fdb my-disassembly.png --address 0x401106 --lines 20
```

The bundled demo is a real compiled ELF file, its C source, a saved project, and exported PNG/SVG. An ELF file can be analyzed on a Mac; it is never executed by this tool. The fixed address above belongs to this bundled build. For your own file, use the addresses returned by `functions`.

## Analyze your own executable

```bash
fdisbull import /path/to/program my-analysis.fdb
fdisbull analyze my-analysis.fdb
fdisbull functions my-analysis.fdb
fdisbull disasm my-analysis.fdb --address 0xADDRESS --lines 40
fdisbull rename my-analysis.fdb 0xADDRESS meaningful_name --author TiGa
fdisbull comment my-analysis.fdb 0xADDRESS 'Evidence and interpretation go here' --author TiGa
fdisbull xrefs my-analysis.fdb 0xADDRESS
fdisbull render my-analysis.fdb function.png --address 0xADDRESS --lines 40
```

Replace `0xADDRESS` with an actual address. Commands return JSON, including errors; one-shot errors exit nonzero. `analyze` defaults to a 10,000-work-item budget and reports remaining work. Repeat it to resume, or seed a chosen executable address with `--start 0xADDRESS`. Unreachable bytes are not silently swept into code.

Supported loaders: little-endian x86/x86-64 ELF and PE, ARM64 ELF/PE, and thin little-endian Mach-O for x86/x86-64/ARM64. Analysis uses preferred static virtual addresses; runtime relocation and imported-symbol resolution are not applied. Test coverage includes real ELF, constructed PE64/Mach-O ARM64, and raw decoding. Fat Mach-O and segmented DOS MZ loading are explicitly rejected. A shared library with no executable entry requires `--entry`.

Raw code requires explicit architecture; specifying `--arch` always selects raw mode:

```bash
fdisbull import segment.bin dos-segment.fdb --arch x86 --bits 16 --base 0x100
fdisbull import arm-code.bin arm.fdb --arch arm64 --base 0x1000
```

Raw 16-bit mode is a **flat code segment**, not a DOS executable loader. Far calls and segment-dependent references remain unresolved.

## Agent interface

No API key or built-in model is required. An agent can invoke CLI commands or keep a local stdin/stdout session:

```bash
fdisbull serve --project my-analysis.fdb
```

Send one JSON object per line:

```json
{"id":1,"method":"analyze","params":{"max_instructions":2000}}
{"id":2,"method":"functions","params":{"limit":100}}
{"id":3,"method":"rename","params":{"address":"0x401106","name":"transform","author":"TiGa"}}
{"id":4,"method":"render","params":{"address":"0x401106","lines":25,"output":"function.png"}}
```

Every response has `id`, `ok`, and `result` or `error`. `fdisbull methods` lists all methods. This is a small JSON-lines protocol, **not MCP or JSON-RPC**. It opens no listening socket. The caller's normal filesystem access applies.

## Byte versions

```bash
fdisbull patch my-analysis.fdb 0xADDRESS '90 90' --label experiment --origin 'manual patch'
fdisbull analyze my-analysis.fdb
fdisbull versions my-analysis.fdb
fdisbull disasm my-analysis.fdb --version 1 --address 0xADDRESS
```

A patch creates an immutable child snapshot and a new analysis queue. The parent bytes, disassembly, xrefs and notes remain available. Operations default to the newest version; select `--version` explicitly when working on another branch. Labels/comments inherit with provenance and require semantic revalidation after a patch. Source-file and mapped-snapshot SHA-256 values are separate: snapshot hashes include region mappings and bytes, not the full original file.

## What this build proves

- Real native decoding and direct branch/call/static-data xrefs.
- Bounded, resumable traversal that stops at returns, invalid bytes and unresolved indirect branches.
- Candidate function entries from entry/symbol/unwind evidence and direct calls.
- Restart-safe bytes, annotations and work, even if the original file disappears.
- Stored disassembly exported as readable PNG/SVG without a GUI.
- Multiple byte versions at the same address without overwriting history.

Function **boundaries**, basic-block ownership, complete CFG recovery, pointer/jump-table analysis, type inference, decompilation, dynamic SMC capture and a desktop UI are future work. Byte-version support is the foundation for SMC, not a claim that runtime modifications are already captured. No LLM interpretation is fabricated by the engine.

## Verify

```bash
python -m pytest -q
```

See [docs/VERIFICATION.md](docs/VERIFICATION.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/API.md](docs/API.md). Keep a project closed before copying its `.fdb` alone; active SQLite WAL state can live in adjacent sidecars.
