# Runtime task and object relationships

The runtime mapping registry preserves task incarnations, bounded source-object
relationships, aliases and map/restore history in an analysis project. It does
not start a guest, change memory, install a manager or select a runtime code
segment. It is available through the normal Python `Project`, JSON-line and CLI
interfaces, and remains queryable after project reopen.

Normal DOS and full-machine sessions attach a bounded automatic tracker. It
invalidates current bindings before execution, input, restored state or writes,
then compares source bytes and recaptures the stopped CPU's page tables before
publishing fresh bindings. No guest helper, inserted interrupt call, code patch
or manually supplied mapping is required. Inspect `session.tracking_status()`
or JSON `debug-tracking`; registry history remains queryable after close/reopen.

The automatic path and two explicit evidence paths have different meanings:

- The automatic tracker owns its capture and invalidation sequence. A normal
  DOS launch can retain its launch lifetime when the backend advertises native
  `lifecycle.dos_guest_exit` tracking. This is the original launched target's
  lifetime, not exclusive ownership of child allocations. Unsupported backends
  retain a separate observation episode for each stop and report that ceiling.
  DESQview uses a source-qualified native lifecycle provider described below.

- `runtime-map` records a relationship supplied by the caller. Its evidence
  label, reference and SHA-256 retain attribution; they do not authenticate a
  running machine, fetch the reference, or prove task ownership. This remains
  true when the caller chooses `kind: "recorded"` rather than `"modeled"`.
- `runtime-map-snapshot` additionally checks a local retained memory snapshot
  against a bounded source-object span, outside declared relocation fields. It
  qualifies only that compared extent at the capture's context. It does not
  establish continuous ownership, the rest of an object, a mapping in another
  task, or the runtime meaning of an excluded symbolic operand.

## Address and identity layers

Use `runtime-objects PROJECT [--version N]` to obtain the admitted object IDs and
bounds. LE objects have one-based IDs such as `1` or `"le:1"`. Generic mapped
regions use their reported `"region:<hexstart>"` identity; that start is an
address, not a region ordinal. An original MZ carrier may expose a separate LE
source view parsed from the same full executable. That does not change the
project's original mapped image or make its mapped digest equal to an LE view.

Keep these identities separate:

1. Original container SHA-256 and file provenance.
2. Selected source object, object offset and bounded extent.
3. The task's project byte version and its own mapped digest.
4. Recorded run, fresh task-incarnation ID and capture epoch/context.
5. Runtime linear/physical addresses and explicitly recorded selector metadata.

A task's `external_id` is an attributed handle, window label or caller task name.
It is not a unique lifetime identity. The same run cannot have two active
incarnations with that external ID. After ending one, starting another task with
the same label creates a fresh incarnation. Ending an incarnation closes its active registry
bindings; it does not delete history. A local debugger run can supply retained
run provenance. An explicitly recorded or modeled external run remains declared
evidence, rather than an authenticated live session.

The registry supports `linear`, `physical`, `preferred` and `selector` queries.
Preferred LE addresses are static lookup keys. Selector queries require an
explicit selector and offset; the registry never uses `selector * 16` to infer
a protected-mode address. A direct map's optional `selector` is a descriptor
object with `value` (16-bit selector), `base`, inclusive `limit` and `bits`
(16, 32 or 64). The explicit base supplies the offset-to-linear relation and
the mapped span must fit its limit. It is attributed caller evidence, not an
observed hidden segment cache. Use object-local offsets and explicitly recorded
relations instead of a single whole-program load delta.

## Public operations

The Python names below correspond to JSON/CLI names with hyphens. JSON requests
also require the normal `project` parameter.

