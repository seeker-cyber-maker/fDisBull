# !!Syndicate Expert: recovery and publication handoff

- **Status:** preservation handoff, 2026-11-03. No merge, tag, release, backend installation or game-code publication is authorized by this document.
- **Scope:** fDisBull Syndicate research (F001/F002 and D-series) plus the most recent **CHimpREC / GOG Galaxy** captured-image reconstruction, which was developed in this thread after earlier Syndicate work.
- **Incident separation:** the earlier inability to publish a PR and the subsequent chat-thread malfunction are separate observations. Neither is evidence of the other's cause. A remote review branch and draft MR now exist, so do not reconstruct the work merely because the original chat is inaccessible.
- **Trust boundary:** this document reports source/receipt facts and historical test claims. It is **not** a new execution, validation of private source bytes, approval of user-submitted rights, or proof of full game/runtime equivalence.

## Executive summary and primary recovery point

**Primary completed reconstruction:** [GitLab MR !68](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/68), *Draft: Rebuild captured PE imports and unpack GOG Galaxy wrappers*.

- Implementation branch: `research/chimprec-gog-galaxy-20261102`.
- Pre-handoff implementation commit: `1607e03ff3ee8a21c4df203baa228eb617ceae58`.
- Parent and baseline main: `3dc5c50d35f310a3ba39b1cf0cf82a20b8df69f7`.
- This branch was pushed after the original publication blocker. The older handoff that said “no remote write” is historical, **not the present GitLab state**.
- The complete earlier local package was called `fDisBull_CHimpREC_GOG_Galaxy_PR_2026-11-02.zip`, with reported SHA-256 `6d99da30b506c972900c0edfa013e913e87706c3ca28f8d1355a6e0f63722a0a`. MR !68's prior attachment review states all 12 proposed repository source files match the corresponding remote files; README was a thirteenth changed path. The local archive itself is **not embedded here**, and its accessibility has not been re-established in this preservation pass.
- The implementation, docs and receipt are already in MR !68; do not re-create the code or open a redundant competing MR.

The parallel [MR !67](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/67) is **a different, unfinished modular CHimpREC branch** (`feature/chimprec-gog-galaxy-rebuild-20261102`, head `8eb3cc173eeeff239da0d83bc3dda95376eaf637`). Its own description says the writer module imported by the facade is absent; it is not an alternative completed implementation. Both !67 and !68 add `src/fdisbull/chimprec_pe.py` with different structures. Review/cherry-pick deliberately; **do not blindly merge both** or replace one with the other.

## What the completed CHimpREC/Galaxy branch implements

The source at the pre-handoff implementation commit changes 13 repository paths:

- `src/fdisbull/chimprec.py` extends bounded PE32/PE32+ IAT recovery, including runtime-qualified code regions, aliases, forwarders, ordinals, ambiguity decisions and explicit invalid-thunk repairs.
- `src/fdisbull/chimprec_capture.py` validates a *source-free* `fdisbull-chimprec-capture-1` receipt: source identity, process/thread topology, runtime regions and an observed OEP transfer.
- `src/fdisbull/chimprec_pe.py` rebuilds captured PE analysis images: preserves application IAT addresses, adds import descriptors/OriginalFirstThunk/name tables in `.reimp`, sets qualified OEP, checksums and parses output. Certificate/bound-import metadata are cleared; the default fixed-base output does not falsely claim valid relocations/ASLR.
- `src/fdisbull/gog_galaxy.py` and `src/fdisbull/gog_galaxy_cli.py` implement the caller-captured GOG Galaxy UPX-wrapper coordinator. No download or process attachment.
- `src/fdisbull/media.py` declares the media route; `README.md`, `docs/CHIMPREC.md`, `docs/GOG_UNPACKING.md`, `docs/GOG_GALAXY_CHIMPREC_2026-11-02.md` and the agent skill's `references/media-modules.md` explain use and boundaries.
- `tests/test_chimprec_rebuild.py` adds authored reconstruction/capture/Galaxy tests.
- `docs/evidence/gog-galaxy-chimprec-2026-11-02/receipt.json` retains source-free historical acceptance counts, digests and limits.

