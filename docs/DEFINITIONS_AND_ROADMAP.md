# Definitions and contract roadmap

This guide reconciles existing source, draft proposals and historical feedback
at the 0.25 baseline. It is a map for review, not a new schema or an assertion
that proposed operations are implemented. [PR delivery and remaining work](PR_BACKLOG.md)
tracks outstanding acceptance. The original documents retain their authors'
version-specific wording and evidence; this guide does not replace them.

## Shared vocabulary and direction

An **IL primitive** is an operation in the shared intermediate vocabulary with
a declared meaning and applicable type, width, ordering and numeric behavior.
A source instruction, a recovered higher-level intent and a presentation
control need not be the same primitive. Existing shared IL and bounded evaluator
behavior are real; the broader semantic language and compiler contracts below
are proposals. The [shared-intents RFC](uil-rfcs/0001-shared-intents-and-compiler-definitions.md)
and [executable Rosetta RFC](uil-rfcs/0002-executable-rosetta-contracts.md)
carry their detailed scope and open decisions.

- **UDL, the input side**, defines mappings from source evidence and retains
  executable source backings and bindings where available. It is not merely a
  disposable translation description, and unresolved regions can remain backed
  by original execution under explicit authority.
- **UIL, the editable shared representation**, composes contracts and meanings
  using the same vocabulary. A semantic contract records admitted inputs,
  state, ordered effects, outputs and dependencies; a source mapping or view
  does not silently establish that contract's correctness.
- **UDC, the output side**, selects implementations/compiler definitions for
  qualified contracts. An original-backed path may start from the retained UDL
  backings; other paths may generate or combine implementations. Output
  selection does not require an automatic whole-program rewrite or imply that
  an unavailable lowering exists.

The logical operation identity says *which* operation is being discussed. Its
**semantic revision** identifies the meaning and contract. A separate
**backing/binding revision** identifies the concrete source or implementation
and its correspondence. A layout-only address change may change a binding
without changing semantics only when correspondence is established. A semantic
edit requires a compatible implementation or explicit rejection. A patched
callee can leave caller bytes untouched while invalidating dependent behavioral
qualification. These distinctions are draft contract requirements, not a
claim of implemented incremental dependency tracking.

## Layers and evidence boundaries

| Layer | Role and boundary |
| --- | --- |
| Code and source | Bytes, instructions and mappings are evidence of an implementation; identities include source/version and address context. Unresolved behavior remains explicit. |
| State and effects | State includes scope and lifetime; effects include order, timing and dependencies. A completed effect does not by itself prove the larger intent completed. |
| Intent | A named goal may span multiple actions, effects or processes. Qualification must identify its completion condition and what evidence covers it. |
| Interface | Context, object, event, focus, modality and completion links describe how an action is exposed; a semantic-only export need not pretend to have interactive fidelity. |
| Scene and spatial | Scene family, requested content, displayed content, readiness and action completion are separate. Geometry must distinguish coordinate spaces, footprints, walkability, colliders, portals and qualified anchors. |
| Z-machine bytecode | A target virtual-machine instruction format. Its v3 processor, retained executable IR and qualified intent recovery inspect or preserve that target; they do not define the generic Z interface. |
| Z and the separate player | The shared scene/action/text interface can project an authored slice or an original-backed game provider. It is not the Z-machine instruction set. A recovered bounded intent does not establish a full parser, scheduler or complete game recovery. |

Persistence is also scoped: a native save, project database, checkpoint and live
process can retain different state. State the actual receipt and restoration
boundary. Missing, stale or conflicting evidence is **unknown**, not false,
absent, blocked, ready or complete. An observed partial effect stays partial or
unknown without evidence for the original intent's completion; do not repeat an
ambiguous action merely because later observation failed.

## Qualification, projections and composition

A bounded proof is about its admitted model and assumptions. Bind the claim to
source and selected version, semantic model, observation adapter, runtime and
solver versions, assumptions and evidence boundary. Distinguish
proved-under-assumptions, counterexample, vacuous assumptions, unknown,
unavailable and invalid model. Solver success alone does not validate source
mapping or whole-game equivalence. The [proof proposal](UIL_Z3_PROOF_CONTRACT.md)
contains seven families and ten prospective synthetic scenarios.

