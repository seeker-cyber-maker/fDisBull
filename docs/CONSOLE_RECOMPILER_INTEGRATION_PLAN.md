# Console recompilers: first-party synthesis and reference plan

**Revision in progress. Research recommendations, reviewed 31 October 2026.**

This is a primary-source inventory and proposed implementation plan, not a new
console backend, a comparative performance result, or a universal-conversion
claim. No surveyed external recompiler was built or executed for this review.
Upstream success reports are attributed, not independently reproduced here.
See the [acceptance and benchmark plan](CONSOLE_RECOMPILER_ACCEPTANCE.md).

**Revised direction:** implement the useful mechanisms ourselves inside one
first-party fDisBull console module. External projects supply research leads,
attributed mechanisms and optional comparison runs, not a collection of mandatory
runtime dependencies. Do not copy their implementation code, translate it
statement-for-statement, or make upstream forks a prerequisite. The earlier
wrapper-first recommendation is superseded by the specification-first route below.
This revision adds a design decision, not that implementation.

## 1. Decision and existing fDisBull work

Recover what a useful mechanism accomplishes and the conditions under which it
works; express that as our own contract, then write and qualify a new implementation.
One public module should contain interchangeable internal capabilities, not one
opaque monolith or one bundled external engine per feature.

| Priority | Proposed action | Result required before promotion |
| --- | --- | --- |
| P0 | Define shared state/effect observations and author small conformance cases | Known-wrong translations fail; CPU variants and reference lineage stay explicit |
| P1 | Implement correct source transitions and target lowering in our existing console pipeline | Saved values, live flags, addressing and calls satisfy the admitted contract |
| P1 | Implement native mapping/overlay selection and invalidation from recovered requirements | Same-address different-code cases select correctly; stale bindings never become success |
| P2 | Implement scheduling and one replaceable device service | Combined timing, state and service obligations hold; not just each isolated component |
| P2 | Use selected external builds as optional differential comparators | Setup and rights are explicit; their absence does not block our authored qualification route |
| P3 | Extend target-specific realizations only when a new use case warrants them | Declared capability, resource and behavior gates pass; no assumed all-console cross product |

These priorities favor native reimplementation. Previously suggested vector
readers and external wrappers remain optional research utilities, not shipping
requirements or proof that a mechanism works.

### 1.1 Recover mechanisms, then synthesize a first-party implementation

Apply the project's recovery method to the recompilers themselves:

```
Published methods + permitted observations + source-assisted findings
    -> independently stated behavior and assumptions
    -> authored model and discriminating tests
    -> common capability contracts and dependency reconciliation
    -> newly written fDisBull implementations
    -> original/reference/target checks
```

A useful mechanism record names its purpose, inputs and state, ordered effects,
outputs, preconditions, failure behavior, timing/resource assumptions, supporting
observations and counterexamples. It is a development record, not a new required
UIL serialization. Record which parts are reported, inspected or actually run.
Read source to resolve missing meaning where appropriate, but do not treat its
names, organization or comments as an implementation template. Changing language
or variable names is not the intended method.

Combine records by behavior rather than upstream project. Two tools' equivalent
bank selectors should become one contract with alternative eligible strategies;
retain distinct variants when their interrupt, timing or memory assumptions
conflict. Matching interfaces alone do not establish composability. Agree on
units, event order, memory visibility, callback/reentry, restore generations,
errors and resource limits before joining implementations.

The first-party module would provide source recovery/bindings, semantic
normalization, target lowering, mapping/continuation management, device-service
orchestration and the comparison interface. Reuse the project's existing
UDL/UIL/UDC identities and console machinery rather than create a parallel
framework. CPU-specific source details remain in executable UDL; target placement
and scheduling remain UDC choices. A bank change may disappear from a qualified
flat-memory output while its source binding remains necessary for validation.
This scope does not require rewriting the project's already approved assemblers,
compilers or reference emulators; it does not claim zero third-party dependencies.

For example, the required meaning of a saved-value sequence is that its later
consumer sees the saved value. Our backend may use a temporary instead of the
source stack. For a loaded-code selector, the required meaning is that the chosen
implementation matches the active bytes and context; our data structure need not
match any surveyed implementation. QEMU's documented state-qualified translation
blocks and invalidation are another primary example of that distinction [S16].
These are design examples, not new executable results.

Use external projects as fallible references. Reproduce selected successful cases
before describing them as working mechanisms; design tests that distinguish the
mechanism from a convenient shortcut or stub. A disagreement with a third-party
tool is not automatically our defect. Check the original CPU/device specification
or qualified original execution and preserve an unresolved disagreement honestly.
Our model and its generated tests also share lineage; hold out additional inputs
and include a separately derived source/reference check.

