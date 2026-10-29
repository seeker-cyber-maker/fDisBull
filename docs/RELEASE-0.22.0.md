# fDisBull 0.22.0

Publication follow-up: [0.22.0 is published and the shared installation is active](PUBLICATION-0.22.md).
That record contains the completed tag CI, eight-asset download readback and
local installed-package acceptance. The source-finalization record below and
the tagged package bytes retain their original scope.

This release adds a bounded Z-machine story harness and source-linked
interaction blocks, plus native game-space maps and explicit spatial-action
policies. The original disassembler and debugger remain the authority for
native instruction and runtime evidence. These features do not reconstruct a
whole game or establish equivalence between interpreters.

## Story harness and interaction blocks

The raw Z-machine v3 harness runs a user-supplied story in a separate worker.
It supports observation, commands, private checkpoints and restoration across
worker processes. Execution requires a separately selected Python environment
with Jericho 3.3.1; neither Jericho nor a story is bundled or installed into a
shared environment by the harness. Checkpoints contain private game state and
transcript data. Other VM versions and Blorb containers remain outside the
qualified profile. See [Zork harness](ZORK_HARNESS.md).

UDL and UIL use the same bounded interaction-block representation and evaluator;
the role records whether a document is used as input or output. Versioned
project storage preserves source evidence and verifies file-bound spans.
Evaluation can refuse unmet requirements, and media or input actions remain
pending host operations. This is not a complete compiler or game engine. See
[interaction blocks](INTERACTION_IL.md).

A recovered mailbox slice for Zork I release 88, serial 840726, links two v3
attribute instructions to original DOS interpreter writes. Under the declared
action-entry and object-state witnesses, first and repeated opening text and
selected fields agreed with the original DOS run and the Jericho/Frotz worker.
Same-session and initialized fresh-process DOS restores, and a fresh worker
restore, reproduced the qualified response. This evidence covers the stated
slice and fields, not the parser, whole RAM, or whole-game parity. The detailed
[Zork verification record](VERIFICATION-ZORK-2026-10-29.md) states the inputs,
normalization and claim limits.

## Spatial maps and action policies

Pinned maps describe known and unknown coverage in game-native units. They
combine safe regions, obstacles, hazards, interaction zones and portals with
actor footprints, conditional layers and evidence. Map-aware movement checks
the target before input and rechecks the observed footprint and scene context
while running and settling. Route proposals and stored-state image exports do
not themselves execute or prove a route. Polling cannot exclude every hazard
between observations. See [spatial maps](SPATIAL_MAPS.md).

Spatial actions retain the original guest input and select an explicit policy:

- **Physical** enforces the qualified proximity predicate without actor edits.
- **Assisted** places the actor at a qualified clear anchor, verifies settling,
  then sends the original input.
- **Story** keeps the actor in place while a source-qualified positional guard
  is temporarily widened; nonspatial conditions remain in guest code.

Fair play locks physical mode for the session, including after state restore.
It is a voluntary workflow policy, not a tamper-proof debugger boundary. Saved
scripts expose spatial policy and action steps; the text player reports a
policy marker without exposing investigator details. Guard restoration is
checked, and an uncertain restoration poisons the session.

The bounded AGI picture decoder produces separate 160 × 168 visual and
priority planes. The AGI 2.917 logic layout scanner qualifies instruction and
condition boundaries and branch targets for supported encodings. Story guards
accept only a qualified, non-negated ego position condition in a matching
attached resource. Structural decoding does not prove reachability, action
meaning, complete AGI semantics or whole-room safety.

## Original-game evidence

The [spatial verification record](VERIFICATION-SPATIAL-2026-10-29.md) describes
native macOS ARM64 DOSBox trials on exact private PQ1 and KQ1 inputs:

- PQ1 room 6: physical interaction at a distant position refused; a qualified
  physical pickup, assisted pickup and stationary story pickup each used the
  original GET RADIO action and awarded two points. A repeated pickup retained
  the one-time score. A score watch stopped without running through the stop,
  and the temporary guard was restored.
- KQ1 room 1: a clear original-walking route reached and settled in its stated
  range; a tree approach stopped near the selected footprint boundary. A
  map-aware moat destination was refused before input. A separate unguarded
  probe entered a fatal moat sequence, retained as a counterexample. Upper
  unqualified coverage remains unknown.

These are edition-, context- and action-specific checks, not arbitrary-game
position-free interaction or a complete fair-play campaign.

## Verification and distribution boundary

Ordinary and native Linux CI must pass on the exact release commit before
tagging. The annotated `v0.22.0` tag records the completed run links; the
[release verification record](VERIFICATION-0.22.md) describes the gates and
distinguishes them from the retained development snapshots.
The historical full local Mac run had 1,429 passed,
104 skipped, 2 failed and 23 setup errors; the failures and setup errors concern
Linux ELF fixtures built with the Apple toolchain. That full run was not green
and does not substitute for Linux CI. Focused checks and privately installed
candidate replays are described in the linked verification records.

Packages are tool-only. Licensed games and story files, saved states,
checkpoints, project databases, private traces and game-derived images are
excluded. Native backends, game inputs and the optional story-worker environment
are separately supplied. Archive verification establishes package contents;
installation and runtime checks require their own evidence.
