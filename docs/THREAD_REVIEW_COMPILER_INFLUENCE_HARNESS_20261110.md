# Thread synthesis: compiler, blast radius, replay, and agent QA (2026-11-10)

Source: user design discussion and a fresh 0.34.1 Linux offline-kit test against an owner-supplied Castles II installer. This note does not include original commercial game bytes or imply full-game reconstruction.

## Architecture and separable deliverables

1. QEMU/TCG is the candidate original CPU execution and lifting engine, while LLVM is the candidate optimizer and native-code generator. The existing UDL/UIL/UDC contracts must remain engine-agnostic. Coordinate with open QEMU migration MR !117.
2. A byte-accurate instruction lift is a prerequisite but not a semantic UIL block. Identify blocks using control and data dependencies, observable effects, state deltas and causal original-engine experiments. Begin with AGI because its bytecode semantics are comparatively explicit. Avoid duplicating the existing AGI partial decoder/native pilot.
3. The blast-radius graph is separate from the contract. An individual register/flag-bit contract records live-in/live-out and observers; versioned sparse dependency paths explain those requirements and construct a proposed proof projection. Absence of a dynamic-taint edge is NOT a proof that a value is irrelevant.
4. A rewind/taint loop should find first divergent boundaries and counterexamples before spending solver time; general equivalence still needs an exhaustive complete domain or a formal proof. Explicitly model exceptions, devices, interrupts, unvisited branches, aliases, event timing and the actual visible/committed game state.
5. Optimize output independently from analysis complexity. Compile small blocks inline or as direct calls, dispatch audio/graphics to existing asynchronous APIs, and add new threads only after a measured speed/latency win and a sound scheduling contract.

## Independent MRs

- !121: bounded, real LLVM scalar compiler PoC (Clang-native, 512 executed input states compared with reference evaluator; two focused tests). Not a TCG lift or DOS game recompilation.
- !122: bit-level/atomic state influence graph and per-step masks for fully authored linear examples (five focused tests; no complete CFG and no formal proof).
- !123 (this MR): opt-in friction report, categorical routing, human scope decision, separate QA receipt (four focused tests; QA independence is a requirement, not an independently completed evaluation).

## Test on supplied Castles II 1.0 GOG installer

- Installer SHA-256: d09debb49922e7e5ac83a5c9dc160053cc10599560d9525317a3925dbbadfe56.
- Native GOG Inno 5.6.2 list and full extraction worked: 259 files; external innoextract unnecessary.
- Original C2CDTOOL.EXE SHA-256 512efad4a4d771f6c975702cad9a688aeef10f8d81798b8c7260e37c74e87d43, DOS MZ x86/16, 287152 bytes, 2053 relocations, 105680-byte overlay, entry 1000:0000.
- Bounded static import/analysis worked but ran out of configured budget after 40 jobs. Not full recovered code.
- Doctor smoke passed on authored DOS target.
- Reused already-present Castles II Xvfb/XTest original DOSBox-X harness with the private copied BAT set to startagain, and the original CD image mounted. Actual menu, in-game map, 11733-byte save, in-session load and fresh-process load passed (15.087 s); save hash unchanged. No guest graceful exit claim.
- No native LLVM replacement of this game has been executed or proven.

## Friction captured

1. AGENTS.md instructs preflight and --version-json, but installed 0.34.1 rejects those commands with exit 2; capabilities/doctor and --version work. First diagnose documentation/registration drift instead of inventing a new preflight feature.
2. ANIM.BOB is unrecognized by file-identify, and this offline media-inspect adapter list has no Castles II BOB adapter. Confirm alternate decoder before requesting approval for a new reusable media module.
3. QEMU executable is absent from this sandbox and not included in the supplied offline kit; QEMU/TCG parity was not tested.
4. The test task was carried through to the original-game Save/Load result rather than being closed after an installer parse or CLI-only test.

## Human-in-the-loop protocol

When the tool capability is truly missing and would expand scope, offer exactly these choices: go_with_it (scoped development branch), do_your_best (existing capabilities/limited local shim), stop_here (park branch with evidence). Never ask again for previously granted implementation details, nor infer permission to merge, trigger CI, release, distribute proprietary assets or weaken verifiers. QA testers should record reproductions and first failed boundaries, not flattering reviews or hostility scores. Salty tester notes remain optional text, separate from objective evidence.

## Next acceptance

Closed IL-v2 CFG to LLVM; TCG-lifting sample vs actual x86 guest state; per-flag decoder including CMP/INC/JC and PUSHF plus unknown interrupts; AGI held-out cross-game semantic slices; Castles II initial serializer block recovered from an actual save/load trace; cold A/B investigation performance vs fresh tool/skill baseline. Keep full suite, exact-source artifact qualification and independent QA as future gates. No hosted pipelines run by this MR.
