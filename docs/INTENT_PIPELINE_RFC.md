# Draft RFC: recovering intent into a portable game blueprint

Status: **draft design**, 28 October 2026. Author: Codex, from the user's
layer goals and the repository documents cited below. This is an architectural
proposal, not a UIL language amendment or a release commitment. The examples
are synthetic and illustrative, not an established syntax or recovered game.

## Goal and present boundary

Recover what a program is trying to do as evidence-backed, typed intent
primitives, then reconstruct those semantics in another language or runtime.
The source might be a DOS executable, an NES game ROM, or an interpreted game.
Extensible adapters make additional sources possible; they do not guarantee
complete or automatic recovery of arbitrary games. A human or agent may have to
resolve ambiguity or retain unknowns. The default is faithful original
behavior, including observable quirks. A correction is an explicitly identified
optional variant with its own evidence and comparisons.

Published 0.19 has persistent disassembly, bounded debugger evidence and
visual scene observations, not this pipeline. The separate 0.20 development
branch, last inspected at `001901d1361ab3a536de61e0292520af1ac32afd`, is a
`0.20.0.dev0` draft: it adds a minimal processor seam, a partial read-only AGI
2.917 inspector, dot-mode and bounded input, movement and model proofs. The
inspector is not an interpreter, and proofs of a supplied model do not prove
that model matches a game. Full Z, UDL, UIL and target generation are proposed,
not implemented. See [release status](RELEASE_STATUS.md),
[scene framework](SCENE_FRAMEWORK.md) and [UIL boundary](UIL_BOUNDARY.md).

The existing boundary puts fDisBull's responsibility at the evidence-backed
UIL export. Target compilers, simulation runtimes and presentation are
independent downstream work; this RFC describes their required handshake, not
an expansion of fDisBull's ownership. UIL amendments continue through the
[existing RFC process](UIL_RFC_PROCESS.md).

## Layer contracts

| Layer | Goal and input | Output and boundary |
| --- | --- | --- |
| Artifact and platform adapter | Identify source containers, resources, load context and platform; preserve original identities. | Versioned artifact inventory, address spaces and platform services, with evidence and unresolved mappings. |
| Machine/VM decoding and execution evidence | Decode source-specific instructions or guest bytecode, and collect bounded execution, state and I/O observations where available. | Instruction facts, control-flow candidates, traces and stops, all tied to addresses and source identity. A decoder does not execute a guest or establish its semantics. |
| C/C++-like structural reduction | Reduce instruction-level detail into understandable operations, data flow, control structures and candidate routines. | An evidence-linked analysis **view**, including unresolved edges and alternatives. It need not be compilable C/C++, and decoded bytecode need not detour through literal C/C++. |
| Z: Zork-like behavioral layer | Organize reduced operations and direct guest evidence into scenes, entities, state, actions and processes: what happens, when and under which conditions. | Candidate behavioral model with guards, effects, timing and evidence, supporting a playable text-adventure projection as well as semantic export. A scene here is a semantic context, distinct from an existing screenshot-based debugger scene. |
| UDL: user-defined language/definition layer | User authors define vocabulary and input recognition mappings from source patterns and Z concepts to intent primitives, retaining input evidence and competing interpretations. They can also define target compiler mappings and libraries. | Versioned definitions, mapping results and provenance, including unknowns. UDL is recovery machinery and an optional design reference for a new backend, not a runtime dependency of a finished UIL package. |
| UIL: universal interaction blueprint | Capture the reconstructed game's meaning in defined, composable primitive and macro blocks. | A self-contained semantic source, interpretable without the original source or UDL recognition machinery. It includes or binds its declared dependencies and unresolved behavior; unsupported required semantics must be refused, not guessed. |
| Target definitions and code libraries | Bind each supported UIL construct to target-specific implementations and declared runtime services. | A compiler and libraries can produce, for example, Rust, Swift, JavaScript or Python, potentially hosted in Godot or an iOS application. Capability gaps and runtime dependencies are explicit. |
| Agent access and optional presentation | Expose the same authoritative simulation through semantic operations; project its state visually when desired. | Agent interface and optional renderer over one simulation, with declared observation limits and reproducible event ordering. |

