# Verification receipt — fDisBull 0.1.0

Final integrated source checked on Linux, CPython 3.12. Native packages: iced-x86 1.21.0, Capstone distribution 5.0.9, LIEF 1.0.0, Pillow 12.3.0.

| Acceptance criterion | Fresh evidence | Result |
|---|---|---|
| Integrated tests | `python3 -m pytest -q --tb=short` | 40 passed, exit 0, 2.75 s |
| Installable source | `python3 -m pip install --no-deps -e .` | Built and installed successfully |
| Distributable package | `python3 -m pip wheel --no-deps --no-build-isolation .` | Python wheel built successfully |
| Actual executable analysis | Compiled included `examples/transform.c` with GCC, imported resulting ELF without executing it | 84 instructions, 10 candidate functions, 22 xrefs, no pending work |
| GUI-free exports | Rendered same stored annotated listing as PNG and SVG | PNG visually inspected; SVG parsed by regression tests |
| Restart persistence | Separate CLI processes, rename, remove original input, reopen/query/export | Passed |
| Patch isolation | New byte version analyzed; original instruction and annotations queried independently | Passed |
| Unsigned addresses | Self-branch fixture above signed 64-bit range | Passed; traversal terminates |
| Format loading | Real ELF, constructed PE64 export table, constructed thin ARM64 Mach-O | Passed; PE RVA normalization covered |
| Raw decoding | x86 16/32/64, ARM64 branches, static references, invalid/indirect/far cases | Passed |
| Export database protection | Database, symlink, hardlink, WAL and SHM targets | Rejected; database remained usable |
| Agent error recovery | Invalid format, nonfinite number and deeply nested JSON followed by valid status | Structured errors; session continued |
| Built wheel smoke | Imported package directly from built wheel; opened saved 84-instruction project and rendered PNG | Passed |

The independent review also reran all 40 tests successfully and imported a copy of `/usr/bin/true`, analyzed 1,000 instructions, deleted that input copy, and reopened the project in a separate process.

Wheel SHA-256: `6cc7a091364fdf7765172c99304f7e80d63758d3d7ae647eade1ba0e9b0ba413`.

## Verification limits

No macOS/Apple Silicon runtime was available. A `py3-none-any` wheel describes this Python wrapper; its native dependencies still require compatible platform wheels. No physical-device, desktop-UI, DOS MZ, debugger or runtime SMC verification is claimed. Constructed PE/Mach-O fixtures validate loader mappings, not broad compatibility with every executable. Function entries are candidates; no complete function-boundary, CFG or decompilation claim is made.
