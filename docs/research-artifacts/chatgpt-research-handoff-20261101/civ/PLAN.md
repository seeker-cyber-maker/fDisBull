# Civilization recovery replication and method benchmark

**Status: proposed study plus completed input-intake checks. Revision in progress.**

Date: 30 October 2026. Project: fDisBull / executable UDL, UIL and UDC.

## Decision

Use the supplied DOS 474.01 media for the first controlled benchmark. Use Civ64's
published process as a methodology reference, not as a claim that its Win16
implementation is the same game build. Use sjmelia/civd's exact 474.01 branch as a
reproducible source-assisted comparator. Keep independent discovery, note-assisted
recovery, and results-derived definition import separate experimental conditions.

The first deliverable should be **one code-backed, semantically editable operation
that runs against the original and a generated implementation**, not another
unqualified whole-game rewrite. Retain executable UDL backings throughout.

## 1. Completed intake, not a reconstructed game

The uploaded ZIP is `Sid-Meier-s-Civilization_DOS_EN_Floppy-Disks-Images-Version-47401.zip`:

- 3,702,050 bytes; SHA-256 `0a7ed4a46f02e1f28dc22e16b679328f3db460a417e7d1a673af90e98f8f503d`.
- ZIP CRC validation passed. Four 737,280-byte raw IMA images and four TD0 members.
- Bounded FAT12 traversal of the IMA images found 205 regular-file entries and
  175 unique relative names. All repeated names have identical contents.
- The FAT copies inside each raw image agree. TD0 members were only hashed, not
  decoded or proven equivalent to their corresponding IMA images.
- No installer, game, historical compiler or third-party implementation was run.

The following hashes independently computed from the uploaded raw images match
`sjmelia/civd`'s `release/474.01` manifest at
`c425f7ba45411111c7c71d926e1ce8d4fa641571`:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| CIV.EXE | 304,512 | 21861cbb5eca78ddf22d7b84219b41a22a1d283c3f7b27f3d1bce98c30eb8e3b |
| MGRAPHIC.EXE | 7,142 | bf8907e955ed52d4a629945756010cedd0b00174e06d370b87e0edd6e92471c6 |
| ASOUND.CVL | 37,923 | 8a9b5b097bf7e5d3cf3202c065c58d7a3e2bf1bcf6a1adfebc021e407bec86f9 |
| MISC.EXE | 980 | 95b18daf25bc51fdd1c989a1d992f3e46ed17a5b73952856f783f8f31766e7fc |

This establishes correspondence to the published reference identities, not an
independent reconstruction of the source or proof of historical provenance.
The parsed CIV.EXE MZ header describes 178,111 bytes, leaving 126,401 trailing
bytes. Preserve the tail; do not call those bytes unused or claim whole-program
analysis from an entry-point pass. Their interpretation needs loader analysis.

### Independently checked startup exception

The upstream branch keeps raw LINK output as CIVRAW.EXE and changes one far-call
destination to form CIV.EXE. Reading the uploaded CIV.EXE, reversing precisely
that four-byte destination in memory, and hashing the result yields the exact
published CIVRAW.EXE reference:

`b04fc0ba243d446047708b04142024391877c52dd21f13bdfee2020ec4579466`.

Its computed CRC32 is `18631131`, while the supplied final image is `45f95f3b`.
Those also match the guards in CRTEDIT.C. Four positions changed; the original
archive and disk contents were not modified. This confirms the relation between
the two referenced images. It is NOT a compiler rebuild, execution test, or
explanation of why the historical game bypassed environment initialization.

## 2. Two projects, two kinds of result

### A. Buyukcaglar/Civ64: native port of the Windows 3.1 game

Pinned source-document revision: `4e46572d727544722d90c24dc2ce51a9c6d22f15`.
Its required original is an 832,512-byte Win16 NE executable, not the uploaded
DOS executable. Its DOS graphics option uses another separately qualified DOS
release, 475.05. Changing the graphics does not turn its rules into DOS 474.01.

The author explicitly credits Claude for recovery, code, testing and documents.
This is not evidence for Codex-specific authorship. The process is documented
substantially, but the original recovered C, port sources and generators are
explicitly excluded from the inspected public copy. Executable releases and
research records are not equivalent to a publicly reproducible source build.

### B. sjmelia/civd: matching DOS source reconstruction

