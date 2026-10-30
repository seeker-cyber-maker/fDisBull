# KQ1 bow-to-king assisted-travel benchmark

## Result

On 29 October 2026, fDisBull 0.21.0 completed the same bounded King's Quest I
route from a fresh room-1 start to score 4, the successful bow response, and the
complete king dialogue. The native dot-mode window was enabled for every run.
The original game and runtime stayed private; this record contains aggregate
timings and generic acceptance guidance only.

| Route | Successful / attempted | Route time median (range) | Inclusive time median (range) |
|---|---:|---:|---:|
| Walking | 3 / 3 | 8.469 s (8.232–14.205) | 11.324 s (10.761–16.839) |
| Five-leg assisted travel | 3 / 4 | 5.200 s (4.723–5.600) | 7.624 s (7.122–8.158) |

Among successful assisted attempts, median route time was 38.6% lower and
inclusive time 32.7% lower than walking. The sample is small and one assisted
attempt failed before the bow, so these figures describe these runs only. The
failure's room and coordinates were correct, but its frozen actor-frame gate
matched 7 of 11 sprite pixels instead of the required 8. Its cause is unknown;
an unchanged retry passed. A complete failed frame was not captured.

Route time began after startup, title handling, binding and source preparation,
immediately before traversal, and ended after the full quest-frame check.
Inclusive time began before project creation and ended after debugger and
project contexts closed. It includes startup and shutdown but excludes game
copy and output-directory creation. A 15-second viewing hold was excluded.
Assisted route time includes its per-leg verification overhead. No headless
comparison was run, so dot-mode overhead is unknown. An older 48.66-second
single-run report used a different environment and verification boundary and
is not comparable. A separate first-leg-only assisted probe was slower and is
not part of the five-leg result.

The benchmark used release 0.21.0 at source commit
`a253600b94f7006f8962ada842eba699279fdbfe`, kit SHA-256
`5f031f181e72c365ec14424215d8c2bf3ab174ce5a9f7a3c1931d77beb1a975f`, and
backend SHA-256
`45fb6ffebe01de70599403a10a4a7d4a3b003621e910c36cc63449846ad3d346`.
The game ran in fast-forward with audio disabled. Every attempt began at room 1,
`x=110`, `y=100`, score 0. Only successful attempts reached the accepted
endpoint; the failed attempt is counted in the attempt total and excluded from
successful-route timing summaries.

## Route and evidence boundary

The five assisted legs used qualified room transitions and within-room
positioning: original west exit 1→2; position at the castle entrance in room 2;
original north exit 55→54; original west exit 54→53; and throne approach in
room 53. Position assistance used fresh runtime bindings and a verified redraw
bit. Original guest input performed room exits, door interaction, bow, score
change and quest dialogue. The route did not write room, score or quest flags
directly.

Early probes showed that memory-position arrival can precede a rendered actor
frame. Final runs pinned the destination scene and used bounded completed-frame
checks before accepting arrival. A memory predicate alone is therefore
insufficient evidence for rendered arrival. The final success gate separately
checked the throne scene, actor presence, successful bow response, score 4 and
the complete king dialogue.

These observations support only the tested edition, route and runtime. Assisted
travel changes traversal and timing; the result does not establish world-state
equivalence with walking, general game performance, or a universal speedup.

## Handoff for room geometry and scene gates

The release coder is implementing bounding boxes and room masks. The following
acceptance work is intended to complement that implementation, not prescribe a
new API. Proposed cases should use authored synthetic rooms, sprites and masks;
they are design requirements, not tests claimed as run by this benchmark.

- Bind geometry to a specific scene revision and resource edition. Reject stale
  masks or actor bounds after the scene changes.
- Check the actor footprint, not only its center. Distinguish traversable
  landings from walls, moat edges and hazards; require a safe landing region.
- Keep memory-position arrival, rendered arrival, original room exit,
  interaction range and latched-motion cleanup as separate observations.
- Use animation-tolerant actor-presence gates without weakening the actual
  destination and interaction success checks. Partial or stale captures cannot
  count as arrival.
- Reconcile unknown write or input outcomes before retrying. Never infer that a
  timed-out operation had no effect.
- On every failed attempt, automatically retain the full completed frame,
  relevant state/checkpoint and a compact receipt so the failure can be
  diagnosed without reconstructing it from a partial pixel count.
- Keep a frozen paired benchmark that reports every attempt, startup-inclusive
  and route-only timing, success criteria, failures and exact runtime identity.

No implementation, new automated native-suite result for this documentation PR,
private game asset, screenshot, save, project database or raw game code is
included in this handoff. The benchmark observations above came from native
game runs.

## Continuation usability notes

Further play reached the gold egg and gold walnut through the original parser
and inventory/score behavior. No confirmed fDisBull defect was found. Two
controller lessons may help long modal-heavy routes; related native coverage
already exists in the keyboard and checkpoint tests.

- A `guest_time` result means the requested guest-time slice completed; it does
  not guarantee queued input releases have drained. Before queuing another
  operation, inspect keyboard state and wait in bounded guest slices until
  `pending_events` and `owned_keys` are both zero. Preserve the live session when
  an action is rejected so the queue can be reconciled.
- Loading a checkpoint invalidates runtime bindings and the current framebuffer
  until a completed frame is available. Rebind observations for the restored
  session and request a bounded frame-producing guest slice before capturing or
  asserting a scene. Include that wait in the operation's guest-time budget.

These are controller workflow notes, not new claims about backend behavior; the
existing tests explicitly cover keyboard draining and framebuffer invalidation
after restore.
