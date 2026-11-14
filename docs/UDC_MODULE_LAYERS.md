# Per-module UDC layers

These three concepts describe how a UDC module realizes a program in a target
shell. They are design documentation, not new schema fields, APIs, or a claim
that general code generation or mixed-language hosting already exists.
The [current DOS compiler](UDC_DOS.md), [native pass-through](NATIVE_UDL_UDC.md)
and [UIL boundary](UIL_BOUNDARY.md) retain their documented limits.

Each UDC module owns its execution, orchestration and presentation contracts.
A shared vocabulary can make those contracts comparable, but it cannot impose
one global ABI, memory layout, scheduler or language choice. Pin the module and
contract revisions, selected backings, adapters, resources and qualification
evidence when reporting a realization.

## Three responsibilities

| Layer | Meaning for this UDC module | Concrete responsibilities |
| --- | --- | --- |
| **Execution** | The program shell scaffold required by the module. | Declare host platform/runtime and deployment dependencies; entry point and calling interface; initialization, event loop or scheduler ownership, shutdown and failure lifecycle; services and resources supplied to the kernel. |
| **Orchestration** | The module's concrete interoperability contract that makes all selected blocks work together. | Bind imports/exports and control flow; reconcile calling conventions, data representations and ownership; define supported bridges between source/output languages, callbacks, concurrency, event order, completion, cancellation and error propagation. Qualify the composed behavior. |
| **Presentation**, also called **polish** | Code fixups and memory structuring that transform recovered/generated code into the kernel running inside that shell. | Perform justified entry/call fixups, symbol binding, layout/alignment, relocation, pointer or handle adaptation, state/data placement and initialization. Record each transformation and its source correspondence; refuse unsupported or unresolved adaptations. |

Here **kernel** means the program core inside the selected shell, not an
operating-system kernel. Presentation/polish includes structural code and memory
adaptation; it is not merely UI styling, graphics or cosmetic cleanup. The
execution layer defines what the shell supplies; orchestration defines how
blocks cooperate; presentation makes their code and memory fit those declared
interfaces. For example, orchestration specifies an owned buffer at a bridge,
while presentation implements its handle/layout adaptation. These responsibilities
may share implementation machinery without becoming interchangeable concepts.

## Preserve the program across languages

General program recovery must retain observable effects, action responses and
timing at the declared observation boundary. Include onset/duration, blocking,
completion, interruption, synchronization, state changes, persistence and failure
behavior wherever material. Keep unknowns explicit. A named `play_sound` call,
an interpreter operation and a sequence of audio-device writes provide different
evidence of an effect; none automatically proves a complete semantic contract.

Blocks can span functions or form only part of one. Recover meanings while
retaining working lower-level operations and opaque dependencies. No language
has privileged semantics, and neither C nor Z is a mandatory intermediate.
A JavaScript audio implementation within a Win32 shell is a valid design only
when that module actually supports its runtime/bridge, deployment, state,
lifetime and timing obligations. An output platform label alone supplies none
of those capabilities.

Sweding permits a different implementation that preserves the required effect,
action response and timing. It does not permit unmarked changes to those
requirements. Explicitly justified and agreed variations remain separate from
equivalence. [PR #59](https://github.com/seeker-cyber-maker/fDisBull/pull/59)
documents sweding separately; this proposal does not import its changes or the
runtime work in [PR #54](https://github.com/seeker-cyber-maker/fDisBull/pull/54).
See [semantic contracts](../src/fdisbull/skills/fdisbull-investigate/references/semantic-contracts.md)
for recovery and evidence boundaries.

## Bounded authored example: threshold notification

Consider a hypothetical `threshold-notifier-v1` UDC module, not a shipped
backend. An authored core accepts one unsigned 16-bit reading per logical tick.
On the first reading at or above 100, it latches an alarm and requests one cue;
later readings request no further cue. There is no reset in this bounded case.
The shell exposes ordered tick delivery and an audio service whose onset,
completion and failure observations are part of the authored contract.

- **Execution:** this module declares a Win32 host, its supported embedded
  JavaScript runtime, `init/tick/shutdown` entry interfaces, the host-owned event
  loop and audio service lifecycle. This is an explicit deployment requirement.
- **Orchestration:** an authored native threshold block cooperates with a
  JavaScript cue block through a declared bridge. The module specifies unsigned
  value conversion, host-owned latched state, ordered calls, a stable cue handle,
  completion callbacks, shutdown/cancellation and failure propagation. A queue
  that adds observable delay cannot be assumed equivalent to synchronous dispatch.
- **Presentation/polish:** generated entry wrappers bind the shell interfaces,
  place and initialize the latch in module state, and translate a native cue
  handle to the bridge's representation without exposing a native pointer to
  JavaScript. Layout, lifetime and fixup evidence must match this module's
  declared contracts; preserving scalar output alone is insufficient.

The authored input sequence `99, 100, 101` requires latch states
`false, true, true` and cue-request counts `0, 1, 1`. That is a small scalar and
ordering check, not proof of audio timing or host integration. Qualification
would additionally compare the composed cue onset/completion, duplicate
suppression, failure and shutdown observations against the declared boundary.
No native/JavaScript bridge, audio playback or original-program parity is
implemented or tested by this example. Missing bridge support is unsupported;
missing timing evidence remains unknown.
