# Verification receipt — fDisBull 0.5.0

Linux, CPython 3.12; iced-x86 1.21.0, Capstone distribution 5.0.9, LIEF 1.0.0, Pillow 12.3.0. Optional managed dependencies remain dnfile 0.18.0 and dncil 1.0.2. No guest code or macOS runtime was executed.

Final integrated `python -m pytest -q`: **290 passed**, exit 0, **13.98 seconds**. Tests cover persisted straight-line/call-return continuations, schema-3 migration and explicit backfill, memory classification/width/overlap, DOS segment alternatives and unknown registers, implicit stack/string effects, REP bounds, native FS/GS, ARM64 access metadata corrections, read-only query/fallback parity, index reset/freshness, exact-entry CFGs, noncontiguous/loop/call/CS-wrap behavior, path evidence, immutable parent versions, shared names, SVG identity/escaping/bounds, and existing loaders/managed/import recovery/protocol/render features. Independent review added six regressions and found two index/implicit-access defects that were corrected before this final run.

## Original DinoPark snapshot

The delivered database was migrated from the previous 46,294-instruction snapshot. `refresh-facts` added **40,658 missing fallthrough sources**, preserving the exact byte version. A forensic audit then supplied three explicit roots with DS=0x4020 assumptions: `38ff:2048` (save-load wrapper), `38ff:16fc` (save wrapper, calling serializer `38ff:0ffe`), and `38ff:3cc1` (corroborated switch block). They added 91, 769 and 23 instructions respectively. This is explicit candidate admission, not newly implemented general jump-table recovery.

Final database: **47,177 instructions**, **652 function candidates**, **57,285 xrefs**, **32,729 memory-access facts**. The implemented queues are stable with zero pending work; all 426 prior seeds remain admitted. SQLite integrity checks passed after closing and reopening the final portable snapshot. A repeated analysis attempted zero work. Source bytes and mapped byte-version identity remain unchanged; original executable SHA-256 is `2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.

The reachable candidate slice from `38ff:2b66` contains **606 instructions, 91 basic blocks, 635 exact flow edges, 28 separate calls**, two RETF exits (`31c1`, `31cd`) and no missing stored successors under assumed call returns. All eight selected sites, including `3168` and `3170`, are reachable. Final graph edges are persisted, not reconstructed. `31ce` is not reached from this entry. This proves static topology under the stated assumptions, not branch feasibility, execution, semantic function ownership or a revenue formula.

`examples/dinopark-cfg.json` includes shortest instruction paths and exact edge evidence. `dinopark-cfg.svg` renders 606 instructions in 91 blocks, 120 interblock edges and eight highlighted sites. SVG XML and instruction counts passed; selected header, condition/loop and booking areas were rasterized and visually checked. Text is selectable and blocks do not overlap. Long outer-gutter edge segments can coincide; endpoint labels, tooltips and links retain exact identities. Rendering needs no Graphviz, Inkscape or browser at runtime.

The writer audit found two exact reads of DS:6F90 and six of DS:6FAC after the explicit roots. Zero fully resolved scalar writes in the stored state does **not** mean zero writers: indexed staff-array read/modify/write sites, initialization and save-load buffers need their recorded conditions. The save-file six-byte prefix supports offsets 3878→6FAC and 3888→6F90. See `DINOPARK_FIELD_AUDIT.md` for evidence, conditional writer sites and limits. Field meaning remains unresolved. The reported frozen-clock experiment was not run here; no Swift concession formula was introduced.

## Wheel and retained scope

`dist/fdisbull-0.5.0-py3-none-any.whl` was imported directly as a ZIP; every packaged Python module exactly matched source. Its public analysis-status, six-read field query, exact CFG, highlighted SVG export and CLI parsing passed. SHA-256: `5558b98ba22ce717d82e191d3e69f915c8d5f62c0f8eb73ec81866540035507f`. `examples/wheel-v05-check.json` retains the check.

The 0.4 receipt is preserved as `VERIFICATION-0.4.md`; earlier corpus, managed, CHimpREC and research scope remain applicable. No new Wine/Apple-container runtime, decompiler, physical CPU probing, SNO x86 semantic verifier or ALD assembly qualification was added. Static stability continues to describe only the implemented rule set, not complete code coverage or observed gameplay behavior.
