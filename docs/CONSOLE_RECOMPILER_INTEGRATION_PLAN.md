# Console recompilers: integration and modification plan

**Revision in progress. Research recommendations, reviewed 31 October 2026.**

This is a primary-source inventory and proposed implementation plan, not a new
console backend, a comparative performance result, or a universal-conversion
claim. No surveyed external recompiler was built or executed for this review.
Upstream success reports are attributed, not independently reproduced here.
See the [acceptance and benchmark plan](CONSOLE_RECOMPILER_ACCEPTANCE.md).

## 1. Decision and existing fDisBull work

Integrate reusable evidence and provider interfaces first, not an entire foreign
recompiler as the new authority. Prioritize the following work:

| Priority | Proposed action | Result required before promotion |
| --- | --- | --- |
| P0 | Adapt selected CPU vectors and authored device tests to the existing console verifier | Known-wrong translations fail; reference lineage and CPU variants are explicit |
| P1 | Add Project Nested as an optional NES-to-SNES comparator; investigate its profiling, mapping and runtime boundaries | Reproducible supported-pair runs with disclosed compatibility settings and dependencies |
| P1 | Wrap romdev experimentally, then repair or reject its unsupported semantics | No required operation silently disappears; conformance precedes production selection |
| P2 | Adapt N64Recomp/runtime separation and guarded-overlay methods into UDC orchestration and UDL bindings | One replaceable service and one bank/overlay transition preserve their contracts |
| P2 | Borrow first-divergence, fallback-accounting and comparison-self-test methods from desktop frameworks | A shared-core comparison is not misreported as independent hardware evidence |
| P3 | Keep large PS2/Xbox 360 runtimes and game-specific port code as references until a concrete target needs them | A scoped use case, component-license review and bounded acceptance justify each dependency |

These priorities select research work; they do not approve dependencies.

