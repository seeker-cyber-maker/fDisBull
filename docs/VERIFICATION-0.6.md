# Verification receipt — fDisBull 0.6.0

Linux, CPython 3.12; iced-x86 1.21.0, Capstone distribution 5.0.9, LIEF 1.0.0 and Pillow 12.3.0. No imported native/managed code or macOS runtime was executed.

Final integrated `python -m pytest -q`: **482 passed**, exit 0, **35.23 seconds**. The suite includes existing loaders, DOS segmentation, metadata, memory effects, graph/render, managed inspection and immutable-version behavior, plus the six new shared analysis capabilities. Independent review supplied regressions for stale signature identities, unknown/overlapping writes, call ABI cleanup, held pointer tables, shared instruction dependencies, orphan call seeds, shrinking types and zero-address raw code.

## Shared algorithms across containers and CPUs

`examples/advanced-formats-v06.json` records fresh public `Project.create → auto_analyze → function_analysis → restart` runs on seven actual minimal native file fixtures: PE x86-64, ELF x86-64, Mach-O ARM64, DOS MZ x86-16, raw x86-64, raw x86-32 and raw ARM64. All use the same normalized `bounded_indirect` rule. Each first native pass decodes assignment and indirect jump; the target return is decoded only after generic recovery and native validation. Every case reaches a fixed point, repeats with zero jobs, and reopens successfully after deleting its input source. Source fingerprints remained unchanged during qualification.

Additional native-byte tests cover guarded absolute and signed relative jump tables, DOS near/far context constraints, stack/frame relations, register aliases, implicit memory effects, call arguments and qualified memcpy/memset effects on x86 and ARM64. Unknown/unbounded indices, stale bounds, tainted table reads and incomplete flow/CFG budgets are not admitted. This verifies current adapters, not every instruction or architecture. The shared solvers consume normalized expressions and effects; adding another CPU still requires a decoder/semantics adapter and ABI evidence.

## Original DinoPark qualification

The retained source executable is 268,480 bytes, SHA-256 `2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`. The base snapshot retains 47,177 instructions, 652 candidate functions, 57,285 xrefs and 32,729 instruction memory-access facts across 31 CS contexts. Its mapped-byte SHA-256 remains `8006cbd191e3ff0a80f537f6d5163559542270f3bf706b7f86d8c4c54248c743`. The prior native discovery queues are stable; this does not make the new whole-project derived analysis complete.

The membership query examines 52,717 stored flow/call edges and produces 10,008 blocks, 114 shared-tail candidates, eight overlapping entries and three tail-call candidates. It performs 47,809 entry/instruction work pairs without a budget stop. Global completeness remains false because 25 unresolved facts remain. The `38ff:2b66` candidate contains 606 instructions in three noncontiguous runs; membership follows edges rather than an address-range label.

Targeted derived jobs for `38ff:2b66` and `38ff:3a28` were run on a fresh copy, with 10,000-instruction, 100,000-step and 256-table-entry limits. The former converges in 14,502 steps, around 15 seconds; the latter uses 24 steps. Both finish their implemented passes without exhausting those limits. The first real-binary run exposed order-sensitive write histories causing repeated solver work; canonical histories and absorbing unknown-memory state corrected that defect, with an independent cyclic regression.

The actual guarded dispatch at `38ff:3a42` remains an unresolved proposal. Its index originates in a memory load and later arithmetic; the solver does not safely retain an opaque bound through that expression. The manually inspected table words are recorded separately and **no targets were admitted from that manual observation**. The frame report likewise retains unknown stack relations after calls with unspecified cleanup instead of inventing arguments or return values.

`examples/dinopark-membership-v06.json`, `dinopark-function-v06.json` and `dinopark-advanced-v06.json` retain the measurements, exact source fingerprints, assumptions and separate-process reopen proof. The selected jobs have generation 1, with **two done and 650 pending** across the advanced project. These were targeted coordinator passes over the retained stored graph, not a whole-project public `auto-analyze` completion. The first public `auto-analyze` also replaces old shallow indirect-target assumptions and requalifies dependent results. Field meanings, the frozen-clock experiment and the concession formula remain unresolved; no Swift gameplay implementation changed.

## Wheel, persistence and scope

`dist/fdisbull-0.6.0-py3-none-any.whl` SHA-256: `9824da07c41498384fce4b2edb4ed423dc67b4ca9e5439578d380f2a0a4d0f7c`. All 34 packaged Python modules exactly match source. Imported directly from the wheel in a separate working directory, all seven format cases, restart checks and CLI protocol smoke checks pass. `examples/wheel-v06-check.json` retains the result.

Schema 1–4 migrations preserve byte versions and annotations while adding schema 5 derived/type tables. Tests establish restartable partial jobs, shared name/type updates, selective invalidation with full-reset fallback, child patch isolation and retraction of stale automatic contracts. Existing SVG/PNG render tests remain green; the displayed graph and disassembly artifacts are retained from 0.5 and their visual qualification is recorded in `VERIFICATION-0.5.md`.

No new emulator, Wine/Apple-container debugger, runtime SMC capture, decompiler, CIL dataflow engine, universal signature database, physical CPU probe or SNO x86 verifier is delivered. macOS execution and actual Godot ALD assembly qualification remain open. A fixed point describes the implemented static rules, never complete binary coverage or observed game behavior.
