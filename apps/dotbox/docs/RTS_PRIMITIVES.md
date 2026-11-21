# RTS action primitives and dynamic observations

Decision: 19 November 2026. Camera movement, entity selection, logical or native
group selection, command choice, target submission, context click and a held
pointer gesture are independent operations. A planner can compose them according
to the current situation. The API contains no automatic select–Move–target
sequence and does not automatically repeat an unconfirmed action.

## Implemented scope

`dotbox.rts_world` validates bounded RTS observations, projects them into the
existing scene schema and compares two observations. `dotbox.rts_actions`
prepares individual requests and supplies a single-owner `RtsController` for
qualified synchronous providers. `dotbox rts` exposes the offline observation
and request tools. The `rts` guide and authored example ship in the ordinary kit.

These are public Python and CLI contracts. The included example and test
provider are authored fixtures. No Dune II memory reader, semantic live binding,
native group selection or production held-gesture driver is installed by this
slice. Existing desktop ownership and diagnostic native-input policy remain in
force. The prior original-game Move and minimap-drag study supplies private
evidence for adapter development; it is not universal RTS behavior.

The [Dune II economy guide](DUNE2_ECONOMY.md), installed as
`dotbox guide --topic dune2economy`, records a completed original first mission.
It supplies observed construction, harvesting, command and event conditions for
future bindings, including placement-preview freshness, reused entity slots and
delayed presentation. Its private native trial does not change the public
provider boundary described above.

## One primitive per request

| Primitive | Explicit arguments | Separate observation needed |
| --- | --- | --- |
| `pan_view` | World `position` in the declared map space | Rendered camera and fresh screen mapping; unit orders are independent |
| `select_entity` | Current `entity_id` | Actual native selection; selecting an ally or enemy does not grant control |
| `select_group` | `group_id`, explicit `entity_ids`, `mode` of `logical` or `native` | Logical membership or separately qualified native selection |
| `choose_action` | `action_id` for the currently selected commandable entities | Armed command/target mode or an immediate command outcome |
| `select_target` | A typed `target` containing exactly `entity_id` or world `position` | Acceptance of the currently pending command; eventual arrival or attack result remains separate |
| `context_click` | Typed `target` | The effect of the qualified right-button binding in this exact context |
| `drag_pointer` | Named `surface`, frame-pixel `start`/`end`, `button`, aggregate guest/frame/host bounds | Source consumption, held movement, release and semantic effect, each checked by the provider |
| `respond_to_event` | Current player-visible `event_id` and explicit `response_id` | The actual modal/story response and resulting phase |

`select_entity` and `select_target` express different intents. The former
changes the selected object. The latter submits a parameter to an already
observed pending command. Selecting an action never supplies its target as a
hidden follow-up. A right click is not assigned a universal Move, Cancel or
Attack interpretation. A drag is not automatically box selection or a drop.

The held gesture is one bounded primitive. Its physical press, held movement
and release stay inside its qualified provider transaction; callers cannot
leave an unbounded button hold between separate controller requests. A drag's
integer limits are aggregate maxima: at most 4,000 guest milliseconds, 400
frames and 15,000 host milliseconds at this generic boundary. Providers may
require smaller limits. These ceilings are not sufficient timing profiles,
minimum durations, or evidence that any particular game consumes the gesture.

An ordinary action requires the `gameplay` phase, explicit current input
readiness and no event whose blocking status is true or unknown. An explicit
event response has a separate route and still needs current readiness and
provider admission. The system does not click through story material to regain
tactical control. Logical grouping is input-free planning and can remain useful
while gameplay input is unavailable.

## Current world observations

The closed `dotbox-rts-world-1` document binds executable identity, edition,
provider/session/branch/revision, observation ID and provider context token.
It declares map coordinates, camera world/screen bounds and frame identity,
phase/readiness, entities, native selection/pending command, logical groups and
observed events. Each domain record retains an evidence reference. A provider
must include relevant resource/profile identity in its edition/context binding;
an executable hash alone does not establish identical game resources.

The model keeps these entity properties separate:

| Property | Meaning |
| --- | --- |
| `owner_faction` | Reported stored affiliation, or unknown |
| `controller_faction` | Reported effective controller, or unknown |
| `relation_to_player` | Reported self/ally/enemy/neutral relation, or unknown |
| `commandable` | Explicit current player command permission, or unknown |
| `visibility` and `audience` | Whether the entity is currently visible, remembered offscreen, hidden or unresolved, and whether it can be described to the player |
| `identity_scope` and `incarnation_id` | Observation-local reference or a provider-qualified allocation lifetime |

An ally can be visible and selectable while remaining uncommandable. A hazard
or NPC can have a faction tag without inheriting ordinary unit behavior. A
player-owned unit can have a different effective controller. None of these
properties is calculated from the display label or inferred from another field.
Unknown permission withholds a command. Enemy/NPC selection can still be a
supported inspection action when its own route is qualified.

Only current visible player-audience entities enter the player scene. The
world can retain offscreen/internal observations without revealing their names,
positions or event text in narration. An omitted entity is not evidence that it
was killed. An expected reinforcement is not a visibly arrived ally. Predictions
and guide expectations belong in the broader model, separately from this current
observation packet.

