# 0.21.0 development candidate: progressive scenes and separate text play

Finalization note: version **0.21.0** supersedes this development snapshot. See
[release notes](RELEASE-0.21.0.md) and the corrected
[verification record](VERIFICATION-0.21.md). The original PQ capture below was
found to precede completed room initialization; release qualification uses both
direction values, a settled landing range, and a distinct destination scene.

This is an untagged source candidate, version **0.21.0.dev0**, based on
`ce9dc5e73b6a780fa1bc6dc6601c83e05b90638f`. The installed shared release remains
0.20.0. No 0.21 release, remote merge, tag or system promotion is implied.

The implementation follows [PR #13](https://github.com/seeker-cyber-maker/fDisBull/pull/13)
at `351c6f3c4af6c92100a605cdbeb88b1b524ed94f` and the stacked
[PR #14](https://github.com/seeker-cyber-maker/fDisBull/pull/14) at
`87d1079a49dd448dd43e80f84d81896bf1f42bf9`. Their retained design documents
describe a larger recovery pipeline. The implemented, tested slice is below;
the draft semantic vectors are not a claim that full UIL or AGI exists.

## Three separate responsibilities

1. **fDisBull recovers and qualifies knowledge.** Immutable workflow revisions
   bind the executable, mapped code, supplied resource inventory, scene revisions,
   supported actions, unresolved dependencies and evidence. One qualified action
   is usable while unrelated research stays explicitly incomplete. Publishing a
   new revision does not mutate an action already in flight.
2. **The live host executes original game behavior.** It freshly checks context,
   resources and availability, sends the declared input or assistance, and records
   observed outcomes. The public text projection omits investigator-only names,
   memory references, guards, source paths and private errors. Opaque tokens
   authorize a fresh context; they are not portable object identifiers.
3. **`fdisbull-player` interprets commands independently.** Its separate wheel has
   no fDisBull dependency. It resolves public targets, asks for clarification,
   and supports passive `look`, `examine`, `inventory` and `help`. It can connect
   to the live host, or interpret an explicitly authored multi-context text slice
   with guards, inventory, ordered effects, ticks and events. Recovered content
   and the player are separate inputs. The authored interpreter is not an AGI
   implementation and does not certify an original-game reconstruction.

Read [progressive workflow API](PROGRESSIVE_SCENES.md),
[public projection and host](TEXT_PROJECTION.md), and
[standalone player format](TEXT_PLAYER.md) for the concrete schemas.

## Explicit teleport and room jumps

`session.assisted_travel(plan, timeout_ms=...)` uses identity-bound runtime
fields, verifies every expected byte before the first mutation, forbids writes
to the declared room field, and records attempted writes and inputs even when
their results become unknown. A debugger stop is retained; it is not resumed
to finish the route. A late matching predicate outside the budget is incomplete.

Within-room travel edits qualified actor fields. A room jump places the actor
at a qualified portal and sends original guest input; the engine performs the
room transition. Its postcondition must include the required destination
position/readiness, rather than accepting a new room byte alone. The PQ trial
exposed exactly that early room-change boundary and now waits for the original
landing coordinates and stopped movement.

These operations deliberately change traversal and its time/hazard exposure.
Their receipts and text replies disclose assistance. They do not establish the
same complete world state as walking. Unknown portals, arbitrary target rooms,
and a complete path planner remain outside the qualified interface.

The normal movement cleanup also checks whether the engine already stopped at
an exit. It avoids a second latched directional press in that case, while still
releasing owned physical keys when necessary.

The initial workflow format qualifies the original byte version and refuses
dispatch with an active RAM or execution layer. Layered saved experiments remain
separate. Keeping the same pixels after a code change is not requalification.

## Actual original-game verification

The same producer APIs, scene workflow, text bridge, player and travel operation
were exercised on private copies of two supplied GOG editions. The replay is
`examples/agi/verify_progressive_text.py`; it requires the user's game directory,
backend and a fresh private work directory. It ships no game data or checkpoint.

| Fixture | Matched within-room task | Original and assisted room transition |
| --- | --- | --- |
| PQ1 AGI executable SHA-256 `29ddd3f3b91d65b6eade156608d7915e3c8b7f47701cb226ff119b717f3e8bd7` | Room 6, X 79..81, Y 120, both direction values 0 | Hallway 6 to adjacent room 5; settled destination X 20..24, Y 130. Original route moves down and right; assisted route places near (143,150), then uses observed input cleanup and the destination scene check. |
| KQ1 AGI resource SHA-256 `5ab189ebd9822739962767afe0113853e23797ef16dd4784d2dc93423934fb74` | Room 1, X 129..131, Y 100, both direction values 0 | Room 1 to room 8; settled destination X 0..4, Y 100. Assisted route places near (154,100), then uses original transition input and the destination scene check. |

KQ uses its original COM launcher and runtime-decrypted interpreter. Its writer
was located and checked in live memory; no static translation from the COM
launcher to the AGI interpreter was assumed. In both games, an execution stop
at the observed `get.pos` code establishes DS:DI, a checked object-zero pointer
establishes the actor record, and original transitions corroborate room/previous
room observations. Restoring a checkpoint invalidates and recreates bindings.

Each matched within-room comparison has three walking and three assisted trials
from the same private native checkpoint. Both use the text command resolver,
fresh scene checks and the same destination range, Y, room and neutral-direction
postcondition. Explicit post-restore preparation is outside each command timer.
Native scene checks use fourteen selected pixels plus qualified memory; known
animated flag pixels were excluded after a negative trial. These are bounded
recognizers, not a proof of every possible modal or animation state.

The evidence includes a blocked open-menu check, stale prior-context refusal,
resource drift refusal with zero guest progress, native PNGs and instruction
traces. Resource changes are tested only in the private copy and restored with
byte-for-byte readback. Source and final working game manifests match.

The isolated installed player also connects to a newly launched host, restores
the private state, performs walking and assisted actions, and observes the
neighboring context. The client has no fDisBull module installed. This verifies
the process boundary rather than merely importing both packages together.

See [verification evidence](VERIFICATION-0.21.md) for measured results, hashes,
test counts and platform limits.

## Cost, confidence and remaining boundaries

The measurements compare warm, authored route contracts. They are not cold
discovery, autonomous puzzle completion, or a sequential-versus-on-demand
analysis benchmark. No agent model inference was timed. Host load is not a
controlled performance laboratory. Guest progress and wall time are separate.
Choose assistance when skipping traversal improves the experiment's expected
reward relative to its cost, and retain the changed control policy in evidence.

The user's report that Dot reached “bow to the king” in 49 seconds is retained
as a historical task reference. This candidate has not repeated that complete
task under a matched startup, observation, assistance and timing protocol. Its
bounded room-route speedups must not be presented as beating that run.

The AGI-language parser under separate development can supply recovered content
or qualified action definitions. This change does not duplicate a whole AGI
decoder, guess unsupported opcode semantics, or export a complete UIL world.
Resource inventories bind the caller-supplied tree; they cannot prove that an
incorrectly selected tree contains the whole edition. Workflow serialization
applies to cooperating workflow/host callers; unrelated raw debugger calls must
not advance the same guest concurrently.

The offline local text package contains its own private rules and future
transitions. Interface filtering is not filesystem isolation. Use the host-side
projection when a player must not receive those definitions.

## Candidate packaging

The core and player are separate wheels at the same candidate version. Core
source distributions and the tool ZIP include the player source through explicit
whitelists. The player wheel guard rejects foreign roots, omitted modules, game
data and databases. Repeated player builds use restricted package discovery so
generated build directories cannot become extra packages.

The Linux offline-kit scripts derive their version from project metadata and
require the matching independent player wheel alongside genuine decoder and Z3
dependencies. Native CI is configured to exercise the new APIs in both DOSBox
profiles. Configuration is not a completed Linux CI run.
