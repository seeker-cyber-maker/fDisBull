# 0.35.0 contribution disposition

This records the finite integration pass on 2026-11-14. The integration branch
is `codex/release-0.35.0-integration-20261114`, based on primary GitHub main
`829453ecae3fb0de236dbdd95be85a554efd1fb7`. It is **not yet a frozen release
candidate**. See the [release process](RELEASE_PROCESS.md) and
[release status](RELEASE_STATUS.md). No preserved contribution is qualified merely
because its branch was mirrored or its files parse.

## Included source

| Contribution | Exact source head | Disposition |
| --- | --- | --- |
| Original GitHub restoration and mirror reserve-policy removal | `e1425b5fb9fc5790610688c3e5fc3845b02948c4` | Integrated; retained newer main CI/authority documentation when resolving conflicts. Volume/ref guards remain. |
| Investigation guide selection and recipes | `f5bc5972f5967c66904d9022f9c0cc04ad577904` | Reviewed eligible dirty source preserved independently of its live worktree and integrated. |
| Native QEMU migration, file layers, source/task bindings, CHIP-8 and virtual-time waits | `de2d6bb71bcd5d8e07462a38f9d6f4f921446cdc` | Integrated full lineage; combined CLI retains preflight, ScummVM options and new QEMU options. Platform/native acceptance remains separate. |
| Bounded PE behavior comparison and Wine loader/process-attach proofs | `25dca2cc9f2a18c5dbe371faf91465db42bde356` | Integrated full lineage with explicit conditional claims; kept QEMU options while adding PE64 process-create loader mode. Private packet qualification remains open. |
| Release front door | `RELEASE_PROCESS.md` SHA-256 `a28ff3311a7d47fe96d301c5084920ae8d37f9e7ad03c85c0230f426831d78d5` | Integrated the exact approved revision, including conditional 0.35 installation/activation authority and DotBox separation; linked from current README/status. |
| Frozen finite CI/release continuation | `0fcbda2c287fa64a14d82d320b8f6d3971071c73` | Integrated from the owner-frozen object; canonical branch `adef0021` read back on primary GitHub, GitLab and local hub. Combined broker retains both loader diagnostics and control inventory. No run or deployment follows from this merge. |
| Authenticated local endpoints and checkpoint selector disambiguation | `dd7c43a46da241dd5e17deefe0e102ba938ac0eb` / `ed4750a7` | Integrated as merge `2ca96ea7`; 43 focused tests passed, 11 missing-input skips. |
| Intended version and current installation documentation | This integration line | Core/player/runtime metadata now 0.35.0. Historical installation notes remain historical; current shared 0.34.1 local candidate is not attributed to the old tag. |

## Equivalent or superseded work, with provenance retained

- Doctor/preflight `43547da35cfefe34a9c6200db62d75efd1c65a13` is preserved at
  `codex/preserve-doctor-identity-43547da3-20261114`. Runtime identity, preflight and
  primary-version behavior are already included. Its candidate-number capability
  field was intentionally omitted by `447057b1` to preserve the reply budget; do
  not reintroduce that older CLI wholesale.
- QEMU dirty snapshot `e2a04747b7ad3a70c8a20bb205581ab1d01a8727` is preserved at
  `codex/preserve-dirty-qemu-tracking-20261114`; use its committed successor
  `c7465858`, included through `de2d6bb7`, with later source-binding, physical
  qualification and stop/input corrections.
- Civ dirty snapshot `0eaf75d1a30d70fcf6d0649be8e78a80178d6cd1` is preserved at
  `codex/preserve-dirty-civ-udc-20261114`. Its unique two-line headless quit-warning
  hunk is already in the included QEMU successor.
- Partial TiGa-RCE import `3365c325351bf09f53d63ee5c46090bf06a1685b` is preserved
  on primary at `codex/preserve-tiga-rce-main-20261114`. All 428 product blobs
  match main; its other three files are import bookkeeping, an incomplete-import
  banner and an obsolete manifest omission. Retain provenance without merging
  its unrelated, incomplete root.

## Preserved with explicit unresolved integration issues