An entity slot is not a durable identity. Observation-scoped members become
unresolved at a later observation. Incarnation-scoped members persist only under
the same source/edition/provider/session/branch and exact qualified incarnation.
Reused slots and restored timelines cannot silently substitute a new unit into
a logical group. The controller reports unresolved members instead of replacing
or dropping them from the requested membership.

Logical groups contain explicit entity references. They do not change native
selection or dispatch per-member clicks. `mode: native` requires a distinct
qualified provider binding. Unsupported native grouping is refused without
falling back to a box drag or an automatic series of unit orders.

## Mission events and changing circumstances

Events carry a current occurrence ID, kind, text, audience, blocking status,
observation ID and evidence. Providers can report reinforcements, an affiliation
change, a hazard sighting, an objective update, a story prompt or a mission
result without forcing them into a player-input sequence. This contract does
not invent a script interpreter or infer a particular mission's schedule.

Every request binds the full validated world digest. An event or offscreen
change can therefore invalidate an old request even when its visible pixels
look unchanged. The bounded scene retains the digest internally, so omitted
entities/events cannot leave an apparently identical scene binding. The digest
does not disclose the internal facts themselves.

`diff_world` compares compatible observations and retains evidence/identity
limits. It does not infer that the preceding input caused every difference.
Concurrent NPC motion, timed arrivals, changing control and scripted mission
effects can occur independently. It also does not interpret disappearance from
a partial observation as destruction.

## Controller and provider contract

The Python entry points are `prepare_action(world, primitive, arguments)` and
`check_action(request, world)`. Both are pure and return `execution:
not_performed`. A serialized request is not a live dispatch token.

`RtsController(provider)` is confined to its constructing thread. It retains
only one pending intent. `prepare(world, primitive, arguments)` replaces an
older pending intention, obtains read-only provider admission for a game action,
and returns an opaque controller-owned single-use token. Logical grouping needs
no game binding. `cancel()` discards the token without any provider call.

`execute(intent)` consumes the token before calling the provider, checks a fresh
world, rechecks admission and rejects a changed ownership or binding identity.
It invokes exactly one `provider.execute` for a game primitive. It does not
automatically wait, observe again, choose another command, repeat input or clear
held input after an uncertain result.

The synchronous provider methods are:

```python
observe() -> world
admit(request) -> admission_or_none
execute(request, *, expected_admission) -> receipt
```

Admission binds the request hash, immutable binding ID/hash, opaque control
token, enabled/readiness booleans and evidence. `control_token` must encode all
relevant ownership and generation/lease dependencies. A new ownership epoch
must change it even if the game observation is unchanged. Evidence labels and
an `enabled: true` field do not independently qualify a live provider.
Providers use `request_digest(request)` for the canonical admission/receipt
hash, and `world_digest(world)` for a world identity. Both use sorted compact
JSON with ASCII escapes. Complete requests must fit 16 KiB before admission;
callers need not reproduce the canonical encodings themselves.

**The provider must enforce the live fence inside `execute`.** Immediately
before each physical effect it must verify the exact context, current supported
ownership, binding and readiness. A paused native adapter must serialize the
whole transaction and refuse foreign stops. A desktop adapter must use its
qualified cooperative input path. The controller's preceding read is not an
atomic native fence and cannot prevent changes inside an arbitrary callback.

For a held gesture, the provider additionally proves source-press consumption
before held movement, preserves exact owned-button state, enforces shared
budgets, and releases only known owned input. It must not continue native calls
after uncertain transport or a foreign stop. Missing semantic or bounded-wait
capability means refusal, not a guessed fallback.

Receipts retain `action_sent`, `accepted`, `complete`, `effects`, evidence and
an optional after-observation separately. Receipt completion is scoped to the
declared binding, not to a mission or broader player goal. Delivery does not
prove acceptance; accepted Move does not prove arrival. Observed differences
do not establish a unique cause.

An exception, asynchronous callback, malformed delivery receipt or unknown
delivery state latches uncertainty and blocks subsequent provider calls from
that controller. A fresh `prepare` cannot clear it. Known acceptance survives a
later invalid observation. Recovery is an independent qualified operation;
only after recovery should a new controller be created. No automatic cleanup or
retry is hidden in a `finally` block.

The controller also retains its coherent observation head. Equal revisions
must have identical content, revisions cannot regress, and a changed source,
provider session or restore branch requires a new controller. A logical group
readout cannot resurrect a member using an observation older than that known
head. Malformed or unavailable read-only admission is a pre-dispatch refusal;
it does not imply that input was sent. A provider-call exception still latches
uncertainty because the provider's runtime state is unresolved.

## Observe through short bounded steps

The callback helper `dotbox.bounded_wait.bounded_wait` composes one observation
budget from short native steps. It accepts an already-fenced synchronous `step`
callback; it opens no runtime or input connection and supplies no new ownership
or observation authority.

