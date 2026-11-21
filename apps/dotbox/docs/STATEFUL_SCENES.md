# Game state, consequences and useful choices

Decision: 17 November 2026. The original game determines flags, inventory,
locks and outcomes. DotBox remembers provider observations, keeps menus tied
to the observed timeline, and helps Dot select useful suggestions. Dot can build
an [internal causal and predictive model](WORLD_MODEL.md), including rule
simulation for planning. That model does not independently commit predicted
effects to the player's game state or this observation store. A z-scene is a
current projection; Dot's world knowledge can be much broader.

The `0.1.0.dev4` offline slice implements a persistent observation store,
state-bound selection, provider admission gates, suggestion policy and passive
scene description. It does not implement live flag extraction, an asynchronous
game runner, speech or a connection from the menu to desktop input. Those
adapters must use the existing engine/scene/workflow contracts and qualified
input path. A separate fDisBull installation is not required by these tools.

## Remember what changed, including changes outside the room

Use the existing provider to read the relevant engine variables, inventory,
object state and script flags. Preserve their typed values and evidence. A
switch may unlock a remote door; picking up an item may start a timer or enable
a later conversation. A fresh internal observation can record those effects
without pretending that the player saw them happen.

The adapter publishes a coherent `dotbox-scene-1` packet after an observation.
Current facts may include internal offscreen facts as well as the permitted
description of the current scene. Use the existing `subject`, `predicate`,
`value`, `audience`, `observation_id` and `evidence_ref` fields. `null` can
represent an explicitly unknown value. A missing fact is not evidence of
absence, falsehood or an unchanged value.

Stateful packets add:

```json
{
  "state_context": {
    "provider_id": "current-engine-adapter",
    "session_id": "play-session-1",
    "branch_id": "timeline-1",
    "revision": 17,
    "context_token": "opaque-provider-context-token"
  }
}
```

This is a fragment, not a complete scene document. The token comes from the
provider's observation/action contract. A revision is an integer from zero to
`2^63-1`, assigned by the single observation publisher when the observation is
made, before work or messages can be reordered. It is not a worker's completion
counter, a cross-host timestamp or a substitute for the provider token. An
adapter whose native revision is not suitable must maintain this ordering for
its own observation stream while retaining the native token.

`SceneStore.record(packet)` binds the store to the source hash, edition,
optional resource-selection hash, provider, session and timeline. It accepts a
newer revision atomically. Repeating the exact current packet is idempotent;
an older revision, conflicting reuse of the same revision, or a different
binding is refused. A restore, restart or changed timeline uses a new branch
identity and a new store. Do not rewrite the old history to make it fit.

The store keeps the latest complete scene packet and the last reported current
fact for each entity/predicate. An optional fact `entity_id` names a stable
provider entity across rooms, such as a particular door, inventory object or
global script variable. Without it, identity is local to the scene and
subject; two rooms' objects both called "door" cannot overwrite one another.
Use provider identities rather than display labels when cross-room tracking
is intended. Entity IDs stay in the internal memory, outside player prose.
Facts omitted from a later packet remain
historical reports with their observed revision; they are not copied into the
new current scene. `memory()` is an internal view and labels whether a report
was observed in the current snapshot. Unknown remains unknown. Reopening the
store preserves these records; it does not make them freshly verified against
the live game.

A revision change invalidates selection from the earlier packet even if the
room, frame identifier and visible facts are unchanged. This deliberately
conservative rule handles offscreen consequences without an unreliable second
dependency engine. Refreshing a small packet and its action gates need not
reconstruct every scene or rerun the guide search. A worker's candidate still
needs current live verification before the lead can publish an observation.

## Four separate questions about an action

| Question | Source and treatment |
| --- | --- |
| Has the player discovered the target? | Current permitted facts and the provider's visibility rules determine the public view. An internal flag cannot introduce an unseen object or sound. |
| Is this action enabled now? | Reevaluate the existing provider's action guard. An opened window normally disables its opening action. A supported attempt may instead remain enabled and be offered only on request. |
| Can this route accept input now? | Reevaluate the provider's readiness predicate. A committed flag does not establish that a popup, handler or animation has finished. A supported continuation can have its own ready route. |
| Is it useful to suggest? | Use the player's goal, permitted discoveries and preferences. Useful actions receive priority; incidental commands remain available for explicit requests. |

Choices retain `available`, the current observation identity, required public
fact IDs and an existing input-route reference. Optional `enabled` and `ready`
are independent provider assertions. If supplied, each must be `true` for
selection; `false` and `null` (unknown) both withhold the choice. Older packets
without these fields keep their existing `available` behavior. Their absence
does not establish that a provider actually checked separate gates.

`requires` means that the named current public facts are present; it does not
evaluate their values. DotBox does not guess action rules from a predicate
named `open`, a verb label or a guide sentence. The adapter must reevaluate the
existing scene/UIL/native predicates and publish updated admission after a
change. In fDisBull 0.34.1, public Z `verbs` list supported bindings; that list
alone does not certify every verb as enabled and ready. Reuse the actual
provider admission checks instead of copying all verbs into the menu.

### Window and door examples

