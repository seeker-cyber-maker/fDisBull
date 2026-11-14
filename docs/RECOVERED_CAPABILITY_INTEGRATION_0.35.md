# Recovered capability integration for 0.35.0

The user has authorized integrating all unique eligible work. The finite
[historical audit](SOURCE_CONSOLIDATION_AUDIT_0.35.md) is complete. Its 44 unique
tip rows overlap and are deduplicated below into capability work, not 44 releases
or a request for new permission. New active feature work is outside this frozen
recovery set. Private games, saves, states, FDBs and original-byte assets remain
excluded; historical reports and proposals retain their original scope.

## Dependency and ownership

| Work item | Recovered source references | Owner / integration branch | Concrete change and check |
| --- | --- | --- | --- |
| Per-object LE modes, schema admission, static backings and views | `51d8bdae`, shared portions of `35f7dffb`/`b875722c`; `test_le_mixed_*` | Integration owner | Integrated in `b5afeaed`: schema9 uniform32 compatibility, guarded schema10 modes/aliases/symbolic fixups, shared static/runtime carrier parser. 196 focused checks including previous0.34.1 reader refusal/immutability, plus1117 surrounding source checks passed (one optional-input skip). |
| Current runtime mappings and containment | `35f7dffb`/`b875722c` and committed QEMU successor `de2d6bb7` | Integration owner / tools owner | Preserve current successor; no stale runtime-mapping overwrite. Current containment/source/input checks400 passed. Port remaining DOSBox-specific RPC hooks in the tools group. |
| Installer/archive/EXEPACK intake and Inno profiles | `0daa9cd0`, `5db0b1b6`; archive/intake/Inno unit and payload tests | Media owner / `codex/recovered-media-035-20261114` | Add missing readers/probes/profile identity while retaining currentMADS/Westwood/loader contracts; focused extraction and package checks. |
| Media/structural adapters and KINT/Sherlock | `73ec8dfc`, `861c0c80`, `94dc9f13`, `b325f4d9`, `e7298561` | Media owner / same branch | Deduplicate shared registries, add missing structure/WAD/SHI/KINT/atlas/media source; authored unit/decoder tests. Historical research stays historical; no original target assets. |
| DOS/MZ/Z-machine UDC and backing reverse edges | `0dc3790f`, `b6051fe2`, `f4f9e339` | UDC owner / `codex/recovered-udc-035-20261114` | Port missing source profiles into currentProject/backing interfaces; preserve ARM64/SYS identity and new per-objectLE decoder widths. Flat-only lifts refuse unsupported mixed modes. |
| Civ variants, arithmetic and source-bound examples | `0eaf75d1`, `1f8d2636`, `6b44cb06`, `9a16c5ec`, `cb976470` | UDC owner / same branch | Reconcile overlapping source histories once; retain newer signed ABI/ILv2/table support, exclude private images/states/atlases, run authored source/variant tests. |
| LLVM scalar, optionalASM-toC, influence and console source slices | `02eb26f4`, `fcef2877`, `9df57f8f`, `3e437a9e`, `3e5900ee`, `3136d2fa` | UDC owner / same branch | Integrate bounded emitters/adapters/examples and Colonization helper; source-generation and unit checks, keeping native/runtime acceptance separate. |
| DOSBox lifecycle, shutdown receipts and RPC tracking | `1e3c1ca8`, `1e837a20`, `e2f6b2d3`, remaining `35f7dffb` hooks | Tools owner / `codex/recovered-tools-035-20261114` | Retain bounded EOF diagnostics, finalizer/headless behavior, completed-stop receipts, all-owned-debugger cleanup and generic tracking; patch-source/hash checks for owned corrupt-MCB shutdown guard. |
| Drive backup/sync, fuzzing, friction and crash recovery | `b3f9dead`, `bc1bcee6`, `d2d78717`, `d87ae33e` | Tools owner / same branch | Integrate source and pure tests; do not install a watcher, start a VM, mutate active targets or exercise live backup/delete operations. |
| RTLink/DOS launch profiles | `e795a9ff` | Tools owner / same branch | Add standalone parser/launch-profile source and bounded discovery tests; coordinate disc/intake additions with media owner. |
| Historical guides/reports and proposals | `09ab554c`, `22903caf`, `46f95e96`, `464bdc5c`, `5d9118ae`, `641b7e95`, `874f0a8b`, `b57f51d5`, `ae39d078`, `cbeb6ce6`, `da5f55a0`, `f8a70aad` | Tools owner / same branch | Sanitize and reconcile documentation into current guide layout. Keep dated observations/design proposals distinct from fresh runtime qualification; no feature invention from a proposal. |
| Deliberate GitLab web/API behavior after skip markers | branch-tree intent at `263cfcca` | n8n CI owner | Owner fix `be68826e` integrated: globaldisable remains highest priority, only web/API admits, pushes/MRs/tags never admit, native blocking gates andci.skip mirrors retained. The tip commit's own delta was zlib headers; policy provenance is the tree plus explicit owner fix. |

Endpoint authentication/checkpoint selector fixes (`dd7c43a4`/`ed4750a7`) are
already integrated in `2ca96ea7`, with43 focused passes/11 missing-input skips.
Equivalent, superseded, intentional-fault/archive and partial-import histories
keep their recorded dispositions; they are not wholesale merged into the release.

## Combination and freeze

The shared LE/schema contract lands first. Each independent owner works in an
isolated tree and commits its source/tests; the integration owner reconciles
sharedCLI/catalog/Project/package seams and checks the combined result. Tests
measure correctness and limitations, not a progress percentage. Heavy native
builds/VM acceptance remain n8n-owned and source-bound to the final candidate.

After all recovered capability rows are integrated, update their exact commit
and check receipts, run proportionate combined source/package checks, and hand
n8n one clean primary-GitHub0.35.0 ref/fullSHA. n8n can prepare delivery and the
approved fresh-prefix installer independently. No provisional source is queued
for publication. Escalation is reserved for an actual conflicting behavior or
product requirement with exact alternatives; ordinary adaptation work proceeds
under the existing authorization. The previous shared prefix stays available
for rollback after approved final installation/activation.
