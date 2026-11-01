# Syndicate Full F001: reviewed additions and provenance

Source Library file:
[fDisBull Syndicate Full F001](https://chatgpt.com/space/file/libfile_5c57f042dff081918f271805b22db481).
The received ZIP is 2,656,225 bytes, SHA-256
`53c85cb2ac29f7986cbee35c83ed059d34bebc92c8258756fb50fe49df63b8c9`.
It contains 325 files; its internal manifest covers 323 payload files, and
`SHA256SUMS` additionally binds the manifest. All 324 checksum entries match.

[manifest.json](manifest.json) records every outer file and its preservation or
deduplication decision. [nested-archives.json](nested-archives.json) records
the 13 retained historical ZIPs and all 325 nested files without extracting
their trees into this checkout. The original archive remains private outside Git;
the intake inventory records its upload state separately.

## What was already preserved

Fresh byte comparisons against current main
`f173aa33d0cd12356ce13a3b23b567bd2b432156` confirm all 21 scene/report files
identified by the package. Existing sources remain at
[`examples/syndicate_z_scene`](https://gitlab.com/brewster-jennings-group/fdisbull/-/tree/f173aa33d0cd12356ce13a3b23b567bd2b432156/examples/syndicate_z_scene)
and its linked report. They are not copied again here.

All 86 research payload files independently reconstruct the six exact Git trees
in [draft !35](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/35),
head `676487fca2d4cbe5e0bd93781a04aff5678da29c`. Those audio, graphics and LE
research trees remain draft/unmerged; their archived patches remain unapplied.
See [reconciliation.json](reconciliation.json) for the pinned identities and
fresh comparison results. Matching Git trees proves exact file preservation,
not correctness or current runtime qualification.

## Selected additions

- `tools/handoff_bundle.py` and its authored tests provide a standard-library
  full-manifest verifier and changed-files-only ZIP creator/verifier. They name
  the parent by manifest ID and SHA-256, retain deletion records for review,
  and do not apply a delta or delete inherited work.
- `semantic-map/` preserves the previously uncommitted semantic mission model,
  HTML/SVG documentation, exact-coordinate ASCII views and candidate approach
  plans. No PNG or original visual asset is copied into this source import.
- `original/` preserves selected original checkpoint/navigation documents and
  the v0.29 source-slice report as historical context. Their operational
  instructions and old status statements are not current authorization.

The maps are conditional projections. Candidate routes are not observed walks;
teleport placement does not qualify native passability, doors, boarding,
inter-level connectors or legitimate mission reachability. Rendering a map does
not recover the entire game or its scripts.

The original report records 63 authored scene tests against a tagged Player
source slice and seven smoke commands. Those are historical source checks,
not a newly installed v0.29 runtime or a new native Syndicate run. New intake
checks are recorded separately in [verification.json](verification.json).

## Verify the selected utility

From the repository root, use the existing test environment and an authorized
external scratch directory:

```sh
TMPDIR=/path/to/private-scratch PYTHONDONTWRITEBYTECODE=1 \
  python -m pytest -q -p no:cacheprovider \
  research/library-handoffs/2026-11-01/full-f001/tools/test_handoff_bundle.py
```

To verify the privately retained full extraction without changing it:

```sh
python -B research/library-handoffs/2026-11-01/full-f001/tools/handoff_bundle.py \
  verify /path/to/private-original-F001
```

`original/03_INCREMENTAL_HANDOFFS.md` describes the archive author's proposed
delivery convention. Future use still requires a declared source, a new private
output path, appropriate storage admission and explicit review of changes.
The selected utility is not an installer or an automatic project restoration tool.

## Privacy and publication boundary

The bounded audit read all outer files and all nested ZIP members. It found no
credential/private-key pattern hits, unsafe archive paths, symlink entries or
original game executable/media/state/database payloads. Hexadecimal switch and
audio fixtures are explicitly authored test inputs. The nontext nested payloads
are copies of the authored semantic-map PNG and three Python bytecode caches.
One historical MR !35 loader-audit document retains a cloud workspace path; it
is not duplicated by this selection. No absolute host roots or raw runtime
buffers are present in the selected additions.

No archived publication script, patch or runtime probe was executed or applied.
All earlier work remains preserved. This source intake does not merge !35 or
qualify its proposed production changes.
