# Versioned semantic input macros

Status: design recommendation; not implemented in fDisBull 0.19.0

Date: 27 October 2026

## Problem

Debugger scripts currently name physical operations. `keyboard.press` queues a
key make, a bounded hold and a key break. That is a useful stable primitive, but
game actions do not share one universal input model.

Police Quest I latches directional movement. A complete arrow press starts
movement and another complete press of the same arrow stops it. Many other games
move while a key remains down and stop when that key is released. A route that
hard-codes either interpretation as the meaning of `down` or `stop` will be wrong
for the other game.

The same issue extends beyond movement. `press`, `release`, `interact`, `confirm`,
`cancel`, `look`, `rewind` and other useful player words can correspond to
different physical inputs, parser commands, scene actions or bounded compound
routes in different games.

## Recommendation

Keep the low-level operations mechanically stable and let a selected,
version-bound macro set define game semantics. A script invokes a macro through
an explicit `macro` operation:

```json
{"op":"macro","name":"down"}
{"op":"macro","name":"stop","args":{"direction":"down"}}
```

Names such as `down`, `stop`, `press` and `release` are intentionally not given a
universal meaning. Their meaning comes from the exact selected macro-set identity.
The execution receipt always retains both the semantic call and its expanded
physical steps.

This is a project/debugger-harness facility. It helps fDisBull replay and compare
the original program. An AEC cartridge may independently consume or translate a
qualified macro set, but that does not move player policy, cabinet presentation
or game-verifier authority into fDisBull.

## Three layers

### 1. Stable physical primitives

fDisBull owns bounded operations whose behavior does not change by game:

- `keyboard.key-down` — queue one physical make transition and retain an owned
  held-key lease;
- `keyboard.key-up` — queue one physical break transition for a key/lease owned
  by the current controller;
- existing `keyboard.press` — queue make, bounded hold and break together;
- existing `keyboard.type` — queue bounded US-layout text input;
- existing mouse, scene, `run`, `wait`, assertion and observation operations;
- future resolver-backed semantic observations and conditional run-until.

`keyboard.key-down` and `keyboard.key-up` are proposed prerequisites. They do not
exist in 0.19.0. Existing `keyboard.press` remains backward-compatible and keeps
its current atomic make/hold/break meaning.

Physical primitives must continue to distinguish queued delivery from game-level
consumption or success. They never infer that a movement, purchase, pickup or
dialog action occurred merely because input was accepted.

### 2. Versioned macro sets

A human, agent, game adapter or cartridge author defines semantic names by
expanding them into bounded declarative script steps. A macro set should be:

- immutable and content-addressed;
- bound to the selected project/static version, target source inventory and
  optional adapter version;
- attributable to its author and linked to the evidence supporting each game
  interpretation;
- explicitly selected by ID/hash, with no ambient same-name precedence;
- revisioned through a parent/supersedes link rather than edited in place; and
- exportable without game bytes, saves, project databases or host paths.

Macro names are user-defined. Invocation remains visibly namespaced as
`{"op":"macro",...}` so a macro called `press` cannot be confused with the core
operation `{"op":"keyboard.press",...}`.

Each macro declares typed parameters, its authority classification and bounded
steps. Suggested authority classes are:

- `player-input` — ordinary controls available to the player;
- `authoring` — setup/recovery operations used to construct or qualify routes;
- `diagnostic` — invasive probes or state manipulation that cannot prove
  ordinary player progress.

The label does not grant permission. The caller selects which classes its mode
allows, and the expanded primitive operations remain subject to their normal
capability and authorization checks.

### 3. Routes and outcome checks

Routes call macros and verify the target-level result. A `move.down` macro may
deliver the correct game input, but successful delivery still does not prove the
actor moved. The route must check a qualified coordinate, scene, parser response,
inventory, score, object state or another claim-appropriate outcome.

The future conditional semantic-navigation primitive complements macros:

```text
macro move.start(direction)
        ↓
run until semantic position predicate
        ↓
macro move.stop(direction)
        ↓
verify settled direction, position and context
```

Macros define *how this game expresses the action*. The semantic resolver and
predicate define *when the observed target condition has been reached*.

