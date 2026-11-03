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

## Align one bounded input leg

`control.align(targets, *, position, start, stop, settled, guard=None,
context=None, label="coordinate", budget=20000, slice_ms=10,
max_polls=2000, max_still_polls=150)` shares sampled coordinate alignment.
The [new KQ1 pair](evidence/native-alignment-coherence-2026-11-01/README.md)
qualifies this source slice with exact goals and one declared approach range.
Other games, ranges and backend adapters still need their own material checks.

Targets are finite `x`/`y` scalars or inclusive two-value ranges. The helper
chooses one axis or a unit diagonal whose path intersects those targets;
unspecified axes must remain unchanged. It does not plan around obstacles or
split a turn into several legs. The adapter owns coordinate units, source
safety, room/domain admission and the ordinary start/stop inputs.

```python
state = control.align(
    {"x": [129, 130]},
    position=lambda s: {"x": s["x"], "y": s["y"]},
    start=lambda direction: start_ordinary_direction(control, direction),
    stop=lambda: stop_ordinary_motion(control),
    settled=lambda s: s["direction"] == 0 and s["control"] == 0,
    guard=source_safe_state,
    context=lambda s: (s["session_id"], s["room"], s["view"]),
    budget=2_000, slice_ms=10,
)
```

These callback names illustrate an adapter binding, not a qualified route.
`position(state)` supplies both axes, `start((dx, dy))` receives the chosen
direction, `stop()` supplies the ordinary stop, and `settled(state)` must return
a boolean. An optional `guard(state)` must return exactly `True`; a supplied
`context(state)` must remain equal throughout the leg. All callback and owned
stop execution must pass through this controller and account measured progress.
The leg's local guest cap also applies to that execution, alongside the global
guest and wall limits. Python callbacks are not forcibly interrupted.

The journal's `fdisbull-native-alignment-1` record retains actual sampled
positions and guest progress, start/stop attempts, the last observation and
completion or failure. A source-supported range can avoid an expensive exact
coordinate proof where the particular pixel is immaterial. Overshoot, drift,
stalled progress, changed context, unsafe state or an unresolved stop retains
the attempt and latches the controller. There is no automatic reversal, retry,
teleport, restore or recovery input. An initially settled goal needs no input.

## Bracket a frame and state without claiming atomicity

`control.capture_frame_state(capture_frame, *, status_reader=None,
state_projector=None, require_fresh=False, baseline_frame_id=None,
baseline_frame=None, expected_session_id=None, guest_ms=1000, slice_ms=20,
max_polls=64)` wraps `fdisbull.frame_coherence.capture_frame_state`.
The same new KQ1 pair exercises the default SDK adapter, paused brackets and
freshness at three settled visual boundaries across the two sessions.

At a meaningful settled visual boundary, the helper reads a stopped-status /
state / stored-frame / state / stopped-status bracket. It binds the controller's
session, mode, frame ID and capture revision, retaining each returned value.
`state_projector` may select the material state fields to compare while the
full before/after observations remain available. Missing observations or
identity/state mismatches return `complete: false`; a stable bracket remains
non-atomic and does not prove that the image depicts the exact CPU state or
that an interface is ready.

The default SDK adapter combines `session.status`, `frame_probe([])` and a
second `session.status`. The probe supplies frame metadata without a PNG;
it does not supply the paused-state fact. Both status reads must explicitly
say stopped, and all three responses must agree on session and revision.
Every raw part is journaled before another read can fail. A custom
`status_reader` may supply an equivalent flat binding for another adapter.

```python
observation = control.capture_frame_state(
    capture_qualified_frame,
    require_fresh=True,
    baseline_frame={
        "session_id": previous_session,
        "mode_id": previous_mode,
        "frame_id": previous_frame_id,
    },
    expected_session_id=previous_session,
    guest_ms=1_000, slice_ms=20, max_polls=64,
)
```

`capture_frame` returns a frame reference, SHA-256 and native metadata with
`source: last_completed_guest_frame`. With the default `require_fresh=False`,
the bracket requests no execution. When freshness is required, cheap status
polls precede capture; an already newer frame needs no advance. Without a
baseline, the initial status supplies it. A full `baseline_frame` binds prior
session, mode and ordinal; a bare `baseline_frame_id` is explicitly the caller's
assertion that the ordinal belongs to the currently pinned session and mode.
All required execution still goes through the owner/controller and its
admission/stop checks. Starting the operation uses strict controller admission;
an already exhausted controller cannot start a new capture operation. If an
admitted freshness slice reaches exactly the global cap, its final read-only
bracket may complete, but no next native slice is permitted.
Protocol session IDs are scoped to their backend server. Keep a baseline in
its owned live run; invalidate it after restoration or context replacement.
An ID comparison does not authenticate an independently supplied record.

Use freshness only when a new appearance or presentation boundary matters,
rather than capturing on every movement poll. Never resume a foreign stop or
an unsafe water/failure state just to obtain a picture. A stale-frame timeout
returns an incomplete record with its last status, without an automatic extra
capture or execution. The caller may retain a diagnostic frame under its own
failure-capture policy. Exceptions retain partial results, latch the controller
and re-raise. `metadata.captured_ticks` describes render time;
`metadata.state_revision` is the capture RPC revision, not a render-CPU revision.

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

## Supplied JPC-RR evidence and its limits

The user-supplied `KQ1-JPC-RR-TAS-Evaluation-2026-11-01.zip` is a separate
evidence source: 20,755,106 bytes, SHA-256
`52040dc1d6b0c25c64255c9e3af68e432b267ac5382a72aa1348d391b4521118`.
A read-only inspection matched all eleven explicitly named analysis resources
to the selected local originals and checked selected movie/capture hashes,
four supplied stock-playback records and landmark PNG/RGB hashes. It did not
independently replay the movies or rerun the native-frame scan.

The authoring records retain checkpoint loads and discarded timing trials;
the supplied playback records describe separate fixed power-on movies.
Their recorded crossing is room 41 `(154,90)` to room 40 `(154,44)`, not a
room 39 bottom bridge clip. No room 39 state record was found in the two scoped
authoring event logs. The useful methodological lessons are bounded alignment,
explicit checkpoint lineage and separate frame freshness; this package does
not qualify the new helpers or establish Robb's original input schedule,
hidden-state equivalence or a universal timing rule. Original archive contents
remain private and are not bundled with the tool.