| Observation | Default conversational behavior |
| --- | --- |
| Window closed; opening route enabled and ready | Offer opening the window. |
| Opening accepted; effect still unknown | Record the receipt and reconcile through supported observation. Do not announce an open window or repeat the opening input automatically. |
| Window observed open; next interaction still busy | Describe the permitted observed change. Withhold routes that are not ready, while retaining a qualified continuation if one is required. |
| Window open; next route ready | Remove the now-disabled opening action. Closing, looking through or climbing through appears only if the provider actually supplies that qualified action. |
| Door closed; lock state unknown | Retain unknown lock state. A supported "Try the door" can be a valid attempt without promising success. |
| Door closed and locked | Keep the visible door. Offer an appropriate supported attempt, investigation or known unlocking action without claiming the door is openable. |
| Door closed and unlocked | Keep `open=false` and `locked=false` as separate facts. Opening and traversal still need their own applicable routes. |

Track `open` and `locked` independently. Closed is not a synonym for locked;
unlocked is not a synonym for open. Do not replace unknown lock state with
`false`. Inventory possession, item consumption, object visibility and
one-time interaction flags likewise need their own observed meanings.

## Small asynchronous steps without guessed progression

An optional private `outcome` record carries the existing provider distinctions:
`id`, `action_sent`, `complete`, `effects`, `phase` and `evidence_ref`.
`effects` is `applied-confirmed`, `partial`, `none-confirmed` or `unknown`.
`phase` is `state`, `interface`, `persistence` or `unspecified`. These fields
describe the provider receipt; they do not mutate any stored flag. Only a
current fact report updates a remembered value. Neither receipt completion nor
an effect category changes a choice's admission automatically.

Treat input acceptance, response text, state commitment and readiness as
different milestones. The preserved Lost in Time investigation gives concrete
reasons: a water response can precede its flag write, while a pump flag can
commit before the final interface acknowledgement. Those are historical
provider-study observations, not a new native DotBox timing qualification.

While an action is pending, Dot can describe already confirmed information,
accept a high-level player intention and let workers prepare likely upcoming
scenes. Workers do not mutate the live game or promote clone state into the
player's history. The lead observes or uses an explicitly supported continuation
and records later evidence. Do not resend an action merely because its effect
is not confirmed yet. Reconcile uncertainty through the provider's read-only
path where available.

Once an action is complete, new input still requires current admission and
ownership. A partially reconstructed next room does not undo a confirmed
inventory or flag change. Conversely, a known flag change does not justify
sending a second independent action while the first handler still owns input.
Scene revision is a freshness fence, not an input lease or execution lock.
The existing workflow and live controller serialize input.

An internal remote-unlock report may invalidate an old route/menu while Dot
continues narrating only the local scene. It does not authorize "You hear the
other door unlock" or reveal the remote consequence as a discovered fact.

## Suggest useful choices; preserve player expression

An optional choice `suggestion` is `prefer`, `normal` or `on_request`; omitted
means `normal`. The shortlist uses eligible preferred choices first, then
normal choices, retaining source order within each group. `on_request` choices
stay in the complete eligible list and can be selected explicitly, but never
fill an otherwise empty shortlist automatically. Preference cannot override
visibility, observation freshness, availability, enabled state or readiness.

This handles commands such as Larry's incidental "lick" interactions without
a blacklist. Usually the adapter marks that choice `on_request`. If the player
asks for it, or current permitted context makes it useful, the choice can be
selected or promoted. Repetition can likewise be incidental or meaningful,
depending on the game. Do not reveal a hidden puzzle solution by ranking a
verb using private guide knowledge in discovery mode.

Description detail and assistance remain independent. A detailed description
does not mean listing every parser verb. The full eligible list supports
explicit requests and "what else?"; a novel request still follows bounded
investigation rather than being invented as a working control.

## Passive look and the installed tools

`look_scene(packet)` and `dotbox scene look` return the current permitted scene
description, without a choice prompt, input, a game turn or a learning probe.
They use the same facts and detail settings as `present`. They do not rewrite
an existing game-action choice named `look`: a real in-game examination,
looking inside a container or another state-changing action keeps its explicit
route. Descriptions are only as current as the provider's supplied text; stale
authored templates must be refreshed when observed state changes.

After exporting the ordinary kit, the two authored window examples can be
recorded into a private store. They contain invented source identities and
route references, not runnable game controls:

```sh
dotbox kit-export --directory /tmp/dotbox-state-example
dotbox scene record /tmp/dotbox-state-example/examples/scene_window_closed.json --store /tmp/dotbox-state-example/state.sqlite
dotbox scene present --store /tmp/dotbox-state-example/state.sqlite
dotbox scene record /tmp/dotbox-state-example/examples/scene_window_open.json --store /tmp/dotbox-state-example/state.sqlite
dotbox scene look --store /tmp/dotbox-state-example/state.sqlite
dotbox scene memory --store /tmp/dotbox-state-example/state.sqlite --subject window
```

Use a new private directory if that example destination already exists. The
store requires an owned private parent directory and regular private file.
`present`, `look` and `choose` accept exactly one packet file or `--store`.
`choose` still requires the displayed `--scene-sha256`, `--observation-id` and
selected `--choice`. Through a store it compares those with the latest
persisted packet in one short transaction and returns an intent only. The
intent preserves the provider context token for the later live check. The
public description does not expose tokens, internal flags or receipt paths.

Before any actual input, the executor must check the live provider token and
route admission plus the supported ownership fence. A fresh local read is not
proof that the game has stood still. The same limitation applies after reopening
a store, while the user speaks, and after takeover. This slice verifies offline
recording and selection; live provider polling and event delivery remain an
integration task.
