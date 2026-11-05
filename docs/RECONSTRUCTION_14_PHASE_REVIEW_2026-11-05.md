# fDisBull: 14-stage UDL → UIL → UDC review worksheet

**Created:** 2026-11-05  
**Status:** Discussion worksheet, not an implementation, approved specification, release claim, or completed review.  
**Target:** Post-0.32 architectural prioritization. No change to the frozen 0.32 release candidate.  
**Source:** [Deterministic pipeline orchestration audit (November 3)](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/codex/integration-0.32-prs-20261104/docs/DETERMINISTIC_PIPELINE_ORCHESTRATION_AUDIT_2026-11-03.md) and [maturity audit](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/codex/integration-0.32-prs-20261104/docs/RECONSTRUCTION_MATURITY_AUDIT_2026-11-03.md). The source currently resides in the 0.32 integration branch; this worksheet does not assert those source documents have landed on main.

## Purpose

Review the **14 responsibility/stage rows** of the audit with TiGa, record design decisions, identify reusable software to replace agent glue, and turn approved decisions into independently testable acceptance criteria. These are not necessarily 14 strictly sequential runtime phases; feedback and qualification can loop or overlap.

For each phase, capture: (1) existing code/evidence, (2) intended software vs agent ownership, (3) supported/unsupported cases, (4) qualification gate and minimum usable deliverable, (5) dependencies/priority, and (6) decision and rationale. A draft note is not an accepted decision.

## Provisional phase alignment and Phase 0 intake specification (2026-11-05 discussion)

**User direction from voice review:** The source audit's 14 entries are engineering responsibilities, not necessarily the right user-facing phase boundaries or count. Separate **Phase 0: Intake** and **Phase 1: Goal setting / brainstorming**. Phase 0 inspects what was supplied and what this instance can do *before* asking the user to choose an analysis objective. Phase 1 should use a brainstorm skill or equivalent structured conversation, grounded in the actual intake findings, so the user and agent do not commit hours to an incorrect or infeasible interpretation of the request. Later sequencing and total phase count remain open for review; do not mechanically add one to all fourteen audit categories.

### Phase 0: Intake and feasibility dossier (provisional detailed design)

**Entry:** Any explicitly supplied file(s) or directory/collection, including an executable, installer, CD/disk/ROM image, resource-only package, archive, project manifest, or an opaque unknown file. A single binary is *sufficient to start*, but it is not sufficient to guarantee a runnable or reconstructable program.

**Mandatory read-only observations, at bounded cost:**

1. **Artifact identity and provenance:** original filename/path within selected collection, size, complete SHA-256 or explicitly partial fingerprint, read extent, opened-descriptor identity, source/carrier/member transformation chain, alternate identical revisions if locally established. Attribution, version labels, copyright/rights and provenance that cannot be proven from bytes remain *user-supplied/unverified/unknown*, not inferred facts.
2. **Container / related member inventory:** distinguish outer installer, compression/archive/filesystem, executable image, bytecode/VM program, resource/media and documentation; enumerate safely within explicit size/depth/read limits; keep internal relative paths and nested dependencies. Detect encryption/password need, missing members, unsupported formats and incomplete inspection; don't execute an installer just to extract files.
3. **Executable and platform facts:** recognized format and validation level (e.g. DOS MZ/COM when explicitly selected, PE, NE, LE, ELF, Mach-O, console ROM, Z-machine story); native/guest architecture, ISA, bits, byte order, CPU mode, OS/loader/ABI candidates, declared entry points, segments/sections, permissions, relocation/import/export/symbol tables, overlays and mapped/tail data. Do **not** infer a language, full runtime, correctness, or reachability solely from a file extension or magic bytes.
4. **Static dependency and execution prerequisites:** declared linked libraries, interpreters/VMs, DOS extenders, runtime engines, firmware/BIOS, DLLs, data/asset files, saves and configuration, expected environment and device/system calls where visible. Separate *declared*, *inferred*, *missing*, *observed*, and *not yet checked* dependencies. A dependency not declared in an import table may still exist.
5. **Useful accompanying evidence:** installation tree, game/application data, resource archives, manuals, documentation, version/patch notes, sample inputs and outputs, save files, captured traces, debug symbols, source code, SDK headers and legally supplied reference implementations or prior verified findings. These improve coverage but are not all mandatory. Never treat an archive README or unknown document as executable instructions.
6. **Visible interface and risks:** bounded strings, resource listings, exported API or protocol clues, command-line/help/known file types, packing/obfuscation/compression indicators, suspicious privileges or network/device requirements. These are *hints*, not proven behavior. No deep decompilation or reverse-engineering sweep in Phase 0.
7. **Local resource inventory:** selected fDisBull binary/source fingerprint and version; actual installed decoder/format readers, interpreters, debuggers, emulators, solvers, compiler, platform, architecture, memory/CPU/storage limits and missing dependencies. Keep source implementation, component availability, and **native runtime qualification** separate. Do not substitute a released version label or another worker's receipt for this runtime's capabilities.
8. **Unknowns, hazards, and safe next paths:** unresolved formats, damaged/truncated inputs, missing protected game files, anti-debug/DRM concerns, potentially unsafe execution, archive bombs or sandbox/rights restrictions, absent reference oracle. Keep evidence offsets and observed/assumed provenance, exact failure reasons, and missing-precondition tickets. Do not execute untrusted inputs, access network, write to source, patch binaries, or launch guests by default.