| Operation | Required parameters | Optional parameters |
| --- | --- | --- |
| `runtime_task_start` | `run`, `external_id`, `evidence` | `version`, `capture_epoch` |
| `runtime_task_end` | `task`, `evidence` | |
| `runtime_map` | `task`, `object_id`, `object_offset`, `length`, `linear_start`, `evidence` | `physical_start`, `selector`, `mapping_context`, `replace` |
| `runtime_map_snapshot` | `task`, `snapshot`, `object_id`, `object_offset`, `length` | `snapshot_offset`, `replace` |
| `runtime_unmap` | `task`, `bindings`, `evidence` | |
| `runtime_map_checkpoint` | `task`, `evidence` | |
| `runtime_map_restore` | `task`, `checkpoint`, `evidence` | |
| `runtime_objects` | | `version` |
| `runtime_tasks` | | `run`, `offset`, `limit` |
| `runtime_mappings` | `task` | `at`, `offset`, `limit` |
| `runtime_resolve` | `task`, `address` | `space`, `at`, `selector` |
| `runtime_mapping_events` | `task` | `after`, `limit` |

Creation returns identifiers under `task`, `binding` or `checkpoint`, plus the
relevant event sequence. Retain those returned identifiers rather than deriving
them from addresses or labels. Event queries are paged; `at` selects recorded
history, not an independently observed moment of guest execution.

An evidence object has exactly the declared provenance fields:

```json
{
  "kind": "recorded",
  "reference": "private-receipt:one-observed-stop",
  "sha256": "<64 hexadecimal characters from the cited evidence>",
  "note": "Bounded observation; task ownership is separately qualified."
}
```

`kind` is `recorded` or `modeled`; `reference` and the SHA-256 are required.
The placeholder above must be replaced with the actual evidence identity.
Notes remain attribution, not permission to strengthen a qualification.

## CLI and JSON workflow

Write operations take one UTF-8 JSON object through `--definition-file`, at
most 4 MiB. The file contains the operation parameters from the table, without
`project`. Duplicate keys, nonfinite numbers, non-object roots and combined
file/direct parameter forms refuse. The file is data; the tool never executes
instructions or commands contained in it.

```sh
fdisbull runtime-objects /private/game.fdb --version 1
fdisbull runtime-task-start /private/game.fdb --definition-file /private/task.json
fdisbull runtime-map /private/game.fdb --definition-file /private/map.json
fdisbull runtime-tasks /private/game.fdb --limit 100
fdisbull runtime-mappings /private/game.fdb TASK_ID
fdisbull runtime-resolve /private/game.fdb TASK_ID 0x1b8000 --space linear
fdisbull runtime-mapping-events /private/game.fdb TASK_ID --after 0 --limit 100
```

For agents, the JSON-line interface accepts the same parameters directly:

```json
{"method":"runtime-mappings","params":{"project":"/private/game.fdb","task":"TASK_ID"}}
```

To bind a capture, start the registry task before taking its qualifying local
snapshot. If the current capture epoch is not yet known, take a baseline
`debug-memory-snapshot` on the owned paused guest solely to learn that epoch.
Register the task with that explicit epoch and the intended task label, then
take a new qualifying snapshot. The adapter requires the artifact to have been
created after registration; a fresh task incarnation cannot reuse an old capture.

The immutable snapshot records run, source, version, address domain,
caller-declared task label, mapping identity and capture epoch. Use its local
artifact ID with `runtime-map-snapshot`. A foreign FDB's artifact
ID is not a local artifact and is not silently attached. Matching container
hashes do not erase the distinction between two projects' mapped versions.
For this path, `runtime-task-start` must record the snapshot's explicit
`capture_epoch`, and its `external_id` must match the captured task label. The
adapter checks run, source, version, task label, epoch and byte extent; a caller
cannot supply an arbitrary mask to exclude inconvenient bytes. Only declared
loader fixup fields are excluded, and at least one independently comparable
source byte is required.

JSON-line numeric parameters are JSON integers. The CLI accepts hexadecimal
address and selector arguments such as `0x2000`; the definition file uses JSON
integer values for those same fields.

## Aliases, replacement and restore

Bindings are bounded relationships. Reverse resolution returns every matching
recorded alias; several linear ranges may legitimately name the same physical
frame. A physical address alone therefore cannot select one source object.

Overlapping active linear mappings require an explicit `replace` list. Unmap
and task-end events close lifetimes without rewriting the original records.
A checkpoint stores a selected task's binding set. Restore is permitted only
for the same active incarnation, closes its current relationships, and creates
fresh binding IDs with restore provenance. It does not resurrect an old closed
record or restore guest RAM. Use actual guest state restoration separately.

