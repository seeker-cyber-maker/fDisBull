# fDisBull 0.21.0

**Source documentation for release finalization.** Version 0.21.0
extends fDisBull's scene and runtime investigation tools with resumable,
revision-bound workflows, an independent text player, and qualified assisted
travel. This document describes the implementation and its evidence boundaries;
it is not evidence that release CI passed or that a package was published.

## Changes

- **Progressive scene workflows** persist immutable revisions of observed
  resources, scene facts, supported actions, unresolved dependencies and
  evidence. A workflow can offer a qualified action while keeping unrelated
  research incomplete. Revisions preserve earlier knowledge and action
  bindings; a revision change does not rewrite work already in flight.
- **Separate `fdisbull-player` package** provides a standalone text command
  interface. It can interpret a declared text slice on its own, or connect to a
  live host. The host's public projection is derived from the original runtime
  and filters investigator-only names, memory references, guards, source paths
  and private errors. The player wheel has no fDisBull dependency; core and
  player packages are independently built and checked.
- **Automatic live-turn persistence** restores the latest private checkpoint
  before the first turn and saves after every model turn, outside model-issued
  commands. The standalone runtime atomically persists its declared state,
  inventory, context, tick and events. Native hosts retain an experiment,
  debugger controls and verified runtime-binding recipes in the private project.
  Corrupt or incompatible saves stop play; only a missing save starts fresh.
  A partially completed action stops the command batch and is checkpointed as
  partial, so later commands cannot silently run past it.
- **Bounded external-agent story sessions** record narration, chosen commands
  and actual outcomes. They limit turns, actions and agent-response time, and
  recheck the wall budget before dispatch. They do not preempt a blocking
  backend operation. The included scripted agent fixture verifies the protocol;
  autonomous LLM puzzle solving is not claimed. See [live player](PLAYER_LIVE.md).
- **Qualified movement and room transitions** use fresh scene checks and
  recorded outcomes. Within-room teleport edits only qualified actor fields.
  A room jump places the actor at a qualified exit and sends original guest
  input so the game engine performs the transition and initializes the room.
  The destination contract includes the declared settled landing range, actor
  and control direction, and a pinned destination scene. Optional observed
  cleanup stops surviving latched movement once. PQ1's earlier room-byte-only
  observation was intermediate and is not accepted as a completed landing.
- **Movement cleanup** detects when the engine already stopped at an exit,
  avoids sending a second latched directional press, and releases physical keys
  owned by the operation when needed.

## Verification scope

The bounded original-game cases use private copies of Police Quest 1 and King's
Quest 1. Their declared settled room transitions are PQ1 room 6 to 5 at
`(X 20..24, Y 130)` and KQ1 room 1 to 8 at `(X 0..4, Y 100)`.
Matched within-room trials, automatic resume, refusal cases,
resource drift, native screenshots and traces are described in the
[candidate record](UNRELEASED-0.21.md) and the
[verification record](VERIFICATION-0.21.md).

These results qualify the recorded contracts and tested paths. Assisted travel
changes traversal, elapsed guest time and hazard exposure, so it does not
establish an equivalent complete world state to walking. The trials are not a
cold-discovery benchmark, autonomous puzzle completion, or a comparison against
the historical 49-second “bow to the king” report. No universal performance
claim follows from the measured authored routes.

The implementation does not provide a full AGI interpreter, full UIL/world
model, whole-game reconstruction, arbitrary room jumps, or deterministic
replay. Unknown room behavior remains unknown. A caller-supplied resource tree
is bound as supplied and is not proof that it contains an entire game edition.
Saved layered experiments remain separate: an active RAM or execution patch
layer is refused by the original-byte workflow rather than treated as the
original executable version. Host serialization governs cooperating workflow
and host callers; unrelated raw debugger calls must not advance the same guest
concurrently.

Voice is planned future work. Qwen TTS is available locally according to the
user; speech recognition and a complete voice interaction still need to be
qualified. This release implements text turns, automatic persistence and the
external agent protocol, without built-in speech input or narration audio.

No game data, saved states or project databases are included in source or
packages. macOS results are development-host evidence only; macOS is not a
release platform qualification. Linux ordinary and native workflows must both
pass against the exact final source commit before tagging. Their required
configuration is recorded in the workflow files; configuration alone is not a
passing run. The [release-status record](RELEASE_STATUS.md) will record actual
run identities and publication state when established.

## Release state

At source finalization the latest published and installed release remains
0.20.0. Tagging requires successful exact-commit CI; the annotated tag and
GitHub Actions supply that readback. Publication and shared-system activation
remain separate actions. See [release status](RELEASE_STATUS.md).