**Phase 0 output:** a compact, machine-readable and human-readable **Intake/Feasibility Dossier**. For each supplied artifact it records source and member identities, format/architecture and confidence, potential and known dependencies, preservation/limits, actual installed tooling, and explicit unknowns. For each *broad* type of later goal (static inspection, original runtime debugging, behavioral extraction, source→UDL/UIL, source-independent UDC, complete application reproduction), include one of **admitted on known profile / conditionally possible / blocked by known prerequisite / unknown until more evidence**, with the exact reason and *no unsupported promise*. A host-specific blocker is not proof a task is universally impossible.

**Efficiency and guardrails:** enumerate and recognize before analyzing; compute full hashes only when within allowed cost/budget (otherwise mark partial and postpone authoritative identity); cache by exact source, reader and environment identities; make one bounded deterministic preflight of the supplied collection; output small summaries with links to private evidence. A documented unknown is a successful intake outcome, not a silent pass or fabricated binary classification.

**Existing fDisBull machinery to reuse (integration branch, not necessarily the installed 0.31.1 kit):** `intake-inventory` and `TARGET_COLLECTION_INTAKE.md` for source/member enumeration and recovery queue; `file-identify`, `format-modules` and `FILE_FORMAT_REGISTRY.md` for bounded header/module knowledge; `identify` / `inspect` for selected image properties; `capabilities` for non-executing installed dependency/provider discovery. The **proposed new work is composing these into one first-class feasibility result**, not rewriting every parser.

**Suggested acceptance gate:** On an authored supported executable, a headerless COM case, an archive containing an executable plus resources, a partially missing resource set, and an unknown/unsupported binary, Phase 0 returns a reproducible provenance-bound dossier. All unsupported/unknown states remain explicit; no binaries run, source bytes mutate, or unapproved deep analysis starts. A fresh agent can use its output to ask relevant goal questions and identify when a requested goal needs files/backends not currently available.

### Phase 1: Goal setting and brainstorming (provisional)

**Input:** Phase 0 dossier, the user's stated task (if any), available brainstorm-style skills and applicable safety/authority rules. Brainstorming should surface plausible tasks based on the *actual* program and capability evidence, rather than presenting a generic menu of every fDisBull feature.

**Output:** a confirmed **GoalSpec** defining desired outcome (e.g., characterize, debug, extract mechanics, translate one block, port a bounded application slice), observable scope/fidelity, acceptable approximations, source/target editions, final reusable artifacts, independent original/model/output acceptance evidence, constraints/budgets, and allowed side effects. Explain infeasible or conditional routes and offer a narrower valid experiment before expensive execution. User consultation happens **here**, not during basic file inventory; retain decisions to avoid circular re-questioning. No consent or approval is inferred from an uploaded binary alone.

**Handoff:** Phase 0 says **what is present and could be attempted**; Phase 1 determines **what the user actually wants and what counts as done**; the subsequent route planner selects exact decoders, backends, proof oracles and execution stages. Do not start hours of generic analysis before those gates.