Pinned 474.01 revision: `c425f7ba45411111c7c71d926e1ce8d4fa641571`.
Inspected main revision: `d9214fcd36aa6003d28aae60c3974b665f752280` (474.05).
The project publishes reconstructed C/assembly, build rules, tool identities and
reference hashes. It credits OpenAI, Anthropic and Google models plus earlier
OpenCiv1 work. It is assisted reconstruction, not independent-from-prior-work RE.

Its outputs include the complete game executable and selected drivers/utilities.
Matching bytes do not establish that inferred source names/types are historically
original, nor that another modern compiler will preserve every relevant behavior.
The separate reciv project is a modern-port lead; it was not built or audited in
this study.

## 3. Method reconstruction

### Civ64's documented workflow

1. **Inventory before porting.** A custom NE reader, Win16 API database and
   Capstone-based recursive decoder account for segments, functions, jump
   tables, globals and imported services. The report says 1,065 functions and
   99.93% of code bytes decoded as instructions/tables; these are author metrics,
   not independently reproduced coverage or a universal equivalence proof.
2. **Bounded annotation work.** The author reports 101 units of roughly 4 KiB,
   splitting the largest routines. Functions, parameters, locals and globals
   acquire descriptions and candidate structures. Naming votes prioritize
   reconciliation; a voted name is not semantic evidence.
3. **Global reconciliation.** Reconcile shared city/unit/civilization/map layouts,
   calling conventions and runtime entries before downstream code diverges.
4. **Readable C recovery.** Translate with explicit 16-bit semantics, syntax-check
   against a shim, and retain pseudo-intrinsics for unresolved runtime behavior.
   The documentation explicitly says this recovered C is not a buildable game.
5. **Independent review.** Separate agents review units against the listing;
   maintain a recovery-errata ledger. The listing takes priority over plausible
   recovered C. Independence of authorship is useful but not independence of
   models, source assumptions or tools.
6. **Generate the executable port.** Inventories feed generators in a defined
   order: inventory, layout, frames, dispatch, interfaces. Replace the relevant
   Borland runtime, implement the required Win16 services, translate the game
   functions, then connect a native host backend.
7. **Preserve difficult semantics first.** Native translated C still accesses
   modeled 16-bit selectors, original offsets and an emulated stack. This is not
   CPU-instruction emulation, but it is substantial source-memory compatibility.
8. **Stage testing.** Establish headless startup, world creation, load/save,
   behavior coverage and then visible application behavior. Keep checked/release
   builds, sanitizers, scenario tests, state/frame comparisons and selected
   original-process observations distinct.
9. **Add presentation under a noninterference rule.** Zoom and graphics changes
   must not add random draws or alter game state. Keep a fidelity ledger for
   chosen or unknown behavior rather than treating all visual similarity as proof.

A useful concrete lesson is the recovery-errata entry concerning a three-word
array plus a neighboring field that the original clears as four words. Giving
those locations separate clean labels too early can erase actual alias/effect
behavior. Another recurring lesson is evaluation order and temporary values
held across calls. These are better conformance cases than merely comparing the
final result of a happy-path calculation.

**Author-disclosed limits:** no synchronized turn-by-turn original comparison;
no original same-seed equality claim; no original-written Hall of Fame/preference/
replay comparison; unmeasured sound output; DOS graphics/timing derived from
listing models rather than executed DOS observations. The report says 108
features were reached, which is not the same as every behavior being validated
against the original. Our replication must keep those denominators separate.

### civd's documented workflow

The author says he explicitly directed the models to use OpenCiv1, let them
construct tools as needed, and iterated toward a trivially checkable byte-level
target once the compiler/toolchain was known. The public repository exposes the
final workflow, not a complete replay of every prompt and recovery decision.

1. Pin Microsoft C 5.1, MASM 5.10, LINK 5.01 and MAKE 4.07, plus options and link
   order. Validate installed tools.
2. Recover compiler-shaped C and retain assembly for code that does not fit the
   selected historical compiler output, rather than forcing all code into C.
3. Preserve memory-model declarations, segment ordering and some counterintuitive
   source forms. The notes say identifier spelling and compiler memory availability
   affect emitted code; selected modules use `loadfix -192`.
4. Use incremental builds during development; use a clean build for acceptance.
   Reject compiler diagnostics even if the historical build leaves an output.