Use [the CHimpREC guide](../CHIMPREC.md), [Galaxy case study](../GOG_GALAXY_CHIMPREC_2026-11-02.md), [GOG route distinction](../GOG_UNPACKING.md), [source-free acceptance receipt](../evidence/gog-galaxy-chimprec-2026-11-02/receipt.json) and the executable suite `tests/test_chimprec_rebuild.py` as the read order. The rebuild accepts **already captured** mapped bytes, qualified export identities, an OEP witness and explicit thunk decisions. Capturing a Windows process is a separate unimplemented backend responsibility.

### Historical validation, not new acceptance

The prior delivery and MR !68 report **19 focused tests** (11 existing CHimpREC and 8 new), including PE32/PE32+ synthetic import rebuilds. On two privately retained GOG Galaxy X-COM wrapper captures:

| Private source label | Qualified imports | Rebuilt output size | OEP |
| --- | ---: | ---: | --- |
| X-COM: UFO Defense Galaxy wrapper | 158 | 1,150,976 bytes | `0x00435143` |
| X-COM: Terror from the Deep Galaxy wrapper | 158 | 1,183,744 bytes | `0x00435143` |

The original mapped captures came from an earlier traced compatibility-process run using **synthetic loader-export address tokens**, not genuine Windows DLL exports. A manual parser and LIEF were reported to agree about import structures. These outputs are **fixed-base unsigned analysis reconstructions**, not verified runnable Windows replacements, nor bit-exact pre-UPX originals. No new private wrapper execution, Windows/Wine attachment, GUI startup or native loader check occurred in this PR publication pass.

MR !68's 2026-11-03 publication refresh reported **8 fresh reconstruction tests passed**. Its later attachment verification read back all 12 packaged source files, parsed seven Python sources and the JSON receipt, **but reran no pytest** in that verification environment because pytest was unavailable. Keep these three verification stages distinct; a checked GitLab upload is not proof of Windows loader compatibility.

## Earlier Syndicate Expert work: reconciliation, not republishing

| Work package | Preserved GitLab object | Current evidence boundary / next work |
| --- | --- | --- |
| Original ASCII/Z scene and early research | Integrated source on main; [MR !35](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/35) merged as preservation | Earlier scene delivery checked 21 file identities and 63 authored tests. It did not qualify arbitrary original walking/boarding. Keep private original assets and ROM/game bytes out of source control. |
| Library handoff and F001/D001 reconciliation | [MR !42](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/42), draft | Inventory/checksum and historical patch receipts, not wholesale patch application or native acceptance. |
| D003–D006 and F002 tactical navigation, doors, vehicles, damage, chronology | [MR !54](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/54), draft | Updated example and history consumers. Original D003 door/vehicle authored checks, D004 navigation, D005 attribution and later historical observations are source-bound; their historical native evidence must not be promoted to fresh verification. |
| D007 selective rewind | Also preserved in draft !54 | Dictionary-based source-free mixed-time study and 32 test cases; **no native guest restoration adapter or safe resume**. |
| D008 campaign/save/research | [MR !55](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/55), draft | Bounded 28,247-byte save interpretation, 50-territory graph, research/finalizer model and passive Player projection; 51 freshly reported source-only tests and nine passive Player commands. Historical 73 native/model comparisons are not newly rerun. No complete campaign or safe native save continuation is established. |
| Completed CHimpREC/GOG Galaxy captured-image reconstruction | **[MR !68](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/68), draft** | Actual branch contains source, tests, docs, acceptance receipt; no native loader acceptance. |
| Parallel alternate CHimpREC modular implementation | [MR !67](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/67), draft | Incomplete writer and overlapping `chimprec_pe.py`; preserve for architectural review, do not merge blindly with !68. |

The current GitLab review state matters more than historical chat phrases such as “local PR only,” “not pushed” or “blocked,” which applied to earlier moments. Do **not** claim that !54, !55, !67 or !68 are merged because their branches exist or because other work was integrated into main.

### Separate ongoing objectives

