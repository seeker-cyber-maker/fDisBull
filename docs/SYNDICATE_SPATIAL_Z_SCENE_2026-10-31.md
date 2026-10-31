# Syndicate: mission-scale Z scene and guarded diagnostic travel

Date: 31 October 2026. GitHub remained disabled and was not contacted.
Runtime: privately installed supplied fDisBull 0.26.0 and fDisBull Player 0.26.0,
Python 3.13.5, original game and supplied DOSBox-X backend. Installation checks
passed. The installed production modules were not modified.

## Result

A functioning mission-1 provider now feeds the **actual shipped Z player**.
Passive observations show positions, team state, linked inventory, per-type
counts, nearest entities, doors, and a separately identified mission target.
Assisted teleport commands perform guarded spatial edits in the original game,
then observe original updates until the agent and carried items agree. The
scene has an asset-free map viewer with elevation layers and conditional paths.

This is a bounded original-backed diagnostic scene, not standalone recovered
UIL gameplay. Walking, combat, persuasion, boarding, door operation, mission
completion and a fair-play line-of-sight projection are not implemented here.

The last whole-program analysis census remains **68,186 instructions, 630
candidate functions, 228,882 instruction-covered bytes (87.49% of the 261,620-byte
executable object)**. It is historical, not a new traversal. All code locations
have not been identified and understood. The scene advances a qualified subset
in parallel rather than presenting incomplete binary analysis as complete.

## One large spatial scene

Mission 1 uses **128 by 96 map tiles and 12 stored height layers**. World positions
are not screen coordinates: x/y fields use 256 units per tile, and z uses 128
units per layer. Elevation is retained because a roof can share x/y with a room
below. The scene is not split every time the camera moves.

The map resource is selected by the observed GAME map-number field, which is 1
in this session. The adapter checks exact resource identities and dimensions.
The terrain view is resource-derived; this pass did not trace a new native map
file-read or prove all collision decisions.

### Actual initial mission census

The spatial index was traversed from all 16,384 cell roots. Every next/previous
link, type, membership flag, unique appearance and coordinate-to-cell relation
was checked. It contained **44 registered entities in 26 occupied cells**:

| Type | Count | Qualification |
| --- | ---: | --- |
| Team agents | 4 | Selected team slots 0 through 3 in this initialized mission |
| Civilians | 2 | Person-role records, not an on-screen or alive count |
| Police | 0 | None registered at this boundary; not a claim about later spawns |
| Guards | 4 | Kept distinct from police |
| Cars/vehicles | 1 | Location is known; boarding/gate/occupant contracts incomplete |
| Doors | 4 | Candidate portals; subtype alone does not establish open/closed state |
| Trees | 11 | Observed entity records, not certified collision footprints |
| Closed-window-class objects | 7 | Resource class, not qualified interaction behavior |
| Open-window-class objects | 1 | Same limit |
| Weapons | 10 | Includes carried weapons; not ten loose pickups |

The earlier file-only census included reserved agent slots. The live initialized
mission has ten registered people: four team, two civilians and four guards.
File records and current game state are not interchangeable.

The team begins at:

| Agent | x | y | z | Raw health |
| --- | ---: | ---: | ---: | ---: |
| person-0 | 91.703125 | 41.671875 | 2 | 16 |
| person-1 | 91.484375 | 41.078125 | 2 | 16 |
| person-2 | 91.484375 | 40.578125 | 2 | 16 |
| person-3 | 91.421875 | 40.078125 | 2 | 16 |

Zero raw health in other person records is **not** used to discard them or call
them dead. Complete life-state and stat initialization semantics remain unknown.
Drug fields, status and vehicle references are retained without inventing a
complete high-level state model. The selected agent's owned weapon is exposed
as a source-linked inventory item, with its type and raw quantity field.

### Nearest entities and mission-critical identity

From person-0 at the initial checkpoint:

| Class | Entity | x, y, z | Straight-line XY distance, tiles |
| --- | --- | --- | ---: |
| Civilian / mission target | person-8 | 64.25, 30.75, 2 | 29.5459 |
| Car | vehicle-0 | 60.53125, 35.71875, 2 | 31.7352 |
| Guard | person-10 | 74.75, 32.25, 2 | 19.3954 |
| Door | object-2 | 73.40625, 33.84375, 2 | 19.9011 |
| Police | None registered | Not applicable | Unknown / not applicable |