## Progress, obstruction and recovery

A movement route should declare both its destination predicate and the semantic
fields expected to keep changing before arrival. It should not wait for the full
guest-time budget when the actor has already stopped making progress.

One possible design shape is:

```json
{
  "until":{"field":"x","in_range":[65,69]},
  "progress":{
    "fields":["x","y"],
    "must_change_within":{"completed_frames":8},
    "on_stall":"blocked"
  }
}
```

The window may be expressed in qualified completed frames, semantic observation
samples or watched writes, according to the adapter. It must not silently use
host sleep as game time. The route should sample after the movement input has
been consumed and should calibrate the window for the target's actual update
rate. Destination success takes precedence when the destination predicate and
the final progress sample coincide.

If every declared progress field remains constant for the complete bounded
window before the destination is reached, stop movement through the selected
game macro and return a failed `blocked` result immediately rather than consume
the route's remaining movement budget. Retain:

- destination and progress contracts;
- start, last-changing and final semantic values;
- qualified frame/sample/write identities and measured guest time;
- input queue/held-key state and whether stop/cleanup settled;
- room/scene before and after;
- an immediate authentic screenshot captured without preparation that advances
  or changes the guest; and
- any screenshot-capture error without replacing the movement failure.

Constant coordinates establish a blocked route under the declared observation
contract. They are compatible with a wall/collision, but do not prove that cause
when focus, animation, input consumption or another game condition could also
prevent motion. A target collision flag or traced collision branch can strengthen
the classification to `collision`.

An optional teleport to a qualified named anchor may recover an authoring or
diagnostic session after the blocked receipt is frozen. It starts a new,
explicitly labeled branch, re-resolves the semantic object and verifies the new
context. It does not change the walked route from failure to success and must not
be exposed as ordinary player progress unless the game itself provides teleport.

## Proposed scene navigation geometry

The scene definition is the natural home for a version-bound virtual
representation of a room. This should be a separate `navigation` extension, not
an overload of the existing screen-pixel action areas. A game's movement
coordinates may describe an actor baseline, feet, tile, world point or logical
room position and may not equal native screenshot pixels.

One possible design shape is:

```json
{
  "navigation":{
    "format":"fdisbull-scene-navigation-1",
    "coordinate_space":{
      "name":"agi-room-baseline",
      "units":"game-pixels",
      "origin":"top-left",
      "actor_anchor":"ego-baseline"
    },
    "room_bounds":{"rect":[0,36,160,168]},
    "walkable":{"subtract":[
      {"rect":[0,36,160,168]},
      {"union":[
        {"polygon":[[0,36],[160,36],[160,48],[0,48]]},
        {"rect":[72,80,91,121]}
      ]}
    ]},
    "colliders":[
      {
        "name":"room.wall.north",
        "kind":"solid",
        "area":{"polygon":[[0,36],[160,36],[160,48],[0,48]]},
        "condition":{"constant":true},
        "derived_from":["project-fact:example-only"]
      }
    ],
    "portals":[
      {
        "name":"room.exit.south",
        "area":{"rect":[70,164,90,168]},
        "destination":"next-room.entry.north"
      }
    ],
    "anchors":[
      {
        "name":"room.safe.center",
        "point":[80,100],
        "qualification":"actor footprint clear under current collider set"
      }
    ]
  }
}
```

The numbers and identifiers above illustrate a schema only. They are not PQ1
facts. A production extension should support the same bounded rectangle,
polygon, union, intersection and subtraction vocabulary as scene action areas,
plus explicit conditional colliders, transition portals and qualified anchors.
If the actor has a non-point collision footprint, store that footprint and its
anchor convention too; a point inside a walkable polygon does not establish
that the complete sprite footprint fits.

Prefer static derivation from the selected game's code and room/control
resources over trial-and-error walking. Every derived region should retain the
exact project/static version, source facts or resource hash, extraction rule,
coordinate transform and evidence status. Deterministic recovery from an exact
room table or control map may support `derived`; a shape inferred from a
decompiler hypothesis remains `inferred` until the relevant semantics are
qualified. Dynamic doors, moving actors, inventory gates and script-controlled
barriers remain conditions, not permanently baked geometry.