5. Preserve raw linker output. Apply the narrow, guarded four-byte startup
   correction as a named reconstruction exception, not a masked comparison.
6. Verify raw/final output and selected drivers/utilities separately.
7. Explain systems in the book/source commentary; separately explore modern ports.

**What we should copy:** executable counterexamples, explicit evidence hierarchy,
source-to-block traceability, reconciliation, staged integration and preserving
raw output. **What we should not copy as dogma:** file-size-based task boundaries,
confidence voting as truth, fixed review counts, whole-game upfront work before
one useful operation, or source-shaped storage as the permanent UIL format.

## 4. First reproduce the reference, then benchmark discovery

An unscored curator lane should reproduce the upstream 474.01 build before any
team uses its inferred semantics as ground truth. It runs the pinned environment,
retains tool and input identities, executes the existing clean verification, and
compares the rebuilt final files directly with the uploaded originals. Raw LINK
and startup-corrected identities are separate gates. Obtain the historical
compiler through an available authorized source; do not assume it is in the
fDisBull offline kit.

Example upstream commands after preparing the pinned checkout:

```
just setup /path/to/available-compiler-images
just verify
```

These are upstream commands reviewed in the repository, NOT commands executed
in this study. Do not run setup in an existing valuable working directory:
its recipe recreates its private tool installation. Use a disposable workspace.

Original native execution remains the behavior reference for recovered code.
The reconstructed code is a second comparator, not a replacement truth source.
An original-byte match can establish artifact preservation while leaving the
semantic interpretation of names/blocks untested.

## 5. The requested three arms

This plan calls the requested "UDP module" a **results-derived definition
module**, without assuming UDP is an adopted project acronym. Its integration
uses executable UDL bindings, UIL contracts and selectable UDC implementations.
A CPU/VM processor module is a narrower decoding component, not this whole module.

| Arm | Allowed target-specific information | Work being measured |
| --- | --- | --- |
| A: independent recovery | Original 474.01 files, common runtime/tools and task description; no external target notes/source/maps | Discover meaning, bind executable source, express UIL and validate output |
| B: notes-assisted | Same as A plus a frozen, curated notes packet | Turn prior findings into supported bindings; measure search savings and correction cost |
| C-source: results-derived module | Same original plus final reconstructed source and required interfaces/build recipe; no narrative analysis notes | Reuse implementation as a backing, recover/declare its contract and import it into the pipeline |

For C-source, identifiers, types and annotations embedded in the implementation
are already prior information. This is intentional reuse, not a blind arm.
Remove separable prose commentary from the packet but do not break the code or
pretend its meaningful names contain no hints. Record packet preparation cost.

Civ64's inspected public copy cannot currently supply C-source with its private
recovered implementation. A **C-binary** arm using only a released executable and
public runtime interface would be a different experiment, with different costs
and capability boundaries. A running EXE is not automatically a callable backing
for arbitrary internal operations. Do not merge its timing with C-source.
The uploaded DOS edition and civd source allow a practical C-source study now,
subject to establishing build availability and applicable reuse permissions.

### Prevent the arms from collapsing into the same experiment

- Freeze a per-arm allowlist of input files/URLs and record access. Embedded code
  or pseudocode in a note counts as implementation assistance, not pure prose.
- Keep the evaluator, original reference captures and expected answers separate
  from the workers. Test interfaces and operation requirements are shared; hidden
  answer tables and reconstructed solutions are not.
- Use fresh isolated contexts/workspaces for each run. This conversation has
  already read notes and belongs to the curator/design lane, not a blind worker.
- Split by semantic regions/dependency clusters, not randomly adjacent functions
  that share an already explained helper. Shared public primitives are held fixed.
- Fresh contexts cannot establish pretraining exclusion. Use the accurate term
  "no supplied target notes" and add private authored mutations as a separate
  generalization test. Do not call a modified target an original release.
- Do not run A then B then C in one long-lived agent and call the difference a
  knowledge-treatment effect. No cross-arm memory, output caches or annotations.

## 6. Common deliverable and acceptance gates

All arms produce the same bounded deliverable:

1. Source revision/resource identity, entry and exit cuts, and dependency closure.
2. An executable UDL binding with actual backing/adapter identities, live state,
   declared effects and unresolved behavior.
3. A label-based UIL contract/body with explicit arithmetic, state relationships
   and event order. Addresses remain in source/realization bindings.