The type-2 objective refers to offset 738, resolving to **person-8**, so the target
is explicitly marked even though it shares the civilian class. The original HUD
also displayed ASSASSINATE. The target's full behavior and completion transition
were not exercised. The eight slots inspected by the recovered native evaluator
remain eight consumer slots; satisfied type-zero placeholders are not presented
as seven additional active objectives.

Nearest means XY geometric distance; elevation is reported separately. It is not
travel time, line of sight or proof of reachability. Unknown character types are
retained instead of being silently dropped. Team agents remain separate from a
future non-team agent's identity; allegiance beyond the selected team is not
inferred solely from the agent type.

## The map is explicit about accessibility

`public/mission-map.html` is self-contained, with full-map/district views, layer
selection, entity markers, mission target, coordinate inspection and candidate
routes. The PNG/SVG provide the district view. No original artwork is included.

The terrain reader checks dimensions, column-directory offsets, column bounds
and the 256-entry class table. Its flat-support/clearance model admits support
classes 5,6,7,8,9,11,13,14,15 with an above-cell class of 0,12 or16. These are
**conditional model rules**, not recovered universal collision semantics.
Slopes, dynamic actors, door state, precise footprints, vehicle access, water,
mission-specific restrictions and inter-layer links are not completely modeled.
The model can have false positives and false negatives; it is not advertised as
a conservative safety proof. Native edge-wrap cases are additionally refused
by the teleport adapter.

At z=2 the model has 11,430 candidate cells in one component. This is not 11,430
certified accessible tiles. Roofs form separate components on higher layers.
No staircase/ladder connection was inferred merely because two surfaces share
x/y or because a diagnostic teleport reached both.

Four-neighbor candidate paths from the starting focus give:

| Destination | Candidate grid steps | Door cells on that path |
| --- | ---: | --- |
| Mission civilian | 38 | object-3 |
| Car | 37 | None recorded |
| Nearest guard | 28 | object-2 |
| Nearest door | 26 | object-2 |

These are model paths, not walked routes. Door edges retain an unresolved gate
condition. A car's entry/exit point, lock state and relationship to any gate are
explicit unknowns. `examine car gate` explains this boundary instead of inventing
an interaction. This also accommodates the ambiguity between vehicle state and
a separate road/door gate in the request.

## Source-grounded relocation rather than x/y-only editing

The original helper at preferred **0x29530 through 0x29654 (exclusive)** computes
old/new spatial cells, unlinks the entity from its previous cell list, repairs
neighbor pointers, inserts it into the new list and writes coordinates. Its
292-byte runtime window exactly matched the original under the observed LE
object mappings, SHA-256
`2cdf665b71cf59e26c8d3c9729f4edae15829ffb872eadbfcb71b1420f3672ad`.

The research adapter **models those operations with guarded memory writes**.
It does not claim to have invoked that helper. It preserves the original code,
updates roots and both link directions, checks the complete graph, and requires
full expected-output memory equality before resuming. It refuses the native
wrap-edge domain rather than guessing how to represent it in the scene.

Only the observed on-foot team raw-state profile is admitted: registered team
person, status byte0, no current target-position fields, no vehicle references,
and coordinates inside the qualified bounds. Other states need their own
adapter. The operation is grouped while paused under one owning controller;
this is not a general multi-client atomic memory-transaction facility.

### Teleport experiments

Five initial exploratory preparations each restored the same original native
checkpoint, checked registers and the full 116,010-byte GAME region, edited
spatial links/position, and requested a 200-ms original execution interval.
Each retained the requested position, coherent links, and team health16.
Actual guest elapsed intervals may overshoot requested budgets.

One exploratory guard-side coordinate, (74.5,33.5,2), remained occupied although
the terrain model excludes it. **That is a useful counterexample to treating
successful placement as passability.** The public route refused that waypoint;
the admitted guard approach was moved to (75.5,32.5,2) and tested separately.
No terrain rule was relaxed merely to make a preferred test pass.

The final acceptance drove six successive commands through the installed
`fdisbull_player.Player` resolver: car approach, mission target approach,
guard approach, door approach, roof probe and start position. All completed
with fresh context, coherent graphs and attached items at the agent's position.
The original baseline was then restored with full GAME equality.

