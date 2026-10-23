# Verification receipt — fDisBull 0.4.0

Final integrated source: Linux, CPython 3.12; iced-x86 1.21.0, Capstone distribution 5.0.9, LIEF 1.0.0, Pillow 12.3.0. Optional managed packages: dnfile 0.18.0 and dncil 1.0.2. No macOS runtime or guest-code execution is claimed.

`python -m pytest -q --tb=short` completed with **231 passed**, exit 0, **14.00 seconds**.

| Capability | Fresh evidence |
|---|---|
| Exact instruction/data byte spans | Beginning, interior, final byte and one-byte instruction positions; overlapping interpretations, CS aliases, range-aware shared names, unsigned address limits |
| Function boundary evidence | Native x86 16/32/64-bit and ARM64 frame patterns, returns, possible tail jumps; bounded read-only candidate scans; no automatic code promotion |
| Representation-only changes | Deferred reanalysis; held unexplored spans suppress overlapping instructions/data and truncated-pointer promotion; byte digests and parent snapshots remain unchanged |
| DLL/library analysis on demand | Selected exports/ordinals or explicit entries, persistent scoped roots, entryless DLLs and actual ELF shared objects; zero GOT pointers do not promote ELF headers into code |
| Consistent module capture | Export selection and project bytes use the same immutable captured image, including a source-change regression |
| Managed inspection and CIL | Real dnfile/dncil parsing of self-authored PE/CLI metadata, methods, tokens, strings, calls, branches, switches, tiny/fat headers, malformed and partial results |
| Native/managed separation | Pure-IL and invalid recognized CLR payloads are blocked from native analysis; retained assembly bytes remain available after source deletion |
| Decoder proposals | 15 focused cases, including actual iced/Capstone validity disagreement and formatting-only differences; alternatives are unconfirmed and never executed |
| Grouped function/library call index | Nine focused tests cover incoming xrefs, import/recovered aliases, DOS CS identities, shared labels, unknown targets, pagination and version isolation; final-wheel public calls passed |
| Current analysis state | Live budget status, admitted versus deferred seeds, unresolved issues with zero pending work, read-only status/disassembly consistency |
| SQL address ordering | Fixed-width hexadecimal sorting/ranges tested at ordinary and unsigned high-half addresses; decimal casts are not used |
| Existing functionality | Prior MZ, PE, ELF, Mach-O, CHimpREC, version/patch, protocol and render regressions passed |

Independent review added ten regressions for module capture, entry/null-pointer handling, held ranges, current queue state and unsigned address queries. All passed. DOS pointer and current-state PNG/SVG exports were produced from the database; the new PNG was visually inspected with readable CS:IP, operands, context and analysis-state header.

## Original DinoPark

A fresh database built with final 0.4 rules again reached a fixed point: **46,294 instructions, 648 function candidates, 15,628 xrefs, 31 CS contexts with decoded code and 415 instruction runs**. All **426 seeds were admitted**, with zero pending code/data/seeds/segment scans. A subsequent call attempted zero work and added zero facts. This run took 18.067 seconds; every round is retained in `examples/dinopark-v04-check.json`.

The delivered 0.3 ZIP was also opened independently and its stored database checked. It already contained the same admitted-seed/zero-pending fixed point. Earlier `stable: false` bounded receipts were historical rounds, not the final state. At `38ff:2b94`, stored bytes `c4 1e c7 bf` decode to raw operands `bx,[0BFC7h]`. The review check makes no runtime revenue or save/load claim. See `QUERYING.md` for pointer and writer-evidence limits.

The original 268,480-byte executable remains unchanged, SHA-256 `2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`. `examples/dinopark.fdb` retains the previously delivered, self-contained snapshot; the fresh 0.4 qualification database is separate. The earlier receipt is preserved as `VERIFICATION-0.3.md`.

## Drive corpus and managed scope

Nine actual native PE samples from the user's VM/Dropbox course collection passed identification, inspection and import. Each received one bounded 5,000-work analysis call. The fresh integrated check stored **15,341 instruction interpretations**: seven implemented queues drained; HideDebugger.dll and deroko-64-_.exe remain explicitly partial. No sample or DLL was executed or OS-loaded. See `CORPUS.md`, `corpus-analysis.json` and `corpus-final-check.json` for exact provenance, results and parser diagnostics. Those receipts identify their point in development; they do not prove protected code was unpacked.

Google blocked IMA Files.zip, 10nop.exe and HyperUnpackMe1/Notepad.exe downloads with `403 cannotDownloadAbusiveFile`. They were not tested. The original course binaries and scratch analysis databases are outside this archive.

The included managed sample and database are explicitly synthetic analysis fixtures, not the ALD game assembly. Actual ALD C# code was unavailable in the retrieved native corpus. CIL support does not reconstruct C# source, verify IL types, interpret exception clauses, debug the CLR or establish NativeAOT origin. Optional dependencies are required for metadata-table and method decoding.

## Research versus implementation

`WINE_DEBUGGER.md` is a sourced future implementation plan for an isolated Wine backend on Apple silicon, with Rosetta qualification and full-x86 QEMU fallback. No Wine debugger or Apple-container session was built or run. `DECODER_RESEARCH.md` correlates Battelle/Sandsifter, REcon's related work, STOKE and the current SNO design. The software decoder comparison is implemented; hardware probing and an x86 SNO semantic adapter are not.

Static stability never proves complete code coverage, live memory values or correct behavioral interpretation. Runtime/JIT/overlay capture, general jump-table recovery, decompilation and native macOS validation remain outside this tested release. The external original-file recognition test skips when its fixture is absent; compiler-based ELF checks require a C compiler.

The final installable `dist/fdisbull-0.4.0-py3-none-any.whl` matched every packaged Python source module. Imports ran directly from that wheel; current analysis status, grouped calls, byte location, retained managed CIL, decoder comparison and SVG rendering passed. The prior selected-export qualification also exercised the real HideDebugger.dll without loading it into an OS process. Wheel SHA-256: `9fe4ef13649e3f9f42f9185acdcc6f1823bcd8e3d96695d44bc30e1e8f1bdf85`.

The included `dinopark-calls.json` indexes 2,983 stored call sites across 555 target groups (534 function targets, 21 unresolved indirect sites). The existing function label at `1000:172f` has 20 incoming call sites. `windows-calls.json` demonstrates import-metadata library identity. DOS static-runtime helpers are not assigned invented library names.
