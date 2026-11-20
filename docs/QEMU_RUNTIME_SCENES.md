# QEMU runtime-memory scenes

`QemuDOSProcessSession.scene_check(scene, *, object=None, compact=False)` and
`scene_assert` accept an explicit `fdisbull-scene-2` runtime-memory observation
profile. This is a separate passive contract. It does not qualify the existing
frame-backed scene campaign, grant completed-frame identities, or change the
default DOS backend.

`scene_wait` also accepts this explicit profile. It observes the same predicates
at stopped boundaries and may advance the native virtual clock between them.
Its executing contract is described below; check/assert remain passive.

```json
{
  "format": "fdisbull-scene-2",
  "observation_profile": {"kind": "runtime-memory", "version": 1},
  "context": {"state": "authored key released", "triggers": ["guest IRQ1"]},
  "match": {"runtime_memory": {"binding": "scene-state", "offset": 8, "length": 1, "hex": "00"}},
  "objects": [{
    "name": "actor",
    "context": {"state": "observed actor state", "triggers": ["explicit byte witness"]},
    "visible": {"constant": true}, "ready": {"constant": true},
    "enabled": {"constant": true}, "outcome": {"constant": false}
  }]
}
```

Save it with `Project.debug_save_scene`. Storage supplies the actual original
source hash, selected byte-version ID/hash and stable object IDs. Each read
revalidates the canonical manifest hash, its source identity, and object ownership.
A revision chain cannot switch between scene-1 and scene-2. Existing scene-1
storage defaults and its screenshot/evidence requirements are unchanged.

Predicates support constants, `all`, `any`, `not`, runtime-memory byte/mask
comparisons and typed scalar `compare` expressions with integers, `add`, `sub`
and `wrap`. Every branch is validated. Source-address reads, pixels, engine
references, `before` baselines, actions, geometry, navigation, handlers and
coordinate domains are rejected. A profile requires at least one explicit RAM
reference. Limits are 1 MiB per definition, 64 objects, 4,096 expression/predicate
nodes across the selected scene and all competing matches, depth eight, 64 KiB
combined distinct requested RAM extents, 64 candidate scenes per exclusive group
and 256 stored scene roots per selected version. Runtime capture receipts are
bounded to 256 unique reads and 4 MiB; predicate evidence, including repeated
cached reads, is bounded to 1 MiB. Every predicate checks the inherited wall
deadline. The first failed read or exhausted limit stops evaluation and prevents
further native reads. Its result is unavailable/incomplete; an expired deadline
preserves partial evidence on the exception without late publication.

Binding names or IDs in a saved scene are references, not capabilities. The caller
must first bind the actual live RAM with an explicit expected-byte witness. Full
restore advances the runtime epoch; the saved scene remains inspectable, but its
old RAM binding is unavailable until an explicit fresh witness is admitted.
These bindings do not infer task ownership, allocation lifetime or source mapping.
Selected CPU/RAM undo similarly invalidates bindings whose frozen-state identity
changed. A fresh permitted read-only witness can inspect the frozen state.

The adapter requires the explicit native virtual-clock profile and a stopped
single-vCPU owner. One owner, restore epoch, lock and inherited host deadline cover
all RAM reads and persistence. CPU/address context and the native virtual clock
must remain unchanged across a completed observation. A failed early observation
has `capture_context_verified: false` and no claimed final clock bracket. It performs no guest execution,
input dispatch, frame capture or RAM mutation. Existing leases remain untouched.

Results use `fdisbull-scene-observation-2`, include `observation_profile` and
`completion_scope: "declared-runtime-predicates"`, and omit `frame`. The shared
status meanings remain `matched`, `mismatch`, `ambiguous` and `unavailable`;
`complete` is true only for matched/mismatch within this declared profile.
`scene_assert` raises `SceneError` unless matched. Both methods persist the exact
observation in `debug_scene_observations`; compact replies retain the observation
ID for retrieving full evidence. Saved observations are historical, not fresh
authority. A late publication timeout preserves any already committed receipt.

The saved-script operations are `scene-check` and `scene-assert`. Every known
literal is validated before earlier script effects; a result reference defers
only its own unknown scalar value and is revalidated at actual dispatch. Whole
scene references cannot prove unknown content during script admission.

Frame/action consumers reject this profile, including ordinary `SceneHandle`,
click/act/navigation and the legacy frame-scene wait, movement scene contexts, assisted travel, spatial map
contexts, workflow actions and text projections. Screenshot overlays, coordinate
domain audits and scene-1 bundle import/export also refuse it. QEMU exposes no
generic scene handle or action methods through this extension.

Host contracts are exercised in `tests/test_qemu_scenes.py`; native optional
witnesses in `tests/test_qemu_scenes_native.py` use the authored IRQ1/BIOS-tick COM
fixture to observe real make/break state and full native restore invalidation.
Those native cases require the existing explicitly selected private QEMU runtime,
FreeDOS boot image, firmware, mcopy, NASM and checkpoint tool. Authored tests are
not evidence of execution until a pinned receipt records their run.

## Wait for declared RAM predicates

```python
result = debug.scene_wait(
    "ready-scene", object="actor", guest_ms=5000,
    timeout_ms=5000, slice_ms=100, compact=False,
)
```

