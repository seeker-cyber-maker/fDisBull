# Proposal: synthetic HUD scenes and reusable game-state observations

Status: **design proposal**, 29 October 2026. This document specifies the
requested feature and acceptance cases; it adds no runtime, game profile,
canonical UIL format or new public command. Examples are authored illustrations,
not recovered PQ1, KQ1 or DinoPark values.

## Problem and intended experience

A player or agent often needs information spread across several game screens.
An investigator may already know the relevant inventory table, quest flag or
management value, yet that knowledge is not packaged as a reusable observation.
The next session either repeats menu navigation or repeats reverse engineering.

Provide an **extra synthetic HUD scene** that can remain available alongside
the current native scene. A player can see useful selected values in one panel;
a headless agent can request the same facts as compact structured data. Viewing
it does not navigate the guest, change its room, manufacture a screenshot or
execute a game action. The original engine remains authoritative when the
provider is the original game.

| Candidate profile | Useful requested information | Qualification still needed |
| --- | --- | --- |
| PQ1 equipment and progress | Selected inventory/item locations, named equipment states, established objectives and opted-in internal flags | Exact edition, runtime bindings and meaning of each selected field |
| KQ1 inventory and quest progress | Selected inventory, current room, score and named quest/timer flags appropriate to the chosen observation profile | Resource/version identity, item/flag semantics and applicability |
| DinoPark management | Cash, debt, food stock, operating inventory, staff and selected expense/time values in one overview | Units, accounting period, committed versus pending values and source bindings |

These are requested coverage targets, not a claim that all fields have already
been recovered. Add derived management indicators only when their inputs and
formula are qualified; display estimates as estimates. An unknown food-consumption
rate cannot produce a confident "days of food left" value.

## Three reusable parts

| Part | Responsibility | Lifetime |
| --- | --- | --- |
| Observation profile | Stable field identities, meanings, types, units, source bindings, validity conditions, access policy and evidence | Immutable revision reusable across compatible sessions |
| Observation snapshot | The values actually captured, their context, coverage, quality and provenance | One recorded observation boundary; serializable and historical afterward |
| Synthetic HUD presentation | Group, label and display those facts; optionally show changes and alerts | A view of a selected snapshot or explicitly refreshed live profile |

The same observation data can feed the HUD, an agent's JSON context and an
appropriate Z/text description. This is a layer **below the Zork-like scene
presentation and above raw memory**: it exposes semantic facts without requiring
narration, object interaction or a complete game reconstruction. Shared semantic
field identities should align with later UIL mappings; this proposal does not
add UIL opcodes or make the HUD a second owner of game rules.

Keep the real game context and auxiliary HUD identity separate. Opening the HUD
must not satisfy a native room matcher or introduce a second matching primary
text context. A host may show it as an overlay, side panel, virtual page or
text table. Synthetic layout coordinates belong only to that presentation and
must never become guest click coordinates. An authored HUD image must identify
itself as synthetic; it is not native screenshot evidence.

## Reuse existing machinery, preserve its limits

The following seams are present in the reviewed main revision
`821f97f4e2a67296909d6badc4c065c913021e82`:

| Existing seam | What can be reused | Missing feature addressed here |
| --- | --- | --- |
| [`runtime_observations.py`](../src/fdisbull/runtime_observations.py): `bind_runtime_memory`, `runtime_memory` | Named bounded runtime reads, anchor witnesses and source/run/load/epoch identity | Persisted reusable binding recipes and semantic field definitions |
| `capture_observations` in the same module | Named typed observations, captures, errors, completeness and stopped-context checks | Profile/snapshot API, explicit coherence, field policies and persistence |
| [`scene_values.py`](../src/fdisbull/scene_values.py): `ObservationReads` | Per-observation read reuse and explicit scalar representation | Bounded bit/enum/scaling and collection adapters where required |
| [Progressive workflows](PROGRESSIVE_SCENES.md) | Immutable revisions, declared resource inventory, dependency evidence and a cooperative controller lock | Optional observation-profile references and coordinated capture |
| [Text projections](TEXT_PROJECTION.md) | Public/private separation, authoritative backend and fresh action bindings | Permitted fact projection and an auxiliary HUD attachment |

