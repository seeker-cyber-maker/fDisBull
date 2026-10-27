# PQ1 conditional semantic-navigation finding

Status: open design/implementation finding

Observed: 2026-10-27

Tested fDisBull release: `v0.18.0` at `416b64d9f4bfcf56e2876656d43f1d6a3d6cfdae`

Current applicability: the relevant public debugger restrictions are unchanged
on `main` at `2544b604bd5736d5f754fbdc2b099cd8905b609a`

## Summary

Police Quest 1 demonstrated three useful movement modes: bounded authentic
walking, a named same-room diagnostic placement, and a proposed authentic
`walk until semantic predicate` route. The first two can be assembled today at
different authority levels. The third lacks one reusable fDisBull primitive.

fDisBull can deliver real keyboard input, stop after a data access, poll bounded
observations and run for measured guest time. Its public DOS memory observations
and data breakpoints, however, must resolve inside the original mapped MZ module.
Its hook API has no predicate and admits only layer, redirect and checked-register
actions. It cannot currently express this complete operation:

> Resolve the current interpreter-owned player coordinate, continue authentic
> movement until a range/crossing/blocked predicate is satisfied, then return a
> bounded semantic receipt so the caller can neutralize and verify the input.

A caller with direct backend access can stop on every write, inspect the runtime
heap field and continue. That bounded probe was sufficient for investigation,
but it is not a stable player/route API. The missing capability is a
resolver-backed semantic observation plus conditional data-watch/run-until—not
a hard-coded PQ1 address or unrestricted heap access.

## Exact tested inputs

No game executable, resource, saved state, screenshot or project database is
included in this repository or pull request. These identities let an authorized
owner identify the bounded reproduction without redistributing it.

| Input | Identity |
| --- | --- |
| Game | Police Quest: In Pursuit of the Death Angel, AGI 2.917 |
| Original interpreter filename | `AGI` |
| Tested debugger alias | `AGI.EXE`, byte-identical alias required by the 0.18.0 nonempty-extension launch rule |
| `AGI` / `AGI.EXE` SHA-256 | `29ddd3f3b91d65b6eade156608d7915e3c8b7f47701cb226ff119b717f3e8bd7` |
| `AGIDATA.OVL` SHA-256 | `f7ca256c1c0ab12509d695baabdd44a3c5e72a570b08118d3ead995a47f4c383` |
| Version evidence | `AGIDATA.OVL` contains the text `Version 2.917` |
| `VIEWDIR` SHA-256 | `e80e7b40535eeaad4b03141613a404329b7bbfd2fef0e9fd08a0a9da3ac457ce` |
| `VOL.0` SHA-256 | `04449e1da52628290906eee1fe81c0cbfdae7a6fb146dfda652c1a7dd6304e52` |
| fDisBull source | `0.18.0`, commit `416b64d9f4bfcf56e2876656d43f1d6a3d6cfdae` |
| DOSBox agent backend | macOS ARM64 Mach-O, SHA-256 `afa92bda2184e0c6f2fd685b164700058d212dd29b74af687de86234473d98d6` |
| Host used for the bounded probe | macOS 27.2, Darwin 27.2.0, ARM64 |

Runtime addresses and coordinates below belong only to the tested binary,
resource set, backend and saved state. They are evidence, not portable constants.

## Bounded observations

The game uses latched directional input: pressing a direction begins continuous
movement and pressing the same direction again stops it. A controlled
approximately 300 ms rightward input moved the observed logical x coordinate
from 60 to 63.

Authentic routes were then exercised through the game's own parser and movement:

- requesting the keys from the room center produced the game's not-close-enough
  response; walking to the object and requesting it succeeded, changing score
  from 0 to 1;
- requesting the radio from the wrong position produced the same proximity
  rejection; walking right and up to it and requesting it succeeded, changing
  score from 1 to 3.

A write watch on an initially suspected coordinate mirror stopped at shipped
interpreter instruction `0824:7C06`. The preceding instruction reads through
`DS:[DI+3]`. In the observed state, `DS=0x1219` and `DI=0x4A87`, identifying the
current ego screen-object record at physical linear `0x16C17`. Current x/y words
were at offsets `+3/+5`; previous x/y were at offsets `+0x16/+0x18`. A guarded
edit of that authoritative object record persisted across an engine cycle,
whereas the initially suspected mirror did not.

From the untouched station-entry state `(60,120)`, a guarded same-room placement
to the already qualified radio anchor `(67,98)` followed by the original parser
command `GET RADIO` succeeded and changed the score from 0 to 2. This establishes
one diagnostic placement and one named anchor. It does not establish arbitrary
safe teleportation, an ordinary player route or a universal AGI object address.