The arrows describe contracts, not a claim that all recovery proceeds linearly.
Evidence may refine an earlier interpretation; every revision retains its
provenance and contradictions. UIL is the executable semantic contract in this
proposal; the structural and Z views help derive it. The exact UIL encoding and
reference evaluator remain decisions for later work.

Z names the behavioral model in this pipeline; Z-machine names a possible
source VM. Z should also support a [playable text-adventure projection](Z_TEXT_PROJECTION.md)
for testing: agents observe grounded scene descriptions and submit named
actions to the same authoritative execution backend. Graphical views and
autonomous processes can share that model. Text presentation alone does not
change the game's timing, observation privileges or action semantics.

The [recovery experience amendment](INTENT_PIPELINE_RECOVERY_CASES.md)
adds practical distinctions and synthetic acceptance cases from bounded
DinoPark reconstruction work: signal state versus queued delivery, action
completion, persistence, agent observation and compatibility behavior. It
refines this draft's requirements without choosing canonical UIL syntax.

The [progressive scene workflow](SCENE_STREAMING_WORKFLOW.md) proposes how to
produce usable scene knowledge during gameplay, compare sequential and
on-demand recovery, and reuse downloaded scene packages. A live-original agent
harness and a reconstructed runtime share evidence and scene descriptions,
with different requirements for which component executes the game rules.

## Blocks and semantic obligations

The UIL blueprint includes the semantic definitions of its blocks; it does not
need the original source recognition machinery. A block is a defined operation,
not merely a suggestive name. Its contract
specifies typed parameters and units, preconditions and action availability,
effects and persistent state, emitted events, ordering and scheduling,
nondeterminism and random streams, external services, failure behavior and
provenance. Numeric representation, overflow, rounding and time must be
specified whenever they affect observation. Unknown or conflicting behavior is
explicit and cannot silently become a default. A macro may describe an entire
routine or sequence; its versioned definition can recursively expand into
smaller blocks with equivalent declared effects. Expansion must terminate or
have explicitly defined recursion and scheduling semantics. A backend must
implement the definitions or report the missing required capability.

A source address, memory layout or UI widget can be retained in provenance or a
presentation mapping without being the meaning of an operation. Conversely,
observable wrap, caps, triggers and timing cannot be discarded merely because
they arose from low-level implementation details. The [UIL boundary](UIL_BOUNDARY.md)
specifies package identity, evidence and qualification requirements, including
candidate, bounded-observed, bounded-reproduced, locally-proved, rejected and
superseded states. Apply them per node when needed; unobserved is not false.
Original bytes and earlier interpretations remain preserved; published evidence
must respect its redistribution classification.

## Worked example: money

Suppose a synthetic source has an action that awards $200. Investigation finds
an unsigned balance in whole dollars, a cap of $999, and a threshold event
emitted only once, on the first upward crossing of $500. A persistent
`threshold_announced` flag starts false. The action is available only when
`award_pending` is true. At the action boundary it clears that flag and sets
`money = min(999, money + 200)`. If `threshold_announced` is false, the old
balance was below $500 and the new balance is at least $500, it sets
`threshold_announced` to true and then emits `threshold_reached`. It then emits
`award_completed`; the balance, both flags and their values survive a
checkpoint, so a later decrease and recrossing cannot re-emit the event. These
are example assumptions, not facts about a real program.

The structural view might show loads, arithmetic, a comparison and stores. Z
names the action and state transition. A UDL mapping proposes a parameterized
`credit_money(amount: dollars)` macro; its UIL definition must include the cap,
guard, threshold and event order above, or expand to primitives that do. The
intent can be read as “add $200 to money,” without a memory address, storage
representation or widget, but the complete contract retains every observable
cap and trigger. Provenance links the candidate to relevant source spans and
traces. If overflow or the event order is untested, mark it unknown instead of
assuming this example's behavior. A target library maps the defined operation,
not just the macro's name, to code. A UI can refresh its displayed balance
later; a stale display is distinct from authoritative money.

## Worked example: scheduled visual actor