Recorded event order and an open registry lifetime do not prove that a manager
left a mapping unchanged between observations. Observe map/restore events or
capture fresh context before using a relationship for a later runtime action.

## QEMM, DESQview and reconstruction limits

For a normal full-machine session, select `guest_profile="desqview"`. The first
provider supports the exact original DESQview 2.8 manager identified by its
SHA-256 in the admitted FAT boot carrier. It follows the observed INT15 vector
chain and validates relocation-independent original manager code and the
manager's current task record/public handle linkage. An owned QEMU execution
breakpoint observes the original manager's natural XDI notifications; it does
not alter executable or guest code bytes. Source-backed task-to-process
containment is read separately from page mappings: the current task's owner
mapping and process record must agree with the original manager's independent
process lookup. Neither a PSP, CR3, menu number nor matching program bytes
supplies that relationship.

A qualified process CREATE/END closes only the source episodes and task aliases
belonging to that native process. An unrelated process END leaves other monitored
process lifetimes open. Task CREATE/END/FREE affects only that process and task
handle; reusing a numeric handle in another process does not join the episodes.
Each process episode has its own recorded identity/generation and a distinct
host episode identifier; task/source aliases retain their qualified owner in
the task's `automatic_tracking` document. A process END advances the reuse
counter, but its empty pending episode is labelled
`end-observed-awaiting-later-source`; it is not evidence of a new live process.
The global manager END is different:
it retires all manager episodes even when an individual task owner is no longer
readable. Unknown or inconsistent scoped containment retires continuity and
keeps the debugger stop visible instead of guessing a target.

The affected target and the emitting/current task are separate observations.
The original swap path can select a process mapping while DX still identifies
the emitting task. SWAP_OUT/IN therefore use qualified process-mapping evidence,
not an inferred task membership. Physical mapping changes still require fresh
stopped CPU, PTE and independent byte readback; containment alone proves no
physical relocation.

An initial attachment records an observation episode; earlier task/process
creation remains unknown. Only naturally observed CREATE notifications set the
corresponding creation flag. Implementation and authored containment tests are
separate from exact-build native qualification; these contracts do not claim a
native positive by themselves. Public breakpoint collisions remain visible, and internal event
handling obeys the original execution deadline and a finite event budget.

Queued public keyboard input is delivered only after bounded GDB execution has
actually started. It shares that lifecycle observation path. An asynchronous
QMP resume, restored checkpoint, write, missing lifecycle breakpoint, failed
provider validation or another coverage gap retires the old observation
episode. Later byte equality does not reconnect it.

Source discovery is a separate bounded operation: original COM/MZ projects,
same-carrier LE objects and bounded FAT12/16 COM/MZ members are supported. Raw
disk member fragments retain exact offsets in the owning raw source object;
they do not invent independent LE identities. Recursive 16-bit code candidates
are compared separately from writable data, with unresolved control flow and
unknown write targets retained. Protected LE discovery uses observed descriptor
and relocation evidence. Excluded loader operands remain symbolic. No match,
ambiguity, unsupported formats and exhausted budgets report unqualified
diagnostics instead of a guessed relation.

Bindings are split at linear page boundaries, retaining exact observed physical
translations even when adjacent linear pages have unrelated physical frames.
They are valid only for their captured stopped state. Automatic lifetime
evidence is recorded in each task's `automatic_tracking` document; the explicit
registry API's caller-declared attribution remains visible alongside it.

QPI page aliases and DESQview mapping handles are useful evidence inputs. QPI's
GetPTE range covers only the first 1088 KiB. A DESQview application menu number
is reusable, and a helper normally observes its own task. Neither promotes a
different application's allocation into a known lifetime.

The existing paused-machine translator owns CPU/A20/page-table observations.
The registry owns attributed source/object relationships and their history.
An object binding does not supply a missing descriptor, effective access
permissions, an unsupported paging walker, or instruction-execution evidence.

LE offset16 operands remain symbolic when their loader/selector interpretation
is unresolved. A matching nonfixup byte span does not qualify those operands or
make a native backing execution-ready. Keep static traversal, observed runtime
bytes, map lifetime and reconstructed execution as separate results.