Current `capture_observations` accepts **1–16 observations** and requires a
paused real-mode guest. It performs multiple reads, does not acquire the workflow
lock itself, and compares available start/end status fields. It is not an atomic
native snapshot transaction. If its final context check fails, earlier values
remain in the result alongside `complete: false`; a HUD consumer must not label
that batch coherent or current. Guest reads can still append debugger events
to the project database.

The current native `fdisbull-scene-1` requires a clean screenshot and actionable
objects with geometry. Do not insert dummy objects to make this feature fit that
schema. The current text projection also requires exactly one matching primary
context. Add an explicit auxiliary presentation seam while preserving both
contracts. A HUD should work without a native screenshot when its selected
fields require only qualified memory observations.

## Observation profile contract

Persist the knowledge needed to observe a field again, rather than a transient
pointer or session binding UUID. A profile should contain:

- Stable profile/field IDs, an immutable revision and parent, and the compatible
  executable, mapped-byte version, relevant resources and adapter identities.
- Per-field label and meaning; storage width, signedness and endianness;
  semantic type; units/scale and accounting scope where relevant. Distinguish
  pending transactions, committed totals, current-period and lifetime values.
- An explicit source kind: project-mapped memory, a qualified runtime binding
  plus bounded offset, or another declared provider. Store the binding recipe,
  locator and anchor evidence privately. Do not trust stored absolute addresses
  or session binding IDs without current identity and witness checks; resolve
  relocation through the qualified locator where required.
- Applicability predicates, dependencies, bounded decoder/derivation and its
  qualification scope. A value visible only after a menu computes a cache must
  remain stale/unavailable until a qualified source or refresh exists.
- Observation permissions, required/optional fields, collection membership and
  completeness rules, refresh policy and evidence references.

An anchor match establishes the expected memory context, not that a field means
"cash" or "has key." Qualify the semantic mapping once from relevant source
and/or discriminating observations. Keep mutable measured values out of stable
identity witnesses unless that restriction is deliberate. Reuse accepted
profiles under matching identities; requalify only dependencies affected by a
change. Reuse qualification so a HUD refresh does not rediscover its fields.
Existing workflow resource rechecks stay intact; a faster validation cache needs
an explicit immutable-input and drift-detection contract before replacing them.

Start with a small selected field set. Item collections need ownership/location
semantics and a declared scan boundary; a partial inventory scan cannot prove
that an item is absent or that the shown list is exhaustive. The partial
[AGI inspector](AGI_LOGIC.md) does not by itself establish PQ1/KQ1 runtime table
addresses or flag meanings.

## Capture and refresh contract

Capture through the current provider under its declared observation policy.
For a native paused capture, use the shared controller lock, preserve existing
debugger stops and require enough start/end evidence for the claimed coherence.
The lock protects cooperating controllers only. Missing generation evidence or
uncontrolled concurrent mutation reduces the claim to incomplete/unknown.

Record profile revision, source/resource identity, run, load/restore epoch,
start/end state revision, observation sequence and host time; include guest time
and frame identity only when available and relevant. Wall-clock age alone cannot
establish freshness. Track requested/captured fields, group coherence, coverage,
per-field known/unknown/stale/unavailable status, and private evidence references.
Known zero and false must survive independently of missing values.

Read-only refresh sends no game input, changes no guest memory and executes no
guest helper. It must not silently resume a breakpoint or advance guest time to
obtain a frame. If a running provider requires a pause, expose that capture policy
and its timing cost. Menu navigation or an in-game computation is a separate,
explicit action with its own outcome and time effects, never hidden inside a
passive HUD read. A display cache is not assumed to be current authoritative data.

Refresh on demand or at qualified action/transaction boundaries. Invalidate live
values on relevant input, guest advancement, context/resource change, restore,
reconnect or lost binding. Retain old values only as clearly dated last-known
information. A global field's binding may remain applicable across a room change;
retaining its value as current still requires the source contract's freshness or
invariance guarantee. Recheck room-local applicability separately.