Syndicate original-game navigation, damage causality, mixed-time native rewind, save/campaign compatibility and CHimpREC are **distinct evidence scopes**. A PE/Galaxy wrapper reconstruction is not completion of the Syndicate game research, and a preserved tactical model is not proof of full native behavior. Other recent fDisBull UDC registry / sweding / CHIP-8 work is separate and should not be introduced into these reviews just because it happened in other chat threads.

## Architecture, decisions, evidence boundaries

1. **UDL = User-Defined Language; UIL = Universal Interaction Language; UDC = User-Defined Compiler.** Use the repository's canonical definitions, not invented expansions.
2. Preserve source-to-UDL, UDL-to-UIL, UIL-to-UDC and emitted-artifact-to-original-runtime qualification independently. A parser round trip or equal final result does not qualify upstream mappings or physical host effects.
3. Import, rebuild, capture and execute are separate capabilities. The current CHimpREC implementation covers import-plan recovery and PE rebuilding from caller-supplied captures, **not** attaching to and controlling arbitrary live processes.
4. Imported/recovered source, original binaries, game assets, captured memory, rebuilt wrappers, saves, user-owned GOG files and byte-retaining databases remain **local-only** under the project's publication policy. A checksum or a retail purchase does not confer redistribution permission.
5. Preserve attributed claims and negative/unknown cases. There is no global `verified: true` state or blanket executable admission from registering a candidate.
6. All ongoing MRs stay Draft pending separate review and qualification. Avoid CI-trigger storms; the repo's feature-branch commits use `[skip ci]`. Mac local-hub mirror synchronization is not established by a GitLab write.

## Tasks on resumption (in order)

1. **Start from this file and the verified GitLab branches, not the chat transcript.** Read MR !68 and its `docs/CHIMPREC.md`, source-free receipt and `tests/test_chimprec_rebuild.py`. Verify this handoff commit is a *documentation-only child* of the original implementation commit.
2. **Review !67 versus !68 explicitly.** One uses an unfinished modular PE writer, while the other contains the full captured-image writer and Galaxy coordinator. Pin exact schema/interface differences and select or compose implementation pieces only after testing. Avoid duplicate source entries and unrelated README/CLI updates.
3. **Run a fresh focused test on the intended merged/current environment**, including existing `tests/test_chimprec.py` and new `tests/test_chimprec_rebuild.py`. Record interpreter/dependency versions, exact source tree and tests. Do not substitute historical reported 19 passes for a new test receipt.
4. If appropriate, run actual Windows/Wine loader acceptance on a **private** captured wrapper using genuine exports, matched source identity, OEP, imports and state. Report failure/unknown plainly. No private bytes in GitLab.
5. Resume original Syndicate gameplay work via !54 and !55 as separate review scopes; check whether historical D003–D008 fixtures still match the chosen current base and decide how to integrate pending passive providers.
6. Only after review, qualification and owner release decision should agents merge, tag, publish a release or activate a shared installation. Keep local Mac/git mirror reconciliation explicit.
7. If the earlier CHimpREC local ZIP becomes available, verify its exact SHA-256 from above and compare member identities to MR !68; **do not infer** that that ZIP was attached to GitLab just because MR !68 cites it.

## Research status / open questions

- CHimpREC: Which real Windows/Wine attach/export-map backend should produce trusted captures? Can actual loader initialization succeed using genuine exports? How should ambiguous provider versions and forwarded imports be compared against live systems?
- Existing !67 modular plan versus complete !68 implementation: what genuine behaviors justify keeping both and what conflicts must be resolved before integration?
- Syndicate: what native driving/walking, unit-damage source causation, mixed-time restoration, effect ordering and campaign/save compatibility still need original-backed confirmation?
- Workflow: Does the selected base include later fDisBull changes that require targeted requalification? Has the local git mirror been synchronized? The original thread failure and former PR blocker do not answer these questions.

## Memory / next handoff

Continue with **the exact GitLab MR URLs and pinned commits**; do not rely on the original chat thread having a working history. The implemented code and historic evidence were not discarded when PR creation was initially blocked. This handoff preserves the whole line of research without conflating former local-only work, open drafts, merged source, and unqualified native behavior.

Authoritative latest branch status must be re-read immediately before editing, since concurrent agents can advance these branches.
