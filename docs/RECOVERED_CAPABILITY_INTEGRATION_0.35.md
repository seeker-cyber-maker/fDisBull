# Recovered capability integration for 0.35.0

The user has authorized integrating all unique eligible work. The finite
[historical audit](SOURCE_CONSOLIDATION_AUDIT_0.35.md) is complete. Its initial 44 unique
tip rows overlapped and were deduplicated into the capability groups below, not
44 releases. All recovered groups now have source implementations in integration
`9f91a90c`; that does not freeze or qualify the release candidate. New active
feature work is outside this finite recovery set. Private games, saves, states,
FDBs and original-byte assets remain excluded; historical reports and proposals retain their original scope.

## Dependency and ownership

| Integrated group | Recovered source references | Source integration and limits |
| --- | --- | --- |
| Per-object LE modes, schema admission, static backings and views | `51d8bdae`, shared portions of `35f7dffb`/`b875722c` | `b5afeaed` reconciles schema9 uniform32 compatibility with guarded schema10 object modes, aliases and symbolic fixups, plus the shared static/runtime carrier parser. The recorded 196 focused and 1,117 surrounding checks (one optional-input skip) cover that seam, not arbitrary mixed-mode execution. |
| Current runtime mappings and containment | `35f7dffb`/`b875722c`, committed QEMU successor `de2d6bb7` | Current successors and source/input bindings remain authoritative; the tools port includes the remaining backend-specific DOSBox RPC hooks without replacing them with stale runtime mappings. |
| Installer/archive/EXEPACK intake, Inno profiles, media and structural adapters | `0daa9cd0`, `5db0b1b6`, `73ec8dfc`, `861c0c80`, `94dc9f13`, `b325f4d9`, `e7298561` | Media contribution `e06b5d66` merged at `39514391`; preservation fix `bf46036a` retains failed extraction artifacts and exclusively writes owned probe outputs (220 focused authored checks). See [media scope](RECOVERED_MEDIA_035.md). Native probes and private-corpus acceptance remain separate. |
| DOS/MZ/Z-machine UDC, backing reverse edges and UIL records | `0dc3790f`, `b6051fe2`, `f4f9e339` | UDC contribution `b86f1d2f` merged at `b1c21ed5`; data-receipt fix `6dafd643` is included as `57e97691`, hashing final emitted bytes after pointer fixups. Current Project/backing interfaces, source identities and per-object LE widths are retained; flat-only compiler profiles do not claim a mixed-mode LE lift. |
| Civ variants, arithmetic and source-bound examples | `0eaf75d1`, `1f8d2636`, `6b44cb06`, `9a16c5ec`, `cb976470` | Included through `b86f1d2f`/`b1c21ed5`, with overlapping histories deduplicated and newer signed ABI/IL-v2/table behavior retained. Private images, states and original-byte atlases remain excluded. |
| LLVM scalar, optional ASM-to-C, influence, CHIP-8/SNES slices and Colonization helpers | `02eb26f4`, `fcef2877`, `9df57f8f`, `3e437a9e`, `3e5900ee`, `3136d2fa` | Included through the same UDC integration with bounded emitter/adapter/example contracts and authored source checks. See [UDC scope](RECOVERED_UDC_ADAPTERS_0.35.md); optional tool invocation and native/runtime acceptance are separate. |
| DOSBox lifecycle, owned shutdown, RPC tracking, fuzzing, friction, crash recovery and RTLink launch profiles | `1e3c1ca8`, `1e837a20`, `e2f6b2d3`, `bc1bcee6`, `d2d78717`, `d87ae33e`, `e795a9ff`, remaining `35f7dffb` hooks | Tools contribution `e78ac8dc` merged at `f14bbc22`, retaining bounded diagnostics, truthful shutdown receipts, owned debugger cleanup and current launch contracts. The recorded pure/source selection passed 336 tests with six native-input skips; no backend launch or service activation follows from that port. |
| Drive library sync and FDB backup | `b3f9dead` | Included with tools; `b5bdde1d` and `170aa463` are integrated through `27838f79`. Legacy unbound proofs recapture once while prior copies remain preserved. Final preservation contribution `3efac6a6` merged at `7f39932d`, with measured-host portability tests `01d32fb2` included as `9f91a90c`. Actual main/WAL identities, private descriptor aliases and held manifest publication were independently reviewed; see [descriptor binding](FDB_BACKUP_DESCRIPTOR_BINDING.md) and the measured host boundary below. |
| Historical guides, reports and proposals | `09ab554c`, `22903caf`, `46f95e96`, `464bdc5c`, `5d9118ae`, `641b7e95`, `874f0a8b`, `b57f51d5`, `ae39d078`, `cbeb6ce6`, `da5f55a0`, `f8a70aad` | Sanitized and reconciled through `e78ac8dc`/`f14bbc22`. Dated observations and design proposals remain historical; importing them does not establish current runtime qualification or implement every proposal. See [tools mapping](RECOVERED_TOOLS_035_INTEGRATION.md). |
| Deliberate GitLab web/API behavior after skip markers | branch-tree intent at `263cfcca` | n8n owner correction `be68826e` is integrated: global disable has priority, only web/API admits, pushes/MRs/tags never admit, and native blocking gates plus `ci.skip` mirrors remain. The historical tip itself added zlib headers; the behavior comes from the reviewed tree and owner correction. |
| Complete tracked source-package inventory | `4f90c55e` | Tool-ZIP/sdist patterns now include the 22 missing eligible tracked files: 15 CommonJS helpers, the Swift watcher and six authored assembly fixtures. A full tracked-inventory regression is included. Preliminary four-artifact tool-only/exact-payload checks passed on source `734000d9`; the final composite artifacts still need rebuilding. |
| Bounded selective QEMU guide replies | `f02c4ba3` | Split the input/display material into a linked selective reference, preserving all content and the existing 64 KiB reply cap. Focused guide/reply checks passed 82 tests with five optional-input skips; this is not QEMU runtime acceptance. |
| Recoverable installer and exact selector restoration | owner installer line through `736cb7c6` | Integrated at `4684a8dc`, alongside the owner CI correction; 88 fresh focused checks on that root covered installer/CI recovery. This supplies installation behavior, not evidence of a new installation or final package acceptance. |