Respect bounded field/read/output budgets. Do not silently raise the existing
16-field limit or stitch unrelated captures into one apparently atomic result.
Group larger profiles under a qualified unchanged boundary, or expose separate
capture groups and their limitations. Derivations require compatible, sufficiently
fresh inputs; propagate unknowns and identify estimates or elapsed-time assumptions.

## Serializable agent context

Yes: snapshots can be saved, transferred between agent turns and compared without
re-reading screenshots or reconstructing the field mappings. Keep three operations
distinct: load a profile definition, load historical observations into agent
context, and restore an authoritative game checkpoint. A snapshot is a selected
observation of game state. It is not presumed to contain all variables, event
queues, timers or random state needed to resume or simulate the game, and is not
presumed to make an agent's task Markovian.

The following JSON is **illustrative design notation**, not an accepted current
API schema. All identities and values are authored. Production identities must
resolve to their pinned definitions and source inventory.

```json
{
  "kind": "observation_snapshot",
  "example_only": true,
  "authority": "authored_example",
  "snapshot_id": "example-snapshot-12",
  "profile_revision": "example-park-overview-r1",
  "source_inventory_ref": "example-source-inventory",
  "audience": "assisted",
  "context": {
    "run": "example-run-3",
    "epoch": "example-load-2",
    "start_state_revision": 42,
    "end_state_revision": 42,
    "sequence": 12,
    "captured_at_utc": "2026-10-29T20:00:00Z",
    "guest_tick": null
  },
  "coherence": "consistent_at_declared_boundary",
  "coverage": "selected_fields_only",
  "complete_for_requested_fields": false,
  "fields": {
    "park.cash": {
      "type": "u64", "encoding": "decimal_string", "unit": "game_currency",
      "status": "known", "value": "5000", "evidence_ref": "example-capture-1"
    },
    "park.debt": {
      "type": "u64", "encoding": "decimal_string", "unit": "game_currency",
      "status": "known", "value": "0", "evidence_ref": "example-capture-2"
    },
    "park.operating": {
      "type": "bool", "status": "known", "value": false,
      "evidence_ref": "example-capture-3"
    },
    "park.food_units": {
      "type": "u32", "unit": "stock_unit", "status": "unknown", "value": null
    }
  }
}
```

Use a defined lossless encoding for integers wider than a JSON consumer's exact
numeric range, as illustrated above. Preserve types, enum meanings, units,
unknowns, completeness and observation scope on round-trip. Serialization must
not run embedded code or reinterpret a stored locator as an instruction to read
arbitrary memory. Imported snapshots start as historical/untrusted observations;
they cannot mint live action tokens or change authoritative guest state.

A compact delta must bind the exact baseline snapshot, profile/source revision,
audience, run and epoch, plus ordered sequence. Reject an absent baseline, a
cross-epoch delta or an out-of-order update. Define omitted-as-unchanged only
inside such a valid delta; an omitted field in a fresh partial snapshot does not
mean unchanged. Carry explicit invalidation/removal records, including fields
lost through errors or policy changes. After restore or changed profile/policy,
start a fresh baseline and discard pending action freshness. An optional opaque
checkpoint reference may link a snapshot to a separately valid save; restoring
that save still requires rebinding and a fresh capture.

## Information policy and controls

Support the requested assistance explicitly. An assisted profile may expose
named internal quest flags or management values even when the original screen
does not show them. A player-information profile aggregates only its declared
available knowledge; historical learned facts carry their own provenance. An
investigator profile can additionally expose bindings and private evidence.
These are observation choices, separate from physical/assisted movement policy.

Apply the selected field policy consistently to HUD labels, IDs, alerts, derived
values, JSON, deltas, saved context, errors and provenance. Do not present privileged
assistance as an unchanged original player information set. Profile changes must
invalidate filtered caches so previously exposed fields cannot persist silently.
Filtering subsequent output cannot erase knowledge already disclosed to a player
or agent; comparisons requiring the same information need a clean context.
User-selected assistance remains available without requiring a whole-game port.

Keep v1 HUD interactions to host presentation operations such as selecting fields,
refreshing or inspecting permitted provenance. A later "open ledger" or game
action button must explicitly dispatch through the existing qualified native or
UIL action interface with fresh preconditions. A displayed flag is not by itself
permission to click or proof that the corresponding action is ready.

