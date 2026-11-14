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

For supported stopped legacy-paged observations, the provider also qualifies
the physical placement of each automatic source snapshot. After capture it
revalidates the exact task/process identity, CPU stop, run, source/version and
capture epoch. Fresh raw-machine sessions use the run ID as their effective
epoch until a genuine restore assigns an explicit epoch; the qualifier uses
the same rule as snapshots and the tracker, without creating a private epoch.
An explicitly invalid epoch or a later epoch change is still refused. Every
captured byte, including relocated bytes, must match two fresh linear and
physical readback passes; uncached page-table readbacks must
retain the sealed mapping. The bounded certificate covers only that snapshot,
with page-split extents and hashes. It does not qualify the physical placement
of every manager record, a whole task's RAM, allocation ownership or lifetime.
The first slice supports A20-enabled, non-PAE legacy32 paging with 4KiB pages
and configured conventional/extended RAM, at most 1MiB and256 pages per proof.
One ten-second observer deadline starts at entry and intersects any exported
caller/transport deadline. The raw machine run's local execution timeout is a
separate budget when it has no exported parent deadline. The proof never
renews a budget between passes, and restores prior transport bounds afterward.

The tracker records each certificate as a local runtime-tracking artifact.
`runtime_map_snapshot` accepts its optional `physical_readback` attachment only
when the local artifact, snapshot, task's native identity, sealed page coverage
and byte hashes agree. Source comparison and its loader fixup exclusions remain
separate; physical equality never excludes fixup bytes. Each resulting binding
has `physical_qualification.qualified: true` for its exact stopped extent.
Physical addresses remain outside task/process identity keys. A registry
checkpoint restore retains the old proof as historical evidence and requires a
fresh readback before a new physical qualification.
Disjoint fragments can share one certificate; overlapping republication or
reuse after any of its binding intervals closes is refused.

A typed physical readback failure withdraws all partial bindings and reports
`physical-unavailable`. The native episode can survive only after independent
stopped CPU and lifecycle-coverage revalidation; a later successful observation
can publish fresh proofs under that episode. Unexpected I/O, identity/CPU drift
and lost coverage retain the existing retirement/fencing behavior. Providers
without this operation and older snapshots gain no direct physical-read claim.

Source availability and native lifetime continuity are separate qualifications.
A typed `SourceMatchError` during source discovery withdraws current source
bindings and exposes no partial source result. It can preserve existing native
task/process episodes only when the owned lifecycle breakpoint, original
manager coverage and stopped CPU context remain independently valid. A later
unambiguous source observation can then publish fresh binding IDs under that
same observed episode. Matching bytes, a reused numeric handle or an ambiguous
placement alone cannot establish continuity. Source-only sessions retain their
one-stop ceiling. Native containment, coverage, unexpected I/O and publication
or journal failures still retire or fence unsafe state; explicit resume,
restore, writes, parent execution and active layers retain their gap behavior.

Each observation failure appends an `observation-error` runtime-tracking
artifact with its phase, reason, exception type/module/message/causes, run,
observation and task/process references, and the lifetime action taken. Live
`tracking_status()["errors"]` contains the total count, last summary and at most
16 recent artifact references. A later successful observation clears only the
current error fields, not this history. The complete recorded errors remain
available after cold Project reopen through `debug_artifacts` and
`debug_export`; no running guest is required. If journal/error recording itself
fails, the tracker must not describe that failure as durably recorded or permit
execution with a stale current mapping. Error messages retain at most 8192
characters and four cause summaries. A shortened message has an explicit
truncation marker and the SHA-256 of its complete UTF-8 message. A failed history
write is exposed as `errors.unrecorded`, not counted among persisted error
references; current binding count is unknown while fenced. Recovery of the
journal can permit final retirement, but does not silently remove that session's
execution fence. Failure of pre-dispatch binding invalidation records phase
`binding-invalidation-before-execution` and action `fence-before-dispatch`, then
re-raises the original failure. The journal's still-open intervals are not
presented as successfully withdrawn, and a later execution request is refused.
These contracts are tested with
authored fixtures; native relocation and native-handle reuse require separate
observed qualification on the exact integrated candidate.

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
ordinary snapshots do not independently read physical target bytes. A
registry physical coordinate is therefore not, by itself, a proof that original
source bytes were independently read at that physical address. Native acceptance
can add a separate bounded stopped physical-read auditor receipt using ordinary
public reads and stable CPU/translation checks. This remains independent of the
automatic DESQview source-snapshot qualification described above.
The stricter `dos_source_admit` operation owns its explicit physical/linear
readback proof independently.


A hidden step over an owned lifecycle breakpoint during a public run preserves
ordinary queued physical edges and leases. It performs no input callback; only
the following continue may dispatch that queue. Public step/trace and active
scheduled-input restrictions remain explicit. Unsupported compositions refuse
before native breakpoint suspension, preserving the stopped owner and its queue.
