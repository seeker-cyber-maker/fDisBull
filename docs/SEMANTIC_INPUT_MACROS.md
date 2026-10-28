# Semantic input and observed movement (0.20 development)

A macro set is an immutable, content-addressed control vocabulary bound to an exact project byte version and source hash. Names have no global meaning. Select the set explicitly by ID; the receipt retains the semantic call, typed arguments, expanded physical operations, authority labels and execution results. Definitions survive project restart; physical key ownership and runtime addresses do not.

```python
controls = project.debug_define_macros({
    'format': 'fdisbull-macro-set-1', 'name': 'latched-controls',
    'macros': {
        'start': {'parameters': {'direction': {'enum': ['left', 'right', 'up', 'down']}},
                  'steps': [{'op': 'keyboard.press', 'key': '$args.direction',
                             'hold_ms': 60, 'gap_ms': 50}]},
        'stop':  {'parameters': {'direction': {'enum': ['left', 'right', 'up', 'down']}},
                  'steps': [{'op': 'keyboard.press', 'key': '$args.direction',
                             'hold_ms': 60, 'gap_ms': 50}]}}})
result = session.macro(controls['id'], 'start', args={'direction': 'left'})
```

This example expresses a latched profile: a complete second same-direction press is the stop command. A held profile instead uses `keyboard.key-down` with an `as` binding, returns `{'lease': '$binding.lease'}` in its declared `outputs`, and passes that token to a stop macro's typed `input-lease` parameter and `keyboard.key-up`. Tokens are owned by one session, consumed once, and invalidated on restore/close. Saving state rejects queued input and held keys. Atomic `keyboard.press`/`keyboard.type` keep their existing meanings.

Expansion is declarative, limited to 1,000 operations and eight nested levels. Cycles, unsupported operations, unsupported capabilities, unknown IDs, bad typed arguments and structurally malformed later calls are rejected before input. `player-input` is the default permitted authority; `authoring` and `diagnostic` require explicit selection and grant no extra permission. There is no embedded host language. Dynamic result fields can still be unavailable at execution; a failed script with newly owned active input closes the session. A successful macro may retain an active key only by returning its lease. Unreturned active input closes the session and makes the macro fail.

`debug_export_macros(id)` returns a hash-checked metadata envelope; `debug_import_macros(envelope)` requires the exact source and mapped-version hashes. It reads no host files and includes no game image, checkpoint or database. As with all authored metadata, inspect provenance strings before external redistribution. Same names do not shadow one another.

## Bounded movement

`session.move` (saved-script operation `move`, JSON method `debug-move`) takes:

- explicit `macro_set`, `start` and `stop` calls; movement control macros contain physical input only;
- named scalar `observations`, a destination `until` predicate and a `settle` predicate;
- `progress={'fields':['x','y'], 'samples':8}` or an explicit completed-frame window with `frames` and `frame_field`;
- separate movement `guest_ms`, total host `timeout_ms`, `slice_ms` and reserved `cleanup_guest_ms`;
- optional `context` predicate and scene geometry (`scene`, `position={'x':'x','y':'y'}`, `target=[x,y]`).

Predicates use `{'field':'x','op':'in_range','value':[65,69]}`, comparisons `eq/ne/lt/le/gt/ge`, and bounded `all/any/not`. Observations may use normal project `memory`, `runtime_memory`, register/status paths or a completed-frame path. Runtime views require `bind_runtime_memory` with a freshly resolved address, expected/masked identity bytes and provenance. They are read-only, session/epoch/source bound, and must be resolved again after restore. They do not weaken normal static-address validation.

Initially satisfied destinations cause no guest execution. Otherwise the actor must initially satisfy `settle`, with typed zero pending/owned keyboard counts. Caller-owned input is rejected without being released. Final context, geometry and destination checks are repeated after cleanup; missing input observations cannot become success. The controller runs measured guest slices; arrival wins over the final stall sample. All unchanged progress fields over the declared window yield early `blocked`, with `blocked_unknown` unless current geometry corroborates a nearby boundary. The authentic diagnostic screenshot is captured with `hooks=False` before stop cleanup, so screenshot preparation cannot alter the failure. Capture errors stay in the failed receipt. A breakpoint, watchpoint, hook or guest stop is preserved, and uncertain input cleanup closes the owned session.

Reaching a predicate is not yet success: stop input must be consumed, the queue empty, no physical keys owned, `settle` true, and the destination retained. Cleanup has its own reserved guest budget within the shared host deadline. Geometry is re-observed, never silently corrected to fit the run. An initially unknown footprint or later contradiction fails; a geometry-bound destination also requires the observed point to equal its declared target. Use a destination range without a geometry target when exact-point sampling is inappropriate.

A blocked route never becomes successful because of a later state edit. Teleport recovery, full AGI control-map extraction, watched-write progress windows and automatic path planning are outside this implementation. Scene geometry is a versioned authored model whose evidence status must distinguish observation, inference and source derivation.

See [scene navigation](SCENE_NAVIGATION.md), [bounded proofs](BOUNDED_PROOFS.md) and [0.20 verification](RECONCILIATION-0.20.md) for the tested scope.
