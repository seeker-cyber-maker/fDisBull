# Full DOS checkpoints in saved scripts

The `qemu-dos` saved-script profile admits `save-state`, `load-state`,
`save-anchor-stone` and `load-anchor-stone` when the owned process has the
full native DOS checkpoint extension and a private checkpoint disk. This closes
a script-route gap in existing checkpoint methods. It does not qualify complete
checkpoint parity or change the default backend, fallback policy or retirement
gate. DotBox maintains the separate DOSBox implementation.

## Public contract

| Script operation | Arguments and defaults | Result |
| --- | --- | --- |
| `save-state` | `name='dos-process-checkpoint.qcow2'`, optional `max_bytes=None` | Existing full `state` artifact receipt |
| `save-anchor-stone` | `name='anchor-stone.qcow2'`, optional `max_bytes=None` | The same checkpoint contract through the existing alias |
| `load-state` | `artifact`, optional `timeout_ms=60000` | Existing verified process-restore receipt |
| `load-anchor-stone` | `artifact` | The same restore through the existing alias; inherits the script deadline |

Names are literal safe filenames. A byte limit is `None` or a literal strict
integer in `1..134217728`; a supplied load timeout is a literal strict integer
in `1..600000`. Booleans, floats and numeric strings are rejected. Anchor load
has no timeout argument. Artifact arguments are existing nonempty identifiers
or references such as `$saved.artifact`; resolved values undergo the same type
and checkpoint-family checks before dispatch.

Save the reusable declaration with `backend: qemu-dos`, then execute its saved
ID. A live declaration may infer the backend using the existing script rules.
For an already admitted stopped process:

```python
route = project.debug_save_script("checkpoint-route.json", {
    "format": "fdisbull-script-1",
    "backend": "qemu-dos",
    "steps": [
        {"op": "save-state", "as": "saved"},
        {"op": "step", "count": 1, "timeout_ms": 2000},
        {"op": "load-anchor-stone", "artifact": "$saved.artifact", "as": "restored"},
        {"op": "assert", "value": "$restored.source_binding_restored", "equals": True},
    ],
})
result = debug.script(script_id=route["script_id"], timeout_ms=10000)
```

The script profile accepts the matching modern process envelope
`fdisbull-qemu-dos-process-qcow2-v2`, or the existing file-aware process envelope
when that is the selected session's exact format. It rejects raw-machine,
entry-v1, owned-machine and LE artifacts. It does not fall back to an entry
loader or translate checkpoint formats. Use the distinct owned-machine or LE
operations for those contracts. Direct Python methods retain their existing
separate profile selection.

The full expanded declaration is checked before route publication or any step.
Known literal artifact IDs are checked for kind, selected version, format and
source/version metadata at admission. References are resolved and checked at
their own step. Native payload/hash/archive/runtime/process/control/workspace
verification still belongs to the existing full loader. A runtime-dependent
refusal can therefore follow completed earlier steps; their evidence remains
in the failed script report. Caller-owned transactions are rejected.

## Deadline and owner rules

One absolute host deadline includes the QEMU script's existing timeline gate,
checkpoint owner lock, capture, snapshot job, transport queries, publication,
restore and script report. Tighter session, VM and QMP/GDB bounds are intersected.
An alias, replacement VM or subsequent step cannot renew that allowance.

Saving under a composed request carries its remaining budget to the actual
QMP/GDB boundary and snapshot job. Successful publication that returns too late
is retained as historical evidence and reported as a failed step. The script
also checks the checkpoint return boundary, so a final checkpoint cannot become
a successful step merely because no next step tests the clock.

The existing full loader is the only source of restoration authority. It
verifies the fresh stopped destination, reaps the original owner, keeps the
same reentrant VM lock, restores eligible source/control state and advances the
capture/checkpoint epochs. Its selected CPU/RAM recovery guard is preserved:
a failed full restore does not clear a frozen projection. Stale runtime RAM
bindings, scene observations and input tokens require fresh admission.

After successful replacement, the prior session, VM, QMP and GDB bounds are
restored independently; a broader session limit must not erase a tighter
continuing native limit. Temporary load and script deadlines do not leak into
the next independent call. The original captured lock is released even after
replacement. Existing held/scheduled-input refusals and restored frame-key
ownership cleanup remain in force.

## Failure and persistence evidence

A failed step stops the route before the next action. The report retains the
completed prefix and any actual native/checkpoint receipt. If uncertain native
capture or restore requires closing an owner, a secondary close failure cannot
replace the primary error. A post-return deadline failure does not replay a
checkpoint or fabricate a new source lifetime.

