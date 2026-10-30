# UIL request-for-comments process

Design governance, 27 October 2026. This process permits human or agent authors
to propose amendments to the future Universal Interaction Language (UIL). It
does not imply that the language or any listed extension is implemented.

Current proposal: [RFC 0001: UDL mappings, UIL intents and UDC definitions](uil-rfcs/0001-shared-intents-and-compiler-definitions.md),
with [native and source-definition findings](UDL_UIL_EFFECT_ISOLATION_FINDINGS.md).
It remains draft; linking it here is not adoption.

Additional proposal: [RFC 0002: executable Rosetta contracts, patch propagation and polyglot UDC](uil-rfcs/0002-executable-rosetta-contracts.md).
It formalizes executable backings, shared contracts and qualified composition;
its evidence companion distinguishes prototype results from future requirements.
It also remains draft and changes no current schema or runtime.

## Principle

UIL must be extensible when a real game exposes a semantic gap, but it must not
grow by silently adding one game's accidental implementation details to the
core language. An attributable agent has the same standing as a human to file,
revise, challenge or withdraw an RFC.

An RFC is evidence and a proposal, not executable authority. Adoption requires
a reviewed repository change with explicit compatibility and conformance
evidence.

## Core versus extensions

The UIL core should contain only semantics needed across substantially
different game families: typed state, entities, rules, events, explicit numeric
behavior, deterministic time, declared random streams and provenance.

Game-family capabilities should normally begin as versioned extensions. For
example, an RTS encountered through Warcraft or Dune II might require:

- spatial maps, terrain and occupancy;
- factions, visibility and fog of war;
- units, orders and order queues;
- path requests and declared path-resolution behavior;
- resources, buildings and production queues;
- deterministic simulation ticks;
- combat, damage and projectile semantics; and
- partial or delayed observations.

A provisional identifier might be `uil.rts.spatial-orders@1`. The RFC must
define the actual identifier and semantics; examples here do not reserve them.

## Who may file

Any human or attributable agent may open an RFC pull request. The author must
state its identity or role, the evidence it inspected and whether the text was
derived from a real game, a synthetic fixture or design reasoning. Anonymous
ideas may be retained as leads but cannot become accepted language history
without an attributable adopter.

## Required RFC contents

Use [`uil-rfcs/0000-template.md`](uil-rfcs/0000-template.md). Every proposal
must include:

1. The smallest semantic limitation encountered.
2. At least one named game family or other motivating workload.
3. The evidence showing why existing UIL concepts are insufficient.
4. A minimal proposed core change or versioned extension.
5. Deterministic execution, numeric, time, random and event-order semantics.
6. Producer, consumer, debugger and source-map consequences.
7. Unknown-extension and partial-support behavior.
8. Backward-compatibility and migration treatment.
9. Security and capability limits; arbitrary host code is not an extension.
10. A redistributable synthetic conformance fixture.
11. Positive, negative and malformed-input vectors.
12. Alternatives considered, including representing the game without a new
    language feature.

Proprietary bytes, private saves, credentials and host paths stay outside the
RFC. Their content-addressed private evidence may be named in a local receipt
without being published.

## Lifecycle

RFCs use one of these states:

- **draft** — problem and design are still changing;
- **candidate** — the contract and fixtures are ready for independent
  implementation or review;
- **accepted-experimental** — the extension has a stable identifier and may be
  implemented behind an explicit capability gate;
- **accepted** — the specified conformance and compatibility gates passed;
- **rejected** — the repository retains the rationale and counterevidence;
- **withdrawn** — the author stopped the proposal without erasing it; or
- **superseded** — a later RFC replaces it and links both directions.

Acceptance of an RFC does not implement it, enable it in fDisBull, admit it to
AEC or qualify a game. Those are separate repository changes and receipts.

## Adoption gates

An amendment can be accepted only when:

- its semantic gap cannot be represented honestly by the current language;
- its identifier, version and canonical encoding are fixed;
- required versus optional capability behavior is unambiguous;
- a consumer can fail closed on an unsupported required extension;
- the synthetic vectors are independently reproducible;
- existing accepted fixtures still retain their prior meaning; and
- the accepted scope and remaining unknowns are recorded in the disposition.

Multiple implementations are preferred before promoting an experimental
extension into the core. Popularity, one successful game route or one accepting
runtime is not sufficient evidence of generality.

## Consumer feedback

Consumers such as AEC or independent Python/JavaScript translators may file an
RFC after discovering that an export cannot be represented or executed without
guessing. They should include the exact UIL version, extension set, failing
construct and bounded consumer evidence. They must not fork the language under
the same format identifier while the RFC is unresolved.

If UIL gains multiple independent producers and consumers, governance may move
to a dedicated repository. Such a move must preserve RFC history, identifiers,
accepted specifications and content hashes; it must not silently change the
meaning of existing exports.