The Python signature matches the existing scene wait. JSON uses
`debug-scene-wait`; saved scripts use `scene-wait`. The QEMU route requires
`runtime_scene_wait`, the native virtual-clock extension, one active owned DOS
process, an explicit scene-2 runtime-memory manifest and current RAM witnesses.
Frame-backed scene-1 remains refused. `guest_ms` is an integer in 1..120000,
`timeout_ms` in 1..60000 and `slice_ms` in 1..1000; Boolean values are refused.
Known invalid literals or profiles in a script are refused before earlier
script effects. Resolved values are revalidated before timeout clamping.

The first poll runs while the guest is stopped. If it matches, the wait returns
without execution or input dispatch. Otherwise, only a complete mismatch permits
the next bounded native clock interval. Every poll uses the existing conservative
scene evaluator, including competing scene recognition and visible/ready/enabled
requirements for a selected object. Ambiguous, unavailable or failed observations
end the wait; missing evidence never becomes a false predicate to poll again.

One absolute host deadline covers original-owner lock admission, manifest and
source checks, input-plan observation, all polls and intervals, and persistence.
It intersects the caller, session, native owner and control-channel bounds. The
selected manifest, competing manifests, original owner/process/project, byte
version and runtime/restore epoch stay pinned. Frozen selected CPU/RAM undo may
still be inspected with check/assert and a fresh witness, but executing waits
refuse it. Full restore requires a new explicit RAM binding.

A genuine DOS exit/TSR advances the process capture epoch. Final publication
accepts only that exact transition described by the returned process and
termination receipts for the original PSP, including a recorded post-close
descriptor when present. It keeps checkpoint, owner, source and selected
projection identity checks. It does not infer a new live source or RAM witness.

After every interval, the native stop takes precedence over another predicate
read. A breakpoint, watchpoint, exception, hook, guest exit/TSR, host stop or
interrupted input terminates with the exact original stop and no later poll,
continuation or automatic input release. Hook registration does not authorize
automatic continuation in this profile. A known pending stop ends without
starting an interval. Only an ordinary native clock-budget stop permits another
poll. Elapsed guest time is measured from observed `virtual_ns`; requested slice
lengths are not elapsed-time evidence. A predicate first observed after the
total guest budget has been exceeded cannot turn that timeout into success.

Pending fixed input uses the generic QEMU wait's existing admission policy. A
wholly undelivered owned batch, press, typing or physical click may be admitted
if its remaining fixed span plus one requested poll tail fits strictly inside
the total guest budget. That full interval becomes the first slice. Partial,
uncertain, retrace or motion plans refuse before execution. An immediate scene
match leaves the arm pending and unchanged. A native stop may cancel an input
suffix; its actual delivery receipt and held leases are retained for explicit
caller resolution. The wait does not replay, repair or release input, and a
scene predicate alone does not prove guest consumption.

The result remains `fdisbull-scene-observation-2` with
`completion_scope: "declared-runtime-predicates"`. Its `wait` member uses
`fdisbull-scene-wait-1` and retains the initial/final observed clock, measured
nanoseconds and milliseconds, original polls and runs, input-plan admission,
terminal outcome and exact stop when present. Success requires
`status: "matched"` and `complete: true`. Terminal non-success raises
`SceneError` with the persisted result; a timeout or debugger stop is incomplete.
`clock_progress_complete: false` distinguishes an exact retained stop lacking
full clock readback from measured elapsed time. Compact replies omit bulky
polls while retaining the observation ID for the complete stored evidence.

There are at most 1,000 polls and 8 MiB of canonical persisted JSON, including
the final observation/stop duplication and metadata. `wait.evidence_bytes` is
the exact stored JSON byte count. Each scene evaluation keeps its existing
individual limits. A size crossing stops further work and publishes no wait
row; the exception retains the already observed prefix, including the receipt
that crossed the limit. That unpublished failure prefix can exceed the stored
document ceiling. It is not truncated into a successful observation.

Unexpected native, deadline or publication failures preserve the primary error
and attach `scene_wait_result`. Any committed receipt is named separately as
`retained_observation`, so a failed operation cannot relabel a saved successful
row. After attempted execution or loss of a control channel, cleanup quarantines
and closes only the original owner. A bounded JSON output artifact is retrieved
through the existing output-export path; retrieving it does not repeat the wait.

Python and saved-script results retain the canonical address types stored in
the observation. Successful JSON replies, including exported output artifacts,
apply the existing public address presentation: integer address fields become
hexadecimal strings, including DOS allocation bounds and driver header addresses
inside retained runs. Verify the complete JSON result against that public
projection of the canonical result; verify stored and reopened observations
against the canonical result itself. No evidence fields are omitted.

JSON failures retain the primary evidence as `error.result`. If a native error
already owns that result, its separate observed prefix is retained as
`error.scene_wait_result`; a script keeps the same two fields on the failed
step. These error receipts retain their canonical address types. The primary
type/message is unchanged. A spilled failure envelope has an
output artifact and `retry_safe: false`; retrieve its evidence without replaying
the operation. If native closure prevents clock-budget readback after a
validated DOS return, the original native error and terminal result survive;
that failure is not a normally completed, persisted terminal wait.

Host contracts are in `tests/test_qemu_scene_wait.py`. The finite
[native gate](QEMU_SCENE_WAIT_GATE.md) covers ten cases and at most eleven owned
VM lifetimes. Its prepared source is not native qualification. This route leaves
frame-probe, absolute clicks, scene-1, actions/navigation and the broader DOSBox
replacement campaign open; the migration inventory remains partial/unqualified.