This representation improves both movement and diagnosis:

- reject an impossible destination or actor footprint before sending input;
- predict the first static boundary intersected by a route;
- classify a constant-position failure at that boundary as
  `blocked_known_boundary` while preserving the ordinary screenshot;
- keep `blocked_unknown` when runtime state disagrees with static geometry;
- select only anchors proven clear for the current room/state before a
  diagnostic teleport; and
- compare runtime discoveries with the source-derived map and preserve any
  contradiction as evidence rather than silently editing the map.

The route receipt should bind the navigation-extension hash and record the
expected/intersected region or portal. Geometry is advisory until the exact
runtime coordinate object and current conditional-collider state have been
resolved. A bounding box alone is never proof that all enclosed points are
walkable.

Together with entities, state, rules and events, this source-backed navigation
model reinforces UIL as a semantic world IR. A Zork-like venue can render a
room and its available actions from that representation, then compile a player
command back into a canonical intent that invokes the selected semantic input
macro or native cartridge action. Point-and-click, debugger and headless agent
venues can consume the same world transition without defining separate game
truths. The wording, visual layout and control affordance may change; the bound
state and event semantics do not.

## Contrasting control profiles

These examples describe the intended distinction, not an implemented schema.

### PQ1-style latched movement

```json
{
  "format":"fdisbull-macro-set-1",
  "name":"pq1-agi-2917-controls",
  "macros":{
    "move.start":{
      "parameters":{"direction":{"enum":["up","down","left","right"]}},
      "steps":[{"op":"keyboard.press","key":"$args.direction"}]
    },
    "move.stop":{
      "parameters":{"direction":{"enum":["up","down","left","right"]}},
      "steps":[{"op":"keyboard.press","key":"$args.direction"}]
    },
    "down":{
      "steps":[{"op":"macro","name":"move.start","args":{"direction":"down"}}]
    }
  }
}
```

Here `move.start` and `move.stop` intentionally expand to the same physical
primitive. Their semantic roles and outcome checks remain different.

### Hold-to-move game

```json
{
  "format":"fdisbull-macro-set-1",
  "name":"held-direction-controls",
  "macros":{
    "move.start":{
      "parameters":{"direction":{"enum":["up","down","left","right"]}},
      "steps":[{"op":"keyboard.key-down","key":"$args.direction","as":"lease"}],
      "outputs":{"lease":"$lease.lease"}
    },
    "move.stop":{
      "parameters":{"lease":{"type":"input-lease"}},
      "steps":[{"op":"keyboard.key-up","lease":"$args.lease"}]
    },
    "down":{
      "steps":[{"op":"macro","name":"move.start","args":{"direction":"down"}}]
    }
  }
}
```

Here releasing the held key is the stop operation. A complete atomic
`keyboard.press` would only produce a bounded pulse and cannot represent an
indefinite movement interval around a semantic wait.

A project may instead define short names such as `press`, `release`, `stop` or
`interact`. Those names remain local to the selected macro set and do not alter
the meanings of core operations.

## Expansion and execution invariants

Before any guest mutation, the engine should select the exact macro set, bind
and type-check arguments, expand every macro call, reject recursion/cycles and
validate every resulting core operation against the current backend. Recommended
bounds are the existing script nesting limit, at most 1,000 expanded operations
and one shared host-time budget.

Macro expansion must not execute Python, JavaScript, shell, native libraries,
network calls or target-provided text. It may only produce allowlisted fDisBull
declarative operations. Existing result bindings may be retained; macro arguments
should use an explicit namespace such as `$args.direction` rather than ambient
host variables.

A macro set must not silently shadow another set. Imports with the same human
name require explicit identity selection. Unsupported operations or authority
classes fail before execution, not after a partial route.

## Held-key ownership and cleanup

Separate key-down/key-up primitives need stronger lifecycle rules than atomic
presses:

1. `keyboard.key-down` returns an unforgeable session-owned lease containing the
   physical key identity.
2. `keyboard.key-up` consumes that lease. It cannot release a key owned by an
   unrelated session or controller.
3. A successful macro may leave a key held only when that output lease is
   explicitly declared and returned to the caller.
