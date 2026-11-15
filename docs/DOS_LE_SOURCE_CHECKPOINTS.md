# Source-qualified LE checkpoints and capture history

The explicit `qemu-dos` LE checkpoint route persists a qualified stopped LE
relation together with a complete owned machine. It supports original unlayered,
unpaged protected32 LE carriers with A20 and one observed CPU. It does not
establish DOS task/allocation lifetime. DOSBox-X remains default and retained.

```python
saved = debug.save_le_source_state('point-a.json', max_bytes=128 * 1024**2)
# Execute to another stopped endpoint; select/admit LE source again as needed.
restored = debug.load_le_source_state(saved['artifact'], timeout_ms=60000)
assert restored['le_source_checkpoint_restored'] is True
assert restored['protected_source_rebound'] is True
assert restored['source_binding_restored'] is False
```

Capture requires an installed qualified LE handle and performs full fresh source
admission/binding before capture. This refreshes the handle; callers must use the
returned/current binding rather than keeping an old handle. Fresh observations
bracket machine capture under one lock/deadline. A single database transaction
publishes the machine artifact, LE companion and joint completion receipt. The
companion pins retained carrier/application/version/producer identities, original
admission/binding references, object placements, GDT material, stopped CPU and
canonical source-instruction proof. Native state remains the separate owned
machine format; no original executable is changed.

Kind `le-source-state`, format `fdisbull-qemu-dos-le-checkpoint-1`, identifies the
companion. Its `size` is JSON payload size; `charged_size` includes the linked
machine payload. `max_bytes` limits the full charge, must exceed the 8 MiB
descriptor reservation, and cannot exceed 128 MiB. The project-wide 256 MiB
runtime-artifact cap still applies. Saving another native snapshot can grow the
private QCOW2; capture budgets account for the actual archive size.

Restore validates source, recipe, immutable references, creation/completion
receipts and their capture order before spawning. It restores the machine,
re-admits LE source and compares the saved canonical location/instruction,
placements, GDT and CPU before publishing completion or clearing a selected-undo
freeze. Binding IDs and capture epochs are newly issued; saved handles are
historical evidence. The result's `artifact` remains the linked machine ID;
`le_source_checkpoint` identifies the selected companion. The original MZ live
ranges stay retired and `_owned_machine_restored` remains set. A failed proof,
publication or deadline check closes/quarantines the uncertain owner and leaves
no valid new history cursor. Cleanup preserves the primary failure.

## Explicit stopped-capture history

```python
history = debug.le_rewind_start(max_steps=2, max_bytes=160 * 1024**2)
point_a = history['cursor']
# Execute/input normally, then stop and explicitly bind a qualified LE view.
point_b = debug.le_rewind_record(advance='capture')
restored = debug.le_rewind(history=point_b['history'], node=point_a)
```

`le_rewind_start`, `le_rewind_status`, `le_rewind_record` and `le_rewind` use the
separate `fdisbull-qemu-dos-le-history-1` provider. It reuses immutable DAG
revisions, pending intents, branch retention and explicit node restoration, with
separate LE busy/cursor state and owner/handle/epoch/producer fingerprints. An
external bind/unbind or unrecorded mutation invalidates the LE live edge before
its effects. Internal LE capture does not borrow MZ history's busy exemption.

This first provider records one stopped full checkpoint per call:
`count=1, advance='capture'`. Stepping is unsupported. Intervening execution or
physical gameplay is an **unobserved interval**, with no instruction-history or
deterministic-replay claim. History charges both companion and machine bytes.
Cold attachment inspects retained history and yields no live connection; an
explicit node restore re-earns machine/source proof and then publishes a valid
cursor. Native process ownership ends when its context/server closes.

## Agent and offline interfaces

Capabilities are `le_source_checkpoints` and `le_source_histories`. Live JSON
methods use `debug-save-le-source-state`, `debug-load-le-source-state` and
`debug-le-rewind-start/status/record` / `debug-le-rewind`. Saved-script operations
omit the `debug-` prefix and require explicit `backend: "qemu-dos"`. Names,
budgets, timeouts and capture-only options are literal; artifact/history/node
references may resolve earlier results. Scripts reject malformed later LE
options before earlier steps execute and inherit the script deadline.

`project.debug_state_info(companion)` statically validates the source recipe,
linked artifact/receipt joins and source proof without a guest. Exact companion,
machine and history exports remain private. Existing MZ `load_state`, state
forks, Anchor Stone loads, ordinary histories, frame timelines, trials and
selected CPU/RAM anchors do not accept the LE companion as their checkpoint.
Their formats and source-ownership checks are unchanged. New LE checkpoint
success can complete full machine recovery while its old selected projection
remains invalid.

This contract is a stopped LE source qualification. Task/allocation lifetime,
active layered source views, aliases, automatic step/frame histories, LE trials
and LE selected undo require separate contracts. It does not qualify full
DOSBox-X parity or backend removal. No CI is dispatched by these APIs.
