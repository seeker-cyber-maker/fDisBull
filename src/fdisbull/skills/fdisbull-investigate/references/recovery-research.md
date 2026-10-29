# Research-led recovery and progression

Use this for a request to investigate or reconstruct a game, not for every
small code question. Respect the user’s desired play policy and spoiler bounds.
Research offers hypotheses and probe choices; it is not authority over the
selected target or permission to obtain game files.

## Qualify prior work

1. Record target hashes, edition, platform, language, executable and resource
   identities, interpreter version and known modifications. Search for prior
   reverse engineering, source, format and interpreter projects for the exact
   target first; then qualified close variants. Record URL, revision/date,
   provenance, license constraints and what version each source actually covers.
2. Read primary implementation/source and format evidence where available.
   Check claimed byte ranges, resource hashes and version mappings against the
   supplied files. A source tree or a recreation can illuminate a hypothesis but
   is not proof that this binary was built from it or behaves identically.
3. When normal progress matters, research manuals and independent guides as
   secondary reports. Synthesize an original, task-scoped checklist covering
   known normal milestones and prerequisite alternatives through the requested
   end condition. Mark missing sections, version conflicts, uncertainty and
   spoilers; do not reproduce a copyrighted guide. If the sources cannot support
   a complete checklist, say so instead of inventing one. Start with the current
   scene and likely frontier; extend the guide as evidence arrives. Preserve
   lineage: a rewritten guide is not an independent witness to its source.

Examples of source categories, not automatic target matches: ScummVM’s
[AGI detection table](https://github.com/scummvm/scummvm/blob/master/engines/agi/detection_tables.h)
records numerous edition and platform identities; its
[AGI logic implementation](https://github.com/scummvm/scummvm/blob/master/engines/agi/logic.cpp)
is an interpreter implementation, not proof of an original runtime path. The
[Zork I historical source archive](https://github.com/historicalsource/zork1)
and [DinoPark static recompilation project](https://github.com/sp00nznet/dinopark)
are source leads with their own scope and version; qualify against the selected
files before relying on them.

This checklist builds on the guide-derived scene investigation proposed in
[PR #20](https://github.com/seeker-cyber-maker/fDisBull/pull/20); the broader
Gob/source-adapter and acceptance contracts there remain proposals.

## Turn leads into qualified scenes

Convert each relevant milestone into candidate scenes, objects, entry state,
prerequisites, actions, transitions, observable outcomes and persistence. Keep
contradictory alternatives and unknowns. Track the source-qualified guide claim,
our inferred steps, code binding, runtime readiness and persistence separately.
For each useful lead, record context, exact claim and origin, inferred steps,
resource/handler and effect binding, required runtime evidence, disposition
and cheapest next question. A practical table in private project notes suffices.
Guide order does not prove a prerequisite; a compressed step can hide closeups
and intermediate interactions. Inspect relevant wrong-item, repeat, refusal and
alternate branches omitted by a successful route. Prioritize the next discriminating
probe by expected decision value, cost and confidence; use a bounded ordinary
input and compare before/after with a control where practical. Confirm input
consumption, readiness, completion and committed effects separately. A native
action timeout or partial reply can leave effects unknown: inspect retained
evidence and current state before deciding whether any retry is safe.

Store source-bound observations and named scene actions as they are qualified;
compose a normal-progress route only from supported transitions and mark each
unverified edge. Select physical, assisted or story policy explicitly, record
interventions, and preserve fair-play constraints. A live snapshot is not a
durable native save; validate save and fresh-load evidence separately. A
separate player or authored projection is a consumer of bounded content, not
proof of complete original-game recovery. A hidden-object clue stays a private
lead: test the search or container action and observe inventory/flag changes;
do not infer absence from pixels or expose future discoveries in public player
narration. Record guide use and prior knowledge in benchmarks: physical fair
play does not establish a cold, guide-free run. Include research and analyst
preparation time in any discovery-efficiency comparison.

## From code to semantics

Trace a candidate from native bytes and offset/version through instruction
meaning, data access and control flow; establish whether a guest interpreter
loads and executes a resource before attributing its behavior to it. Bind
source spans and assumptions to supported UDL lifts, propagate those into UIL
state/effects and retain unmodeled edges. Verify a changed candidate only at
the declared inputs/outputs with satisfiable assumptions, and compare selected
original-runtime outcomes where authorized. A narrow Z3 result proves equality
of supplied models at that boundary, not model fidelity, full-game equivalence
or independent generated code. See [udl-uil-udc.md](udl-uil-udc.md).