Projections may lose information differently: compare facts, epistemic state,
affordances, event traces, hidden-state exposure, narrative and unresolved
meaning rather than only text similarity. Exact bytes, semantic equivalence,
refinement, executable preservation and a lossy presentation are different
claims. Polyglot composition additionally needs explicit adapter types,
numeric conversion, exceptions, ownership, lifetime and runtime dependencies.
The scalar C/JavaScript prototype reported in [RFC 0002's evidence companion](uil-rfcs/0002/README.md)
does not establish Rust, shared-buffer ownership or general compiler support;
its source archives are separate deliveries, so public receipts alone do not
reproduce it.

## Proposal and acceptance map

| Source | Current evidence or bounded slice | Remaining proposal and acceptance |
| --- | --- | --- |
| [#7 interface draft](uil-rfcs/0001-interface-description.md) | Named scenes, targets and conditions exist. The draft preserves E41 observations. | Linked event/control/context identities, focus/modal and completion contracts, and vectors **P1–P4, N1–N4, M1–M4** are prospective. This historic draft also calls itself RFC 0001; it is distinct from the existing shared-intents RFC and is not adopted by this link. |
| [#9 readiness report](SCENE_CONTENT_READINESS.md) | Existing matchers can express the narrower E43 pattern; requested/displayed/ready distinctions exist. | Its seven proposed conformance scenarios remain a set to qualify. A stable footer is not proof of displayed content or action readiness. |
| [#10 macro proposal](https://github.com/seeker-cyber-maker/fDisBull/blob/ae39d078595b7557e090b56a036853680374f1e5/docs/SEMANTIC_INPUT_MACROS.md) and [current macro contract](SEMANTIC_INPUT_MACROS.md) | Bounded macros, movement and geometry exist via #12. | Semantic world IR, bidirectional projections, loss axes and future acceptance checks remain proposed; physical, assisted and story policies remain distinct. |
| [#11 proof contract](UIL_Z3_PROOF_CONTRACT.md) | Narrow arithmetic, readiness and guarded-transition proof builders exist. | General world, containment, geometry, movement and trace adapters plus ten scenarios are proposed; a model proof is not proof of the recovered mapping. |
| [#29 executable Rosetta RFC](uil-rfcs/0002-executable-rosetta-contracts.md) | Authored prototype results and sanitized vectors have the limitations stated in the companion. | **R01–R18** are prospective acceptance cases: identity and backings, patch/dependency propagation, mixed runtimes, blueprint edits, restoration and rejection. No generic executor, visual editor or automatic compiler is added. |
| [#15 DinoPark feedback](https://github.com/seeker-cyber-maker/fDisBull/blob/5d9118ae6c967439c935471c1ca4e992ce2fcdfb/docs/DINOPARK_SAVE_TRAVEL_FEEDBACK.md) | Historical original-backed reports and bounded later provider slices. | **F1–F20** remain an attributed acceptance ledger; consult the backlog for individual open persistence, navigation, REP and other seams. Historical tests do not qualify the current build automatically. |
| [#16 KQ1 assisted benchmark](KQ1_ASSISTED_TRAVEL_BENCHMARK.md) | Historical small-sample paired route and failed attempt. | Edition-bound geometry, separate arrival witnesses, neutral input, failed-attempt capture and a frozen paired benchmark remain to qualify. |

The separate [RFC process](UIL_RFC_PROCESS.md) governs adoption. Linking or
retaining a proposal does not adopt it, resolve its PR, or turn its cases into
tests. Detailed current-source status and other feedback are in the
[backlog](PR_BACKLOG.md); historical reports should be read with their pinned
runtime and original limits.

## Suggested sequencing for 0.26

Ship the documentation reconciliation independently. For implementation,
prioritize the already identified REP partial-completion interpretation and
its authored native acceptance; it affects truthfulness of debugger results.
Select one bounded, evidence-backed persistence or semantic-observation seam
next, with independent acceptance and explicit unknowns. Keep linked interface
conformance, general proof adapters, full UDL/UIL/UDC compilation, polyglot
ownership, visual editing and generalized recovery as separate later work until
scoped contracts and qualified implementations exist. This is a recommendation,
not a promise that any feature ships in 0.26 or that one target's evidence
qualifies another.