4. At least one selectable UDC realization through the existing scaffold. Portable
   realization must execute its claimed replacement, not secretly call the old code.
5. A counterexample-capable comparison report, source map, residual coverage and
   a compact next-question record.

Checks are the same across arms: entry-domain witnesses; boundaries and alternate
branches; relevant aliasing; ordered writes and external events; RNG state and
number/order of draws; failures and partial effects; repeated actions; and state
not permitted to change. Include native caller state when it is part of the cut.
Do not require every machine register if the declared contract legitimately
excludes it. Do not compare noisy/undefined fields through arbitrary masks chosen
after observing a mismatch.

Exact-byte reconstruction is an additional score for the original-backed target.
A portable UDC is judged by behavior, not whether it reproduces old register
allocation. Simply retaining original bytes earns preservation coverage, not
recovered intent coverage. An edited UIL operand must affect generated behavior
or be rejected for lack of a matching backing.

## 7. Recommended sequence

### P0: establish inputs and comparator (partly completed)

Completed: image intake, relevant artifact identities, four reference hash matches
and the in-memory startup exception relation. Pending: actual clean source build,
original game boot, original harness/checkpoint capture and downstream tool profile.
Keep fDisBull revision/toolchain/backend pinned; a newer branch is a separate trial.

### P1: three small, complementary slices

A curator selects version-matched actual source cuts for:

- A deterministic table/numeric rule such as one terrain-yield calculation.
- A stateful operation involving RNG or persistent state, with its call count/order.
- One branch-heavy interaction with a visible result and a refusal/repeat path.

These are workload categories, not assertions that their boundaries are already
recovered in this pass. Keep required source assets and state manageable. Avoid
whole-world generation or AI orchestration as the first measurement.

Run each slice in A/B/C-source once as an instrumented pilot: nine tasks. This
finds packet/acceptance defects; it does not support a statistical winner. After
freezing the protocol, use at least three fresh runs per slice/arm, budget
permitting, and report uncertainty and failures. Compare outcomes by slice rather
than pretending correlated queries are independent samples.

### P2: one bounded original-to-generated interaction

Compose the accepted slices into a useful read/calculate/act/report sequence.
Keep the existing shell work fixed. First preserve any necessary source-memory
relationships through explicit adapters. Then test an alternative state layout
without changing UIL, as a separate transformation and cost measurement.

### P3: patch and transfer

Use an actual available patch and its declared transformation when possible. The
source's VERSIONS comparison is a set of researched leads, not the original patch.
Acquire/version-match later inputs before claiming a 474.01-to-474.03/05 binary
comparison. Useful separate cases include a near-to-far visibility-buffer move
(binding/layout) and a changed game predicate (behavior).

Evaluate incremental invalidation versus fresh recovery. Reuse unchanged bodies;
recheck dependent behavior even where caller bytes are unchanged. Count unchanged
qualified coverage, newly examined bytes/blocks, solver/native work and regressions.
A modern target must not inherit a new behavior merely because the generated C
looks familiar.

### P4: only then vary providers and worker allocation

Hold knowledge treatment fixed while comparing current tooling against one
external provider and a selective combined route. Do not simultaneously change
provider, model, notes access and agent count. Separately compare fixed work-unit
parallelism with dependency-based workers; count total compute, publication lag,
waiting and duplicate analysis. One controller owns each live mutable guest.

### P5: wider systems and full-game claims

Expand to a full turn only after state/RNG/service contracts work. Use identical
initial snapshots and recorded inputs; supply/replay external time and random
inputs at declared boundaries or restore complete generator state where possible.
An equal seed alone is insufficient across distinct RNG implementations. Compare
well-defined quiescent checkpoints and ordered effects, not only final treasury.
Original and generated saves are useful independent checks but do not cover all
runtime state. Preserve intended original quirks or explicitly label rule changes.

## 8. Cost model and reporting

Pre-register budgets for wall time, aggregate tokens, tool calls and native time.
Stop criteria are uniform; stopped/unsupported tasks remain in the denominator.
Report first-accepted-operation time and total accepted-scope time separately.

```
measured_cost = preparation + discovery/import + model/adapter work
              + validation + corrections + orchestration/integration
```

