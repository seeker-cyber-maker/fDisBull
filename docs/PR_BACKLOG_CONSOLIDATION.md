# PR consolidation, 0.28 gap analysis and 0.29 slate

Status: consolidated review object in !12. This document replaces the closed
GitLab review descriptions; every source branch and exact head remains available.
Baseline: `release/0.28.0` at `d06bffb` (local package/install) and `main` at
`b21b204`. The 0.28 candidate is **not** a superset of current `main`: see
“0.28 baseline gap” below.

## Scope and method

- Reviewed the 11 GitLab merge requests created on 2026-10-31, oldest first.
- A head is “in 0.28” only when `git merge-base --is-ancestor <head>
  release/0.28.0` succeeds. “Merged” registry records are reported separately
  from ancestry; no hosted CI is claimed.
- The local PR registry has 83 GitHub records (23
  merged, 11 closed, 49
  open). They are historical evidence, not GitLab review objects; this review
  does not close GitHub records.
- No source code was changed by this consolidation. Branches are retained.

## Disposition, oldest to newest

| MR | Created | Title | Head | Target | Diff | In 0.28 | Disposition |
|---|---|---|---|---|---|---|---|
| !1 | 22:06 | Add source-backed macOS ARM64 investigation | `bbcb67d` | main | 19 files, +1,927/-35 | yes | closed — landed in 0.28 |
| !2 | 22:07 | Report analysis capabilities and app replication boundaries | `2d6f460` | !1 | 10 files, +534/-5 | yes | closed — landed in 0.28 |
| !3 | 22:26 | 0.28.0 release candidate | `d06bffb` | main | release integration | n/a | kept open — release candidate |
| !4 | 22:28 | Preserve PR 56 console modules and full Miniplanets NES port | `b95c1e8` | main | 149 files, +36,509/-10 | no | closed — specs collated here |
| !5 | 22:29 | Remove Miniplanets rendering cap and optimize exact globe reuse | `b6fc1f1` | !4 | 36 files, +4,351/-276 | no | closed — specs collated here |
| !6 | 22:30 | Normal KQ1 goat play and reusable Z scene | `9d2c5cf` | pr/82 | 17 files, +1,908/-3 | no | closed — specs collated here |
| !7 | 22:34 | Add reversible macOS sessions and display-bound capture | `e1b6f16` | !2 | 17 files, +1,869/-4 | no | closed — specs collated here |
| !8 | 22:53 | Qualify ordinary KQ1 troll bridge and extend the Z scene | `08daea5` | !6 | 13 files, +1,751/-28 | no | closed — specs collated here |
| !9 | 23:07 | Add cpuinfo replica and fDisBull native comparison | `2375c54` | !7 | 23 files, +1,871 | no | closed — specs collated here |
| !10 | 23:22 | Deduplicate feature CI and bound agent status polling | `eaaf9ca` | main | 7 files, +745/-12 | yes | merged in main via b21b204 |
| !11 | 23:23 | Cortex-M/Thumb static firmware analysis (PR #74 continuation) | `a8a6469` | main | 17 files, +918/-23 | no | closed — specs collated here |

## 0.28 baseline gap (release blocker)

`release/0.28.0` (`d06bffb`) was cut before `main` gained:

- `36c2e79` Z world language and Zork I room/exit map
- `1ef16ba` Civilization I world snapshot and read-only Z provider
- `acd6af4` / `4cab95b` integrations of those examples
- `b21b204` CI trigger/polling merge (the CI code itself is already in 0.28)

As a result, `release/0.28.0` currently deletes the Civ/Z world docs and
examples relative to `main`. This is the same class of stale-merge defect fixed
in `d06bffb`; it must be repaired before MR !3 is merged. Required action:

1. Merge current `main` into `release/0.28.0` and resolve package/CLI registries.
2. Re-run the full suite and refresh `docs/RELEASE-0.28.0.md`.
3. Rebuild local wheel/player/tool ZIP, `check_dist`, and reinstall the shared
   prefix (standing rule: every packaging run gets a system install).
4. Only then decide the tag. Linux CI and native rebuild remain open gates.

The 0.28 release is local-only: no tag, no package upload, no publication.

## Landed in 0.28

### !1 — macOS ARM64 investigation (merged)

Landed at `bbcb67d` (19 files): exact ARM64 slice/instruction backings,
source-bound `ghidra-arm64` instruction/C diagnostics and one-shot
`macos-observe` LLDB. **Still open:** app-level UIL export, automatic
SwiftUI-to-UI recovery, persistent debugger/attach, and whole-app equivalence.
Ghidra comparison is bounded to a 4 KiB entry window and is not semantic
translation.

### !2 — capabilities and replication boundaries (merged)

Spec: [docs/CAPABILITIES.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/2d6f46039d907ebc6bbe801183b08a8215a535e0/docs/CAPABILITIES.md) and [docs/MACOS_APP_REPLICATION.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/2d6f46039d907ebc6bbe801183b08a8215a535e0/docs/MACOS_APP_REPLICATION.md).

Landed at `2d6f460` (10 files): projectless `capabilities`, 19-entry catalog,
dependency discovery without execution, and the app-replication case study.
**Still open:** the documented priorities themselves — reversible sessions,
display-aware capture, differential behavior recording, Swift navigation,
persistent C/source maps, preference/resource handling and typed UIL host
effects. !7 and !9 are the first implementations.

### !10 — CI coordination (merged)

Spec: [docs/CI_COORDINATION.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/eaaf9ca2dec90e1020fe29ba9d6a802b0d99d288/docs/CI_COORDINATION.md).

Landed at `eaaf9ca` (7 files) and now in `main` via `b21b204`: bounded status
reads, duplicate-feature-CI avoidance, script/tests/docs. **Still open:** the
GitLab project has no CI configuration; the hosted ordinary/native lanes have
not run for 0.28.

## Unmerged reviews and gap analysis
### !4 — Preserve PR 56 console modules and full Miniplanets NES port

- Head: `b95c1e8`; target: `main`; diff: 149 files, +36,509/-10.  
- Specs at head: [docs/CONSOLE_MEDIA_PARSING.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/b95c1e880a63f7c1899b182de90988920189e47c/docs/CONSOLE_MEDIA_PARSING.md), [docs/CONSOLE_UDC.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/b95c1e880a63f7c1899b182de90988920189e47c/docs/CONSOLE_UDC.md), [docs/CUE_ISO_PARSING.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/b95c1e880a63f7c1899b182de90988920189e47c/docs/CUE_ISO_PARSING.md), [docs/GENESIS_ROM_TO_NES.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/b95c1e880a63f7c1899b182de90988920189e47c/docs/GENESIS_ROM_TO_NES.md), [docs/MINIPLANETS_FULL_GAME.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/b95c1e880a63f7c1899b182de90988920189e47c/docs/MINIPLANETS_FULL_GAME.md), [docs/MINIPLANETS_NES_LEVEL.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/b95c1e880a63f7c1899b182de90988920189e47c/docs/MINIPLANETS_NES_LEVEL.md).  
- Merge state: conflicts in `scripts/check_dist.py`, `src/fdisbull/cli.py`, `tests/test_distribution.py`; 149 files is the largest unmerged stack.  
- 0.28 gap: console/media parsing, SH-2 ROM-to-ASM and the full Miniplanets game are absent.  
- 0.29 decision: split console/media modules from the game; rebase the modules first. The full game remains experimental and private-ROM/toolchain-gated.  

<details><summary>Original review description (verbatim)</summary>

> Preserve the source-backed review previously tracked as GitHub PR #56 in the private GitLab project. This draft uses the existing imported branch at `b95c1e880a63f7c1899b182de90988920189e47c`; it does not rewrite that historical head or claim fresh CI for it.
>
> The branch adds bounded NES/SNES/Sega and CUE/BIN/ISO parsing, interchangeable SH-2 ROM-to-ASM modules, and an experimental full Miniplanets NES implementation through the reviewed procedural UIL profile. The game covers all 55 stages, 479 initial actors, score, lives, timer, game flow, globe-style presentation and an NES arrangement of the soundtrack. Original ROM/assets and generated cartridges remain private external inputs.
>
> Retained qualification at this head includes 2,678 original-Genesis common cases, 1,262 actor cases and 4,822 native NES complete-state cases. Normal runtime, audio timing and the earlier mapper-race fix have separate bounded receipts. These results are historical at this exact source, not GitLab pipeline results. Whole-game formal equivalence, automatic arbitrary-ROM conversion, physical NES operation and natural completion of all levels remain unqualified.
>
> The newer Miniplanets performance/display update is reviewed separately as a stacked draft targeting this branch. It contains the latest tested executable, the previous hot-path optimization and the bounded dirty-upload work, keeping the incremental diff reviewable.
>
> This preserved branch predates the current main integration. Integration readiness is separate from this stacked review; no integration merge, release or global installation is requested here.
>
> [Contracts and retained methodology](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/b95c1e880a63f7c1899b182de90988920189e47c/docs/MINIPLANETS_FULL_GAME.md).
>
> The latest qualified update is [the stacked uncapped-rendering/performance draft !5](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/5) at `b6fc1f17cbe1b1dfcf5705fd724ee0446ec7b872`. It removes the two-epoch render cap, reaches 32.24 coherent swaps/s in the seeded orb workload, and retains the Genesis/native accuracy gates; movement performance and remaining limits are reported separately.

</details>

### !5 — Remove Miniplanets rendering cap and optimize exact globe reuse

- Head: `b6fc1f1`; target: `!4`; diff: 36 files, +4,351/-276.  
- Specs at head: [docs/MINIPLANETS_FULL_GAME.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/b6fc1f17cbe1b1dfcf5705fd724ee0446ec7b872/docs/MINIPLANETS_FULL_GAME.md) (uncapped rendering section) and `docs/evidence/miniplanets-full-game-2026-10-31/`.  
- 0.28 gap: no uncapped rendering, terrain reuse or audio hot-path changes.  
- 0.29 decision: only after !4; retain the measured 32.24 swaps/s but do not claim 60 Hz or movement parity.  

<details><summary>Original review description (verbatim)</summary>

> The NES main loop now attempts a new globe view after every completed game update whenever the previous upload is consumed. The two-epoch rendering gate is removed. Exact terrain reuse, conservative upload-plan certificates and audio hot-path changes recover CPU time while preserving the existing state and coherent-display contracts. The seeded orb workload reaches **32.24 completed swaps/s**, exceeding the former 30 fps rendering ceiling. The build remains below 60 Hz.
>
> This draft is stacked on [preserved PR56 / !4](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/4), targeting its unchanged source branch. It includes the earlier native/display optimizations and this uncapped follow-up.
>
> Source head: `b6fc1f17cbe1b1dfcf5705fd724ee0446ec7b872`. Tested cartridge: `8da56a19cf65be2aae46a913584d72776df0da6819d9784ec577e3ca75c012e6`. Source cartridge and procedural UIL program hashes are unchanged.
>
> | Workload | Previous game updates/s | New game updates/s | Previous completed swaps/s | New completed swaps/s |
> |---|---:|---:|---:|---:|
> | Stage 0 | 41.18 | 49.06 | 20.60 | 29.76 |
> | Stage 40, eight maces | 27.60 | 29.02 | 13.79 | 28.40 |
> | Stage 43, orbs | 33.33 | 41.06 | 16.67 | 32.24 |
> | Stage 44, dense fireballs | 25.87 | 28.10 | 12.95 | 26.29 |
>
> The comparison uses the previous qualified commit `f34f6ef06f8a9e708073d095499205345d3950a6`, the same source-initialized assisted stage seeds, invulnerability and neutral controllers. Each pinned-core run has 3,100 physical frames, 100 warmup frames and 2,999 measured emulated hardware-frame intervals. The observer is checked against byte-neutral control replay. Host execution throughput is excluded. Completed swaps mean coherent buffers, not necessarily changed pixels.
>
> A separate 3,000-frame movement run with active audio reaches **43.54 game updates/s and 15.42 completed swaps/s**. It checks 104,044 PPU data writes and 744 coherent flips. Static-camera cache performance should not be read as movement performance.
>
> Implementation and methodology:
> - Terrain reuse requires the complete world/camera and conservative animation-mask key to match. Delay capture during movement; restore the whole cached plane after invalidation, or only the pause row when staging still owns the exact terrain. Animation masks pass 21,504 atlas frame-pair comparisons, with a deliberately wrong mask detected.
> - Per-nametable terrain certificates bypass redundant terrain scans only for a proven cache hit and identical overlay. Terrain misses invalidate both certificates, nonterrain views clear the target, debug uploads invalidate staging, and HUD bytes are always compared. An isolated unchanged-path planner comparison falls from approximately 6,072 to 646 cycles per call; this excludes IRQ/mapper/PPU work.
> - Audio skips no-op envelope phases, specializes volume work and combines selection scans. The original 512-state corpus falls from 6,763.47 to 6,254.47 mean cycles (7.53%). The separately reported expanded corpus improves 10.94%; all 32,768 PSG level/attenuation pairs match.
> - Immutable pending plans, inactive-table writes and the same safe NMI deadline remain enforced. Full-dirty 296-byte uploads still require four data frames. Audio profiles still consume about 40–45% of native CPU time.
>
> Fresh qualification:
> - Original Genesis: **2,678 common cases + 1,262 actor cases**, 439,775 actual instructions, 192 observed HV samples, both actor variants equal. The separate 6,044-frame full-flow run is assisted UIL execution.
> - Final native cartridge: **4,822 complete-state cases / 79 fields**, **11,599 completed state/controller checks**, 280 replayed HV words and 33,282 projection pairs.
> - Rendering: two distinct 65,536-case cache protocols, 40,960 terrain cases, 2,236 planner calls and negative invalidation/certificate controls. In 229 shared complete game states, plane/palette/attributes/projection cache/OAM count/selected OAM match the previous cartridge.
> - Display: **5,823 coherent seeded flips**, plus the 744-flip movement run; no observed late PPU writes, active-table writes, content mismatches, runtime faults or sampled stack wrap. Eight synthetic upload cases cover six full-dirty and two OAM-only commits.
> - Sound: 32 tracks plus mixed workload, **270,752 services / 1,161 commands / 2,579,855 matching ordered APU writes**; all five unchanged strict tempo-v2 windows pass. The first feedback capture was correctly rejected for having only 3,077 rows; a fresh capture adds 24 neutral tail frames to meet the unchanged 3,101-row observation rule. Its complete original prefix matches, and the rejected observation is retained.
> - **344 affected tests pass**, including the prepared native toolchain and private-ROM asset checks. Full Mac suite: **2,771 passed, 142 skipped, 3 failed, 23 setup errors**, with the same 26 platform-fixture failure/error identifiers as the prior baseline; the full suite is not green.
> - Four tool-only archives pass guards. **791 frozen source files and 224 installed resources match**. Wheels built from a freshly extracted sdist reproduce the exact tested cartridge in a fresh private install; baseline/mixed variants compile and match all 55 stage loads and 55 first frames.
>
> The feedback route reaches the goal at epoch 896 / host frame 1,194 and the next stage at epoch 1,146 / host frame 1,576, followed by its neutral tail. The fixed host-timed route remains a DNF. These are finite source-bound comparisons, not whole-game formal equivalence, natural completion of all levels, generic ROM translation, Genesis pixel/FM waveform identity or physical NES qualification.
>
> [Detailed methodology](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/b6fc1f17cbe1b1dfcf5705fd724ee0446ec7b872/docs/MINIPLANETS_FULL_GAME.md#uncapped-rendering-exact-terrain-reuse-and-audio-optimization-2026-10-31) · [Sanitized uncapped receipt](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/b6fc1f17cbe1b1dfcf5705fd724ee0446ec7b872/docs/evidence/miniplanets-full-game-2026-10-31/uncapped-rendering.json)
>
> The local PR56 follow-up record and this GitLab draft use the same source head and review text. Original ROM/assets, generated cartridges, raw states/audio/captures and native cores remain private and excluded from GitLab and tool packages. Verification is local; no hosted CI or release certification is claimed. No integration merge, tag, package publication or system installation is performed.

</details>

### !6 — Normal KQ1 goat play and reusable Z scene

- Head: `9d2c5cf`; target: `pr/82`; diff: 17 files, +1,908/-3.  
- Specs at head: [docs/AGI_NATURAL_GOAT.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/9d2c5cff0a76dd7e3e732701c2fdd2e581d5fb82/docs/AGI_NATURAL_GOAT.md), [docs/AGI_DOS_HOST.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/9d2c5cff0a76dd7e3e732701c2fdd2e581d5fb82/docs/AGI_DOS_HOST.md), [docs/AGI_Z_SCENES.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/9d2c5cff0a76dd7e3e732701c2fdd2e581d5fb82/docs/AGI_Z_SCENES.md).  
- Merge state: stacked on unmerged `pr/82/agi-logic103-qualification` (`33ad1a9`); the parent cannot merge alone.  
- 0.28 gap: no AGI/KQ1 goat scene, print-occurrence or native-view work.  
- 0.29 decision: rebase PR #82 first, then the !6/!8 stack; !8 carries the three parent P2 fixes.  

<details><summary>Original review description (verbatim)</summary>

> Add bounded ordinary-play evidence for the KQ1 goat and export a reusable source-backed Z scene. This draft is stacked on `pr/82/agi-logic103-qualification` at exact parent `33ad1a9fc2512b1ade9973bf7bffb2e4e0f17d1b`.
>
> The retained fresh native run lures the goat and leaves the pen through ordinary play, with score changing from 2 to 7. The projected logic 103 path matches 18 actual source operations. Native VIEW mirror-cache validation is included, and a separate installed 0.27 player consumed the generated scene.
>
> Source head: `9d2c5cff0a76dd7e3e732701c2fdd2e581d5fb82`. Archived local verification at this exact head: **514 passed, 2 skipped**. These are retained local results, not GitLab CI acceptance. No GitLab CI configuration or pipeline is currently validated for this draft.
>
> Read-only review found three P2 issues: stale print-occurrence selection, propagated route-budget handling, and an unknown-entry search attempt. Their fixes are being prepared in a stacked troll follow-up. **Do not merge this parent draft without that follow-up.**
>
> Original game files, saved states, byte-retaining databases, raw private source and generated private scene content are excluded. This draft does not claim whole-game recovery or release readiness. Keep it unmerged; no integration merge, installation, pipeline activation or release is requested.

</details>

### !7 — Add reversible macOS sessions and display-bound capture

- Head: `e1b6f16`; target: `!2`; diff: 17 files, +1,869/-4.  
- Specs at head: [docs/MACOS_REVERSIBLE_CAPTURE.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/e1b6f164bdc139262d340395b203246c948d01bd/docs/MACOS_REVERSIBLE_CAPTURE.md).  
- 0.28 gap: no `macos-snapshot`, `macos-session`, recovery journal, display-bound capture or Swift helper.  
- 0.29 decision: strongest small candidate. Land with mixed-scale/rotated-display limits explicit; no general GUI recorder.  

<details><summary>Original review description (verbatim)</summary>

> App investigation previously depended on manual screenshots and unjournaled
> UI changes. A language test could leave an absent preference overridden, and
> using image-local coordinates as global screen coordinates could target a
> different monitor. Add an explicit native observation/session path with
> owned-change restoration and inspectable capture coordinates.
>
> `macos-snapshot` reads current app identity, permissions without prompting,
> display UUID/bounds/pixels/scales, target windows and bounded accessibility
> state. `macos-session` records a private durable journal, optionally performs
> one explicitly authorized status-menu action and declared preference changes,
> captures a selected display region, then restores only its owned changes.
> `macos-session-recover` reinspects an interrupted journal before restoration.
>
> The shipped Swift helper uses ScreenCaptureKit and CoreGraphics global logical
> coordinates, including negative origins, with display-local conversion and
> explicit pixel dimensions. Menu actions bind bundle/PID/launch date. An
> AXPress error can occur after opening a menu, so delivery and observed effects
> are recorded separately and the input is not replayed. Closure uses menu
> AXCancel or one Escape pair directed to the exact PID, followed by observation.
>
> Preferences retain exact key presence and typed plist values. Absence restores
> by deletion. External changes become conflicts; stale process identity and
> unknown menu state refuse mutation. Locks cover cooperating controllers;
> exceptions and handled termination enter cleanup, while SIGKILL/power loss
> require explicit recovery. No watcher, automatic app launch/quit, privacy
> setting change, general GUI recorder or UIL host binding is introduced.
>
> Local head: `e1b6f164bdc139262d340395b203246c948d01bd`.
> Stack base: `2d6f46039d907ebc6bbe801183b08a8215a535e0`, the capability-report
> draft mirrored as GitLab !2. Review ref: `pr-local/macos-reversible-capture`.
> This is an unmerged source draft, not a release or active installation.
>
> Verification:
>
> - **116 focused checks passed**, including faults, typed/absent preferences,
>   stale identity, conflicting controllers, external menu ownership, and real
>   authored child-process SIGTERM/SIGKILL/recovery tests.
> - Full `python -m pytest -q`: **2394 passed, 123 skipped, 3 failed, 23 errors**.
>   The failure/error test set exactly matches the retained exact-base receipt
>   (**2358 passed, 123 skipped, 3 failed, 23 errors**). Those fixtures depend on
>   Linux ELF/linker behavior or case-sensitive filesystem behavior unavailable
>   on this Mac. These are local results, not GitLab CI or release acceptance.
> - Explicit native acceptance passed on macOS 27.2 arm64 with **two physical
>   displays**. The authored menu was captured on the negative-X display;
>   both displays' global/local rectangles and PNG dimensions were verified.
>   AXPress returned `-25204` while open was observed; AXCancel returned success
>   and closed was observed. A temporary Japanese string key returned to exact
>   absence. The exact authored fixture process was stopped afterward.
> - Native source SHA-256:
>   `3b1f00b90785c96cdf1afef3bd235cf92d45ce9573e462677c7bf4cc5428a8c5`.
> - Source ZIP **659** entries and wheel **188** entries pass package gates.
>   Swift source and the explicit native acceptance driver/fixture are required
>   source resources; compiled helpers and captures are not packaged.
> - Independent review caught and repaired null rectangle handling, index bounds,
>   malformed recovery flags, unbounded journal reads and uncertain AX delivery.
>   Final review found no remaining material issue in the tested scope.
>
> Limits: native live acceptance used an authored fixture; it does not qualify
> arbitrary originals. Both connected screens are 1x; physical mixed-scale and
> rotated display setups remain untested. Preference-domain sandbox coverage,
> cached UI refresh, atomic exclusion of manual/external actions, and restoration
> of undeclared app/OS effects remain unresolved. Original-app/replica comparison
> is a separate downstream experiment using this implementation.
>
> The GitLab test connector found the existing native and capability commits
> already mirrored exactly, but no merge requests. Their draft reviews are now
> GitLab !1 and !2. This draft's source is transported with ordinary Git to
> preserve the authored commit object; the connector creates and verifies the
> review object. Historical GitHub discussions/CI are not GitLab evidence.
> Two unrelated newer local branches remain outside this chat's publication.
>
> Original binaries, resources, byte-retaining databases, preference journals and
> screenshots stay private. Only authored source, sanitized receipts and hashes
> are included in the review evidence. Simple Menu Status Replica was not reopened
> or changed by this work.
>
> The final follow-up converts an unresolvable output-home path into a controlled refusal before native actions. Its regression check and final full suite pass with the same host failure set; the tested native helper source is unchanged.

</details>

### !8 — Qualify ordinary KQ1 troll bridge and extend the Z scene

- Head: `08daea5`; target: `!6`; diff: 13 files, +1,751/-28.  
- Specs at head: [docs/AGI_TROLL_BRIDGE.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/08daea56e9754f38f56f028659e9fce8d0394f4e/docs/AGI_TROLL_BRIDGE.md), [docs/AGI_Z_SCENES.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/08daea56e9754f38f56f028659e9fce8d0394f4e/docs/AGI_Z_SCENES.md).  
- Merge state: stacked on !6; includes the three review-fix commit `1eb7b09` and troll-route evidence.  
- 0.28 gap: troll bridge route and the corrected print/budget/entry-search behavior are absent.  
- 0.29 decision: same stack as !6; no standalone merge.  

<details><summary>Original review description (verbatim)</summary>

> Extend the fresh KQ1 goat route through the troll bridge and retain the observed outcome as a third guarded action in the reusable Z scene. This draft is stacked on [!6](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/6), targeting `codex/kq1-natural-goat-scene` at exact base `9d2c5cff0a76dd7e3e732701c2fdd2e581d5fb82`.
>
> The stack includes review-fix commit `1eb7b09d8d058308647782df6b31df835a36dfb1` and troll-route commit `08daea56e9754f38f56f028659e9fce8d0394f4e`. It closes the parent's three P2 findings: retaining and revalidating the admitted print occurrence, propagating the remaining route guest and wall budgets, and journaling entry-search dispatch before a potentially unknown transport result. Movement is retried only after a newly completed observed dialogue explains a consumed stop key, with four attempts maximum.
>
> Two fresh native physical-input runs completed. The final run crossed the bridge to room 25 at (34, 44), with water false, score 7 -> 11, the carried carrot retained, following false, troll removed and troll unpaid. The original logic-25 score addition at `0x01b8` is bound to native writer `0x72da`, resume `0x72de`, BX = 3 and AL = 4. A separate 32-fetch trace records bounded continuation; it does not certify completion of every fetched instruction. The final native run's implementation hashes match the published source, and original source/copy hashes remained unchanged. The first attempt's movement-settling failure remains recorded in the receipt.
>
> The exporter requires contiguous observations, exact completed source-message occurrences, explicit frame visibility and matching supplied score-write/trace hashes. The installed 0.27.0 player passed both in-process and separate content-process checks for `use carrot on goat`, `use route`, and `use bridge`, the typed final state, stale/repeated-command refusal, in-memory checkpoint restore and token invalidation.
>
> Local verification at this source: **384 passed, 4 skipped** using `python -m pytest -q tests/test_agi*.py tests/test_il_scenes.py tests/test_text_player.py tests/test_player_checkpoints.py tests/test_player_live.py`. The diff check and staged privacy audit of 11 files passed. Packaging checks were not run; there is no packaging change. These are local results, not GitLab CI acceptance. No GitLab head pipeline is validated for this draft.
>
> Committed sanitized evidence: [receipt.json](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/08daea56e9754f38f56f028659e9fce8d0394f4e/docs/evidence/agi-troll-bridge-2026-10-31/receipt.json), SHA-256 `3b061fc6d94d84b6876f14a0a2d68e49876abc1331085a7d14fbb746edf3de29`. It binds the native attempts, source/runtime identities, score write, selected frames, generated scene/provenance and player/check logs.
>
> Original game files, saved states, byte-retaining databases, raw private source/captures/traces and generated private scene content are excluded. Hashes establish byte identity; the exporter validates supplied evidence rather than authenticating an execution chain. This is the selected route in the supplied AGI 2.917 edition and a partial authored scene projection, with no whole-game recovery, autonomous scene timing or durable-save claim. Keep this draft unmerged. No integration merge, installation, pipeline activation, tag or release is included.

</details>

### !9 — Add cpuinfo replica and fDisBull native comparison

- Head: `2375c54`; target: `!7`; diff: 23 files, +1,871.  
- Specs at head: [docs/CPUINFO_REPLICATION_COMPARISON.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/2375c54550a01f48ab1ef2271ccd65eecc4e5a99/docs/CPUINFO_REPLICATION_COMPARISON.md).  
- Merge state: stacked on !7; experimental app under `experimental/macos/cpuinfo-replica`.  
- 0.28 gap: no cpuinfo replica or native comparison receipt.  
- 0.29 decision: after !7 as an experiment; keep the 311 pending code items and unqualified login/localization/restart behavior visible.  

<details><summary>Original review description (verbatim)</summary>

> Build a separately identified native AppKit replica of the installed cpuinfo
> 1.7.0 bars app, then use the new fDisBull session/capture path to compare its
> observed default English UI. Retain a frozen authored source snapshot under
> `experimental/macos/cpuinfo-replica` and a calibrated comparison report.
>
> The app implements per-core bars, overall image/text modes, Default/B/W themes,
> the source-assisted interval/menu controls and its own preferences. Its separate
> identifier keeps settings and login registration independent of the original.
> Modern login registration and Activity Monitor actions are implemented but
> were not exercised by the comparison.
>
> fDisBull reopened the original's private FDB, revalidated 13 entry instruction
> backings and retained Mach CPU API import evidence. That capsule remains
> incomplete, with 311 stored code items pending. Most rendering/menu semantics
> come from the public v1.7.0 source, pinned to
> `d7f9e846909f9775e1d6d03214796dbaff4d5492`, and native observations. This is
> source-assisted reconstruction, not automatic binary-to-UIL recovery.
>
> The original was captured on the main display and the replica on the negative-X
> display. Both test-opened menus were confirmed closed afterward. The original
> kept its process identity; only the coordinator-owned replica was stopped.
> The read-only packet comparator verifies:
>
> - Seven visible root-menu labels, order, enabled states and normalized frames.
> - Both root menus at 218×200 points, with 24-point non-separator rows.
> - Ten 3-pixel colored bar groups with 2-pixel gaps and matching relative starts/baseline in these 1x captures.
> - Display identity, global/local conversion, PNG dimensions, menu coverage and cleanup receipts.
> - A deliberately wrong menu-label mutant is detected.
>
> The app's **24 core checks and 26 renderer/native checks** passed, including
> authored 1x/2x/3x pixel geometry. Root independently rebuilt/tested the imported
> snapshot, verified all source hashes, and reproduced the sanitized comparison.
> Production app sources are unchanged from the actual observed app. No GUI was
> started by the source snapshot build or headless checks.
>
> Head: `2375c54550a01f48ab1ef2271ccd65eecc4e5a99`.
> Tree: `73dc89b68d62063f56107e95c4fb5c3e0d63bcf5`.
> Base: `e1b6f164bdc139262d340395b203246c948d01bd`, the reversible-capture draft
> GitLab !7. Source branch: `pr-local/cpuinfo-replica-comparison`.
> Canonical standalone app source: `718136e9c918e124703219891b5450a600ecd814`.
> Live capture tool source: `ecbe4c577bcd57d7224a5594a8475dda4c412d10`; the final
> parent follow-up only changes invalid output-path refusal, with the same native
> helper source. This is an unmerged experiment, not a release or installation.
>
> Keep the boundaries visible: CPU fills came from different sampling times;
> fonts/full pixels/synchronized counters are not qualified. The original's
> Start at Login is checked while the replica is unregistered, as expected for
> independent apps. First/reset/topology readings intentionally start unknown,
> unlike upstream's initial-zero/since-boot first sample. Japanese localization,
> login-helper equivalence, hidden-submenu actions and restart persistence remain
> unqualified. No original bug was causally diagnosed or patched.
>
> The workflow comparison is not a speed benchmark: these are unequal targets,
> cpuinfo has public source, and prior work informed the attempt. The tool adds
> reliable coordinate/state evidence and restoration; it does not recover the
> app's Swift intent automatically.
>
> Only authored source, notices, sanitized labels/relative geometry and hashes
> are committed. Original binaries/resources, raw instruction bytes, FDBs,
> screenshots, raw AX trees, preference journals and compiled apps are excluded.
> The experiment directory is excluded from normal tool packages. No GitLab CI,
> whole-app parity or installation claim is made.
>
> The bundled investigation skill now includes the reversible native comparison workflow. Its discovery/skill/distribution checks pass (93 tests); the parent tool PR retains its separately recorded full-suite result.

</details>

### !11 — Cortex-M/Thumb static firmware analysis (PR #74 continuation)

- Head: `a8a6469`; target: `main`; diff: 17 files, +918/-23.  
- Specs at head: [docs/CORTEX_M.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/a8a6469e80bef6d448d58b72e98b593c1cb2b952/docs/CORTEX_M.md), [docs/PLATFORMS.md](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/a8a6469e80bef6d448d58b72e98b593c1cb2b952/docs/PLATFORMS.md).  
- Merge state: independent of the current release; schema-9 store is compatible with 0.28 (`SCHEMA = 9`); no merge conflicts reported.  
- 0.28 gap: no Cortex-M/Thumb decoder, vector loader, CFG/annotation path or 121GW acceptance.  
- 0.29 decision: strong independent candidate; rebase, rerun focused/real-firmware checks, and keep Armv8-M/AAPCS32 out of scope.  

<details><summary>Original review description (verbatim)</summary>

> Adds the first Cortex-M/Thumb static analysis milestone for an explicitly declared little-endian Armv7-M vector layout. Import a flat flash image with a caller-selected base/vector count, traverse reset and interrupt candidates, retain immutable analysis versions, and reopen/query/render stored state. Native Capstone supplies instruction facts; fDisBull owns traversal, references, annotations and persistence.
>
> This is the GitLab continuation of **unmerged GitHub PR #74**, imported from the local PR registry without contacting GitHub. Source branch `pr/74/cortex-m-thumb` is current at **`a8a6469e80bef6d448d58b72e98b593c1cb2b952`**. Target is GitLab `main`; this MR remains **draft and unmerged**.
>
> ## Behavior and reviewed fixes
>
> - Validate vector/SP/reset metadata, preserve raw Thumb tags, discover reset first, and retain invalid/reserved interrupt evidence.
> - Decode mixed 16/32-bit Thumb, PC-relative literals and IT context. Preserve conditional fallthrough and unknown indirect/exception-return destinations.
> - Rebuild vector metadata and entry/function seeds independently for each patched version.
> - Protect referenced LDRD/VLDR literal-pool spans with the correct transfer widths; retain VSTR memory writes with unknown register-derived destinations.
> - Recover aligned PC references from wide ADDW/SUBW ADR aliases, including 32-bit wrap.
> - Integrate the schema-9 private object store and preserve exact source restoration for parent and reset-vector children. An explicit validated import entry cannot become a stale child override.
> - Declare Armv7-M profile assumptions. Armv8-M Security/SecureFault layouts remain outside this milestone.
>
> Nine pre-integration regression cases were demonstrated failing before the earlier repairs. The existing implementation, qualification outputs and unrelated checkout remain preserved.
>
> ## Recorded real-firmware qualification
>
> The retained source-head receipt covers 121GW 2.05: **144,616 bytes**, SHA-256 `8f885f12f567c2cccd9862d9fe26f127e2a674c9afbce9f7a38d441b3f396722`. Declared base `0x08006000`, 73 vectors, reset `0x08029174`.
>
> A fresh schema-9 import passed **23 acceptance operations**, including a non-stable budget stop, fixed-point discovery, fresh-process restart after moving the input copy, persistent annotations, isolated NOP and reset-vector children, unchanged parent bytes, and real stored-state PNG/SVG/CFG files. The PNG is 1560×1024. The original analysis retains 2,274 instructions, 102 function candidates, 3,053 references and 56 visible issues.
>
> This is bounded static discovery. Device state and indirect behavior remain unknown; no firmware execution, hardware flashing, complete recovery or derived AAPCS32 semantics is claimed. Firmware, databases, companion objects, raw listings and images remain private outside Git.
>
> ## Retained validation at a8a6469
>
> These results are imported from the prior local receipt; the real firmware was not rerun as part of the separate CI-trigger review.
>
> - Focused Cortex-M/storage/loading/CFG/render/memory checks: **192 passed, 2 deselected**.
> - Prior full macOS run: **2,355 passed, 122 skipped, 3 failed, 23 errors**. Twenty-five nonpassing cases require Linux ELF/compiler fixtures. One unchanged fixture requires distinct `VOL.2` and `vol.2` files, unavailable on the case-insensitive Mac volume.
> - Real 121GW acceptance: **23 operations passed**, covering restart, patch isolation and stored-state image exports.
> - Wheel/sdist content checks passed; a separate clean installed-wheel environment checked the Thumb fixes, real-image analysis, exact reset-child source candidacy and metadata/annotation/PNG readback with the byte store absent.
> - Earlier hosted successes on `ba5e428` are historical and do not qualify `a8a6469`.
>
> ## Current coordination
>
> Linux/hosted CI is explicitly deferred by the user while the local GitLab workflow is established. No GitLab pipeline was started or configured, and GitHub was not accessed for this update. Keep this MR draft and unmerged. No tags or releases are authorized.
>
> The separate CI trigger/polling fix is tracked in !10. Its local integration does not merge this Cortex-M branch.

</details>

## Proposed 0.29 slate

Recommended theme: **finish investigation depth before adding another game
runtime**. Start from a refreshed 0.28 release branch; every candidate must be
rebased and re-qualified, not merged from its historical base.

| Priority | Candidate | Size | Why | Prerequisites / risk |
|---|---|---|---|---|
| P0 | Refresh 0.28 with current `main`, Linux CI/native gates, tag decision | release | Prevents the current Civ/Z world revert; publication cannot proceed | No GitLab CI; native backends inherited; full suite has 3F/23E macOS environment limits |
| P1 | !7 reversible macOS sessions/capture | 17 files, +1.9k | Completes the !1/!2 app-investigation path with owned-change restoration | Mixed-scale/rotated displays, sandbox, cached UI and manual-action atomicity untested |
| P1 | !11 Cortex-M/Thumb | 17 files, +918 | Independent architecture milestone with real 121GW acceptance and schema-9 store | Armv8-M Security/SecureFault, AAPCS32 semantics and device state out of scope |
| P2 | PR #82 + !6 + !8 KQ1 AGI stack | 70 + 17 + 13 files | Reuses the strongest original-observation evidence; closes the parent P2s | PR #82 is unmerged; no packaging checks in !6; parent must not merge alone |
| P2 | !9 cpuinfo replica/comparison | 23 files, +1.9k | Exercises !7 on a real AppKit comparison; calibrated menu/geometry evidence | Experimental; 311 stored code items pending; login/localization/restart unqualified |
| P3 | PR #56 modules + !4 + !5 Miniplanets | 149 + 36 files | Console/media parsing is broadly useful; full game is experimental | Conflicts in three registry files; private ROM/cc65; whole-game and physical NES unqualified; 60 Hz not reached |
| P3 | PR #79 first-party console synthesis | revision in progress | Custom synthesis path after console modules | Checked only against 0.26 runtime; no full suite; do not start before PR #56 base is reconciled |
| Deferred | App-level UIL export, persistent macOS debugger, differential recorder | research | !1/!2 explicitly leave these unimplemented | No bounded contract yet; keep as research, not 0.29 scope |
| Deferred | PR #38/#39/#42/#49/#50/#54/#57 UIL/UDC stack and PR #61–#66 | large | Older cross-cutting stack; runtime fixes depend on it | Requires a separate theme decision; do not cherry-pick isolated fixes without the stack |

Operational items for 0.29:

- Add GitLab CI or run the existing GitHub ordinary/native workflows on the
  final SHA. The 0.28 local suite is not Linux acceptance.
- Keep package gates (`check_dist`) aligned with the resources actually shipped.
  PR #64/#65/#66 target resources from the deferred stack; only port them when
  those resources land.
- PR #77 (manual PyPI licensing/publication) remains blocked on license readiness;
  do not publish from this workspace.

## Started but never completed

| Task | Where it stopped | Evidence / limit | Next action |
|---|---|---|---|
| 0.28 publication | Local install `0.28.0-d06bffb`; no tag/upload | Linux CI absent; release branch now behind `main`; 3F/23E macOS environment failures | Refresh release, run Linux/native gates, rebuild/install, then tag |
| App-level UIL export / automatic SwiftUI recovery | !1 description; !2 case study | “does not implement automatic SwiftUI/app-to-UIL recovery”; no persistent debugger/attach | Keep research-only; define a bounded contract before code |
| Differential behavior recording / Swift navigation / C maps / preference-resource effects | !2 priorities | Listed as downstream priorities, not implemented | Fold into !7/!9 follow-ups with explicit receipts |
| Reversible macOS capture limits | !7 | Mixed-scale/rotated displays, preference sandbox, cached UI refresh, manual/external action exclusion, undeclared effects | Qualify or document each; do not widen to a general GUI recorder |
| cpuinfo reproduction | !9 | 311 stored code items pending; login helper, hidden submenu, Japanese, restart persistence unqualified | Finish or mark the capsule permanently partial; keep replica/source provenance separate |
| KQ1 parent review fixes | !6 → !8 | Parent says “do not merge without follow-up”; !8 carries the fixes but the PR #82 base remains unmerged | Rebase PR #82 + !6 + !8; rerun 514/384 checks and distribution checks |
| KQ1 AGI base | `pr/82/agi-logic103-qualification` | 70 files, +10.8k, not in 0.28 and not an MR | Rebase and review as the first commit of the KQ1 stack |
| Cortex-M Armv8-M / AAPCS32 | !11 | Armv8-M Security/SecureFault layouts and derived AAPCS32 semantics explicitly out of milestone | Keep as a separate Armv8-M milestone |
| Miniplanets full port | !4 | 149 files; whole-game equivalence, arbitrary ROM conversion, physical NES, natural completion unqualified; conflicts with main | Split console modules; rebase; private ROM/cc65 gate; do not claim completion |
| Miniplanets movement/60 Hz | !5 | Movement 15.42 swaps/s; 32.24 swaps/s only in the seeded orb workload; below 60 Hz | Profile movement path after !4; publish the workload, not a blanket fps claim |
| Priority DOS/UDC fixes | PR #61–#63 | Open registry records; dependent on unmerged #54/#57/#50 stacks | Re-evaluate only if the UDC stack is admitted to 0.29 |
| Package-gate hardening | PR #64–#66 | Open; require resources from the deferred stack (Ghidra AsmC, source-concepts guide, terminal JSON) | Port with the resource stack; no 0.28 backport without the resources |
| First-party console synthesis | PR #79 pending revision | 80 focused tests + 1.17M native arithmetic comparisons; checked against 0.26 runtime; no full suite | Reconcile with PR #56 base, run full suite, then decide |
| PyPI/core-player publication | PR #77 | Manual, license-gated workflow; not enabled | Resolve license metadata and protected environments first |
| Linux/UDC portable stack | PR #38/#39/#42 etc. | Open, old, cross-cutting; no 0.28 ancestry | Decide as a 0.29 theme or keep deferred; do not cherry-pick silently |

## Archive: registry PRs

The registry has 83 records; `in 0.28` means the recorded head is an ancestor of
`release/0.28.0`. Open records may be superseded or merged by squash without an
ancestor head; this table is a gap scan, not a closure record.

| PR | Title | State | In 0.28 |
|---|---|---|---|
| 1 | Mid-dialog keyboard restore | closed | no |
| 2 | Investigation methodology / skill resources | closed | no |
| 3 | Define the UIL export boundary and agent RFC process | closed | no |
| 4 | test/docs: distinguish keyboard delivery from delayed application polling | closed | no |
| 5 | docs: separate state completion from UI-ready pre/post screenshot captures | closed | no |
| 6 | PQ1 runtime-resource layer gap | closed | no |
| 7 | UIL interface-description amendment | open | no |
| 8 | PQ1 runtime navigation and observation capability ladder | closed | no |
| 9 | docs: distinguish scene-family matches from content-ready transitions | open | no |
| 10 | docs: define UIL as the venue-neutral world IR | open | no |
| 11 | docs: define UIL bounded proof contracts | open | no |
| 12 | fDisBull 0.20 debugger and interpreter foundations | merged | yes |
| 13 | Progressive scenes and separate text play | closed | no |
| 14 | Stacked text-player slice | closed | no |
| 15 | release-feedback PR | open | no |
| 16 | docs: add KQ1 continuation usability notes | open | no |
| 17 | RFC: UDL mappings, UIL intents and reusable UDC definitions | closed | no |
| 18 | Keep authored Z test fixtures available in tool source archives | merged | yes |
| 19 | Record v0.23 merge and installed-acceptance evidence | merged | yes |
| 20 | Define held-out study for parallel recovery, normal-play discovery and unverified scaffolds | merged | yes |
| 21 | docs: document media-only no-CD rip scope and music-loop risk | merged | yes |
| 22 | Propose synthetic HUD scenes and serializable agent observations | merged | yes |
| 23 | Add native GOG Inno Setup unpacking without Wine | merged | yes |
| 24 | Recover bounded mailbox game intents over preserved word16 IR | merged | yes |
| 25 | feat: add DOS/4GW LE loading and DOS format implementation findings | merged | yes |
| 26 | Record native recovery shutdown and repeated-failure acceptance | merged | yes |
| 27 | Add evidence-qualified GameFAQs guide-writing skill | merged | yes |
| 28 | Add source-bound Z-machine v3 processor and bounded analysis | open | yes |
| 29 | RFC: formalize executable Rosetta contracts and polyglot UDC | open | no |
| 30 | Distinguish the Z scene interface from Z-machine bytecode | merged | yes |
| 31 | Share structural types between projects with a DOS/Win16 pilot | merged | yes |
| 32 | Recover Zork scene UIL, resolved dispatch, and window intent | open | no |
| 33 | Extend game guide skill for discoveries, routes and recovered formats | merged | yes |
| 34 | Qualify installed 0.26 Z reconciliation against original DinoPark | merged | yes |
| 35 | Report selected DOS process termination independently of debugger cleanup | merged | yes |
| 36 | Load Win16 NE images and map Colonization food counterparts | merged | yes |
| 37 | Reconcile completed Z checkpoint saves without saving again | merged | yes |
| 38 | Persist snippet links and select UDL implementations for native output | open | no |
| 39 | Milestone: shared UIL, selectable code, and native program shells | open | no |
| 40 | Document Civilization reverse-engineering and patch leads | merged | yes |
| 41 | Improve DinoPark analysis, Z recovery and DOS audio inspection | open | yes |
| 42 | Linux x86-64 scaffolds and portable C blocks under shared UIL | open | no |
| 43 | PRIORITY: keep game binaries out of FDBs and require exact source-layer approval | merged | yes |
| 44 | docs: audited research-only Library collection | merged | yes |
| 45 | docs: record LE whole-binary findings and UDL overlap reconstruction contract | closed | no |
| 46 | Document collection intake and version-to-layer decisions | open | no |
| 47 | Add selectable Tic-Tac-Toe and Five-Dice UDC variants | open | no |
| 48 | Add absolute paths to native shell output receipts | open | no |
| 49 | Add interchangeable bounded ASM-to-C engines and DOS comparison | open | no |
| 50 | Add Civilization city production UIL and executable UDC slice | open | no |
| 51 | Teach target-led documentation, reconstruction reuse and guide-derived Z blueprints | open | no |
| 52 | Add CivD food swaps across DOS and ARM64 with parameterized strategy Z | open | no |
| 53 | Ship reusable media adapters and missing-tool recovery guidance | merged | yes |
| 54 | Add bounded DOS COM UDC and block composition guidance | open | no |
| 55 | 0.27.0 cloud release candidate: schema9 storage and qualified integrations | merged | yes |
| 56 | Add console modules and an experimental full Miniplanets NES port | open | no |
| 57 | Add MZ and Z-machine scaffolds with native output checks | open | no |
| 58 | Reuse unchanged native CI builds and remove redundant feature runs | open | no |
| 59 | Define equivalent sweding during UIL-to-UDC realization | open | no |
| 60 | Add deterministic AGI scene census for KQ1 and PQ1 | open | no |
| 61 | PRIORITY next release: hash final DOS data bytes after pointer fixups | open | no |
| 62 | PRIORITY next release: preserve signed UDC returns and semantic events | open | no |
| 63 | PRIORITY next release: repair packaged test collection and high-FD acceptance | open | no |
| 64 | Require the Ghidra adapter resource in package gates | open | no |
| 65 | Require the source-and-concepts guide in package gates | open | no |
| 66 | PRIORITY review: verify assertions and require the terminal resource | open | no |
| 67 | Add direct guest decoder modules and bounded AGI UDL/UIL lifts | open | no |
| 68 | Recover and execute one KQ1 bow interaction with UDL | open | no |
| 69 | Guide diagnostic execution beyond normal progression, with Syndicate asset findings | open | no |
| 70 | Colonization: shared DOS/Win16 production UIL with original-body replay evidence | open | no |
| 71 | Extend direct AGI lifts with scalar control flow and logic calls | open | no |
| 72 | Share compact AGI control-flow continuations and verify KQ1 topology | open | no |
| 73 | Run recovered Snake and shared food UIL in interchangeable Wasm/WebGPU shells | open | no |
| 74 | Add Cortex-M/Thumb static firmware analysis | open | no |
| 75 | Document 0.27 publication and per-module UDC layers | open | no |
| 76 | Model KQ1 object and resource effects with resumable host requests | open | no |
| 77 | Prepare manual, license-gated PyPI distribution for core and player | open | no |
| 78 | Connect AGI effects to an original DOS host and verify KQ1 logic 103 | open | no |
| 79 | [Revision in progress] First-party console synthesis from existing recompiler research | open | no |
| 80 | Document caller and asset coverage, probe failures and retained-provider recovery | open | no |
| 81 | Document Syndicate graphics contracts and diagnostic tooling improvements | open | no |
| 82 | Qualify KQ1 logic 103 branches, blocking dialogue and Z probes | open | no |
| 83 | Add source-backed macOS ARM64 investigation path | open | yes |

### Registry dependencies not represented by an MR

- **PR #82** (`pr/82/agi-logic103-qualification`, 70 files, +10.8k): base of
  !6/!8; unmerged and not in 0.28.
- **PR #79** first-party console synthesis: `pending/first-party-console-synthesis-20261031`;
  revision in progress, checked against 0.26 only.
- **PR #42** Linux x86-64 scaffolds / portable C UIL: open, base for the
  deferred UDC stack; not in 0.28.
- **PR #61–#66** priority fixes/gates: open; runtime fixes depend on the
  deferred UDC stack; #64–#66 are package-gate hardening for resources absent
  from 0.28.
- **PR #77** PyPI publication workflow: open, license-gated, not enabled.
- The three open records whose heads are already in 0.28 are #28, #41 and #83;
  their records are stale relative to the release ancestry.

## Closure record

- Consolidated review: !12 (this document).
- Landed in 0.28: !1 and !2 closed with a pointer to this document; !10 is merged in `main` via `b21b204`.
- Unmerged informative reviews: !4, !5, !6, !7, !8, !9, !11 closed with their
  exact heads and source branches retained; their full descriptions are in the
  sections above.
- !3 (0.28 release candidate) remains open.
- GitHub registry records are not closed by this GitLab-only action; they remain
  evidence for 0.29 triage.