## Proposed implementation increments

1. Add immutable profile storage and a read-only snapshot operation over existing
   observations. Use a few qualified scalar fields, explicit unknowns and no HUD
   graphics, game-input macros or broad inventory scans.
2. Render the same snapshot as a synthetic text HUD and agent JSON. Verify that
   they agree while the current native scene remains unchanged.
3. Add snapshot save/load, baseline/delta semantics and resume-time revalidation;
   retain native checkpoints as a separate authority.
4. Add one edition-qualified Sierra item/flag profile and a small DinoPark
   management profile. Reuse existing recovery evidence where it applies; collect
   only the missing field/context qualification.
5. Add bounded collections, derived metrics and graphical presentation only when
   required by the next useful profile.

Use existing project revision, observation and artifact mechanisms where they
fit. Select canonical schema/API names during implementation review; do not
extend strict existing scene/IL envelopes with unrecognized keys.

## Acceptance cases and benefit measurement

These are requirements for the future implementation, not executed conformance.

| ID | Case | Required result |
| --- | --- | --- |
| H01 | Show a HUD while the native office remains current | One primary game context; auxiliary HUD identity; no guest input or fake native geometry |
| H02 | Read cash/debt from the office without opening their menus | Same qualified underlying values at the same boundary; zero menu navigation |
| H03 | Read missing food, a known zero debt and a known false flag | Unknown stays unknown; zero and false retain their typed meanings |
| H04 | Runtime epoch changes midway through a capture | Batch loses coherence; partial earlier reads are not displayed as current |
| H05 | Save, reload and relocate runtime storage | Old binding IDs and action freshness fail; recipe rebinding and fresh capture recover supported fields |
| H06 | Native restore has no fresh framebuffer | Memory-only HUD can capture after qualified rebinding without advancing the guest solely for a screenshot |
| H07 | Imported JSON or stale context accompanies an action | It supplies historical context only; the action still requires current provider preconditions |
| H08 | Large integer, enum, unknown and partial inventory are serialized | Lossless round-trip; no false collection completeness or inferred item absence |
| H09 | Delta has the wrong baseline/epoch or removes a field | Reject mismatches; explicit removals/invalidations clear cached values; no ghost flags |
| H10 | Switch from investigator/assisted to player-information profile | A new filtered baseline; no privileged field survives through cache, names, alerts or derived values |
| H11 | A value is only a stale menu cache or needs guest execution | Report its actual status; any active refresh is separately requested and receipted |
| H12 | More than 16 fields or a derivation spans captures | Enforce budgets and declared coherence groups; no silent atomicity or freshness claim |
| H13 | Executable/resources/profile interpretation change | Invalidate affected bindings/qualifications; preserve reusable unaffected evidence |
| H14 | Same qualified fact is shown in HUD, JSON and Z | Values and information policy agree; presentation does not invent a second world |

Measure native menu actions/screens avoided, time and model input/output needed
to answer a management/inventory question, cold profile qualification cost,
warm binding/refresh cost, stale/unknown rate and action errors. Compare at equal
information permissions and guest-time policy. Record internal-flag assistance
as a separate experiment where it intentionally changes the information set.
No performance gain or original-game fidelity result is claimed by this proposal.

## Related work

- [Native scenes](SCENE_FRAMEWORK.md), [progressive workflows](PROGRESSIVE_SCENES.md)
  and [text projection](TEXT_PROJECTION.md) provide existing integration boundaries.
- [PR #18](https://github.com/seeker-cyber-maker/fDisBull/pull/18) proposes the Z
  consumer over shared IL; its scene format is not changed here.
- [PR #19](https://github.com/seeker-cyber-maker/fDisBull/pull/19) connects DinoPark
  to an original-backed provider; original execution retains authority there.
- [PR #20](https://github.com/seeker-cyber-maker/fDisBull/pull/20) defines the
  minimum source acceptance and reuse requirements relevant to profile recovery.
- [UIL ownership and export scope](UIL_BOUNDARY.md) remains unchanged. This PR
  contains no original game bytes, states, private addresses or native captures.
