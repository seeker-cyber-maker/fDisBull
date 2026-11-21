# Repositories and publication

## Combined development source

DotBox development is being integrated into
https://github.com/seeker-cyber-maker/fDisBull under `apps/dotbox/`.
The first review branch is `codex/shared-dotbox-core-20261121`, based on fDisBull
main. Reusable reversing components live in `packages/fdisbull-core/`.
The [shared codebase policy](https://github.com/seeker-cyber-maker/fDisBull/blob/codex/shared-dotbox-core-20261121/docs/SHARED_CODEBASE.md) defines product
boundaries, input commits and coordination with active QEMU migration.

Follow the root repository's `AGENTS.md` for publication: original GitHub is the
preferred source/review platform; a guarded service preserves the local Git hub
and GitLab peers. Publish a reviewable branch and draft GitHub PR, preserve
other agents' branches/review targets, and verify actual destination heads.
Do not dispatch CI or rebuild native components simply because application
source changed. Manual GitLab pushes require its existing `ci.skip` policy.

The user's standing instruction authorizes reviewable source checkpoints and
BBS updates. A review branch is not a merged main branch, package release or
qualified installation. Keep those outcomes explicit.

## Preserved DotBox repositories

- Original primary: https://github.com/seeker-cyber-maker/DotBox
- Independent mirror: https://github.com/TiGa-RCE/DotBox

Preserve both repositories and their own parent histories. They retain the
pre-consolidation source and a transition notice pointing to the combined
development branch. Do not overwrite them with the entire fDisBull tree,
force refs, delete history, archive them automatically or maintain a second
copy of extracted shared kernels. Account permissions remain independent.
An urgent legacy fix, if needed, is explicitly scoped and cross-linked rather
than silently diverging from the combined implementation.

This transition supersedes the old requirement to duplicate every continuing
DotBox implementation checkpoint into both standalone repositories. The new
canonical shared change is recorded on both affected BBS projects; legacy
repository notices preserve the route to it. No new automatic synchronization
service or scheduled workflow is installed.

## Product and evidence boundaries

Agent BBS projects `dotbox` and `fdb` remain separate, with their own goals,
roles, histories and acceptance. Shared changes have one implementation owner
and linked product tasks referencing the same exact source and evidence.
Routine discussion stays on BBS. A test-only checkpoint may contain an
authored receipt with the exact tested source, command, outcome and limits.
Keep private game data and raw captures outside Git.

DotBox installs with the small shared package, without the full fDisBull
application. Native source preparation remains separately owned and versioned.
The pinned DOSBox-X base and ownership overlay retain upstream provenance.
The overlay contains modified DOSBox-X source under GPL-2.0-or-later, as recorded
in `native/README.md`; preserve notices and corresponding source when
distributing an emulator binary. This checkpoint publishes no native binary
or game data. The release portal remains the planned binary delivery venue.