4. A macro failure releases keys it acquired but did not validly return. If
   release cannot be proven, the owned session closes.
5. Saving native state continues to reject pending input or owned held keys.
6. Restore, target exit and controller teardown cancel queues and release owned
   keys under the existing fail-closed input policy.
7. A route receipt distinguishes key-down accepted, key held, key-up accepted,
   queue drained, game state observed and semantic action verified.

This avoids an invisible global “last direction” variable. A route should pass
an explicit direction or lease to `move.stop`, unless a qualified target adapter
provides an observable current-direction field.

## Evidence and receipts

Every macro invocation should retain:

- macro-set ID/hash and project/static-version identity;
- macro name, revision, author and authority class;
- bound arguments and expanded core steps;
- backend capability/profile and input state before/after;
- each primitive result and any target-level outcome observation;
- held-key leases created/consumed/returned;
- measured guest time and host time;
- stop, timeout, cleanup and incomplete conditions; and
- the final claim ceiling.

A macro receipt proves which expansion was attempted. It does not prove the macro
definition is correct for every game state. Counterexamples should create a new
revision or superseding macro set while preserving the earlier receipt.

## Acceptance checks for a future implementation

Use redistributable authored fixtures rather than proprietary game assets.

- A latch fixture starts and stops movement with two atomic presses; a key-up by
  itself does not falsely claim a stop.
- A hold fixture moves between key-down and key-up; an atomic press produces only
  a bounded pulse.
- Two selected macro sets may use the same semantic names while expanding to
  different physical operations with distinct hashes and receipts.
- Missing/extra/wrong-type arguments, recursion, cycles, excessive expansion,
  unsupported operations and unknown macro IDs fail before guest mutation.
- A mid-macro failure releases unreturned held-key leases; uncertain cleanup
  closes the session.
- A successful start/stop route records delivery separately from a verified
  coordinate/state outcome.
- A route whose required x/y progress remains constant for the declared frame or
  observation window fails early as `blocked`, neutralizes input and preserves
  an immediate authentic diagnostic screenshot.
- A destination reached on the final allowed progress sample succeeds rather
  than being misclassified as blocked; a screenshot failure does not erase the
  movement failure receipt.
- A diagnostic teleport after obstruction creates a separate recovery receipt
  and cannot rewrite the failed walked-route result.
- Source-derived room bounds, walkable areas, colliders, portals and anchors
  retain byte-version and extraction provenance; a known-boundary blockage is
  distinguished from an unexplained constant-position failure.
- Navigation geometry uses an explicit game-coordinate space and actor anchor;
  screenshot-pixel areas are not silently treated as movement coordinates.
- A conditional collider change invalidates the active route preflight and
  forces a fresh semantic observation before movement or teleport.
- Restart preserves immutable macro definitions but not session-owned leases or
  stale runtime addresses.
- Existing `fdisbull-script-1`, `keyboard.press`, `keyboard.type`, scenes,
  screenshot hooks and routes retain their current behavior.
- Package checks exclude games, states, databases, runtime images and private
  macro evidence while including reusable tool documentation and fixtures.

An authorized PQ1 replay may supplement these fixtures. It should verify that a
second same-direction press stops its observed ego record and that a key-up-only
profile does not misreport success. That replay remains bounded evidence for the
identified PQ1 edition, not a universal movement rule.

## Non-goals

- Do not hard-code PQ1 control semantics into fDisBull core.
- Do not rename or weaken the exact meaning of existing physical operations.
- Do not allow arbitrary host code in macros.
- Do not let a macro label promote authoring/diagnostic actions to player input.
- Do not infer application consumption or game success from queue acceptance.
- Do not add hidden mutable macro state when explicit arguments or semantic
  observations can express the route.
- Do not make fDisBull the AEC cartridge runtime merely because both can consume
  the same qualified control vocabulary.
- Do not treat a rectangular room bound as a complete collision map or erase a
  runtime counterexample to source-derived geometry.

## Claim ceiling

This document recommends a boundary and acceptance contract. It does not
implement macro persistence or expansion, separate key-down/key-up input,
semantic navigation, scene-navigation geometry, an AGI adapter or an AEC
control profile.
