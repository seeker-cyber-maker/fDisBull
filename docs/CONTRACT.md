# fDisBull 0.1 implementation contract

Local, agent-first disassembly project. No network service, LLM subscription, or graphical desktop required. The first release uses Python bindings to native iced-x86, Capstone and LIEF, SQLite, and Pillow. The decoder owns instruction decoding; our analysis owns work order and persisted interpretation.

Acceptance: import an actual executable, follow direct control flow, retain functions/xrefs and annotations after process restart, export database-backed SVG/PNG, and retain both byte versions after an explicit patch. Never execute imported code. No claims of decompilation, dynamic SMC capture, or complete function recovery.

## Shared module interfaces

`model.py` defines:
- `Region(name: str, start: int, data: bytes, executable: bool, writable: bool = False)`
- `Seed(address: int, name: str, source: str)`
- `Image(format: str, arch: str, bits: int, entry: int, regions: list[Region], seeds: list[Seed], metadata: dict)`

`loader.py`: `load_image(path: str | Path, *, arch: str | None = None, bits: int | None = None, base: int = 0, entry: int | None = None) -> Image`. `arch` canonical `x86` or `arm64`. Explicit raw mode if arch is provided. Raw x86 accepts 16/32/64; arm64 64. LIEF for ELF/PE/thin Mach-O; MZ loader if feasible. Reject unsupported modes clearly. Enforce bounded file/image sizes; no execution.

`decoder.py`: `decode(data: bytes, address: int, arch: str, bits: int) -> dict | None`, keys `address` (int), `size`, `bytes` (hex string), `mnemonic`, `operands`, `text`, `flow` (`next`, `call`, `jump`, `conditional`, `return`, `stop`, `indirect_call`, `indirect_jump`), `target` (int or None), `data_refs` (list[int]). No invalid instructions accepted.

`render.py`: `render_snapshot(snapshot: dict, output: str | Path, format: str | None = None) -> dict`. Snapshot keys `title`, `arch`, `bits`, `version`, `sha256`, `instructions` list. Rows contain `address` (0x hex str), `bytes` (hex str), `mnemonic`, `operands`, `name` (str or None), `comment` (str or None), `xrefs` (list of dict). Return output path, format, width, height. PNG and SVG supported, no desktop/browser. Escape untrusted binary names/comments in SVG.

## Ownership
Coordinator owns model, db, analysis, CLI, packaging, tests and shared contracts. Loader agent owns loader.py and decoder.py only. Renderer agent owns render.py only. Review agent read-only. No shared-file writes.
