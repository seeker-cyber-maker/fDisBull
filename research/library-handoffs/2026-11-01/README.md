# Library handoff intake — reviewed November 3

This directory preserves the November 1 Library intake and its November 3 review.
The branch has been updated from main `3dc5c50d35f310a3ba39b1cf0cf82a20b8df69f7`.
MR !42 remains draft/unmerged, and handoff MR !74 remains separate and unmerged.
The project is now public; earlier private-upload wording is historical, and
current remote attachment availability/access controls have not been rechecked.

Read [the current review](REVIEW_2026-11-03.md) and use the
[reviewed handoff utility](tools/README.md) for new packaging. The 28 bound
imports, including the old utility, remain byte-for-byte unchanged.

The original intake reconciled retrieved deliveries with the then-current
GitLab source, draft reviews and recorded uploads. It preserves selected authored
additions without restoring whole project trees, applying archived patches,
merging drafts or changing the released runtime.

The file inventory is incremental. A successfully retrieved archive is not
evidence that every file in the originating Library has been enumerated.
See [inventory.json](inventory.json) for exact source URLs, sizes, hashes,
verification state and remaining intake gaps.

| Delivery | November 1 preservation record (historical) |
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
| KQ1 JPC-RR evaluation | Already preserved in [draft !37](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/37) at `7e5b13acb1bed91faebba6e558acb627c3d1bc5d`, with a recorded original ZIP upload. All 41 selected KQ1 files are now on main; its Library-only handoff statement is superseded. |

The November 1 publishing receipt recorded byte-identical project-upload
readbacks for nine handoff archives and the distinct tool source snapshot.
The inventory keeps that historical metadata; it is not a current download or
privacy guarantee. The two matching release
copies use their existing canonical package files. All three release copies have
separate package-byte comparisons. Authenticated metadata accounts for all ten published release
artifacts, including the native offline kit and source companion; those two
larger artifacts were not downloaded or run during this intake. These nine
handoffs, three release copies and three standalone receipts/reports cover 15
identified Library files without claiming an exhaustive listing of unrelated files.

At the November 1 intake, GitLab `main` was
`f173aa33d0cd12356ce13a3b23b567bd2b432156`. Syndicate research !35,
Zork recovery !36 and KQ1 preservation/comparison !37 remain draft and unmerged.
The Anchor/delta/frame-input stack !14 → !16 → !30 is also draft and unmerged.
Those MR states are historical: !14, !36, !37 and !41 subsequently merged,
while !16 and !30 closed. Their source tips are ancestors of the main used here.
This intake remains pending as !42; preservation is distinct from integration.

Raw delivery ZIPs, historical bytecode caches, private runtime observations and
game-derived media remain outside Git. Selected semantic maps are authored
projections with explicit geometry/reachability limits, not original game assets.
Archived instructions and publication scripts are historical source material;
they confer no authority to launch targets, publish, install or delete anything.

No native guest, CI, release, installation or MR merge is part of this intake.
The reviewed generic utility creates manifest-bound handoff ZIPs; its deltas are file
delivery records and are unrelated to the debugger CPU/RAM delta implementation.

The November 1 local checks exercised the original utility: 16 tests and seven
subtests passed. The original F001 payload and D001's separate derived payload
both passed their manifest checks. Other archived installation/probe scripts were
only parsed; their historical test claims were not rerun. The Git selection retains
text, semantic projections and hash inventories. Original archives were not
added to Git. [verification.json](verification.json) is the historical intake
receipt; the current review records the new tests and fixes.
