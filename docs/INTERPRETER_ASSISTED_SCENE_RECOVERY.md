# Proposal: interpreter-assisted scene recovery

This is a proposed investigation method, not an implemented extractor, new Z
format, or evidence of game recovery. Use it to choose and test source-recovery
questions while preserving the original interpreter as an independent execution
reference. [PR #32](https://github.com/seeker-cyber-maker/fDisBull/pull/32)
already recovers source-specific Zork scene, dispatch and window-intent documents;
this proposal complements those definitions and their explicit residual paths.
It does not replace them with observations or claim their reported results were
independently rerun here.

## What an interpreter can contribute

An explicitly selected interpreter can expose output and state changes for
bounded commands from a known starting state. Depending on its actual APIs and
verified bindings, it may also expose current room, object relationships,
attributes, parser results or dispatch events. These are different observation
channels, not guaranteed capabilities of every interpreter. The current
`zork_worker` bridge exposes command results and private state snapshots; it
does not expose a verified scene graph, object visibility, admissible actions or
parser dispatch API. A new inspector or instrumentation would need its own
versioned capability, source identity, tests and privacy boundary.

There is a concrete upstream starting point: [Jericho's public implementation](https://github.com/microsoft/jericho/blob/master/jericho/jericho.py)
offers `get_world_objects`, `get_player_location` and dictionary access. Its
action generator attempts candidates and requires supported game bindings;
it is not an exhaustive parser specification. Preserve the uncleaned object
view (`clean=False`) as evidence: the cleaned view can suppress moving objects.
These upstream methods are not capabilities already exposed or qualified by
the current fDisBull bridge; check the selected version and story first.

A room number or parent relation can suggest membership; it does not alone
prove an object is visible, reachable or enabled. A parser response is one
sample under one state, not a complete grammar or action inventory. A transition
observation covers its actual path; hidden flags, alternate branches, dynamic
callbacks, scheduler events, RNG and partial effects can remain unknown. Other
engines need their own adapters: the existing AGI 2.917 logic inspector is a
partial static decoder, not an AGI interpreter.

## Separate artifacts and contracts

1. **Private observation bundle:** exact story and interpreter hashes, version,
   seed, checkpoint identity, command and prior-action identity, observation
   channel, bounded execution outcome and any relevant event ordering. Keep
   story bytes, private text, state and transcripts outside Git. Do not treat a
   timeout or failed observation as proof that an action had no effects, and do
   not retry an uncertain action without the existing continuation contract.
2. **Source-bound UDL evidence:** qualified story-byte locations and decoded
   instruction/table facts, pointer and routine identities, guard dependencies,
   writes, output, dispatch, returns and residual joins. Static source identity
   and runtime bindings need separate verification; labels and observed values
   alone do not establish meaning or completeness.
3. **Qualified UIL and Z projection:** address-independent scene identities,
   conditions, actions and ordered effects only at supported boundaries, with
   explicit residual/unknown behavior and provenance to each obligation. The
   existing `fdisbull-il-scene-1` projection and PR #32's source-specific scene
   and dispatch documents are distinct consumers/contracts; do not silently
   map between them or introduce an additional incompatible format.
4. **Independent player and evidence:** publish an authorized content package
   separately from interpreter, source database and observation bundle. Check
   player behavior and checkpoint continuation from its own inputs; inability
   to reach the original interpreter must not fabricate successful behavior.

Keep static source candidates, runtime observations, inferred associations and
accepted contracts distinguishable. Do not promote a recorded action into
complete parser, room, world or whole-game semantics.

The first implementation should be a capability-negotiated, passive snapshot
reader producing scene **candidates**, followed by explicit guarded probes.
Bind object identities to the source story/table and observations to the exact
state; invalidate live candidate tokens after commands or checkpoint restore.
Avoid sending `look` as if it were passive observation. Resolve accepted fields
and transitions into the existing UDL/UIL/Z contracts, with private evidence
references and residual joins, while retaining the independent player. This
keeps interpreter execution and recovered content as separate components.

## A bounded experiment

Use one already qualified edition and one room with a simple object and one
transition. Declare in advance the scene, visible/hidden and reachable/enabled
questions, target actions, supported normal/refusal paths, continuation and
observable effects. Include a distinct target in a similar state and at least
one held-out alternate state. Avoid assuming that an object record or displayed
label uniquely identifies the player-facing action.

For an interpreter-assisted arm, take a private checkpoint, perform a small
fixed sequence of authorized observations and commands, and record source-bound
room/object/dispatch candidates and state deltas where the selected backend
actually supports them. Compare normal, repeated and refused actions; retain
unknowns and the original ordered output/effects. Restore only under a verified
checkpoint and continuation contract. Then use static source traversal to bind
candidate values, guards, writers, parser admission and residual behavior; a
runtime sample alone cannot authorize semantic lowering. Build the existing
scene consumer's supported projection with unsupported paths explicitly
residual. Compare the source interpreter and independent player at the same
admitted boundaries, including ordered state/output and checkpoint continuation,
with a deliberate wrong-target or wrong-guard negative control.

Run a static-first arm against the same edition, predeclared obligations,
accepted evidence standard and held-out cases. Select the information mode
before the work and avoid sharing findings between arms. Record setup, source
and tool reading, native probes, implementation, validation, corrections and
failed attempts. Compare accepted source-linked obligations, unresolved and
incorrect claims, commands/probes, output volume and total elapsed work. Report
whether interpreter assistance reduced effort **at equal qualified coverage**;
no speedup follows merely from a faster first observation. Preserve all unknowns
and treat a missing observation as missing, not absence.