The baseline is not a blank console scaffold. [PR #56](https://github.com/seeker-cyber-maker/fDisBull/pull/56),
reviewed at `9e74d0d00cd51924f6754aa0cefaccd176947ed3`, records scalar NES/Genesis
UDC support, original-CPU checks, and a source-bound Miniplanets Stage 1-1 NES
specialization. Its [level report](https://github.com/seeker-cyber-maker/fDisBull/blob/9e74d0d00cd51924f6754aa0cefaccd176947ed3/docs/MINIPLANETS_NES_LEVEL.md)
reports 784 aligned original-Genesis/NES transitions on eleven selected fields.
Those are existing project receipts, not new runs by this review. Audio rendering,
later levels and original globe presentation remain outside that result. Its NES
table/scene extension is not supported by the Genesis backend, which refuses it;
shared scalar support does not imply that every richer profile is interchangeable.
The PR was open/draft at review; do not call it a released-main capability.

Extend that baseline. Keep [UDL/UIL/UDC roles](DEFINITIONS_AND_ROADMAP.md) intact:
UDL retains executable backings and source bindings; UIL expresses meaning using
logical identities; UDC selects realizations and orchestrates runtime services,
placement, adapters and fix-ups. Optional C or foreign IR views are not mandatory
intermediate steps, and a direct recompiler does not automatically recover intent.

## 2. Existing work and recommended disposition

The references are upstream primary documents. Status labels below are upstream
self-descriptions, not reliability scores. Multiple frontends, multiple platforms
and arbitrary whole-game conversion are different capabilities.

| Work | What it supplies / observed scope | Recommendation for fDisBull |
| --- | --- | --- |
| [Project Nested](https://github.com/Myself086/Project-Nested) | NES-on-SNES hybrid translation/runtime; compatibility is game-specific [S1] | **Optional comparator first.** Study AOT/JIT choices, mapper transitions and target budgets; do not replace UIL with its machine model |
| [romdev](https://github.com/monteslu/romdev) | Registry-driven lifters, IR, emitters and hardware adapters, including NES-to-SNES/Genesis [S2] | **Modify before trusting.** Import no permissive success behavior; use an experimental adapter and the repair gates below |
| [Castlevania SNES port](https://github.com/rumbleminze/castlevania-snes) | Game-specific assembly port, graphics conversion and audio adaptation; author reports physical-console tests [S3] | **Study, not wholesale vendor.** Extract general service requirements; keep game bytes, artwork and title-specific modifications separate |
| [N64Recomp](https://github.com/N64Recomp/N64Recomp) | Symbol/metadata-assisted literal MIPS-to-C translation, overlays and replacement configuration [S4] | **Adapt architecture; optional future frontend.** Generated functions can be candidate executable backings, not automatically meaningful UIL |
| [N64ModernRuntime](https://github.com/N64Recomp/N64ModernRuntime) | Separate runtime and bridge libraries; callbacks for host I/O, overlay and save services [S5] | **High-priority orchestration reference.** Reuse qualified components only when an N64 target needs them; avoid a mandatory runtime dependency |
| [NESRecomp](https://github.com/mstan/nesrecomp) | Beta NES/Famicom-to-host framework with CPU translation and console services; title integration remains necessary [S6] | **License-gated reference/comparator.** Study mapped execution and runtime seams; not a physical Genesis emitter |
| [SNESRecomp](https://github.com/RetroPortingToolKit/snesrecomp) | Beta SNES-to-host framework with runtime and interpreter fallback [S7] | **Adapt verification methods.** Evaluate co-simulation and fallback reporting before optional integration; not NES-to-SNES output |
| [PSXRecomp](https://github.com/RetroPortingToolKit/psxrecomp) | Beta PS1-to-host framework; overlay discovery, compilation and guarded cache selection [S8] | **Adapt overlay contracts.** Keep loaded-image identity, dependencies and ABI flavor in backing selection; code reuse is license-gated |
| [RetroRecomp](https://github.com/ArthurReboulSalze/RetroRecomp) | Multiple desktop-conversion profiles with explicit native/fallback and fidelity limits [S9] | **Evidence/reporting comparator.** Study its differential methodology and first-divergence handling, not its title counts as proof |
| [XenonRecomp](https://github.com/hedge-dev/XenonRecomp) | Xbox 360 PPC-to-C++; no complete runtime supplied; supports function replacement patterns [S10] | **Defer full integration.** Use replacement/ABI ideas when needed; unresolved MMIO and exceptions cannot become assumed services |
| [ReXGlue](https://github.com/rexglue/rexglue-sdk) | Early-development Xbox 360 AOT/runtime work rooted in Xenia [S11] | **Watch/reference.** Too large a dependency for the immediate NES/Genesis/SNES gap |
| [PS2Recomp](https://github.com/ran-j/PS2Recomp) | Experimental PS2 ELF-to-C++ with partial runtime behavior and explicit triage stubs [S12] | **Defer; learn refusal rules.** Temporary return handlers must never qualify semantic equivalence |
| [jamulator retrospective](https://andrewkelley.me/post/jamulator.html) | Author's historical account of NES static-translation problems, including indirect flow, mappers and scheduling [S13] | **Methodology reference only.** Convert failure categories into regression cases, not a production dependency |
| [SingleStepTests 65x02](https://github.com/SingleStepTests/65x02) and [680x0](https://github.com/SingleStepTests/680x0) | Single-instruction initial/final state vectors generated using reference implementations [S14] | **First integration candidate: vector readers.** Pin selected datasets and retain oracle lineage; add composition/device tests separately |
| [NES test-ROM collection](https://github.com/christopherpow/nes-test-roms) | Third-party CPU/device test programs [S15] | **Selective test integration.** Inspect each program's provenance, target assumptions and reuse terms; never assume one blanket license |

The earlier conversational survey called SNESRecomp alpha. The currently inspected
main README calls it **beta**. Use that corrected description without promoting
individual titles to full-game validation. No compatibility percentage or
performance ranking was independently established for any project here.

## 3. Concrete modifications to consider

### 3.1 romdev: strict candidate adapter and semantic repairs

The source review is pinned to
`3bc339e1c381adfb4e53b66138d9284dfcd53a28`. It concerns the physical-Genesis
hardware-port emitter, not every romdev runtime or WASM path. In that emitter,
push/pull operations generate comments, explicit flag operations generate NOPs,
and full source-flag behavior is not modeled. Its documented logic-only hardware
path drops device writes and synthesizes a ready status. The orchestrator can
supply empty-return stubs for missing callees. [S2]

Recommended work, as our adapter policy or a reviewed upstream contribution:

- Treat unsupported required instructions, unresolved callees, hardware operations
  and discarded effects as a failed qualified build. Keep an explicitly selected
  triage mode separate, marked incomplete. A residue report must affect eligibility.
- Model saved values, live flags and carry/borrow through the relevant region.
  A physical stack may disappear after a qualified transformation; its live values
  cannot. Call/return mechanics, callbacks and target scratch clobbers need checks.
- Audit source addressing modes, index extension, memory mirrors, indirect access,
  instruction destinations and MMIO adapter preservation. These are review targets,
  not newly executed bug reports.
- Put genuine device implementations behind explicit capabilities; synthetic
  ready values and dropped audio writes do not satisfy a playback contract.
- Preserve emitted-to-source mappings and the tested source/target pair. A generic
  registry must not imply that all lifters and emitters form a valid Cartesian product.

A minimal authored discriminator is:

```asm
lda #1
pha
lda #2
pla
sta $10
```

With a valid stack and no interrupt, the source stores 1. Applying the inspected
push/pull omission predicts 2. This remains a **source-review prediction** until
an actual emitter, assembler and target CPU replay confirm it. Do not advertise
it as an executed end-to-end defect. Test both immediate output and continuation
behavior after any repair. Retain attribution and submit only scoped fixes.

### 3.2 Project Nested: comparator, then candidate mechanisms

Do not start by copying its entire emulator. Establish an optional build/run
adapter for a supported NES input and SNES output. Record exact settings,
profiling input, AOT/JIT execution and supported cartridge behavior. Investigate
whether a noninteractive export seam exists; a proposed batch wrapper is not a
claim of an existing CLI. Its own compatibility guidance is a lead, not our gate.

The research deliverable is a qualified mechanism: for example, a bank-change
invalidation method, an interrupt-compatible boundary, or a bounded audio service.
Only then decide whether to adapt code or implement the contract independently.
SNES instruction compatibility does not remove all NES CPU/device differences.
Use an independently selected original-target reference, not Nested alone.

### 3.3 N64/PSX patterns: realization without mandatory rediscovery

N64Recomp separates literal function translation from its runtime; the runtime
uses callbacks for platform I/O and has an overlay bridge. PSXRecomp separates
extraction, compilation and guarded selection and does not require full
high-level decompilation before preparing executable overlays. [S4, S5, S8]

Adapt those boundaries to our source identity and implementation-selection
records. A source backing must identify the ROM/disc revision, physical bank or
loaded resource, instruction mode, byte revision and admitted entry context where
these matter. An address alone is not a stable implementation identity. A patched
or reloaded image invalidates dependent selections, not unrelated logical names.

Expose replaceable implementations under one contract. A low-level retained
runtime is a useful implementation, not a failed abstraction. Conversely,
translation to native C does not establish semantic recovery by itself. Keep
compatibility execution, recovered meaning and target-native realization as
separate measurements. A replacement must actually execute before receiving
replacement coverage; no hidden fallback to the original body.

### 3.4 Integration belongs behind interchangeable capabilities

Use optional providers for decoding, lifting, retained execution, lowering,
linking and device services. Each provider declares supported ISA/modes,
source/target pairs, state/effect profiles, resource limits, dependencies and
refusal behavior. Register per-capability choices, not one global "best tool".

A CPU-model view may contain registers and physical locations; UIL's recovered
operation uses logical labels and a declared contract. Do not force address-free
meaning by deleting unresolved machine behavior. Keep that behavior in executable
UDL support until a qualified abstraction is available. UDC owns placement,
calling conventions, buffers, continuations and service plumbing.

Operations such as `play_sound(sound_id)` may select different codecs or runtimes
without changing application UIL, once their meaningful completion/order/fidelity
contract is established. A device-register write is not automatically a complete
sound. Start with one input-to-state-to-visible-or-audible-effect interaction,
using the existing console pipeline rather than creating another shell framework.

## 4. Component and license boundaries

Record licenses for the exact files, runtime pieces, test data and emitted
support code selected. Do not infer permissions from a repository's popularity
or the presence of source. This table is an inventory of inspected notices, not
legal clearance for a particular distribution or commercial workflow.

| Component | Notice inspected / implication for this plan |
| --- | --- |
| Project Nested | MIT-style permission/notice text [L1]; preserve notices and review any selected dependencies |
| romdev original code | MIT, but LICENSE explicitly distinguishes third-party cores/toolchains and their terms [L2]; do not vendor the bundle under one label |
| NESRecomp, SNESRecomp, PSXRecomp | Each inspected LICENSE says PolyForm Noncommercial 1.0.0 [L3]; no default code integration or commercial-use approval is proposed |
| N64Recomp | Repository identifies MIT [S4]; assess the separate runtime and rendering components individually |
| Test-ROM collections and title-specific ports | Per-file/game/asset terms require review; no game content or third-party fixture is copied by this PR |
| Other listed projects | Code-adoption licensing remains unqualified here; explicit review precedes use or redistribution |

An optional process wrapper is an engineering isolation boundary, not a way to
remove a dependency's license obligations. For restricted components, obtain
appropriate permission or choose a suitable alternative before applicable use.
Public design documentation can inform our own proposal; copying implementations
still requires review. Retain origin even for permitted adaptations.

The recommended first patch adds readers/protocol adapters and authored controls,
not bundled games, BIOS dumps, external emulator binaries or vendor code. Keep
private retaining artifacts outside Git. Add opt-in acquisition only with explicit
inputs, pinned versions, documented rights and no automatic execution of a remote
build script. CPU vector generators are not independent hardware witnesses.

## 5. Follow-up work packages

| Work package | Scope | Completion evidence |
| --- | --- | --- |
| CRI-01: comparison interface | Extend existing #56 observation/input machinery with provider capabilities, trace identities and fallback accounting | Authored fixtures pass and a known-wrong implementation fails at the expected boundary |
| CRI-02: CPU conformance adapters | Read selected 65x02/680x0 vectors; add multi-instruction composition controls | Correct CPU variant, declared domain, explicit unsupported results and replayable counterexamples |
| CRI-03: romdev repair trial | Pin its relevant path; reproduce the proposed failure, repair or refuse it | Before/after emitted source and actual CPU observations; no broad correctness claim |
| CRI-04: NES-to-SNES comparator | Qualify a small supported input with Project Nested and our applicable route | Same behavior contract, counted setup/manual effort, disclosed runtime and physical-target limits |
| CRI-05: one device-bearing interaction | Recover input/state plus a sprite/tile or sound event; select two realizations | Ordered effects and lifecycle behavior agree within a stated fidelity profile |
| CRI-06: bank/overlay and patch reuse | Two source bodies share an address; then change or reload one | Correct source identity, stale-selection refusal and selective requalification |

These packages are prospective, not newly filed issues or assigned workers.
CRI-01/02 can proceed without waiting for every frontend; CRI-03/04 are independent
research lanes after shared observation criteria exist. Preserve one controller per
live guest. Defer PS2/Xbox 360 integration until a target makes its cost worthwhile.

## Sources and review limits

Primary sources were inspected on 31 October 2026. Moving-branch links below
identify the inspected documentation location, not a permanent execution pin.
Before a build comparison, resolve and record an immutable revision and component
hashes. The romdev source review and fDisBull baseline above are already pinned.

- **S1:** [Project Nested README](https://github.com/Myself086/Project-Nested/blob/master/README.md) and [release history](https://github.com/Myself086/Project-Nested/releases). Compatibility and real-target intent are upstream statements.
- **S2:** romdev at `3bc339e1c381adfb4e53b66138d9284dfcd53a28`: [orchestrator](https://github.com/monteslu/romdev/blob/3bc339e1c381adfb4e53b66138d9284dfcd53a28/packages/romdevtools/src/analysis/recompile/index.js), [lifter](https://github.com/monteslu/romdev/blob/3bc339e1c381adfb4e53b66138d9284dfcd53a28/packages/romdevtools/src/analysis/recompile/lift-6502.js), [Genesis emitter](https://github.com/monteslu/romdev/blob/3bc339e1c381adfb4e53b66138d9284dfcd53a28/packages/romdevtools/src/analysis/recompile/emit-m68k.js). Orchestrator/lifter were read in the preceding survey; the pinned emitter and head were rechecked for this increment.
- **S3:** [Castlevania SNES README](https://github.com/rumbleminze/castlevania-snes/blob/main/README.md), project structure and author-reported tests. No code/art/audio is imported.
- **S4:** [N64Recomp README](https://github.com/N64Recomp/N64Recomp/blob/main/README.md), literal translation, runtime and overlays; [repository/license](https://github.com/N64Recomp/N64Recomp).
- **S5:** [N64ModernRuntime README](https://github.com/N64Recomp/N64ModernRuntime/blob/main/README.md). Runtime source licensing is not resolved by N64Recomp's root notice.
- **S6:** [NESRecomp README](https://github.com/mstan/nesrecomp/blob/master/README.md), beta and game-specific integration.
- **S7:** [SNESRecomp README](https://github.com/RetroPortingToolKit/snesrecomp/blob/main/README.md), current beta/runtime boundary; the earlier survey's co-simulation leads require a pinned implementation review before adoption.
- **S8:** [PSXRecomp README](https://github.com/RetroPortingToolKit/psxrecomp/blob/master/README.md) and [overlay sharding](https://github.com/RetroPortingToolKit/psxrecomp/blob/master/docs/AOT_SHARDING.md).
- **S9:** [RetroRecomp compatibility/evidence](https://github.com/ArthurReboulSalze/RetroRecomp/blob/main/docs/COMPATIBILITY.md) and [NES profile](https://github.com/ArthurReboulSalze/RetroRecomp/blob/main/docs/NES.md). Its account includes a video error not caught by its internal CPU comparisons; that motivates distinct device checks, not a newly reproduced defect here.
- **S10:** [XenonRecomp README](https://github.com/hedge-dev/XenonRecomp/blob/main/README.md), runtime exclusion, replacements and unsupported behavior.
- **S11:** [ReXGlue README](https://github.com/rexglue/rexglue-sdk/blob/main/README.md), early status and Xenia lineage.
- **S12:** [PS2Recomp README](https://github.com/ran-j/PS2Recomp/blob/main/README.md), experimental scope and temporary handlers.
- **S13:** [jamulator author retrospective](https://andrewkelley.me/post/jamulator.html), 7 June 2013. Historical analysis, not a current compatibility claim.
- **S14:** [65x02 vector methodology](https://github.com/SingleStepTests/65x02/blob/main/README.md) and [680x0 vector methodology](https://github.com/SingleStepTests/680x0/blob/main/README.md).
- **S15:** [NES test-ROM collection](https://github.com/christopherpow/nes-test-roms). Individual test provenance/licensing still requires inspection.
- **L1:** [Nested license](https://github.com/Myself086/Project-Nested/blob/master/License.md).
- **L2:** [Pinned romdev license/bundle distinction](https://github.com/monteslu/romdev/blob/3bc339e1c381adfb4e53b66138d9284dfcd53a28/LICENSE).
- **L3:** [NESRecomp license](https://github.com/mstan/nesrecomp/blob/master/LICENSE), [SNESRecomp license](https://github.com/RetroPortingToolKit/snesrecomp/blob/main/LICENSE), [PSXRecomp license](https://github.com/RetroPortingToolKit/psxrecomp/blob/master/LICENSE).

No new game run, emulator benchmark, conversion, hardware test, upstream bug
submission or dependency installation is included. Proposed modifications and
acceptance cases remain separate from the source observations that motivate them.
