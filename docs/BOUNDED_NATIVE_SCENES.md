# Shared native control and scene receipts

`BoundedNativeController` and `ReceiptAssembler` extract the common mechanics
from the KQ1 scene work. The game adapter still owns its source profile,
coordinate interpretation, safe-state predicates, explicit pending transitions
and owned breakpoint protocols. These helpers do not infer a game's semantics
or turn a supplied receipt into authenticated native execution.

## Ordinary-input controller

```python
from fdisbull.native_controller import BoundedNativeController

control = BoundedNativeController(
    debug, read_state=read_qualified_state,
    total_guest_ms=120_000, total_timeout_ms=90_000,
    journal=journal, inputs=inputs,
)
control.press("left", 100)
control.type_text("look")       # Does not press Enter.
control.press("enter", 300)
state = control.wait(lambda s: s["room"] == destination, "room transition",
                     budget=5_000, slice_ms=50)
```

The session provides `run`, `keyboard_state`, `keyboard_press` and
`keyboard_type`. Only original guest inputs are sent. There are no coordinate,
register, code or flag writes. An optional `admission_check` lets an adapter
refuse *before* either input or execution. An `input_advance` adapter preserves
a caller's overridden execution policy; it must account progress through this
same controller.

Accepted input and an idle queue establish delivery/settlement, not that the
game accepted the intended action. Keep the game-specific outcome check. Existing
saved scripts retain their own schema and bounded operations; this helper adds
no arbitrary callbacks to a saved script.

The journal records dispatch intent before transport, returned guest progress
and uncertain replies. Guest and wall budgets are separate. Waits inspect the
predicate initially, retain the last observation and measured progress, and
refuse local guest overshoot or wall expiry before reporting completion. Equality
at the guest limit is allowed when the goal is observed there. The wall deadline
is checked after observations, predicates and input-settlement reads as well as
before execution. Callbacks must themselves use bounded operations; the helper
does not forcibly interrupt arbitrary Python code.

An uncertain/rejected input, invalid progress, unowned stop or timeout latches
the controller. Further controller execution/input calls refuse. Inspect the
retained result and caller-owned guest state; do not instantiate a fresh
controller and treat that as recovery. Cleanup and readonly queries remain the
caller's responsibility.

An optional `stop_handler(result)` may return exactly `True` after handling a
stop it owns. It must retain its source/stop checks and use `account_guest` for
any execution it performs. The AGI adapter keeps its original print observer,
blocking-dialogue acknowledgement and source-specific watch handling. Unknown
hooks and guest errors do not become pending room transitions.

`status()` copies the controller's progress, blocked reason, input count, wait
records and last known state/keyboard observations. These are observations, not
a certificate of readiness or game completion.

## Assemble one evidence snapshot

```python
from fdisbull.scene_receipts import ReceiptAssembler

assembly = ReceiptAssembler(source_identity, runtime_policy, load_private_artifact)
inputs = assembly.inputs(captured_inputs)
observed = assembly.observations(
    records, expected_ids=["before", "after"],
    input_count=len(inputs), message_count=len(messages), require_progress=True,
)
receipt = assembly.receipt(observed, edges=[{
    "id": "walk", "before": "before", "after": "after", "complete": True,
}], artifacts=[{
    "role": "portable-test-summary", "visibility": "public",
    "path": "linux-tests.log", "sha256": summary_sha256,
}, {
    "role": "full-test-log", "visibility": "private", "sha256": full_log_sha256,
}])
```

Frame references use a path, SHA-256 and native metadata. Each artifact is read
and hashed once per assembly snapshot, within the aggregate byte cap. Returned
frame records retain metadata and hash while removing private paths. The loader
owns path confinement. A new assembly is needed when reading a changed snapshot.

Observation assembly checks exact ordered identities, duplicate/missing/extra
captures, count limits and chronology. It preserves valid partial records and
issues rather than silently pairing unequal lists. State typing and engine
conditions stay with the adapter. Last-completed frames remain last-completed;
monotone frame IDs do not establish freshness or atomicity with memory reads.

Receipt completion requires complete observations and explicit completed edges
whose endpoints exist in forward order. Edges may span intermediate captures.
It never follows from the absence of errors alone. This is completion of the
supplied-record assembly, not native authenticity, deterministic replay or
whole-game parity.

Artifact catalogs name role, visibility and digest, with a portable path for
public evidence. A private full log and its public summary have separate roles
and hashes. Byte-identical private and public copies of a selected screenshot
are permitted; no image is copied by this API.

## Retain failures independently

`retain_evidence([(label, callback), ...], report)` attempts every callback,
returns the original exceptions and appends persistence errors. It does not
overwrite the primary error or invent completion. The existing AGI retention
wrapper uses it for the journal, partial capture, predicate, original/copied
file integrity and final report. The route's final completion gate still needs
its explicit verdict plus successful teardown, integrity and persistence.

The bridge exporters now share frame/observation/input assembly. The ordinary
AGI controller shares transport, budgets and keyboard settlement, while the
specialized source observers keep their own bounded protocols. Source/backend
identity is bound once per stable run; this does not remove required per-stop
mapping checks.

For the original gameplay example, see [the bottom-row route](AGI_BRIDGE_BOTTOM.md).
The [shared-component verification](evidence/shared-native-scenes-2026-11-01/README.md)
records the new native pair, completed scene receipt and exact test scope.
The local source changes do not update installed packages or release a version.