### A partial result improved the completion rule

An earlier sequential trial updated the agent correctly but its carried weapon
still had the previous coordinates at the first observation. The adapter
withheld success and held the session. One additional bounded original update,
without another teleport write, brought the weapon into agreement.

The final implementation waits on the actual relation rather than a fixed sleep:
agent at requested position, valid spatial graph, and all observed owned items
at that position. It permits up to ten requested 200-ms windows and a wall-time
bound; it records actual elapsed time. Missing completion remains partial/held,
never a reason to replay the original writes. The superseded partial trial and
its raw receipts remain private and were not relabeled as passes.

## Actual Z-player integration

The provider implements the existing JSON-lines `observe` and `act` interface.
No production grammar or player fork was needed. It returns the declared public
projection with a context token, objects, inventory and partial-coverage flag.
The wording explicitly identifies a **global diagnostic** view; the player's
stock “Visible” label refers to its exposed catalogue, not native line of sight.

Working passive commands include `look`, `examine team`, `examine civilians`,
`examine police`, `examine guards`, `examine nearest car`, `examine car gate`,
`examine mission target`, `examine objectives`, `examine map`, and `inventory`.
The local text map is centered on the focused agent and preserves elevation.

`focus team agent N` changes the observer focus only, not native selection.
`advance world` requests a bounded original execution window. Teleport commands
are explicitly marked spatial policy assisted. Unsupported boarding is refused
before input. Passive reads do not advance time or issue writes. Stale tokens
are rejected; mode, source-window, controller-generation and revision changes
prevent silent reuse of an old binding.

The delivered recorded snapshot is deliberately read-only. The live adapter
requires original assets and a freshly verified, owned DOSBox session. Automatic
Z `--live` checkpoint/recovery certificates are not implemented; the adapter
refuses those operations instead of fabricating replay safety.

## Runtime binding and a new code/data observation

The fresh binder verified **9,209 code-side fixup records**, inferred all four
runtime object bases and compared the **261,620-byte executable object**. The
bases in this run were 0x1C4030, 0x204030, 0x190B90 and 0x218030. They are not
universal load addresses. The observed CS/DS selectors were0158/0160.

The first whole-object check refused26 differing bytes. Two were the previously
qualified saved-DS field. The other24 were within eight dwords at preferred
**0x48AD0..0x48AF0**. Source stores such as0x48BA2 and0x48BF8 write an indexed
pointer list there; the renderer reads it at0x43CE6. The observed values are
runtime data in an executable object, not evidence that the corresponding zeros
should be newly decoded as instructions.

The binder records this bounded32-byte mutable-data prefix explicitly, along
with the saved-DS word. All other compared bytes matched after relocation.
It does not ignore arbitrary executable-object differences or claim to know
every possible writer/entry into the larger surrounding region. An unexpected
mutation outside the admitted fields rejects binding. The earlier helper-only
binding and later broader binder are distinguished in their receipts.

## Verification, preparation and retained friction

- **27 authored tests passed**, covering list integrity, cycles, missing links,
  zero-health retention, unknown roles, mission target identity, occupied and
  empty destination cells, same-cell moves, edge/state/rider refusals, height
  separation, bounded map parsing and actual player projection.
- The final original-session acceptance passed eleven passive commands, stale
  action refusal, unsupported boarding refusal, six successive teleport actions,
  focus changes and exact GAME restore. Passive commands retained both the
  runtime revision and GAME bytes. This is a bounded mission slice, not full
  gameplay acceptance. Source-free results are in `evidence/`.
- Two original console runs through `python -m fdisbull_player --backend-command`
  exercised the JSON-lines transport. A final recorded-snapshot console run
  checked inventory and target output and refused teleport without a live guest.
- The native low-level `state.save/load` path saved a protected-mode checkpoint
  and restored CPU registers plus all GAME bytes in the same owned session.
  The higher-level project checkpoint wrapper refused the sampled protected-mode
  preparation. The lower-level result is not being advertised as automatic Z
  checkpoint certification, cross-session portability or disk rollback.