The data-watch stop is post-write and before the next instruction. That makes
the newly written coordinate available for a conditional decision. A range or
crossing predicate is safer than exact equality because one movement update may
step over an exact value.

## Current public boundary

The relevant APIs deliberately bind observations to static project authority:

- `DebugSession.memory()` rejects a range outside the original mapped MZ module;
- `_data_breakpoint()` applies the same mapped-module restriction;
- `wait()` can compare memory, registers or status, but its memory observation
  calls the restricted public memory method;
- `hook()` has no condition/predicate and can only change layer stacks, redirect
  execution or apply checked register edits after each admitted hit.

Those restrictions are safer than accepting an arbitrary conventional-RAM
address. The gap is an explicit semantic runtime authority that re-resolves the
interpreter-owned object in each live session.

## Proposed primitive

The exact API remains a design choice. It should separate reusable semantic
identity from session-local address evidence. One possible two-part contract is:

```json
{
  "observation": {
    "adapter": "agi-screen-object-v1",
    "selector": {"object": "ego"},
    "fields": ["x", "y", "previous_x", "previous_y", "room", "direction", "didnt_move"]
  },
  "until": {"field": "x", "in_range": [65, 69]},
  "limits": {"guest_ms": 3000, "watch_hits": 256, "unchanged_hits": 8}
}
```

Required invariants:

1. Bind the adapter to exact target/resource identity and an adapter version.
2. Resolve the object in the current paused session; never reuse an earlier heap
   address as sufficient authority.
3. Support bounded equality, ordering, range, change, unchanged-count and
   crossing predicates without arbitrary target-supplied code execution.
4. Preserve post-access-before-next-instruction semantics in the receipt.
5. Bound guest time, host time, watch hits, unchanged hits and retained evidence.
6. Return the resolved field/address as per-session evidence together with
   start/end values, predicate, hits, context, measured guest time and stop reason.
7. Stop and report incomplete on ambiguous resolution, room/context change,
   target exit, other breakpoint/hook, adapter mismatch or exhausted budget.
8. Re-resolve after state restore, resource reload or session restart.
9. Keep target-specific route composition and stop-input policy in the consumer;
   fDisBull should expose the bounded semantic stop, not pretend every program
   uses the same movement latch.
10. Preserve existing mapped-module memory, breakpoint and hook behavior.

The consumer can then implement a target-specific `walk until` transaction:
send ordinary direction input, wait on the semantic predicate, send the target's
ordinary neutralizing input, and verify settled direction, in-range coordinate,
unchanged context and an empty input queue. If the coordinate remains unchanged
for the declared limit or the adapter reports a no-movement flag, the route ends
as blocked rather than consuming its entire budget blindly.

## Acceptance checks for a future implementation

Use a deterministic open fixture rather than PQ1 assets.

- A synthetic DOS interpreter allocates and relocates a player-object record
  outside the imported MZ image.
- A version-bound adapter resolves the current object and exposes typed fields.
- A write predicate stops only after the requested range/crossing condition,
  while retaining a bounded count of nonmatching hits.
- Exact-equality, range, crossing, changed and unchanged-count predicates have
  positive and negative tests.
- Wrong target hash, ambiguous object, stale address after relocation, context
  change and exhausted budgets fail closed with distinct incomplete outcomes.
- Restore/restart forces fresh resolution and never trusts the old address.
- A target-specific fixture route clears its latched input and verifies a
  settled final state after the predicate stop.
- Existing module-bound memory waits, breakpoints and hooks remain unchanged.
- Distribution checks prove no game files, states, screenshots, databases or
  proprietary evidence entered the package.

An authorized PQ1 rerun can supplement those tests but is not the portable
regression fixture.

## Related observation alternatives

The same investigation also validated object-state observation with an
ego-transparent rendering projection. The separate runtime-resource-layer
finding in pull request #6 records that authority gap. The bundled
`fdisbull-investigate` skill now routes among authentic walking, conditional
walking, named routes, diagnostic placement, persistent or transient actor
hiding, a neutral observation anchor and actor-visible review. These alternatives
must remain labeled by authority; none turns a diagnostic shortcut into proof
of ordinary play.

## Claim ceiling

This finding establishes authentic bounded walking and proximity-gated pickups,
one state-specific authoritative ego record, one guarded same-room diagnostic
placement and a concrete public API gap for the exact inputs above. It does not
validate the proposed primitive, generalize the adapter to other AGI releases,
prove arbitrary teleport safety or convert a diagnostic route into player
progress.