Endpoint authentication/checkpoint selector fixes (`dd7c43a4`/`ed4750a7`) are
already integrated in `2ca96ea7`, with43 focused passes/11 missing-input skips.
Equivalent, superseded, intentional-fault/archive and partial-import histories
keep their recorded dispositions; they are not wholesale merged into the release.

## Combination and freeze

The shared LE/schema contract and all deduplicated recovered capability groups
are implemented in the combined source. Draft [GitHub PR #87](https://github.com/seeker-cyber-maker/fDisBull/pull/87)
remains the review vehicle. Group-specific checks above evaluate their recorded
source revisions; they are not final combined-SHA acceptance or a progress score.

The final FDB source-preservation correction is integrated at `7f39932d`.
Independent authored macOS checks cover actual SQLite main/WAL descriptor
admission, held source transactions, immutable read-only alias preflight before
writable destination access, immutable completed snapshot scans, exclusive held
manifest inode/hash proof and retention of stages without pathname cleanup.
Portability tests measure alias support instead of assuming it: the observed
Linux SQLite 3.45.1 canonicalizes aliases and is refused before writable SQLite
access. The latest owner component selection recorded 82 passes and two
expected host-case skips; skips do not establish successful backup support. This
is measured macOS acceptance, not general Linux/Windows backup support. SHM
reader marks are recomputable cache metadata; main/WAL content preservation does not claim byte-identical SHM. See the [binding contract](FDB_BACKUP_DESCRIPTOR_BINDING.md).

The package-inventory correction `4f90c55e` is also integrated. Preliminary
four-artifact tool-only/exact-payload checks passed on source `734000d9` and
`9f91a90c`. A fresh clean-source artifact receipt is required for the final handoff.

The owner installer component `c7e8670d` is integrated at `74440ea5`. It
supports either retained official PyPI wheels or a separate official-sdist and
source-built Darwin arm64 wheel provenance record. The original build logs,
toolchain and identities remain inspectable. These are operator execution
records, not proof that an arbitrary recorded command ran; actual dependency
build/import validation remains a separate installation-input gate. The local
installer/verifier/pipeline/package selection passed 104 checks after this merge.

All recovered source implementations and known integration corrections are now
included. Final clean-source artifact receipts bind the candidate used for the
handoff; prior local artifact checks at `734000d9` and `9f91a90c` are retained
without substituting for that final binding.

After that freeze, hand n8n one clean primary-GitHub 0.35.0 ref/full SHA.
Exact-SHA ordinary/native Linux CI, backend/runtime acceptance, complete offline
packaging and network-disabled DOS/PE32/Win16 consumption remain separate gates.
Public delivery and approved fresh-prefix installation/activation require their
own receipts; the previous shared prefix remains available for rollback. This
source status is not a package-publication receipt, and no historical runtime
result qualifies this candidate by inheritance. The approved release process is unchanged.