An original Dune II test requested 25,000 guest milliseconds with a 1,900-frame
ceiling. That single native operation reached its 15,000-millisecond host
timeout despite a separate 30,000-millisecond enclosing request budget. The
owner stopped further native calls and closed the process; the partial guest
outcome remains unknown. The [bounded-wait receipt](evidence/bounded-wait-2026-11-19.json)
records that failure, the offline checks and one subsequent live observation.

```python
from dotbox.bounded_wait import bounded_wait

# The caller has already qualified this callback and one outer host deadline.
result = bounded_wait(
    fenced_step,
    max_frames=1900,
    max_guest_ms=25000,
    slice_guest_ms=5000,
)
```

Each call receives the remaining aggregate frame allowance and at most the
remaining guest-time allowance or `slice_guest_ms`, whichever is smaller.
The slice limit is an integer from 1 through 5,000 guest milliseconds; aggregate
limits are 1 through 10,000 frames and 1 through 30,000 guest milliseconds.
Reaching the frame ceiling ends the entire observation even when time remains.
Slicing changes neither aggregate ceiling and never renews the enclosing host
deadline. The callback must enforce that same deadline and recheck its native
ownership, capability, stopped context and receipt provenance on every call.
Short guest slices do not guarantee a particular host execution speed.

The result uses the separate `dotbox-bounded-wait-1` aggregate schema. It records
the original limits, each slice's request and unmodified receipt, total completed
frames and guest milliseconds, and the aggregate stop cause. Receipts are copied
before a later callback can reuse its data. A frame limit takes precedence when
both aggregate ceilings are reached; the raw receipt retains the native cause.
The aggregate is not a native frame receipt or proof that construction, arrival
or another gameplay goal completed.

Malformed accounting, unknown or contradictory stop causes, and zero progress
raise an error before another callback. Callback exceptions propagate without
retry or cleanup calls. Earlier slices may already have advanced the guest;
the caller's journal must retain partial evidence and apply its terminal failure
policy. An error never authorizes replay of the observation or preceding input.

Forty-one authored helper cases and a 199-case integrated offline suite passed;
the smaller suite is included in the larger count. In a fresh original Dune II
run, the same 25,000-millisecond observation completed as five 5,000-millisecond
slices, totaling 1,753 frames within the unchanged 1,900-frame ceiling. All five
raw receipts matched the native journal, and no input or save/restore was sent
during that observation. The caller retained its original 30,000-millisecond
host deadline. This qualifies the accounting contract and this single live
observation; it does not establish a Dune II provider, native ownership, current
visibility or a universal host-time guarantee. The separate prepared-opening
readiness attempt still missed its 180-second profile, taking 285.051 seconds.

## Offline commands

Export the kit into a new directory and use its authored example:

```sh
dotbox kit-export --directory /private/rts-kit
dotbox guide --topic rts
dotbox rts primitives
dotbox rts validate /private/rts-kit/examples/rts_world.json
dotbox rts look /private/rts-kit/examples/rts_world.json
dotbox rts project /private/rts-kit/examples/rts_world.json
dotbox rts prepare /private/rts-kit/examples/rts_world.json \
  --primitive choose_action --arguments '{"action_id":"move"}'
```

`project` emits a valid `dotbox-scene-1` packet with no fabricated live choices.
Its packet can be recorded with the existing `SceneStore`/`dotbox scene record`
flow. `check REQUEST WORLD` compares a saved request with the supplied current
world; `diff BEFORE AFTER` reports observed changes. None of these CLI commands
opens a game or an input connection.

## OpenDUNE reference and original-game boundary

The source study uses OpenDUNE commit
[`ebea79aeba025be2fe9004570e9255044aacc0be`](https://github.com/OpenDUNE/OpenDUNE/tree/ebea79aeba025be2fe9004570e9255044aacc0be),
which expects Dune II 1.07 data. The retained original-game trial uses the
separately identified v1.0 executable. No OpenDUNE code is copied into these
modules and no original game assets enter the public fixtures.

Useful source distinctions include singleton `Unit_Select` versus AI `Team`,
ordinary viewport right-click recentering versus earlier TARGET/PLACE branches,
`Unit_GetHouseID` versus `House_AreAllied`, and sandworm target priority without
an alliance exclusion. Fremen palace reinforcements use their own house and HUNT
behavior; they are not ordinary player-selected troops. Hints, Mentat screens,
mission results and campaign animations have separate control phases. See
[`unit.c`](https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/unit.c),
[`viewport.c`](https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/gui/viewport.c),
[`house.c`](https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/house.c),
[`structure.c`](https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/structure.c),
and [`opendune.c`](https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/opendune.c).

These reference facts inform the contracts. Original v1.0 NPC behavior,
reinforcement schedules, right-click outcomes and story transitions still need
their own relevant evidence before a live binding can advertise them.

## Verification

The [verification receipt](evidence/rts-primitives-2026-11-19.json) binds the
final runtime modules and records 101 new public cases, an independent 113-case
run including 12 additional regressions, and the full repository result of
1,169 passed with 15 unconfigured native fixtures skipped. Final-source offline
integration reprocesses 21 retained original observations into four branch-bound
scene stores, with 80 stale/cross-branch store refusals and three cross-restore
diff refusals. No new native calls or commercial assets are part of this cut.
