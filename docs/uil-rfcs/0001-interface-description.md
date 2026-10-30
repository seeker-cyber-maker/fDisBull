# UIL RFC 0001: Events require an interface description for interactive fidelity

- Status: draft; identifier and encoding require maintainer review
- Author or agent identity: ChatGPT, DinoPark investigator, requested by TiGa
- Date: 2026-10-27
- UIL core version: not yet specified; amendment to the design in PR #3
- Proposed extension identifier: `uil.interface@1` (provisional, not reserved)
- Supersedes: none
- Superseded by: none

## Semantic limitation

An event describes a transition or effect, not necessarily how a user can cause
it or what the user can observe. An interactive export consisting only of events
can omit controls, modal focus, pending-versus-committed displays, unavailable
actions and presentation completion. A consumer could execute the right formula
through an interaction that never exists in the original program.

Amend the UIL design as follows: interactive-fidelity exports must supplement
semantic events with a provenance-bound interface description. Bind event and
interface identities without collapsing them. Purely autonomous internal events
must not be assigned invented buttons. An export with unknown interface behavior
may remain a candidate, but must disclose that gap and must not claim interactive
fidelity. Nonvisual command/protocol interfaces are valid interface descriptions.

This RFC does not design a renderer, player, general-purpose interpreter or
complete UIL grammar. Implementation remains with the fDisBull agent and the
separate consumer projects under the existing ownership boundary.

## Motivation and evidence

DinoPark original-DOS E41 supplies two concrete observations:

- The same visible OK label and command ID accepts a pending staffing draft on
  a detail panel, but commits the roster on the enclosing screen. Context is
  necessary to identify the semantic action.
- A pending staff value changes before the corresponding display and control
  enable state finish updating. A state event alone is not a ready interface.

E41 also observes a salary display derived from pending rather than active
staff. These bounded, original-input observations motivate the amendment; they
are not a universal UI model. Original executable SHA-256 is
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
The E41 report and portable scene evidence remain in the user's research packet;
no proprietary bytes, private paths, database or native checkpoint are embedded.

Other motivating workloads are point-and-click interfaces and parser-driven
adventures. PQ1/KQ1 AGI are user-named parallel investigations, not implementations
or compatibility results produced by this RFC. An interface may expose text
verbs, spatial targets, hotkeys, or combinations without changing the event's
meaning. The screenshot-hook implications are documented separately in PR #5.

## Proposed semantics

### Minimal linked description

For each recovered interactive surface retain, where applicable:

1. A stable interface/context ID, its state/subpage/modal/focus conditions and
   links to the original source/evidence. Names alone do not prove a context.
2. Stable object/control IDs, labels and declared roles. Keep existence, visible
   presence, occlusion, readiness and enabled state separate; represent unknown
   observations explicitly rather than coercing them to absence.
3. An input binding to a named semantic action, including its context and
   preconditions. One label or command code may map to different actions in
   different contexts. Keep draft acceptance, final commitment and cancellation
   effects distinct. Bind keyboard focus or pointer hit geometry when recovered.
4. A projection from model fields to displayed values. Identify draft, committed,
   cached or reconstructed sources and preserve recovered rounding/formatting.
   A displayed number is not automatically the authoritative stored value.
5. The action's semantic event references and completion relationships: input
   receipt, state transition, control update, presentation and persistence when
   relevant. One action may produce multiple events; one event can have multiple
   interfaces. No one-to-one correspondence is assumed.
6. Resource/geometry references needed by the recovered interface: native
   coordinate space, transforms, layering, masks and resource identities to the
   extent established. An image or sound invocation must retain observable
   ordering and completion dependencies. Reducing code to a drawing operation
   must not erase a palette change, hit region, blocking condition or shared-RNG
   effect that changes behavior. Unknown details stay unresolved.

This is a semantic description plus evidence references, not an executable host
plugin. Actual consumer widget choices and rendering remain downstream.

### Time, ordering and observations

Use the UIL core's declared time domain and event order, once specified. Do not
encode host sleep durations as recovered application semantics. The synthetic
fixture below uses integer logical steps solely to make ordering explicit.
Several observations can occur at the same step; provenance must state their
order or that it is unknown. Do not impose a total order absent from evidence.

A state transition can occur before a control update or visible redraw. A new
completed video frame can still contain old application pixels. Record distinct
milestones and their correlations rather than inventing one global `ready` event.
No new random stream is introduced by this extension. Any original time or RNG
consumption associated with interface work must remain in its original declared
stream/order. Presentation can be nonblocking; continuous background animation
need not prevent an otherwise qualified action.

Event replay and interface replay have different claim ceilings. A semantic
consumer may run a rule directly for analysis, but must not claim it exercised
the original input path. An interactive consumer must honor the required input,
focus/modal and action-availability contract, even when rendering differently.

### Encoding boundary

The final schema is deliberately left to the UIL owner. The minimum export
relationship is stable interface/action IDs -> stable event IDs, with reverse
source-map/evidence links and explicit unresolved entries. Include any required
interface payload in canonicalization and the content-addressed receipt; it is
not an optional prose file that can be silently dropped. Until a canonical
encoding is accepted, the examples below are draft conformance vectors, not
valid serialized UIL or a second competing language implementation.

## Capability declaration

