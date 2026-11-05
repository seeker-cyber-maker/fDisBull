# GitLab fDisBull MR coordination snapshot: 2026-11-04

**Read scope:** all 78 project merge requests, **33 opened / 21 merged / 24 closed**, and the discussion threads for each MR (including non-system comments and review-correction notes). This is a **point-in-time index**, not a GitLab mutation or approval; always reread the current MR before editing or merging.  
**GitLab project:** https://gitlab.com/brewster-jennings-group/fdisbull  
**Main inspected:** `3dc5c50d35f310a3ba39b1cf0cf82a20b8df69f7`; **latest release:** `v0.31.1`; **v0.32 draft** !78 not a release.

## Cross-lane coordination decisions

- **Source-of-truth architecture:** !45 (merged, after terminology corrections); existing 14-stage inventory + deterministic plan !64; reusable env/ISA/target packages !65; provider alternatives and service contracts !66. New [phase contracts](../MACHINE_PIPELINE_STAGE_CONTRACTS_2026-11-04.md) provide the handoff/granularity, not parallel competing schemas.
- **CHIP-8:** !61 decoder/VM pilot is not a full original-equivalence proof; !69 Python UDC PoC is **paused and stacked on !61**, not approved for an automatic merge; !58 is a different connected-block swede experiment. !65 owns held-out, natural/synthetic and 1/2/3 blind-gap acceptance.
- **Known correctness cautions:** !45 terminology/undeclared-operation corrections were applied before merge. !48 contains review findings about pointer comparison and wrapping exceptions; !43 has record-validation failures tracked by !49. !59 contains a later **original Colonization DOS code correction**: do not treat its original-vs-reference Tea Party claim as settled solely by its earlier benchmark summary.
- **Overlapping PE work:** !67 is incomplete (missing writer) and !68 is a separately completed candidate; both touch `chimprec_pe.py`. Treat as alternatives, **not** automatic cherry-pick candidates; !78 selects reviewed !68 portions.
- **Release/CI:** !71 owns local Linux package completeness/qualification; !78 is a frozen v0.32 candidate with incomplete exact-source required native evidence. Do not trigger hosted CI, merge, tag or activate installations via this documentation draft. !74 contains an explicitly installed hot-patch and separately preserved crash evidence, not automatically main/release.
- **Research handoffs:** merged !34/!35/!36/!37 preserve historical Civilization/FF7/Syndicate/Zork/KQ1 source analyses; pending !42, !50/!54/!55/!56 preserve newer deliverables. Closed stacked KQ1 MRs are historically useful but **not** general capabilities.
- **Policy:** Original game binaries, private databases, captured-memory files, ROM-derived artifacts, and runtime snapshots must not be pushed into this public repository. Truthful source-versus-model-versus-original claims and agent handoff receipts remain mandatory.

## Complete MR index (all project states)

| MR | GitLab state | Title | Routing lane |
|---|---|---|---|

