# Universal Interaction Language export boundary

Design boundary, 27 October 2026, with implementation scope clarified on
1 November 2026. This document assigns responsibility for a future general UIL
export. Bounded implemented profiles now exist, including the
[common indexed contract](COMMON_UIL_CONTRACT.md), primitive interaction IL,
Zork IR and partial intents. They do not establish an automatic whole-game
recovery or one consumer supporting every profile.

## Purpose

fDisBull recovers evidence-backed meaning from original programs and resources.
UIL is the portable, agent-readable semantic source produced at the end of that
work. A UIL document can describe scenes, entities, state, rules, events, time,
randomness and declared objectives while retaining links to the original bytes
and observations that support each recovered statement.

UIL is a consumer-neutral boundary. Agent Entertainment Center (AEC) may later
compile a qualified UIL export into one of its cartridges. An unrelated project
may instead translate the same export into Python, JavaScript, Rust, a diagram,
a test corpus or another representation. None of those downstream products is
part of fDisBull merely because UIL made it possible.

## fDisBull responsibilities

fDisBull owns work that requires access to the original artifact or its
recovery evidence:

1. Pin the original executable, resource and project-byte identities.
2. Recover native instructions, embedded scripts, external-file structures,
   labels, data flow and bounded runtime observations.
3. Lift related low-level operations into typed semantic statements without
   erasing unresolved behavior or competing interpretations.
4. Assign stable UIL node and field identities.
5. Preserve source maps from UIL nodes to original byte spans, native addresses,
   external-file intervals, debugger events, scene observations and supporting
   evidence.
6. Define and validate canonical UIL syntax and producer-independent semantics.
7. Record which bounded original-game comparisons were actually performed and
   the resulting claim ceiling.
8. Emit a deterministic, content-addressed UIL export and an independently
   inspectable export receipt.

The shared-label graph may eventually gain UIL endpoints so a supported field
name can resolve across file bytes, native state and semantic source. Such a
link remains an authored correspondence. Label propagation does not by itself
prove runtime execution, byte equality or behavioral equivalence.

## Required export properties

A future UIL export must be self-contained as a semantic source package or use
only relative, content-addressed references declared by its envelope. It must
include or bind all of the following:

- UIL format identifier and version;
- canonical UIL payload digest and byte length;
- producer identity, version and source revision;
- original-source inventory digest without host paths;
- stable semantic node identities;
- source-map and evidence-index digests;
- explicit numeric, overflow, rounding, time and random-stream semantics used
  by the recovered rules;
- unresolved, unsupported and conflicting interpretations;
- validation receipt identities and their bounded claim ceiling;
- redistribution classification for original or derived content; and
- deterministic canonicalization rules sufficient for another implementation
  to reproduce the payload digest.

Content recovered from a program is untrusted data. A UIL package cannot gain
host execution authority by embedding Python, JavaScript, shell commands,
native libraries or another executable extension. A later language design may
provide bounded intrinsics, but their identifiers and semantics must be part of
the versioned UIL contract rather than arbitrary host code.

## Qualification language

The producer must distinguish at least these conditions:

- **candidate** — structurally valid UIL containing hypotheses or unresolved
  behavior;
- **bounded-observed** — named rules were compared with identified original
  observations under declared inputs and starting state;
- **bounded-reproduced** — the UIL semantics reproduced the declared
  observations within their comparison contract;
- **locally-proved** — a named, bounded rule property has a retained proof
  receipt;
- **rejected** — a preserved counterexample contradicts the candidate; and
- **superseded** — a newer export replaces this interpretation without erasing
  its historical identity.

These are per-export and, when necessary, per-node properties. A finite route,
matching screenshot or local arithmetic proof cannot silently promote an
entire game to complete equivalence.

## Language amendments

Human and agent investigators may encounter a game family that the current UIL
cannot represent honestly. They may file an attributable RFC proposing the
smallest compatible core amendment or a versioned capability extension. A
real-time strategy game such as Warcraft or Dune II may, for example, expose
needs around spatial occupancy, factions, fog of war, unit orders, production
queues, deterministic ticks or combat systems that simpler adventure and
programming games did not reveal.

The [UIL RFC process](UIL_RFC_PROCESS.md) requires evidence of the semantic gap,
explicit execution behavior, backward compatibility, fail-closed handling by
older consumers and redistributable conformance fixtures. An accepted RFC does
not automatically implement the feature, activate it in fDisBull or require a
consumer to support it.

## Explicit stop line

fDisBull stops after producing and validating the evidence-backed UIL export.
It does **not** own:

- an AEC cartridge format or cartridge compiler;
- an AEC world virtual machine;
- campaign, expedition, scoring or peer-handoff policy;
- player-facing cabinet tools;
- an AEC verifier or result authority;
- text, point-and-click, web or other presentation layers;
- general Python, JavaScript, Rust or other target-language generators; or
- promotion of a downstream implementation to native-game equivalence.

fDisBull may use a small reference evaluator when needed to validate UIL syntax
or individual semantic rules. That evaluator must not grow into a game console,
player framework or preferred downstream implementation.

## Consumer handshake

The fDisBull side ends with two immutable identities:

1. a UIL export digest; and
2. an export receipt digest describing provenance, validation and limitations.

A consumer begins with an independent intake decision that binds both digests,
the exact UIL contract version it supports and its own treatment of unresolved
capabilities. The consumer stores derived code, cartridges and runtime receipts
under new identities. It never rewrites the upstream export and never inherits
its claim ceiling merely by parsing it successfully.

This permits AEC and ordinary language-conversion projects to evolve
independently while retaining a common, auditable semantic source.
