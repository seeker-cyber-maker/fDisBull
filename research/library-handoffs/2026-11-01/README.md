# Library handoff intake, 2026-11-01

This directory reconciles retrieved ChatGPT Library deliveries with existing
GitLab source, draft reviews and private uploads. It preserves selected authored
additions without restoring whole project trees, applying archived patches,
merging drafts or changing the released runtime.

The file inventory is incremental. A successfully retrieved archive is not
evidence that every file in the originating Library has been enumerated.
See [inventory.json](inventory.json) for exact source URLs, sizes, hashes,
verification state and remaining intake gaps.

| Delivery | Current disposition |
| --- | --- |
| [Syndicate Full F001](full-f001/README.md) | Verified archive and nested identities; 21 existing main files and 86 files in draft !35 freshly reconciled. Unique handoff tools and semantic documentation selected here. |
| [Syndicate D001](syndicate-d001/README.md) | Verified two additions against the exact F001 parent, applied only to a separate private derived copy; original files unchanged. |
| [Research and implementation](research-implementation/README.md) | All 11 console source files match main; selected research is already preserved in draft !34. Private observation buffers and historical patches stay in the complete private archive. |
| [Syndicate Consolidated](syndicate-consolidated/README.md) | 80 of 84 outer files match F001 by content; four distinct wrapper/inventory files are recorded without restoring the old tree. |
| [v0.29 source check](v029-source-check/README.md) | 36 of 40 outer files match F001; its nested Consolidated archive is exact. This is historical source-only evidence. |
| [v0.29 core/player receipt](v029-core/README.md) | Historical Linux install receipt; locally rebuilt wheel hashes differ from the publisher's files while 200 package source files match the exact tag. |
| [Dependency receipt](v029-dependencies/README.md) | Historical Linux five-wheel dependency installation, with inactive authored probe source; no application/native installation here. |
| [Release intake](release-intake/README.md) | Four historical status documents recorded by identity, separate from fresh canonical package metadata. |
| [Partial handoff 000](partial-000/README.md) | Earlier access/status checkpoint retained as historical data; no archived checklist automatically executed. |
| [Three Library release copies](release-copies/README.md) | Source distribution and dependency archive match canonical GitLab package bytes. The tool ZIP is a distinct source snapshot, recorded separately without replacing the published ZIP. |
| [Three standalone receipts/report](receipts/README.md) | Two exact F001 receipts are selected as source files; the standalone installation report exactly aliases its existing private archive member. |
| KQ1 JPC-RR evaluation | Already preserved in [draft !37](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/37) at `7e5b13acb1bed91faebba6e558acb627c3d1bc5d`, with its complete original ZIP retained as a private project upload. Its Library-only handoff statement is superseded. |

The nine handoff archives and the distinct tool source snapshot have complete
private project-upload copies with byte-identical readback receipts supplied by
the publishing owner. Their links are in the inventory. The two matching release
copies use their existing canonical package files. All three release copies have
separate package-byte comparisons. Authenticated metadata accounts for all ten published release
artifacts, including the native offline kit and source companion; those two
larger artifacts were not downloaded or run during this intake. These nine
handoffs, three release copies and three standalone receipts/reports cover 15
identified Library files without claiming an exhaustive listing of unrelated files.

At this intake, GitLab `main` is
`f173aa33d0cd12356ce13a3b23b567bd2b432156`. Syndicate research !35,
Zork recovery !36 and KQ1 preservation/comparison !37 remain draft and unmerged.
The Anchor/delta/frame-input stack !14 → !16 → !30 is also draft and unmerged.
Preservation in a review or private upload is distinct from integration into main.

Raw delivery ZIPs, historical bytecode caches, private runtime observations and
game-derived media remain outside Git. Selected semantic maps are authored
projections with explicit geometry/reachability limits, not original game assets.
Archived instructions and publication scripts are historical source material;
they confer no authority to launch targets, publish, install or delete anything.

No native guest, CI, release, installation or merge is part of this intake.
The new generic utility creates manifest-bound handoff ZIPs; its deltas are file
delivery records and are unrelated to the debugger CPU/RAM delta implementation.

Fresh local checks exercised the selected handoff utility: 16 tests and seven
subtests passed. The original F001 payload and D001's separate derived payload
both passed their manifest checks. Other archived installation/probe scripts were
only parsed; their historical test claims were not rerun. The Git selection retains
text, semantic projections and hash inventories; complete raw archives remain
private. See [verification.json](verification.json) for the focused intake gates.