Separate cold setup from warm reuse. Source-assisted import cannot hide its
module-construction cost; blind recovery cannot quietly consume a warmed project.
Count all parallel workers' cost and human steering. Keep machine build/export
milliseconds separate from interpretation time. Report accepted contract coverage,
residual coverage, false acceptances, rejected candidates, later regressions,
and cost to the first held-out task after a definition is learned.

Report both marginal operational savings and the fact that upstream assistance
encodes prior human/agent work. Do not estimate upstream labor from line count.
The three arms need not have equal starting knowledge; their purpose is to
measure the value of those different starting conditions under equal outputs.

## 9. Counterexamples worth making mandatory

- C expression reloads a value after a write instead of preserving its first read.
- Equal-looking state cells are merged even though they have different identities.
- A source overflow wraps while a target saturates or widens it silently.
- A display/input adapter consumes an extra RNG value or commits an action twice.
- A logical object is assigned separate storage even though source ranges alias.
- A table/handler belongs to another release despite a plausible function name.
- A patched helper changes behavior while its unchanged caller reuses a stale receipt.
- A results-derived wrapper passes by falling back to the source code it claims to replace.
- A whole-file hash passes because the expected file was copied rather than regenerated.

Mutation checks validate the verifier as well as the candidate. Use the actual
original executable and independent expected behavior where available; comparisons
among outputs sharing one incorrect model are not independent confirmation.

## 10. Practical evidence discipline

Hash immutable inputs, tools and published outputs at intake/change boundaries.
Record exact write ranges for patches and use byte comparisons when diagnosing a
mismatch. Do not hash each byte or rehash every asset after every semantic query.
A content digest establishes identity, not meaning. Retain compact claim receipts
and failures; expand source excerpts/traces only for the question being investigated.

Keep game images, executables, retained bytecode, private saves and byte-retaining
databases outside Git. A public plan can contain identities, authored tools,
methodology and sanitized results. Inspect upstream licensing/provenance before
redistributing imported implementation code; public visibility alone is not an
experimental control or an attribution waiver.

## 11. Source index (pinned where available)

- Civ64 process and limitations: https://github.com/Buyukcaglar/Civ64/blob/4e46572d727544722d90c24dc2ce51a9c6d22f15/docs/README.md
- Civ64 design/generator structure: https://github.com/Buyukcaglar/Civ64/blob/4e46572d727544722d90c24dc2ce51a9c6d22f15/docs/DESIGN.md
- Civ64 source-to-port disposition: https://github.com/Buyukcaglar/Civ64/blob/4e46572d727544722d90c24dc2ce51a9c6d22f15/docs/TRACE.md
- Civ64 C/listing contradictions: https://github.com/Buyukcaglar/Civ64/blob/4e46572d727544722d90c24dc2ce51a9c6d22f15/docs/RECOVERY-ERRATA.md
- Civ64 deviations: https://github.com/Buyukcaglar/Civ64/blob/4e46572d727544722d90c24dc2ce51a9c6d22f15/docs/FIDELITY.md
- civd 474.01 overview: https://github.com/sjmelia/civd/blob/c425f7ba45411111c7c71d926e1ce8d4fa641571/README.md
- civd reference hashes: https://github.com/sjmelia/civd/blob/c425f7ba45411111c7c71d926e1ce8d4fa641571/civ.sha256
- civd build/verify commands: https://github.com/sjmelia/civd/blob/c425f7ba45411111c7c71d926e1ce8d4fa641571/justfile
- civd historical-toolchain details: https://github.com/sjmelia/civd/blob/c425f7ba45411111c7c71d926e1ce8d4fa641571/book/src/architecture/toolchain_clues.md
- civd explicit startup editor: https://github.com/sjmelia/civd/blob/c425f7ba45411111c7c71d926e1ce8d4fa641571/src/CRTEDIT.C
- civd edition differences: https://github.com/sjmelia/civd/blob/c425f7ba45411111c7c71d926e1ce8d4fa641571/VERSIONS.md
- Author's methodology account, October 20, 2026, posts 1, 11 and 17: https://forums.civfanatics.com/threads/civ-1-period-accurate-decompilation-source-available.705195/
- Existing fDisBull leads, not an executed replication: https://github.com/seeker-cyber-maker/fDisBull/pull/40

This document is a study plan based on inspected upstream sources and new static
input checks. No new game execution, compiler rebuild, three-arm benchmark,
Civ64 source build, performance win, or complete UDL/UIL conversion is claimed.
No GitHub mutation was performed in preparing this delivery.
