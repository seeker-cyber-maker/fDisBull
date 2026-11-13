# Recorded runtime mappings and automatic stopped-state tracking

Runtime bindings are source-qualified observations with explicit lifetimes.
They are not an implicit live address map. Every task has a new incarnation ID;
native handles, PSPs and page-table roots do not establish continuity by
themselves. Before execution or an unmonitored mutation, the session closes its
current mapping intervals. Historical queries preserve the earlier placement.

The registry is an additive Project mixin using four SQLite tables:
`runtime_mapping_tasks`, `runtime_mapping_events`, `runtime_mapping_bindings`
and `runtime_mapping_checkpoints`. Opening or creating a project ensures those
tables exist. This port preserves the current Project schema and external
object-store behavior; it does not introduce the private mixed-LE schema10 or
replace the loader, analysis processor or Project implementation.

The public Project/JSON methods are `runtime_objects`, `runtime_task_start`,
`runtime_task_end`, `runtime_tasks`, `runtime_map`, `runtime_map_snapshot`,
`runtime_unmap`, `runtime_mappings`, `runtime_resolve`, `runtime_map_checkpoint`,
`runtime_map_restore` and `runtime_mapping_events`. JSON method names use
hyphens. CLI writes accept one bounded `--definition-file` JSON object; duplicate
keys, nonfinite values, project overrides and definitions over4MiB are refused
before opening the project. Caller-recorded evidence is labelled `recorded` or
`modeled`; it is not automatically native authentication.

`runtime_map_snapshot` requires a fresh local snapshot after task start, with
the same source/version/run/task/capture epoch. It compares only declared
file-backed bytes, excludes loader-declared fixups, requires nonempty compared
bytes, and verifies sealed page/mapping evidence. Canonical LE object IDs cannot
be bypassed through a generic region alias. Linear, physical, preferred and
selector queries use half-open ranges and journal event intervals; physical
aliases return all matches rather than guessing ownership. Checkpoint restore
creates new binding IDs and never writes guest memory.

`AutomaticRuntimeTracker` is a normal session-owned observer. Its callbacks are
`before_execution`, `after_stop`, `internal_stop`, `close` and `status`.
`before_execution` must finish invalidation before native dispatch. A completed
action is never replayed because optional source enrichment failed. The machine
owner attaches the tracker after recording its debug run and handles owned
breakpoints through the existing stop/pending-instruction path. The tracker
records artifacts using the session's normal `_artifact` method, captures fresh
`memory_snapshot` witnesses and splits bindings at observed4KiB linear pages.
The public machine session attaches this observer after run creation and cold restore;
the QEMU-DOS process source-admission operation remains a separate stopped proof.

Original-source relationships are unavailable while an execution-only code
layer is active: unchanged RAM cannot prove what the guest is fetching. Such a
stop invalidates bindings, ends prior task episodes and removes the original
manager lifecycle provider. Clearing layers permits a new stopped observation
and new source-qualified lifetime; it does not revive the earlier episode.

The DESQview provider qualifies the explicitly selected original2.8 manager
from its declared FAT boot member and runtime fingerprints. It relates task and
process records using original-source ownership checks, distinct from physical
placement. Task/process events require the affected target's membership;
swap notifications use their explicitly qualified process mapping; manager END
is global. An unrelated process END does not retire another qualified process.
Unknown or malformed containment fails closed, and creation before attachment
remains unknown. No custom guest helper is needed for this observer.

## Port provenance and current LE boundary

The four module implementations originate in the private W7 source checkpoint
`66e0945ea6a83c4f54473651cae062a7d3f1de846c3ce62ffaf2d843caffce43`.
They are `runtime_mappings.py`, `runtime_tracking.py`, `runtime_desqview.py` and
the legacy `runtime_source_matching.py` adapter. The tracker adds the
execution-only-layer guard described above. Tests retain the public registry,
snapshot, source-match and containment contracts using authored inputs only.

The legacy matcher supplies bounded raw-FAT COM/MZ discovery needed for normal
DESQview sessions as well as its older protected-mode path. Its `discover`
returns at most one record with `source_identity`, `identity_evidence` and
`source_spans`. Each span provides `name`, `address`, `length`, `object_id`,
`object_offset` and optional exact source `fragments`.

Its protected path and the MZ-to-LE registry view use the explicit
`load_runtime_le_carrier` parser. This admits declared BW-bound and mixed-width
runtime carriers without changing ordinary static `load_le` admission. MZ and
embedded LE object addresses retain separate namespaces. Both source matchers
use the same complete bounded masked-window search, including complementary
fixup-mask ambiguity refusal. A file-backed extent must be unique even when an
alternative has no common unmasked anchor.

The legacy matcher reports virtual/linear-only comparison scope and
`physical_mapping_qualified: false`. The separate QEMU-DOS stopped
[`dos_source_admit`](QEMU_DOS_PROTECTED_SOURCE.md) operation compares linear and
physical reads and publishes a private evidence artifact. It does not install
a continued LE process binding or authorize source-addressed hooks/layers.

The historical private native DOSBox-X Doom evidence and QEMU DESQview evidence
do not qualify this newly integrated source. Exact-source host tests, installed
package readback and actual backend checks remain separate integration-owner
gates, recorded in the [maintained handoff](DOS_QEMU_HANDOFF.md).


The Engine snapshot path retains its existing PTE-derived translation evidence;
it does not adopt the private W7 per-page `physical_readback` extension. A
registry physical coordinate is therefore not, by itself, a proof that original
source bytes were independently read at that physical address. Native acceptance
can add a separate bounded stopped physical-read auditor receipt using ordinary
public reads and stable CPU/translation checks. Such a receipt qualifies only
those observed extents and does not upgrade the automatic provider's scope.
The stricter `dos_source_admit` operation owns its explicit physical/linear
readback proof independently.
