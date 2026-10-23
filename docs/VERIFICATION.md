# Verification receipt — fDisBull 0.3.0

Final source tested on Linux, CPython 3.12. Native packages: iced-x86 1.21.0, Capstone distribution 5.0.9, LIEF 1.0.0, Pillow 12.3.0. No macOS execution is claimed.

| Requirement | Fresh evidence | Result |
|---|---|---|
| Integrated suite | `python -m pytest -q --tb=short` | **160 passed**, exit 0, 11.34 s |
| MZ loader | Header/page validation, secondary-header ambiguity, relocations, duplicate fixups, minimum allocation, custom load segment | Passed |
| Segmented decoding | Near/far branches, CS:IP wrap, DS/ES/SS overrides, BP-relative addresses, bounded constants, unknown values | Passed |
| Stack state | SP/SS changes and possible stack writes invalidate saved constants; native call adjustments respect operand size | Passed |
| Recursive discovery | Entry traversal, relocation-backed far-call targets, relocated callbacks and paired literal initializations | Passed |
| Fixed-point dependencies | New indirect-call CS triggers budgeted callback rescans; one-item budget resumes correctly | Passed |
| Representation reset | Callback rediscovery, scalar/string values, selected entry CS persistence, stale code-role retraction | Passed |
| Shared identity | CS aliases retain separate instructions and share names/representations; reopen after source deletion | Passed |
| Patch isolation | Relocated words reverse to file form, duplicate/overlapping fixups, child-only memory and source changes | Passed |
| Stored views | Exact segmented addresses do not silently advance; PNG/SVG show CS:IP and context | Passed; DOS PNG visually inspected |
| Previous formats and recovery | ELF/PE/Mach-O, headers, imports/exports/strings, recursive data work, CHimpREC offline recovery, protocol/render protections | Passed in integrated suite |

An independent scoped review added and reran 16 regression cases for the DOS state and discovery boundaries. All passed after integration.

## Original DinoPark executable

The actual 268,480-byte `DINOPARK.EXE` was imported into a fresh project at load segment `0x1000`. Source SHA-256:

`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`

The loader applied **4,139 relocation records**. The header occupies 18,432 bytes; the module occupies 250,048 bytes. No trailing overlay was present in this file. Startup propagation established DS `0x4020`.

| Stored result | Count |
|---|---:|
| Instructions | 46,294 |
| Function candidates | 648 |
| Xrefs | 15,628 |
| Segment candidates | 33 |
| CS contexts containing decoded instructions | 31 |
| Contiguous decoded instruction runs | 415 |
| Unique relocation-backed far-call target seeds | 360 |
| Relocated data far-pointer seeds | 35 |
| Paired literal far-pointer initialization seeds | 31 |

Six bounded rounds (10,000 work items maximum per call; 53,255 attempts total) reached `stable: true`, with zero pending code, data, seeds or segment scans. Subsequent analysis attempted zero work and added zero facts. A separate process reopened the project and confirmed the same counts, both known stored instruction starts (`38ff:53fd`, `38ff:4827`), and the same idle fixed point. The original source digest remained unchanged.

`examples/dinopark.fdb` is the analyzed, self-contained project; it retains the imported file and relocated-memory snapshots inside the database. The raw executable is not supplied separately. `dinopark-analysis.json` records every round and the reopen check. The segment and code-region JSON inventories and the PNG/SVG disassembly at `38ff:53fd` are included beside it. No annotations were invented for this project.

## Limits

This is static analysis, not game execution or DOS emulation. Segment bounds and roles are inferred; a candidate selector does not classify every byte in its window as code. Function entries and callback targets remain candidates with evidence. Calls and deferred seeds carry the assumptions stated in analysis receipts. Unknown indirect targets, general jump-table recovery, runtime overlays, arbitrary self-modifying code, PSP/device behavior and A20 wrapping remain outside the supported model. Stability covers the implemented rules and queue, not proof that every possible function has been found.

Native Apple Silicon/macOS execution, live Windows attachment and import-table rebuilding remain unverified or unsupported. Existing PE/ELF/Mach-O limits and CHimpREC provenance are described in README.md and THIRD_PARTY.md.

The external original-file recognition test skips when its fixture is absent after extraction. Other tests are self-contained; the ELF compiler test also requires a C compiler. The included DinoPark project remains usable without that external fixture.

The installable `dist/fdisbull-0.3.0-py3-none-any.whl` was built from the final source. Every packaged Python module matched that source; imports ran directly from the wheel. Its info/analyze/segments/code-regions/disasm/render workflow passed against the saved DinoPark project. Wheel SHA-256: `4e6e7158c38bd6bab24a0f15629071b06bd86ff44826ae0211e8ba87ce861db0`.