A fresh implementer can receive the contract and authored cases rather than the
upstream implementation. A separate validator checks source fidelity and target
behavior. This reduces mechanical copying and overfitting but is not an automatic
clean-room or legal guarantee. This research has already inspected source, so
its provenance must say so. No arbitrary rule requires every new mechanism to
have an executable third-party comparison before it can be independently qualified.

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
| [Project Nested](https://github.com/Myself086/Project-Nested) | NES-on-SNES hybrid translation/runtime; compatibility is game-specific [S1] | **Recover mechanisms for our module.** Study AOT/JIT choices, mapper transitions and budgets; optional comparator only, no required emulator import |
| [romdev](https://github.com/monteslu/romdev) | Registry-driven lifters, IR, emitters and hardware adapters, including NES-to-SNES/Genesis [S2] | **Architecture and adversarial reference.** Write our own lifters/emitters; reject the observed omissions instead of inheriting or forking this backend |
| [Castlevania SNES port](https://github.com/rumbleminze/castlevania-snes) | Game-specific assembly port, graphics conversion and audio adaptation; author reports physical-console tests [S3] | **Study, not wholesale vendor.** Extract general service requirements; keep game bytes, artwork and title-specific modifications separate |
| [N64Recomp](https://github.com/N64Recomp/N64Recomp) | Symbol/metadata-assisted literal MIPS-to-C translation, overlays and replacement configuration [S4] | **Specify and reimplement needed mechanisms.** Separate translation, replacement and runtime duties; no required generated-C or imported-frontend path |
| [N64ModernRuntime](https://github.com/N64Recomp/N64ModernRuntime) | Separate runtime and bridge libraries; callbacks for host I/O, overlay and save services [S5] | **High-priority behavior reference.** Implement needed service/orchestration contracts ourselves; no mandatory N64 runtime dependency |
| [NESRecomp](https://github.com/mstan/nesrecomp) | Beta NES/Famicom-to-host framework with CPU translation and console services; title integration remains necessary [S6] | **Behavior/reference comparator.** Study mapped execution and services; any optional execution remains subject to its own terms |
| [SNESRecomp](https://github.com/RetroPortingToolKit/snesrecomp) | Beta SNES-to-host framework with runtime and interpreter fallback [S7] | **Reimplement verification methods.** Specify comparison self-tests and fallback reporting; not NES-to-SNES output |
| [PSXRecomp](https://github.com/RetroPortingToolKit/psxrecomp) | Beta PS1-to-host framework; overlay discovery, compilation and guarded cache selection [S8] | **Reimplement guarded selection.** Keep loaded-image identity, dependencies and ABI assumptions; no source-code import |
| [RetroRecomp](https://github.com/ArthurReboulSalze/RetroRecomp) | Multiple desktop-conversion profiles with explicit native/fallback and fidelity limits [S9] | **Evidence/reporting comparator.** Study its differential methodology and first-divergence handling, not its title counts as proof |
| [XenonRecomp](https://github.com/hedge-dev/XenonRecomp) | Xbox 360 PPC-to-C++; no complete runtime supplied; supports function replacement patterns [S10] | **Defer full integration.** Use replacement/ABI ideas when needed; unresolved MMIO and exceptions cannot become assumed services |
| [ReXGlue](https://github.com/rexglue/rexglue-sdk) | Early-development Xbox 360 AOT/runtime work rooted in Xenia [S11] | **Watch/reference.** Too large a dependency for the immediate NES/Genesis/SNES gap |
| [PS2Recomp](https://github.com/ran-j/PS2Recomp) | Experimental PS2 ELF-to-C++ with partial runtime behavior and explicit triage stubs [S12] | **Defer; learn refusal rules.** Temporary return handlers must never qualify semantic equivalence |
| [jamulator retrospective](https://andrewkelley.me/post/jamulator.html) | Author's historical account of NES static-translation problems, including indirect flow, mappers and scheduling [S13] | **Methodology reference only.** Convert failure categories into regression cases, not a production dependency |
| [SingleStepTests 65x02](https://github.com/SingleStepTests/65x02) and [680x0](https://github.com/SingleStepTests/680x0) | Single-instruction initial/final state vectors generated using reference implementations [S14] | **Optional test evidence.** Author our conformance first; separately reviewed vector readers must retain CPU variant and oracle lineage |
| [NES test-ROM collection](https://github.com/christopherpow/nes-test-roms) | Third-party CPU/device test programs [S15] | **Optional comparison corpus.** Author device requirements/tests; separately review any external fixture before use |

The earlier conversational survey called SNESRecomp alpha. The currently inspected
main README calls it **beta**. Use that corrected description without promoting
individual titles to full-game validation. No compatibility percentage or
performance ranking was independently established for any project here.

## 3. Concrete first-party capabilities to implement

### 3.1 romdev findings: requirements for our own lowering

The source review is pinned to
`3bc339e1c381adfb4e53b66138d9284dfcd53a28`. It concerns the physical-Genesis
hardware-port emitter, not every romdev runtime or WASM path. In that emitter,
push/pull operations generate comments, explicit flag operations generate NOPs,
and full source-flag behavior is not modeled. Its documented logic-only hardware
path drops device writes and synthesizes a ready status. The orchestrator can
supply empty-return stubs for missing callees. [S2]

Requirements for newly written native implementations, not instructions to copy
or fork this emitter:

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
behavior in our implementation. An optional scoped upstream report is separate
work, not a prerequisite for our module.

### 3.2 Project Nested: investigate and independently realize mechanisms

Use its design and supported examples to formulate our own mapping, compilation
and scheduling requirements. An authorized external run may help discriminate
hypotheses; it is optional, not the production path. Record exact settings,
profiling input, AOT/JIT execution and cartridge behavior if such a comparison is
performed. Do not assume an existing noninteractive CLI or treat its own
compatibility guidance as our acceptance gate.

The research deliverable is a qualified mechanism: for example, a bank-change
invalidation method, an interrupt-compatible boundary, or a bounded audio service.
Implement the selected contract in our native module, with target-specific
strategies where required. SNES instruction compatibility does not remove all
NES CPU/device differences.
Use an independently selected original-target reference, not Nested alone.

### 3.3 N64/PSX patterns: realization without mandatory rediscovery

N64Recomp separates literal function translation from its runtime; the runtime
uses callbacks for platform I/O and has an overlay bridge. PSXRecomp separates
extraction, compilation and guarded selection and does not require full
high-level decompilation before preparing executable overlays. [S4, S5, S8]

Specify those boundaries in our source identity and implementation-selection
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

### 3.4 One native module with interchangeable internal capabilities

Implement coherent native capabilities for decoding, lifting, retained execution,
lowering, linking and device services. Optional external providers can still aid
research, but normal operation must not require the surveyed recompilers. Each
implementation declares supported ISA/modes,
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

## 4. Original implementation and reference-use boundaries

The default deliverable is newly authored implementation and tests, not selected
upstream code. Do not paste, transliterate or route another implementation through
UIL as a way to relabel the same expression. Preserve research attribution and
separate facts/functional requirements from copied source, documentation, tables,
fixtures, assets or generated support code. A source-assisted development record
is not automatically a clean-room record.

WIPO distinguishes ideas and methods from their protected expression, and notes
that software-related inventions can raise separate patent questions [L4]. This
plan makes no legal-clearance claim for a specific implementation or distribution.
Do not infer either automatic license inheritance from learning an idea or
automatic freedom from obligations merely because output code looks different.

For optional external runs or any separately authorized reuse, record licenses
for the exact files, runtime pieces, test data and emitted support code selected. Do not infer permissions from a repository's
popularity
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

The recommended first patch adds first-party semantic mechanisms and authored
controls using existing project interfaces, not obligatory external wrappers,
bundled games, BIOS dumps, external emulator binaries or vendor code. Keep
private retaining artifacts outside Git. Add opt-in acquisition only with explicit
inputs, pinned versions, documented rights and no automatic execution of a remote
build script. CPU vector generators are not independent hardware witnesses.

## 5. Follow-up work packages

| Work package | Scope | Completion evidence |
| --- | --- | --- |
| CRI-01: comparison interface | Extend existing #56 observation/input machinery with provider capabilities, trace identities and fallback accounting | Authored fixtures pass and a known-wrong implementation fails at the expected boundary |
| CRI-02: original semantic core and conformance | Author transitions/lowering and composition controls; optionally read reviewed external vectors | Correct CPU variant, declared domain, explicit unsupported results and replayable counterexamples |
| CRI-03: first-party lowering trial | Use the romdev findings to specify saved-state/flag/address requirements, then implement independently | Source/our-UIL/target comparisons reject omissions; optional external reproduction is reported separately |
| CRI-04: NES-to-SNES realization | Recover a useful mechanism from Nested/documentation; implement our own supported route with optional external comparison | Same behavior contract, counted discovery/implementation effort, disclosed runtime and physical-target limits |
| CRI-05: one device-bearing interaction | Recover input/state plus a sprite/tile or sound event; select two realizations | Ordered effects and lifecycle behavior agree within a stated fidelity profile |
| CRI-06: bank/overlay and patch reuse | Two source bodies share an address; then change or reload one | Correct source identity, stale-selection refusal and selective requalification |

These packages are prospective, not newly filed issues or assigned workers.
CRI-01/02 can proceed without waiting for any surveyed tool; CRI-03/04 are
independent research lanes after shared observation criteria exist. The first
slice should be one known supported stateful operation with saved values and
live carry, followed by a bank-switch case and one device effect. Hold its UIL
fixed across two supported realizations. Do not reimplement every console first.
Preserve one controller per
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
- **L3:** [NESRecomp license](https://github.com/mstan/nesrecomp/blob/master/LICENSE), [SNESRecomp license](https://github.com/RetroPortingToolKit/snesrecomp/blob/master/LICENSE), [PSXRecomp license](https://github.com/RetroPortingToolKit/psxrecomp/blob/master/LICENSE).

No new game run, emulator benchmark, conversion, hardware test, upstream bug
submission or dependency installation is included. Proposed modifications and
acceptance cases remain separate from the source observations that motivate them.

### Additional references for this revision

- **S16:** [QEMU translator internals](https://www.qemu.org/docs/master/devel/tcg.html), state-qualified blocks, execution boundaries and invalidation. A design precedent, not newly integrated code or a console benchmark.
- **L4:** WIPO [copyright scope](https://www.wipo.int/en/web/copyright/protection) and [computer software](https://www.wipo.int/en/web/copyright/activities/software). General background only; not a determination about this project.