| Preserved branch | Exact head | Issue retained |
| --- | --- | --- |
| `codex/preserve-root-dirty-20261114` | `48cf02fe2cd41ad8bf5533ddbe50e29ad35f9fe3` | Root CLI semantic delta adds a duplicate `z-controller` parser. Raw dirty work is preserved, but duplicate registration is excluded. Current docs are reconciled separately. |
| `codex/preserve-dirty-automatic-relocation-20261114` | `35f7dffb0df031760d9b17b61f4b81e665fc1aa2` | Unique LE schema10/object-width decoder and competing loader/Project contract require reconciliation with the current carrier implementation. |
| `codex/preserve-dirty-mixed-le-20261114` | `51d8bdae7fe4db82edd45fe25531899bf9139300` | Same schema/loader seam; not wholly equivalent to current code. No wholesale overwrite. |
| `codex/preserve-dirty-desqview-containment-20261114` | `b875722cfd832624cb57ab41b6f725de468aab57` | Older containment/source snapshot includes competing schema10 assumptions. Preserve unique ideas; current qualification/source bindings remain authoritative. |

n8n froze `codex/ci-end-to-end-stabilization-20261114` at
`0fcbda2c287fa64a14d82d320b8f6d3971071c73`, followed by the bounded correction
`adef0021cf5dc39c66601e9afadedf188dfb8a9f`. That immutable local source is now
integrated; its live worktree/index were not swept. The owner corrected the plain-output parser failure. Exact canonical branch
`adef0021` readback is verified on primary GitHub, GitLab and the local hub.
The remaining contribution/delivery issues below still prevent a final freeze.

The public-metadata transport prototype
`75114464333fb96771e0e2fc6f1be6497e015d69` is separately preserved on primary as
`codex/preserve-public-metadata-prototype-20261114` and excluded from active
integration ancestry. The intentional CI fault branch `9f821c17` is excluded.

Owner correction `adef0021cf5dc39c66601e9afadedf188dfb8a9f` removes the retained
legacy GitHub reserve stops and forces plain provider machine output. The direct
VPS path and retained GitHub entrypoints no longer impose reserve floors. The
current source-to-release flow
explicitly does not install the shared application; fresh-prefix activation and
verification remain an open final stage of the full release process. Native Wine
input identities also need acceptance against the combined loader/control-inventory
source, not an assumed transfer from a predecessor helper.

## Coverage and remaining integration work

The initial registered-worktree census contained 85 entries: 68 were readable
and 17 were stale/unavailable registrations. Five missing primary tip objects
were fetched by exact advertised ref; committed-head reachability is complete
for that captured snapshot. Three previously unpublished immutable heads were
preserved on primary. Eligible dirty snapshots were made with separate indexes;
original worktree/index bytes were retained, including n8n's active edits.

A wider primary-branch graph audit found 688 advertised heads, with every tip
object locally available. At provisional integration `ab5f3f17`, 290 branch names
were not ancestors and reduce to 126 independent maximal tips. **Ancestry is not
content uniqueness:** this set includes historical squashed/cherry-picked work,
aliases, recovery snapshots, retired experiments, the intentional fault and the
explicit preserved issues above. Their finite content-equivalence/disposition audit is now complete; see the
[complete source consolidation audit](SOURCE_CONSOLIDATION_AUDIT_0.35.md). After
the endpoint-authentication merge and final ancestry check, the 126 tips comprise
27 content-equivalent, 35 superseded, 18 intentionally preserved, 2 integrated
and 44 with concrete unique adaptations still required. These are tip counts,
not counts of independent capabilities. This does not claim all historical
contributions are integrated.
The private operational receipt `primary-integration-coverage.json` lists every
head and exact OID for the next bounded comparison pass.

The three older LE snapshots share one mixed-width static-import/analysis
prototype, not three independent new formats. Current containment, source
matching and input successors passed 400 focused checks; their results do not
establish the absent schema10 static decoder/Project behavior. The preserved
DOSBox RPC automatic-tracking hooks also require backend-specific adaptation
instead of assuming that QEMU lifecycle coverage transfers.

Before freeze, implement the [remaining source adaptations](SOURCE_CONSOLIDATION_AUDIT_0.35.md)
under the existing integrate-all instruction, or obtain a direct human scope
decision naming deferred work. Close the remaining delivery gaps, then qualify
one exact primary-GitHub SHA. Ordinary/native CI, complete offline packaging,
network-disabled DOS/PE32/Win16 consumption, public delivery and fresh shared
installation verification remain independent open gates.