No report publication starts after the inherited deadline has expired. The
original step error instead carries `script_result`, an observed in-memory
`fdisbull-script-result-1` prefix. A report-store failure also carries that
prefix. If an earlier native error already owns `result`, that result stays
separate and the secondary report-store error is recorded as
`script_publication_error`. This narrow envelope is exposed by JSON
`debug-script`, including unexpected native exception types only when the
checkpoint-script code has attached the verified envelope. Unrelated error
serialization is unchanged.

The existing output policy can externalize the full JSON success or failure
response. Its `retry_safe: false` marker means export the evidence; do not rerun
the script. A late committed checkpoint or result artifact is not rolled back.
When a store fails before returning an artifact identifier, the tool does not
invent one or claim successful publication.

Three saved objects have distinct identities: the reusable `debug_scripts`
declaration, the route-copy artifact in `script_artifact`, and the returned
script-result artifact. The stored report equals the canonical returned result
without its additional top-level `artifact` key. Python/FDB evidence retains
canonical integer addresses; successful JSON applies the existing complete
public hexadecimal address projection. Error evidence retains canonical
values. Comparisons must preserve all fields and respect those exact shapes.

## Host verification

The focused host module has 72 passing cases. The affected checkpoint,
full-loader, script, input-cleanup and output selection passed 573 cases; these
counts overlap. The real project/FDB, archive hashes and controls, canonical
checkpoint methods, full-load guard, snapshot protocol and replacement-owner
path are exercised with authored QEMU ownership/DOS-observation seams and real
QMP/GDB protocol framing. These tests do not execute a guest or prove VMState
fidelity.

The initial red checks demonstrated the refused saved route and a 50 ms parent
deadline being ignored by a save that accepted a 60 ms QMP reply. New checks
cover malformed whole-route and resolved arguments, profile refusal, caller
transactions, both alias pairs, gate contention, tighter prior limits,
selected-freeze recovery, late checkpoint and report publication, native error
receipt retention despite close/store failures, cold FDB reopen and complete
canonical/public JSON equality. Error export is checked without any new native
dispatch. Prepared native source is not counted as a passed native gate.

## Prepared finite native acceptance

`tests/test_qemu_checkpoint_script_native.py` defines exactly two cases:

| Test suffix | Entry and checkpoint pair | Maximum VM lifetimes |
| --- | --- | ---: |
| `test_native_saved_process_checkpoint_script[state_anchor]` | Python saved ID; `save-state` → `load-anchor-stone` | 2 |
| `test_native_saved_process_checkpoint_script[anchor_state]` | JSON saved ID; `save-anchor-stone` → `load-state` | 2 |

Each case uses the existing independently authored `CHECK.COM` fixture, a
standard clock, audio off, standard retrace, released input and no layers,
hooks, task views or file workspace. It records the initial verified DOS
allocation, then saves a 19-step route containing three preparation
instructions, a mid-program save, one INC instruction, opposite-alias restore,
exact CPU/RAM comparisons and one ordinary post-restore INC canary. That canary
must produce the same next CPU/RAM state on the replacement owner. This is a
RAM/CPU continuation claim, not a graphical restoration claim.

The only VM launches are the initial owner and the one restored owner in each
case: **two cases, four VM lifetimes maximum**. Offline cold Project reopen
checks exact route/checkpoint/report bytes and hashes without another VM. JSON
uses the full public projection of one captured canonical result, verifies
real nested process-address conversions and exported byte length/SHA, and
requires no reexecution to export. Witness files include owner/epoch/lock,
source/media, checkpoint, route and canary results. Native inputs and FDBs stay
outside Git.

Required environment variables are `FDISBULL_QEMU_DOS`,
`FDISBULL_QEMU_DOS_BOOT_IMAGE`, `FDISBULL_QEMU_DOS_MCOPY`,
`FDISBULL_QEMU_DOS_FIRMWARE` and `FDISBULL_QEMU_IMG`; set
`FDISBULL_REQUIRE_QEMU_DOS_OS=1` for required admission. Use the sealed combined
QEMU producer and its matching qemu-img and firmware. The previously verified
full FreeDOS boot input has SHA-256
`552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc`.
The minimal runtime boot image lacks the configured command interpreter path
and is not an interchangeable input for this lane.

Each test establishes a 90-second cumulative host limit before preparation;
startup is at most 15 seconds and the saved script at most 30 seconds,
intersected with that original end. The restored constructor receives remaining
time, not a fresh exact public allowance. Root's separately reviewed controller
must add one shared outer deadline, bounded close/reap, no retries, immutable
source/test/producer/media/fixture pins, maximum four owners/eight QEMU and boot
logs, and explicit output/storage bounds. This document is not permission to
launch. Root owns native admission, execution and outcome reconciliation.

Native status for this newly admitted script profile is **prepared, not run**.
The two cases do not qualify raw or entry-only scripts, file-workspace,
protected/V86/task checkpoint combinations, graphical/device/audio continuation,
general game compatibility, or DOSBox retirement.