| [!1](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/1) | closed | Draft: Add source-backed macOS ARM64 investigation | intake/ISA |
| [!2](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/2) | closed | Draft: Report analysis capabilities and app replication boundaries | intake/ISA |
| [!3](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/3) | merged | Draft: 0.28.0 release candidate | governance/release |
| [!4](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/4) | closed | Draft: Preserve PR 56 console modules and full Miniplanets NES port | intake/ISA, UDC/providers |
| [!5](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/5) | closed | Draft: Genesis-to-NES research handoff (possible, not recommended) | intake/ISA, UDC/providers |
| [!6](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/6) | closed | Draft: Normal KQ1 goat play and reusable Z scene | runtime/evidence |
| [!7](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/7) | closed | Draft: Add reversible macOS sessions and display-bound capture | runtime/evidence |
| [!8](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/8) | closed | Draft: Qualify ordinary KQ1 troll bridge and extend the Z scene | runtime/evidence |
| [!9](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/9) | closed | Draft: Publish combined macOS status replica and current cpuinfo comparison | UDC/providers |
| [!10](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/10) | merged | Deduplicate feature CI and bound agent status polling | governance/release |
| [!11](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/11) | merged | Draft: Cortex-M/Thumb static firmware analysis (PR #74 continuation) | intake/ISA |
| [!12](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/12) | merged | Draft: Collate PR specs, 0.28 gap analysis and 0.29 proposals | governance/release |
| [!13](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/13) | closed | Draft: Qualify goat water branches and the original AGI river-edge skip | runtime/evidence |
| [!14](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/14) | merged | Draft: Add Anchor Stone history and compare direct restore | runtime/evidence |
| [!15](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/15) | closed | Draft: Qualify KQ1 bridge corner and reusable Z scene | runtime/evidence |
| [!16](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/16) | closed | Draft: DOS and Wine delta rewind with Anchor Stone comparisons | runtime/evidence |
| [!17](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/17) | closed | Draft: Qualify KQ1 mushroom-island route and Z scene | runtime/evidence |
| [!18](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/18) | merged | Draft: Improve DinoPark analysis, Z recovery and DOS audio inspection (PR #41) | runtime/evidence |
| [!19](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/19) | closed | Draft: Extend shared Snake UIL to Win32 and segmented Win16 | UDL/UIL, UDC/providers |
| [!20](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/20) | merged | Draft: Preserve Tic-tac-toe, Five Dice and Snake versions | UDL/UIL, UDC/providers |
| [!21](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/21) | closed | Draft: Qualify KQ1 clover cave route and preserve Robb TAS handoff | runtime/evidence |
| [!22](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/22) | closed | Draft: Add checkpointed KQ1 gnome and chest Z scenes | runtime/evidence |
| [!23](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/23) | closed | Draft: Qualify KQ1 dragon and mirror Z scenes | runtime/evidence |
| [!24](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/24) | merged | Draft: Common UIL composition and native Snake windows/input | UDL/UIL, UDC/providers |
| [!25](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/25) | closed | Draft: Detect and qualify KQ1 dragon boundary exceptions | runtime/evidence |
| [!26](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/26) | merged | Prepare 0.28.0 release candidate | governance/release |
| [!27](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/27) | merged | Draft: Give agents verified GitLab MRs and report handoffs | governance/release |
| [!28](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/28) | merged | Draft: Console synthesis progress, Ghidra routes and agent file handoff | intake/ISA, UDC/providers, governance/release |
| [!29](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/29) | closed | Draft: Audit scene coordinate domains and KQ1 edge seams | runtime/evidence |
| [!30](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/30) | closed | Draft: Automatic full-state frame and input timelines | runtime/evidence |
| [!31](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/31) | merged | Draft: Durable standing probes for unknown code and meaningful values | runtime/evidence |
| [!32](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/32) | closed | Draft: Shadowrun ARM64 courtyard actors and source-backed menu | intake/ISA |
| [!33](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/33) | closed | Draft: Verify KQ1 bottom-row crossing and add a reusable Z scene | runtime/evidence |
| [!34](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/34) | merged | Draft: Preserve ChatGPT Civ, FF7 and Space Quest research | governance/release |
| [!35](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/35) | merged | Draft: Preserve ChatGPT Syndicate audio, graphics and LE research | UDL/UIL, governance/release |
| [!36](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/36) | merged | Draft: Recover preserved Zork scene runtime and methodology | UDL/UIL, governance/release |
| [!37](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/37) | merged | Draft: Preserve KQ1 JPC-RR evaluation and verified macOS comparison | runtime/evidence, governance/release |
| [!38](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/38) | closed | Draft: Share bounded native control and scene receipt assembly | runtime/evidence |
| [!39](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/39) | closed | Draft: Add bounded native alignment and frame-state coherence | runtime/evidence |
| [!40](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/40) | closed | Draft: Recover SNES Shadowrun movement into UIL and native ARM64 | intake/ISA, UDC/providers |
| [!41](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/41) | merged | Add lossless delta storage to the automatic frame timeline | runtime/evidence |
| [!42](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/42) | opened | Draft: Preserve Library handoffs and reconcile published artifacts | governance/release |
| [!43](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/43) | opened | Draft: Add indexed UIL records, Civ world projection and media extraction | intake/ISA, UDL/UIL, UDC/providers |
| [!44](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/44) | merged | Draft: Refresh README and bundled skills after v0.30.0 | governance/release |
| [!45](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/45) | merged | Draft: Consolidate UDL-UIL-UDC architecture, schemas and Z-world harness reference | UDL/UIL |
| [!46](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/46) | opened | Draft: Teach progressive console support in the investigation skill | intake/ISA, governance/release |
| [!47](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/47) | opened | Draft: Define worker context and bounded evidence review | governance/release |
| [!48](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/48) | merged | Add bounded typed C to UIL importer from reviewed delivery | UDL/UIL |
| [!49](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/49) | opened | Draft: Correct integer slot and array operand validation in UIL records | UDL/UIL |
| [!50](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/50) | opened | Draft: Add paired Colonization production and difficulty UIL examples | UDL/UIL, UDC/providers |
| [!51](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/51) | opened | Draft: Document proposed parallel research workspace lifecycle and boundaries | governance/release |
| [!52](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/52) | opened | Draft: Preserve prepared matched research methodology pilot and dispatch packets | governance/release |
| [!53](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/53) | opened | Draft: Retain deterministic execution and agent guidance requirements | UDL/UIL, governance/release |
| [!54](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/54) | opened | Draft: Add Syndicate tactical history and source-free selective-rewind study | UDL/UIL |
| [!55](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/55) | opened | Draft: Add Syndicate campaign and research source study | UDL/UIL |
| [!56](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/56) | opened | Draft: Add portable UIL text, Z-harness and large-world reference studies | UDL/UIL |
| [!57](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/57) | opened | Draft: Connect block discovery, guided sweding and contribution intake | UDC/providers |
| [!58](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/58) | opened | Draft: Exercise fresh-agent sweding across one, two, and three blocks | UDC/providers |
| [!59](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/59) | merged | Draft: docs,test(benchmark): 4-stage cold-agent skill evaluation and Elephant-Goldfish Method (EGM) analysis | governance/release |
| [!60](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/60) | opened | Draft: Add Win32/Win16 debugger routes and repair protected DOS input | runtime/evidence |
| [!61](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/61) | opened | Draft: Probe CHIP-8 ISA and corpus with Sandsifter-inspired fuzzing | intake/ISA, UDL/UIL, UDC/providers |
| [!62](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/62) | opened | Draft: 0.31.0 release candidate | governance/release |
| [!63](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/63) | opened | Draft: PE32-first reversible UIL fusion with local macOS Clang | UDL/UIL, UDC/providers |
| [!64](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/64) | opened | Draft: Audit fDisBull maturity, deterministic workflow, and generic UIL/UDC milestones | UDL/UIL, governance/release |
| [!65](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/65) | opened | Draft: Reusable environment/ISA/target packages and CHIP-8 end-to-end gap tests | intake/ISA, UDL/UIL, UDC/providers, governance/release |
| [!66](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/66) | opened | Draft: Catalog portable service contracts and alternative realizations | UDL/UIL, UDC/providers |
| [!67](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/67) | opened | Draft: Finish CHimpREC captured PE rebuilding and GOG Galaxy wrappers | intake/ISA |
| [!68](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/68) | opened | Draft: Rebuild captured PE imports and unpack GOG Galaxy wrappers | intake/ISA |
| [!69](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/69) | opened | Draft: Preserve CHIP-8 Python UDC PoC and interrupted-work handoff | UDL/UIL, UDC/providers |
| [!70](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/70) | opened | Draft: Add NES C/Python-before-UIL recovery experiment | intake/ISA, UDL/UIL, UDC/providers |
| [!71](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/71) | opened | Draft: Move full Linux qualification locally and enforce complete packages | governance/release |
| [!72](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/72) | opened | Draft: Add fast scene checks and contain DOS shutdown failures | runtime/evidence |
| [!73](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/73) | opened | Draft: Add experimental ScummVM AGI and Lost in Time Gob debugger backends | runtime/evidence |
| [!74](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/74) | opened | Draft: Fix headless quit dialogs and preserve recovery evidence | runtime/evidence, governance/release |
| [!75](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/75) | opened | Draft: SNES hardware inputs and playable keyword conversations | intake/ISA, runtime/evidence, UDC/providers |
| [!76](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/76) | opened | Draft: Handoff common UIL CI recovery and verified Linux suite | governance/release |
| [!77](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/77) | opened | Draft: Add catalog intake, DinoPark playback and media framing | intake/ISA |
| [!78](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/78) | opened | Draft: Prepare reviewed 0.32 feature release and exact-source local qualification | governance/release |

**State warning:** GitLab `merged` and `closed` reflect review-object state. Many historical titles still start with “Draft”; descriptions preserve exact source/evidence and qualification limits. An MR included in a release can still have a separate open handoff or subsequent unqualified branch.
