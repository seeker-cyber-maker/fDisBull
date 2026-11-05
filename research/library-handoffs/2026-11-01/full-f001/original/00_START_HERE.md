# Syndicate complete authored-work handoff: F001

**Download and retain this whole folder. This is the full baseline, not a delta.**

This package contains the currently available authored Syndicate research,
scene implementation, semantic/ASCII/graphical documentation, sanitized evidence,
publication drafts and historical deliveries. It is a checkpoint for continued
work, not a claim that the game investigation is finished.

## Start here

1. Read [GitLab status](01_GITLAB_STATUS.md) before attempting any integration.
2. Use [the current scene](scene/README.md) and
   [ASCII/precision guidance](scene/ASCII_PRECISION_AND_ROUTING.md).
3. Read [continuation priorities](02_CONTINUE_HERE.md).
4. Preserve `MANIFEST.json` and `SHA256SUMS` with this folder. Future partial
   packages identify this baseline or their immediate predecessor by its exact
   manifest hash. See [incremental delivery](03_INCREMENTAL_HANDOFFS.md).

## Navigation

| Directory | Contents |
| --- | --- |
| `scene/` | Current research scene adapter, tests, exact-coordinate ASCII view, navigation models and graphical-map tools. |
| `scene/public/` | Semantic mission snapshot, terrain model, HTML/SVG/PNG documentation, ASCII views, and candidate approach plans. |
| `research/early-le/` | Physical LE scope, validation gaps and selected independent tools. |
| `research/le-dispatch/` | Conditional switch recovery, replay tools and verification. |
| `research/asset-recovery/` | Compression, sprite, map, animation and sound-format investigations and diagnostic tools. |
| `research/graphics/` | Original-code graphics contracts, caller/loop findings and proposed improvements. |
| `research/dosbox-driver-loads/` | Actual DOSBox driver mappings and observed original service calls. |
| `research/audio-progress/` | Service outcomes, timer-callback context, repeated-loop progress and no-delay negative control. |
| `research/audio-lifecycle/` | Intro cancellation versus end-of-track, caller policy, XMI reader and tests. |
| `research/audio-patches/` | Proposed audio documentation/evidence patches, retained separately from implementation claims. |
| `runtime-v029/source-check/` | Exact tagged Player-source compatibility check, receipts and download utility. Not a full installed runtime. |
| `publication/` | Historical PR drafts, exact proposed repository files, patches and publication receipts. Old NOT SUBMITTED labels are historical; consult current audit. |
| `history/archives/` | Thirteen original authored-work delivery ZIPs retained unchanged. They contain repeated versions; do not apply every patch. |
| `audit/` | Commit-pinned GitLab audit, exact file/tree comparisons and browser-download limitation. |
| `verification/` | Packaging tests and exact-source scene test receipts. |
| `tools/` | Standard-library manifest verifier and delta ZIP creator, with tests. |
| `reports/` | Convenient top-level report copies. For relative evidence links, prefer the corresponding report in its `research/` directory. |

## Preserved graphical documentation

Open [the interactive map](scene/public/mission-map.html),
[the PNG](scene/public/mission-map.png), [district ASCII](scene/public/mission-ascii.txt),
or [subtile ASCII](scene/public/team-subtile-ascii.txt).
The display grid does not replace exact integer engine XYZ coordinates.
Candidate terrain routes are not certified walking routes; teleport placement
is not evidence of native passability.

## GitLab at this checkpoint

Main was inspected at `498c0887f8d15ca3b2fb3dc8994d2de24e144273`.
All 21 intended scene/report files match it by exact Git blob identity.
An additional 86 research payload files match six complete Git trees in draft
MR !35 at `676487fca2d4cbe5e0bd93781a04aff5678da29c`.
That draft remains open and unmerged. Preservation is not implementation acceptance.
The full status and links are in `01_GITLAB_STATUS.md`.

## What this package does not contain

- Original game installers, executables, media assets or story images.
- Private byte-retaining analysis databases, object stores, emulator memory,
  original-game screenshots or native checkpoints.
- A running DOSBox session or durable cross-session native execution state.
- The full fDisBull v0.29 offline runtime, dependency bundle or native backend.
- Every earlier unrelated game's research or an entire GitLab repository mirror.

Keep those private inputs separately. This is complete for the retained authored
Syndicate handoff, not a complete runnable-game backup. The requested v0.29
runtime download did not succeed: Browser.list_tabs reported that the originating
browser context was unavailable. This does not establish that the user was signed
out. No runtime installation is claimed.

## Verification

From this extracted directory:

```sh
python3 -B tools/handoff_bundle.py verify .
```

For reproducible source-only scene checks, write results outside the baseline:

```sh
python3 -B runtime-v029/source-check/run_source_checks.py --output ../source-check-F001
```

The fresh packaging check passed 16 authored tool tests. The exact tagged Player
source check passed 63 authored scene tests and seven smoke commands. These do
not constitute an installed-wheel test, a new native-game run, or current full
repository CI. Historical original-game evidence retains its own source and
runtime identities.