Consider a synthetic scene process with persistent `visible: bool` and a
`phase` and deadline measured in simulation ticks. On entering the scene,
set `visible = true`, emit `actor_shown`, and schedule a deadline at tick
`now + 3`. At that deadline, set `visible = false`, emit `actor_hidden`, then
schedule the next show at `now + 2`. On that deadline show and repeat. For this
example, scheduled transitions run in deadline order before action dispatch at
the same tick; ties use a stable process ID. Scene exit cancels pending events.
A visual refresh reads the resulting visibility after transitions; it does not
advance the timer. These choices are part of this example's contract and must
be recovered rather than presumed for a real game.

Z describes the scene, actor and process; UDL maps the evidence to UIL state,
events and a scheduled repeating macro (which expands to the two transitions).
Agent observation can report visibility and the state delta without drawing;
a renderer projects the same state at its next frame. A scene refresh callback,
a simulation tick, a render frame and a timer deadline are distinct. If the
original callback also advances the timer or triggers logic, that effect must
first move into the simulation with the same ordering, and tests must show the
result before drawing can be skipped. An ACT-style show/wait/hide loop is a
conceptual motivation only; this example does not assert ACT timing or reveal
proprietary assets or code.

## Agent-first operation and rendering

A reconstructed runtime should expose semantic observation, available actions
and guards, action submission, resulting state deltas and events, bounded step,
reset, checkpoint and replay, plus trace/evidence references. Observations may
be partial; hidden state should not become automatically player-visible. Record
initial state, input order, clock and random state and external-service results
needed for replay. A checkpoint must declare external effects it cannot restore.
A graphical projection reads simulation state and updates as that state changes;
its refresh is not the authority for game state.

Dot-mode is a watch-only view of the same agent-controlled simulation. Current
DOSBox headless execution can still render internally; it is not evidence that
the original game is renderer-independent. The proposed reconstructed
agent-mode may omit actual drawing only after logic hidden in rendering is
separated and tested against the original under declared timing and input
conditions. Visual output may still be needed to test visual fidelity.

## Source adapters and interpretation

* **DOS/x86:** identify the COM or MZ container and resources, load/relocation
  context, segmented project and runtime addresses, x86 instruction facts and
  DOS/BIOS, input, video, audio and clock services. Map file offsets, loaded
  addresses and traces only when supported by evidence.
* **NES:** identify the ROM container, mapper and bank layout; model CPU
  address space and ISA separately from mapped/banked storage, PPU graphics,
  audio, controller input and hardware timing. Instruction decoding alone does
  not establish peripheral behavior, bank mappings or frame semantics.
* **Guest language:** AGI, Z-machine or ACT-like interpreter resources add a
  separate guest-language layer atop the host machine. Retain distinct guest PC,
  resource offset and native dispatch addresses and evidence for their mapping.
  Decode guest operations separately from implementing an interpreter or
  demonstrating execution. An ACT-style embedded animation can be modeled as
  a conceptual show/wait/hide process without assuming its implementation or
  timing.

Each adapter needs explicit source identity, decoding and service versions,
address units, capabilities, unknowns and bounded tests. Source-specific data
is evidence for mapping, not permission to invent cross-platform equivalence.

## Preservation and validation

Comparison begins with an identified original, initial state and a declared
observable interface. Align inputs, action boundaries, simulation time, random
streams and external services; preserve divergences, stop reasons and test
budgets. Compare action availability, state deltas, event order and persistence,
then any required visual/audio output at declared observation points. Include
negative cases, boundary values, malformed/unsupported constructs and replay
from checkpoints. Where state cannot be observed, report the comparison ceiling;
matching screenshots or one route alone do not prove full equivalence. Use
redistributable synthetic fixtures for public conformance. Retain evidence
references and counterexamples without publishing private games or saves.

Target definitions require versioned capability negotiation, deterministic
canonicalization and compatibility fixtures. Unknown required blocks fail
closed; an older consumer must not reinterpret a newer block under the same
identifier. Translation validation can compare an emitted target with UIL over
bounded traces or prove a narrowly stated property, but neither a finite test
nor a local proof establishes whole-game equivalence. Corrections are separate
variants, compared against the faithful baseline and never silently substituted.

## Methodology: reproduce and compare a bounded behavior