Interactive-fidelity exports declare the reviewed interface capability as
required. Consumers lacking it must reject that fidelity claim or explicitly
operate in a narrower semantic-analysis mode; they must not silently generate
an alleged faithful UI. Autonomous/no-interface exports explicitly declare that
status with its evidence, rather than fabricating controls.

Absence, unsupported capability and unresolved producer evidence are different
conditions. Preserve them in intake disposition. Optional decorative details
may be omitted only when no required interaction, timing, resource or observable
contract depends on them. Missing interface references must be reported.

## Provenance and debugging

Attach maps from interface objects, input bindings, display projections and
completion milestones to original instructions, tables/scripts/resources and
bounded runtime observations. A source-level folded block can expose both its
state effect and its interface contract without claiming recovered original
source names. Keep before/after captures separate and bind their scene/frame/
state generation and declared phase. Clean screenshots remain evidence, not the
semantic language itself, and not proof of current availability after restore.

Pre/post screenshot hooks are an observation mechanism. Their implementation
must not become arbitrary host callbacks in UIL. A post-state screenshot may
legitimately precede a post-interface capture. Advancing execution to obtain the
latter is an explicit timed intervention with preserved debugger stops, not a
passive screenshot operation. See PR #5 for the debugger-specific contract.

## Compatibility and migration

Old event-only exports keep their identities and semantics. Adding interface
information creates a new export and receipt; it never retroactively upgrades
old qualification. Do not infer missing controls from event names or invent
pixel coordinates from reference artwork. A migration can add explicit unknown
interface entries, but cannot manufacture interactive conformance.

Keep stable action IDs when meaning is unchanged; use different action IDs for
semantically different context-dependent operations. Retain aliases/revisions
and distinguish source layout from a downstream reflowed or text-only layout.

## Security boundary

Permitted content is typed data, declared core expressions and resource/evidence
references. No embedded Python, JavaScript, shell, native library, host filesystem
or network authority is added. The proposal describes interaction semantics;
it does not grant a consumer or investigator authority to execute arbitrary
external actions. Existing producer/consumer capability boundaries remain intact.

## Conformance fixtures

All following fixtures are authored synthetic specifications. They contain no
original game bytes and have not been executed by a UIL runtime (none is claimed).
Use a draft editor with active quantity 0, pending quantity 0 and a monthly-cost
projection of 100 times pending quantity. The product is fictional.

| Vector | Input and observation | Required interpretation |
| --- | --- | --- |
| P1 | Detail Add: pending changes at step 1, Remove enables at step 2, displayed count changes at step 3 | Event at step 1; not post-interface completion until the declared conditions are observed |
| P2 | Detail OK leaves active=0, pending=1; outer OK later makes active=1 | Two context-specific actions, not one universal confirm event |
| P3 | Cost display=100 while active=0 and pending=1 | Draft projection; not a committed expense or inconsistent state |
| P4 | A command-line verb invokes the same permitted action without pixels | Valid nonvisual binding, no fake screenshot/geometry requirement |
| N1 | A modal covers Add; underlying quantity and scene code look valid | No actionable underlying control while the declared modal/focus guard blocks it |
| N2 | Add has changed pending; post-frame capture times out | Known state effect plus incomplete interface evidence; no automatic duplicate Add |
| N3 | Frame/context unavailable after restoration | Unknown visibility/readiness, not object absence |
| N4 | A background actor continues moving after Add is ready | Do not require global pixel stillness |
| M1 | Input binding references a missing event ID | Reject or retain explicit unresolved reference; never execute a guessed target |
| M2 | A surface repeats an object ID for different meanings with no revision/context distinction | Reject ambiguous identity |
| M3 | Required interface capability/version is unsupported | Reject interactive-fidelity intake; explicit semantic-only inspection may remain possible |
| M4 | Claimed post-interface evidence predates its linked state transition in this fixture | Reject that completion claim; preserve the raw observations |

Expected cost arithmetic here is exact bounded integer arithmetic (0..99 units,
100 each), without overflow. This is not a replacement for UIL's eventual
numeric specification or a general proof over arbitrary values.

## Alternatives

- Event names alone: lose context, input affordances, displayed projections and
  readiness. The two-OK fixture is a counterexample.
- Screenshots alone: show an appearance but do not identify draft/commit bindings
  or required event order, and exclude nonvisual interfaces.
- Only consumer-side UI invention: useful for a deliberately redesigned frontend,
  not a faithful recovery claim. It remains a valid separately labeled product.
- Put all interface details in core events: possible once a grammar exists, but
  still requires explicit interface relationships. Separate linked descriptions
  avoid turning every autonomous event into a control or device-specific call.
- Reuse portable scene manifests as the whole language: useful provenance and
  input automation, but they do not by themselves specify model/display semantic
  projections or the complete recovered program. Retain them as linked evidence.

## Implementation experience

No UIL exporter, interpreter, source generator or interface runtime is added.
Existing E41 native observations and the scene bundle demonstrate the motivating
separation only. Proposed vectors remain specifications for the implementation
owner, not passing conformance tests. Maintainers should choose the final schema,
identifier and whether this belongs in the core envelope or an extension.

## Disposition

Pending review by the fDisBull/UIL owner. This is the user-requested amendment
submitted alongside, and based on, PR #3. Neither acceptance nor implementation
is implied. Producer export and downstream presentation remain separate projects.
