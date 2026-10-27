# Universal Interaction Language export boundary

Design boundary, 27 October 2026. This document assigns responsibility for a
future Universal Interaction Language (UIL) export. It does not claim that a
UIL grammar, exporter, compiler, runtime or game conversion is implemented.

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

## UIL as semantic intermediate representation

UIL is not only an interchange file from which another source language can be
generated. It is the proposed semantic intermediate representation of the game
world itself: the versioned contract between recovered meaning and every later
execution, observation or presentation surface.

More precisely, UIL is the intermediate language and its canonical parsed world
graph, state model and event rules are the intermediate representation. JSON or
another future encoding transports that model; the serialization is not the
architecture by itself.

A Zork-like venue can therefore be a reference projection of UIL rather than a
separate prose adaptation. Its two directions have distinct roles:

- the text renderer derives room descriptions, visible objects, exits and
  transitional messages from the UIL world state, observation policy and
  emitted events; and
- the parser resolves player verbs, nouns and qualifiers into canonical UIL
  intents or actions before the world state changes.

The same UIL state can feed a point-and-click scene, graphical replay, debugger,
headless agent protocol, test fixture or verifier. Those surfaces may organize
authorized observations differently, but they must not privately invent world
facts, commands, collision behavior or outcomes that are absent from the bound
UIL version and its declared extensions.

This makes the text venue useful as more than an accessibility or output mode.
It can be a conformance surface for the intermediate representation. Given the
same starting state and canonical intent sequence, independently implemented
text, graphical and headless consumers should agree on the canonical state and
event trace within the declared comparison contract. Pixel layout, prose and
input affordances may differ without changing game semantics.

Presentation still has authority boundaries. A prose renderer may summarize or
name an authorized observation, but it does not turn hidden, occluded, unknown
or merely inferred state into player-visible truth. A parser may offer aliases,
but each accepted command resolves to an attributable canonical intent. When a
consumer cannot represent a required UIL capability, it fails closed or invokes
the RFC process instead of approximating the rule silently.

fDisBull remains only one evidence-backed UIL producer. AEC may later author an
original game directly against the same semantic contract, with separate
authorship and qualification provenance. Such native content is not described
as recovered from an original executable merely because it uses the same IR.

### Round-trip loss accounting

Treating the text venue as an IR projection makes the path measurable. A
`Zork-like source or transcript → UIL → Zork-like venue` comparison should emit
a loss receipt rather than rely on whether two passages sound similar.

The comparison should retain at least these independent dimensions:

- **observable facts** — visible entities, properties, exits and relations
  retained, omitted or invented;
- **epistemic state** — `present`, `absent`, `occluded`, `unknown`, `inferred`
  and hidden facts preserved without unauthorized promotion or leakage;
- **affordances** — original player intents still expressible, newly invented
  interactions and aliases or disambiguation that did not survive;
- **transition semantics** — matched starting state and canonical intents yield
  the same state changes, failures and ordered events;
- **time and randomness** — declared ticks, waits and random-stream consumption
  remain equivalent within the comparison contract;
- **narrative payload** — required authored messages, tone-bearing labels or
  clues retained separately from freely paraphrasable connective prose; and
- **unresolved meaning** — ambiguity and unsupported constructs remain explicit
  rather than being resolved by the renderer's guess.

Do not collapse those dimensions into one flattering similarity score. Report
precision and recall for typed observable facts and affordances, trace
differences for transitions/events, explicit leak counts for hidden facts, and
a ledger of unsupported or changed constructs. Exact text equality is required
only for content declared verbatim; otherwise prose may differ while the
semantic projection remains lossless under its declared observation contract.

Both round-trip directions are informative. `UIL → text → recovered UIL` tests
whether the venue expresses enough authorized information to reconstruct its
declared observable projection. `Text/source → UIL → text` measures recovery and
rendering loss against the original interaction surface. Neither finite test
proves that the complete game or every paraphrase is equivalent.

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