### Phase 2: Documentation and prior-art research (automatic, documentation-first)

**User decision, 2026-11-05:** After read-only Phase 0 intake and Phase 1 goal-setting, perform an **automatic, goal-focused documentation and prior-art research pass**, without requiring another user-approval ceremony. The work should **start by understanding the program from existing documentation** and then choose what is worth investigating in its bytes. Manuals, scans, walkthroughs, maps, fan knowledge, format specifications, source-code reimplementations, earlier fDisBull work, and reference software are all documentation/evidence for this phase. They are not separate mandatory phases, and executable code is only one documentary source.

**Boundary:** Phase 0 inventories input files and labels documentary resources without deep reading; Phase 1 confirms what success means; **Phase 2 reads, searches, cross-references and synthesizes the relevant knowledge**. Phase 2 may recommend a route (reuse, adapter, targeted original RE, new implementation) but may not falsely elevate documentation to verified original behavior. Its deliverable is actionable research intelligence, not an unbounded literature review.

#### Documentation corpus and extraction

1. **Owner-supplied and package documentation first:** enumerate game/application manuals, help, release notes, command cards, readme files, disk inserts, setup/installation instructions, keyboard templates, configuration descriptions, specification files and source bundles already present in the user-selected collection. Preserve original location, input hash, page IDs and edition/language. A manual embedded in an installer is worth extracting with a **qualified, non-executing** reader if available.
2. **Readable vs image-only PDFs:** identify whether the manual has a usable text layer. For scanned/image-only manuals, use an **optional local OCR adapter** to create a private, searchable, **page-cited** Markdown/JSON evidence index, even for a non-vision agent. OCR can be performed in bounded page shards, with tool/profile/source identity and review flags. Column ordering, symbols, diagrams and low-confidence words require image/manual inspection or an explicit `uncertain` status. **OCR confidence is not evidence that text reading order is correct.** Do not silently treat figures as understood after OCR.
3. **Guides, maps and walkthroughs:** search the selected game's edition, platform and language plus variant names, engines, community guides, reverse-engineering notes, speedrun routes, GameFAQs-style walkthroughs, preservation sites and existing local notes. Collate multiple sources without assuming they agree; record specific page/section/URL and edition per claim. For long guides, extract a concise, cited knowledge index rather than a copyright-incompatible full reproduction.
4. **Existing source and compatible technologies:** search existing ports, open recreations, engine families, reverse-engineered format decoders, data files and debugging projects. Examples mentioned by the user: Sherlock → Watson; Dune-like titles → their applicable open-source reconstructions; Civilization family → Freeciv/OpenCiv/Civ64/CivD candidates. A title/name resemblance **does not establish code or rules compatibility**. Pin commit, version, license, asset rights, exact supported semantics, and whether a candidate was only located/read versus built, exercised, or compared. Check both the user's local prior work and outside repositories.
5. **Extract structured, testable facts:** build a **Documentation Intelligence Ledger**, not only a prose summary:
   - **Controls:** stated keyboard keys, mouse requirements, click regions, menus, dialogs and Save/Load controls. Distinguish physical mouse support, emulator mouse connection, actual application consumption and alternative keyboard navigation.
   - **Scenes and navigation:** rooms/locations, cardinal transitions, doors, destinations, special interaction conditions, visible/movable objects, inventory, items that can be taken, NPC actions, triggers, puzzles and event dependencies.
   - **Mechanics and data:** rules, resources, effects, save-game schema hints, command grammar, graphics/audio file clues and potentially relevant original functions, strings and tables.
   - **Technical/reuse leads:** existing algorithm/code/source candidates, relevant file formats, emulator/runtime requirements, corresponding fDisBull modules, version mismatches and licensing obligations.
   Every entry must have a precise source citation/locator, target edition, claim type, confidence, status (`documented`, `candidate`, `original-observed`, `contradicted`, `unverified`), and the **next concrete observation or search** that could check it. Separate a manual author's assertion, a third-party guide's advice, source-code behavior, and actual measured original-game facts.