**Anthropic reports:** Its [27 October 2026 report](https://www.anthropic.com/research/discovering-vulnerabilities-with-claude)
describes using binary-analysis tools, an annotated C reproduction of relevant
features, and comparison with the binary before further analysis. It also
observes that intended component behaviors can combine into unexpected
outcomes. Its broader process tracks coverage, uses diverse analysis approaches,
measures marginal discoveries, examines variants and standardizes verification.
The report does not disclose the exact comparison harness, fixtures or coverage,
complete prompts or reproduction, a formal proof, or completion of the whole
binary. Its account is an inspiration, not evidence of game equivalence.

**Proposed fDisBull practice:**

1. Choose a small behavior slice with named entry conditions, observable
   actions, state, timing and explicit boundaries. Preserve artifact identity,
   source evidence, assumptions and competing interpretations. Structural
   reduction may include an executable C-like reproduction when useful; it is
   still an analysis view, not a required language or a substitute for evidence.
2. Apply matched inputs and starting conditions to the original and model;
   compare available semantic observations, action guards, state deltas and
   events at declared boundaries. Record stops and counterexamples, investigate
   discrepancies, and refine the candidate before expanding the slice. Compare
   rendering separately when the claim includes visual behavior. Agent-mode
   must preserve simulation behavior even when drawing is omitted.
3. Compose primitives only within their verified bounds, then test interactions
   through shared state, event order, timers and external services. Retain
   unknowns: individual agreement does not prove the composition. Carry the
   same inputs, evidence and comparison obligations through Z, UDL mapping, UIL
   and each target; a mapping or generator must not silently widen the claim.
4. Track which behaviors and conditions have actually been compared and their
   claim ceilings. Use a different targeted analysis or a related variant when
   it can resolve a gap; measure added verified coverage and counterexamples,
   not the amount of output. Scale effort to the question rather than requiring
   multiple agents or a new framework.

Observed agreement supports only the stated bounded behavior. Intent remains an
interpretation supported by evidence, not something established automatically
by matching outputs; security findings do not establish complete game recovery.

## Staged milestones and decisions

1. Specify one small synthetic adventure scene: typed state, one guarded action,
   scheduling, evidence/unknowns and agent operations. Agree on a versioned UIL
   contract and public positive, negative and malformed fixtures.
   Use the [recovery cases](INTENT_PIPELINE_RECOVERY_CASES.md#synthetic-acceptance-cases)
   to distinguish plausible but observably different implementations.
2. Recover a bounded adventure-game vertical slice with source-specific
   evidence, an explicit Z/UDL mapping and a self-contained UIL package. Compare
   original and reconstructed transitions, replay and optional visual output;
   record the limits rather than claiming a complete game.
3. Independently implement a small target and check the same conformance
   fixtures. Add renderer-independent agent operation only after the hidden
   render-logic comparison passes. Expand backends and sources based on evidence.
4. Use state-based games such as Lands of Lore as further workloads. Dune II
   and Warcraft are later stress tests: sequential unit behavior loops, shared
   definitions with per-unit state, scheduling and shared-world interactions
   need explicit semantics and tests. They are not prerequisites for the first
   slice or commitments for 0.20.

Open decisions include canonical encoding and versioning, precise time and
scheduler model, provenance packaging and rights, how uncertainty blocks
execution, observation visibility, external-service contracts, macro recursion
limits, and which source/target pair to qualify first. This is not a universal
physics language: Call of Duty is outside the intended Z fit. It does not promise
complete decompilation, automatic intent inference, a general-purpose emulator,
commercial asset redistribution, or faithful reproduction without evidence.

## Research inspirations

[FrAG](https://ravenheartss.github.io/assets/pdf/cog23_frag.pdf),
[MACE](https://www.usenix.org/events/sec11/tech/full_papers/Cho.pdf),
[TextWorld](https://arxiv.org/abs/1806.11532),
[Jericho](https://arxiv.org/abs/1909.05398), and
[translation validation](https://people.eecs.berkeley.edu/~necula/Papers/tv_pldi00.pdf)
are inspirations for examining game behavior, agent interfaces and validation.
They do not establish that this proposed pipeline works.