- Keyboard input reached the menu/world screen. Because protected-mode clicking
  was refused, **two source-verified synthetic menu-click preparations** wrote
  cursor/press coordinates and one-shot click flags, six guarded writes total.
  Mission entry is therefore assisted setup, not a fully ordinary mouse route.
- An early `police` alias was missing, and an offline semantic export initially
  omitted an inventory-owner identifier used by the renderer. Both display-path
  issues were corrected and tested. The live scene uses semantic owner IDs.
- Two Chromium screenshot attempts timed out without producing a screenshot.
  The HTML's syntax and interactive JS branches passed a DOM/canvas-stub test,
  not a real-browser visual acceptance. The SVG was rendered to PNG and inspected
  visually; corrected high-contrast markers are used in the delivery.
- At shutdown the debugger's stored close receipt reports `stop deadline expired`
  and `process_reaped:true`. Both owned process IDs were absent. The private
  controller then called a nonexistent `Project.close` method, so its separate
  cleanup JSON was not written; the database's already committed close receipt
  remains intact. The delivered controller uses the actual `Project.__exit__`
  method with nested cleanup. This final controller-cleanup correction was
  syntax/review checked, not exercised in another native session. No clean
  selected-program exit or process exit code is inferred.
- The complete original897-path census remained unchanged, with no unexpected
  files. The native baseline was restored before closure. Cleanup is recorded
  separately and is not a selected DOS-program exit or mission completion.

## Local implementation recommendations

The pending PR adds the bounded adapter/tools and authored tests as a research
example, plus this report. It does not modify a production runtime, publish a
release or claim current-upstream compatibility. The last reviewed remote base
remains90e748c; it was not rechecked while GitHub is disabled.

| ID | Requirement for an integrated implementation |
| --- | --- |
| SZ01 | One mission-scale spatial scene with world coordinates, elevation and local projections; camera motion does not invent a new world. |
| SZ02 | Source-bound active-record census, stable per-class IDs, explicit life/visibility/count scope and separate objective-target references. Unknown roles remain visible. |
| SZ03 | Distinguish XY-nearest, same-floor proximity, conditional path cost and verified accessibility. Door/vehicle occupancy and boarding retain their own contracts. |
| SZ04 | Guarded relocation preserves spatial roots, predecessor/successor links, actor state and attachments; placement alone is not a walkability certificate. |
| SZ05 | Completion follows observed predicates, not a fixed delay. Preserve a committed move with pending attachment updates; no duplicate teleport on late observation. |
| SZ06 | Passive snapshots and action tokens are bound to source, module/load generation, state revision, selected observer and coherent read boundary. |
| SZ07 | Expose protected-mode checkpoint capabilities accurately without weakening compatibility, disk, input and cleanup checks or inventing Z replay-safe certificates. |
| SZ08 | Treat mutable data inside executable objects separately from instruction edits; qualify exclusions with source consumers/writers and reject unexplained changes. |
| SZ09 | Keep semantic Z examples, reports and sanitized receipts publishable separately from private source assets, checkpoints, memory, screenshots and byte-retaining FDBs. |

## Sources and epistemic boundary

Paul Chavent's libsyndicate file-format research
(https://icculus.org/libsyndicate/libsyndicate.html) was consulted for candidate
record families, role encodings, units and terrain classifications. This is
reference-guided investigation, not blind rediscovery. Runtime list invariants,
objective references, source helper behavior, actual player actions and observed
teleport effects were checked separately against this original release.
The actor classification is a reference-informed interpretation supported by
the selected records, not a claim that every role/state in every mission is
fully recovered. No external guide was substituted for a successful game route.

## Knowledge pack

**Architecture:** Original DOSBox session -> verified object mappings -> coherent
GAME snapshot and source-linked terrain -> semantic scene -> unmodified Z player.
Assisted actions -> guarded linked-state changes -> original update -> observed
agent/attachment completion.

**Decisions:** Keep one mission scene; preserve z; global diagnostic visibility;
separate type from mission role; expose unknowns; no automatic movement/boarding
or inferred gate opening; no GitHub access or publication.

**Next:** Recover and qualify original door/gate transitions and vehicle boarding/
exit points, plus local collision/footprint and stair connectors. Those checks
would promote selected candidate paths rather than treating a teleport tour as
proof that the map can be walked. Continue the separate missing-code ledger;
this first scene does not close it.