6. **Turn the ledger into work:** generate a *hypothesis/checklist and directed probe plan* tied to the GoalSpec. For a room guide identifying a chest, wardrobe and movable dresser, provide explicit objects to seek in scene handlers/resources/variable references and original-game observations; do not claim those structures have already been recovered. When a guide gives room exits or pickup items, create expected transition and inventory tests. Unknowns feed a prioritized question list rather than spawning unlimited speculative reconstruction. Targeted runtime or static probes happen in the later analysis/validation phase, not automatically under documentation reading.
7. **Feasibility and route comparison:** use found references to choose the least unnecessary original RE. Check original/source distinction, edition parity, integration cost, licensing, dependency and proof obligations; recommend reuse, adapter, targeted RE or new implementation with stated uncertainty. A failed search does not prove no solution exists. Cap the first research pass, preserve source lists, and reopen only for material discoveries or a changed goal.

#### Grounded examples, with evidence ceilings

- **Sherlock 1.50:** [MR !97](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/97) explicitly says the original agent investigated and built much of a native solution before searching prior art. TiGa's later [Watson reference](https://github.com/koro-xx/Watson/releases) exposed relevant clue relations, hint logic and build approach. The reference was **reviewed, not built or run** there; reuse requires version-specific verification and GPLv3 compliance. This motivates an automatic research checkpoint, not a claim that fDisBull auto-ported Sherlock.
- **Castles II:** [MR !85](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/85) describes a **source-only, optional local Tesseract OCR pilot** on a 55-page scanned GOG manual. It extracted page-cited setup, castle-design and campaign Save/Load/PAUSE descriptions and flagged pages needing visual review. It is **not part of the published 0.31.1** and not evidence that the OCR-derived controls have all been executed. [MR !84](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/84) separately observed original-game mouse and Save/Load behavior. The integration should reuse this pilot where qualified, not invent another generic OCR system.
- **Alone in the Dark and Police Quest (user's examples):** collated guides can become **scene-level investigation checklists**: expected containers/movable furniture, pickups such as key/radio, or cardinal room graph edges. These are source-backed *hypotheses* until matched to the exact edition and original-run evidence, not verified extraction results from this worksheet.
- **DOS/legacy input uncertainty:** manuals can tell a worker that a menu should support a mouse or key. A nonreactive emulator click may indicate guest-device setup or focus trouble rather than a missing game control. Preserve these explanations separately and run the corresponding discriminating tests later.

#### Phase 2 outputs / exit criteria

1. **Documentation Corpus Manifest:** enumerated embedded/private and external sources, edition and language claims, ownership/license constraints, URLs/local paths, hashes/commits, page-citation coverage, text/OCR/diagram status, and any inaccessible or missing items.
2. **Documentation Intelligence Ledger:** structured, provenance-preserving control map, menu map, room/scene graph candidates, item/action checklists, rules, version mismatches, source-code leads and explicitly unresolved/conflicting assertions. Keep private proprietary source material and full extracted manuals outside GitLab; publish only permitted summaries and sanitized fixtures.
3. **Research/Reuse Decision Receipt:** route candidates and criteria, tool/skill coverage, what could be reused, what remains to implement, independent evidence required, and a bounded plan for the user's accepted goal. Includes statuses `matched`, `no suitable match found in searched sources`, `partial/unavailable`, and `needs verification`.
4. **Handoff to analysis:** a short set of exact, source-cited questions, expected observations and possible code/resource anchors, so the next agent investigates *what matters* rather than searching blindly.

**Acceptance proposal:** On a cold Castles II-like scanned manual, text-only agent tools must surface page-cited menu/input/Save/Load clues via an available OCR route or report the missing OCR dependency explicitly; on a held-out adventure input plus multiple inconsistent guides, generate a cited scene graph/checklist with conflicts retained; on Sherlock, find/review a relevant source implementation *before* custom reconstruction. Distinguish all three documentation assertions from independent original-run proofs. These are **proposed tests, not tests already run for this new phase**.

**Policy:** Phase 2 is automatic after the P1 goal and permitted source scope. Extra human approval is not required merely to read/search documentation, but existing permission controls still apply to external writes, restricted resources and execution. Do not copy entire copyrighted walkthroughs into a public MR. The original fourteen responsibility areas are retained below, pending remapping; the final total phase count is undecided.

### Disposition and remaining design questions

- **Captured user preference:** Separate Phase 0 intake from Phase 1 goal discussion, with a brainstorm skill informed by first inspecting inputs. Preserve this as a user-originated direction.
- **Proposal, awaiting review:** exact dossier schema, capture budgets, feasibility categories, which missing items block a particular goal, and whether Phase 0 inventory runs tool-only or with a bounded agent explanation pass.
- **Not claimed:** existing fDisBull already emits this unified dossier, has a generic goal parser, or automatically routes every file/host combination.
- **Additional skills:** The user referenced uploaded skills with names ending in “AI”; their exact names, source files and applicability have not yet been verified. Do not declare them integrated until located and reviewed.

## Fourteen-phase map

| # | Phase (as described in audit) | Audit assessment | Main gap to review |
|---:|---|---|---|
| 1 | Input discovery / collection | Mixed | Batch content-addressed intake, edition/dependency closure and retained unknowns |
| 2 | Environment / capability selection | Mixed | Select legal backend/profile from actual installed capabilities, without agent guesswork |
| 3 | Static decoding | Software-led | Deterministic ambiguous-entry inventory, unknown indirect edges, and safe resume |
| 4 | Def-use / effect summaries | Agent-led | Generic backward slicing, typed live-in/out, memory aliases, flags, and may-write summaries |
| 5 | Runtime setup and control | Mixed | Idempotent session recipes, stable snapshots, probe templates, and exclusive ownership |
| 6 | Choosing semantic boundary | Agent-led | Algorithmic candidate cuts that identify a meaningful, testable operation |
| 7 | UDL lift | Mixed to agent-led | Declarative lifter registry and visible unsupported residuals, not custom one-off adapters |
| 8 | UIL composition | Mixed | Canonical type/effect semantics and loss/refusal checked bridges between UIL profiles |
| 9 | Source → UIL validation | Mixed | Differential original/model runner with independent oracles and negative cases |
| 10 | Provider discovery / sweding | Mixed; drafts | Qualified reusable block catalog, missing-provider tickets, cold worker synthesis |
| 11 | UIL → UDC build | Software-led on admitted profiles | Legalization, dependency/build graph, exact target support and explicit refusals |
| 12 | Target execution / comparison | Mixed | Repeatable original/model/output differential comparison and first-divergence receipts |
| 13 | Optimization feedback | Prototype | Reversible proof-checked, measured candidates; never promote changed semantics by intuition |
| 14 | Packaging, CI, and user delivery | Mixed | Verified closure manifest, source/artifact IDs, accessible deliverables, privacy and native gates |

## Discussion prompts and provisional exit tests

**1. Input discovery / collection**  
Decision pending. Should the default input be an executable, installer, disc image, folder or all of them? Proposed gate: one command inventories a supported collection, hashes sources, links resources/editions, and reports unknown files without fabricating relationships.  
**Notes:** _To discuss._

**2. Environment / capability selection**  
Decision pending. Where do host constraints, retained tools and runtime variants live? Proposed gate: a goal and environment inventory deterministically select an admitted route or give exact missing requirements, without running unapproved binaries.  
**Notes:** _To discuss._

**3. Static decoding**  
Decision pending. How much uncertain code-discovery work should be auto-queued? Proposed gate: repeatable worklists preserve overlapping interpretations and undecidable indirect edges; interruption/resume reproduces identities and frontier.  
**Notes:** _To discuss._

**4. Def-use / effect summaries**  
Decision pending. This is one likely high-value bottleneck. Proposed gate: a general analysis recovers admitted live-ins, live-outs, flags, alias sets, and conservative external effects on held-out examples; unsupported effects stay unknown.  
**Notes:** _To discuss._

**5. Runtime setup and control**  
Decision pending. Proposed gate: pinned source/backend/host identities, clean launch, controlled input, checkpoint and restart with explicit differences between guest and external host state. Exclusive session lease prevents multiple controllers interfering.  
**Notes:** _To discuss._

**6. Choosing semantic boundary**  
Decision pending. How do we define a useful operation without naming the game? Proposed gate: candidate boundaries from data/effect cuts on an unfamiliar target; wrong boundaries produce measurable counterexamples, not silent acceptance.  
**Notes:** _To discuss._

**7. UDL lift**  
Decision pending. Proposed gate: a reusable source-backed lift emits typed ports, state/effects and unsupported residuals; a second unrelated source can reuse the same registry and gate.  
**Notes:** _To discuss._

**8. UIL composition**  
Decision pending. Proposed gate: core semantics plus explicit bridges for legacy/common/memory/record/Z profiles, with order, ownership, width and unknown/refusal rules retained. Two independent consumers pass shared conformance cases.  
**Notes:** _To discuss._

**9. Source → UIL validation**  
Decision pending. Proposed gate: compare original observation with independently interpreted UIL, report the first divergence, and include boundary, reset, negative and refusal probes. Agreement between two authored models alone is insufficient.  
**Notes:** _To discuss._

**10. Provider discovery / sweding**  
Decision pending. Proposed gate: discover and reuse a source-independent block when available; when absent, issue a bounded synthesis ticket for a fresh agent and independently qualify any produced provider. Exercise 1-, 2- and 3-block graphs with a stateful effect.  
**Notes:** _To discuss._

**11. UIL → UDC build**  
Decision pending. Proposed gate: a target-capability preflight either emits a complete admitted realization with pinned dependency graph or refuses with missing constructs. No hidden deletion of callbacks, effects, or state.  
**Notes:** _To discuss._

**12. Target execution / comparison**  
Decision pending. Proposed gate: run original, UIL and target realization against matched inputs, compare ordered observations and persistence separately, and retain first-difference evidence.  
**Notes:** _To discuss._

**13. Optimization feedback**  
Decision pending. Proposed gate: source-qualified baseline, proven or independently checked candidate meaning, measured cost on target, provenance, bounded loop and opt-in reversible selection.  
**Notes:** _To discuss._

**14. Packaging, CI, and user delivery**  
Decision pending. Proposed gate: one delivery receipt identifies tested source, built artifacts, exclusions, privacy checks, actual binary download/install/run and blocked native tests. An upload is not a completed delivery.  
**Notes:** _To discuss._

## Cross-cutting questions

- Should the workflow coordinator be a small local-first SQLite-backed DAG/state machine, with agent involvement only for ambiguous meaning and genuine exceptions? This is the audit's recommendation, **not yet an approved architectural decision**.
- Which two unrelated held-out programs will prove reuse without game-specific core conditionals?
- Which receipts can be cached under transitive source/semantic/provider/host dependencies?
- Do we set a stop rule against adding more decoders or engines until one bounded source→UIL→UDC operation achieves independent G5 acceptance?
- How do we count unknown/refused and untested operations as denominators, rather than citing only passing tests?

## Decisions ledger

| Phase | Decision | Rationale | Owner | Acceptance evidence | Status |
|---|---|---|---|---|---|
| Phase 0 / Phase 1 | User direction: separate read-only input/capability intake from subsequent brainstorm-based goal setting. | Avoid choosing an unsupported or wrong objective before analysis; detailed acceptance remains under review. | User + review agent | Proposed dossier and brainstorming contract in this document; no implemented or tested feature claimed. | **Direction captured; specification provisional** |\n| Phase 2 | User direction: automatic documentation-first research after goal-setting; manuals/PDF OCR, guides, maps, scene checklists, ports/recreations and prior code all belong to one evidence phase. | Sherlock !97 missed Watson until late; Castles II !85 shows page-cited OCR; guides can constrain original-game investigations without replacing actual evidence. | Review agent + user | Manifest + cited intelligence ledger + route decision; proposed OCR, conflicting-guide, and cold Sherlock acceptance checks. | **Direction captured; implementation/tests provisional** |\n| Original 14 audit categories | Mapping, numbering and phase count pending review. | Original audit rows are responsibility areas, not a proven sequence. | Pending | Pending | **Unreviewed** |

## Change and release boundaries

This documentation-only worksheet contains **no software implementation** and claims **no new runtime qualification**. Keep it as a draft MR while discussing. Do not automatically merge into the frozen 0.32 release branch. Changes to the fourteen phase descriptions, notes, accepted decisions and acceptance tests should be made on this worksheet branch with a clear commit history.

Source and context: [0.32 integration MR !95](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/95), [0.32 release MR !78](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/78), [14-stage audit](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/codex/integration-0.32-prs-20261104/docs/DETERMINISTIC_PIPELINE_ORCHESTRATION_AUDIT_2026-11-03.md).
