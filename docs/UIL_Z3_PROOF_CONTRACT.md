# UIL invariants and bounded solver proof contract

Status: design contract for a future UIL validator and locally proved rule
receipts. This document does not claim that fDisBull exports UIL, validates a
complete game world, or proves behavioral equivalence to an original program.

The [UIL boundary](UIL_BOUNDARY.md) permits a semantic node or export to be
qualified as `locally-proved`. This document defines what that phrase may mean
for world structure, scene navigation, movement profiles, content readiness and
finite traces. It also defines what a satisfiable or unsatisfiable Z3 model does
**not** establish.

This contract complements the semantic-input and navigation proposal in
[PR #10](https://github.com/seeker-cyber-maker/fDisBull/pull/10). It is kept in a
separate change so that the 0.20 implementation can adopt, amend or reject each
solver seam without conflating documentation agreement with executable
evidence.

## Objective

Use a solver as a strict checker of an explicit finite model. Do not use a
solver as a replacement for recovery evidence, runtime observation, game-engine
validation or the player's investigation.

The intended chain is:

```text
original bytes and runtime observations
                 |
                 v
       attributed semantic claims
                 |
                 v
      versioned finite solver model
                 |
                 v
        solver result and receipt
```

Every arrow is a separate authored correspondence. A solver can check the model
it receives. It cannot independently establish that recovered instructions,
decompiled C/C++, a screenshot, a memory field or a UIL node was mapped into
that model correctly.

## Preserve three-valued knowledge

Recovered game knowledge is not ordinary closed-world Boolean data. At minimum,
each relevant proposition has three epistemic states:

- **known true** — admitted evidence supports the proposition;
- **known false** — admitted evidence supports its negation; and
- **unknown** — evidence is missing, unavailable, ambiguous, conflicting or
  outside the declared scope.

Omission must not mean false. For example:

- a missing collider observation does not make the route clear;
- a missing object sample does not prove that the object is absent;
- a missing coordinate does not prove that movement stopped;
- a missing readiness field does not make the interface ready; and
- an unmodelled exit does not prove that the exit is blocked.

Z3 is two-valued at the proposition level, so an adapter must encode knowledge
explicitly. A suitable finite encoding can use a tag such as
`TRUE`, `FALSE`, `UNKNOWN`, or a pair such as `known_F` plus `value_F`. The
adapter may constrain `value_F` only when `known_F` is true. It must not assert
`not F` merely because no evidence asserted `F`.

Conflicting observations should normally remain an explicit conflict in the
semantic layer. They must not be resolved by whichever fact happened to be
encoded last. An implementation may reject a conflicting model or encode the
competing interpretations as alternatives, but its receipt must say which
choice it made.

## Version-bound proof subject

A proof receipt must bind every identity needed to understand its scope. The
minimum subject envelope is:

- original executable, story, resource and external-file identities used by
  the recovery;
- selected fDisBull byte-version identity;
- semantic model or UIL payload digest and format version;
- source-map and evidence-index digest, when present;
- observation-adapter and game-profile identities;
- runtime engine or verifier identity when runtime evidence is used;
- canonical solver-model digest;
- solver name and version;
- assumptions, finite bounds and timeout;
- result status and any counterexample; and
- a human-readable claim ceiling.

Source material and runtime material are separate identities. A source tree may
describe one historical build while a purchased or installed game executes
another. The receipt must not label a runtime result with only the source
artifact's version.

### Zork calibration example

The bounded Zork experiment that motivated this distinction used two legitimate
Z-machine v3 stories:

| Role | Release | Serial | Size |
| --- | ---: | ---: | ---: |
| MIT-source compiled story | 119 | 880429 | 86,838 bytes |
| Purchased GOG runtime story | 88 | 840726 | 92,160 bytes |

The declared seven-command mailbox and house-navigation trace agreed on outcome
class, room, inventory and open-container state. That is evidence for the named
trace and fields. It is not evidence that the two complete stories are
equivalent, nor permission to identify Release 88 results as Release 119
results. A UIL receipt must retain both identities.

## Check families

Each check family below has a separate subject and claim ceiling. Passing one
family must not promote an export through another family automatically.

### 1. World referential integrity

A structural validator may establish, for a declared finite world model, that:

- every known passage target names a declared scene or an admitted external
  reference;
- every known entity location names one declared scene, container, inventory or
  other permitted location kind;
- identifiers are unique in the namespace in which they are declared;
- aliases do not resolve ambiguously within the selected version;
- a blocked exit has an explicit bounded observation or authored reason rather
  than an invented destination; and
- an unresolved exit remains explicit `unknown`.

Passing these checks establishes internal referential consistency. It does not
establish that every room, object or exit in the original game was recovered.

### 2. Containment and visibility preconditions

A finite object model may establish that:

- each entity has at most one immediate location in a state;
- the containment graph is acyclic;
- inventory, direct scene placement and container placement are mutually
  exclusive immediate locations;
- a container cannot directly or transitively contain itself;
- declared capacity bounds are respected when capacity semantics are present;
- a hidden or enclosed entity cannot become visually observable unless a
  declared visibility rule permits it; and
- unknown container state or unknown occlusion does not become visible or
  absent by default.

These checks concern the supplied containment model. They do not prove parser
behavior, narrative descriptions or complete object-tree recovery.

### 3. Scene geometry

For a declared game-space coordinate system, a validator may establish that:

- dimensions, actor footprint and anchor are internally well formed;
- spawn, destination and safe-teleport anchors lie inside declared bounds;
- an anchor advertised as walkable fits the complete actor footprint inside the
  authored walkable region;
- known-active colliders do not overlap an advertised clear anchor;
- portal endpoints name valid scenes and coordinates; and
- source-derived geometry retains its extraction rule, source facts and
  evidence status.

Conditional colliders need epistemic treatment. A collider known active can
make a point blocked. A collider known inactive can be excluded for that state.
An overlapping collider with unknown activation makes the point `unknown`, not
`clear`.

Geometry establishes properties of the authored spatial model. It does not
prove that the game will accept input, that physics matches the shape, or that a
route will complete at runtime.

### 4. Movement profiles

Physical input primitives must retain stable meanings. An atomic key press must
not silently become a held or latched movement operation.

A movement-profile validator may require:

- an explicit profile identifier and game/version binding;
- one declared movement style, such as atomic, held, latched or another
  versioned extension;
- explicit start, observation, neutralization and stop behavior;
- finite guest-time, host-time, step, frame or poll bounds as applicable;
- an explicit destination predicate;
- an explicit policy for debugger stops, scene changes and missing
  observations;
- no automatic resend of a state-changing action; and
- no inherited key-release semantics for a latched profile unless the profile
  declares them.

The Police Quest pattern in which a second complete direction press stops
movement and a conventional hold-to-move pattern therefore require distinct
profiles. Sharing the word `stop` is not a reason to share physical input
semantics.

Passing profile validation establishes that the policy is finite and internally
specified. It does not establish that a particular game consumes the input as
modelled.

### 5. Bounded blocked-route detection

A route may be classified `blocked` only from a declared observation contract.
For example, a profile may require qualified x/y observations to remain equal
for `N` consecutive completed samples while:

- the destination predicate remains known false;
- the same scene and coordinate interpretation remain active;
- the actor is expected to be moving;
- no debugger stop, hook, guest error or portal transition intervenes; and
- all required samples are complete.

The detector must not report `blocked` before the declared bound is met.
Movement that resumes before the bound expires invalidates that candidate
window. A scene change, teleport, checkpoint restore or discontinuity resets
the detector unless the selected profile explicitly defines another
version-bound behavior.

Missing coordinates, incomplete samples, an unknown destination predicate or
an unknown movement expectation produce `unknown` or an explicit interrupted
result. They are not evidence of a collision.

Known source geometry plus a runtime stall may support a narrower result such
as `blocked_known_boundary`. A stall without a qualified boundary remains
`blocked_unknown` or `unknown`, according to the declared result vocabulary.
The immediate authentic failure screenshot is evidence attached to the result;
it is not itself a proof of collision.

### 6. Scene content readiness

Scene-family recognition, requested content, displayed content, readiness and
action completion are separate propositions. A validator may establish that a
declared action requires the particular facts named by its contract, for
example:

- the scene family is matched;
- requested content is known;
- displayed content agrees with the request;
- required controls or state are ready/enabled; and
- the action's precondition is known true.

A scene may be ready for screenshot comparison but unready for navigation,
interaction or a completeness claim. `NOT_READY` requires evidence for a known
false requirement. A missing requirement produces `UNKNOWN` or an incomplete
observation, not `NOT_READY` and never `READY`.

Passing a readiness formula proves only that the supplied facts satisfy that
formula. It does not prove that the facts were measured correctly or that the
following action will succeed.

### 7. Finite trace consistency

A solver may check whether a finite sequence of declared states, intents,
events and observations is consistent with an explicit transition model. A
trace check should bind:

- the initial-state identity or complete declared initial facts;
- every admitted command or intent;
- each state transition and observable event selected for comparison;
- the runtime engine/verifier identity;
- the semantic model identity;
- the compared fields; and
- the finite length and any time/random-stream assumptions.

A conflicting trace should retain the first conflicting step, unsatisfied
constraint or concrete counterexample when available. A satisfiable trace means
that at least one model execution is consistent with the supplied constraints.
It does not establish that the transition model is complete, uniquely inferred
or equivalent to the original game outside that trace.

## Solver outcomes and allowed language

The public result vocabulary must preserve at least:

- **proved-under-assumptions** — the negation of a named property was
  unsatisfiable within the exact finite model and assumptions;
- **counterexample** — a satisfying assignment contradicts the proposed
  property;
- **vacuous** — the assumptions themselves were unsatisfiable, so no useful
  property result was established;
- **unknown** — the solver timed out, returned unknown, or the adapter lacked
  required facts or capability;
- **unavailable** — the selected solver was not installed or could not run; and
- **invalid-model** — the supplied model or envelope failed structural or type
  validation before solving.

`SAT` must not be presented as “the game is correct.” `UNSAT` must not be
presented as “the game cannot do this” unless the admitted correspondence and
model completeness needed for that statement were independently established.
A timeout is not a counterexample, and an unavailable solver is not a failed
game rule.

## Relationship to bounded expression checks

If the bounded expression-equivalence checker proposed for 0.20.0 lands, it
should remain a deliberately smaller interface. Equality of two explicitly
supplied fixed-width expressions under assumptions is different from world
integrity, epistemic state, geometry, navigation policy or trace consistency.

Do not encode an entire UIL claim into an opaque expression and then inherit an
expression-equivalence result as world validation. A future implementation may:

1. reuse a common receipt envelope and solver loader;
2. give each check family its own versioned input/result format;
3. lower a validated family-specific model into Z3 internally; and
4. preserve the family-specific claim ceiling in its receipt.

The family validator, not Z3 syntax, is the public semantic authority.

## Minimum synthetic acceptance scenarios

An implementation should use redistributable synthetic fixtures and establish
at least the following:

1. A passage to an undeclared scene is rejected.
2. An overlapping collider with unknown activation returns `unknown`, never
   `clear`.
3. A containment cycle is rejected with the involved identities retained.
4. A held or latched movement profile without bounded neutralization is
   rejected.
5. A blocked detector does not fire before its configured consecutive-sample
   bound and does fire at the bound for a complete qualifying trace.
6. Missing one required coordinate or destination observation prevents a
   blocked verdict.
7. Scene-family match with missing content-readiness evidence cannot satisfy an
   action-ready predicate.
8. A contradictory finite transition trace yields a conflict or
   counterexample tied to the relevant step.
9. Two story or engine versions with the same title remain separate proof
   subjects even when a bounded trace matches.
10. Timeout, unavailable solver and invalid model remain distinct results.

Original game files, saved states, project databases and proprietary screenshots
must remain outside Git. Tests committed to the repository must use newly
authored synthetic data or redistributable fixtures.

## Acceptance boundary

This document becomes implemented only when executable validators, schemas,
tests, persistence behavior and user-facing documentation land together and
their actual results are retained. A documentation merge records a design
decision; it is not evidence that the validators exist or that any game has
passed them.

A later release may claim a check family only when it can answer all of these:

1. What exact subject and version was checked?
2. Which observations and authored correspondences entered the model?
3. Which facts remained unknown or unsupported?
4. What finite bounds and assumptions were applied?
5. What did the solver return?
6. What narrower claim is justified by that result?
7. Which stronger claims remain explicitly unestablished?
