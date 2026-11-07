# Sweding: recreate the effect across implementations

Start with the [repeatable reconstruction recipe](reconstruction.md) when
recovering an original operation or qualifying a replacement.


Use this reference during UIL → UDC selection when a target has no ready-made
implementation of an operation. **Sweding** borrows the homemade recreation
idea from *Be Kind Rewind*: reconstruct the intended effect with the means
available. Here it can be fully equivalent; it does not imply lower quality.

This is model-neutral architecture and investigation guidance. It adds no
opcode, schema, command, compiler, media player or automatic language bridge.
The installed target's supported profile and refusal rules still apply.

## Meaning and realization

UIL names intent and required observable effects. UDC selection and orchestration
choose how to realize them. Missing a target-language primitive is a realization
task; it does not by itself show missing UIL semantics. Keep the operation's
semantic identity while changing its implementation language, encoding, library
or device. Do not lower UIL intent into backend machinery merely to fit the
first available implementation. If the meaning itself is unresolved, retain
that uncertainty and use the existing semantic-recovery/RFC process.

For recovered behavior, the default equivalence requirement is **observational
indistinguishability from the original in effect, action response and timing**
at the specified observation boundary. The user's Turing/Voight-Kampff analogy
describes this goal, not an implemented test or a subjective similarity score.
An underspecified operation name must not silently erase original behavior.
Recover the material observations before claiming an equivalent backing.

Include relevant onset, duration, blocking and completion, looping, interruption,
synchronization, state changes, partial effects and failure responses. Internal
file bytes, encoding and language can differ when they cannot distinguish the
experience or behavior at that boundary. Exclusions and tolerances need evidence,
justification and agreement; do not invent a permissive timing window to pass
a candidate. Newly authored UIL has its own explicit contract as the authority.

Use [semantic-contracts.md](semantic-contracts.md) to recover the boundary and
[udl-uil-udc.md](udl-uil-udc.md) to check the currently implemented target limits.

## Choose and qualify a backing

1. Pin the operation/contract revision, source edition and original backing,
   admitted inputs/environment, observer and material effects including time.
   Keep unknown coverage visible. A narrow block claim can be useful without
   recovering the whole game, but must not be reported as whole-game parity.
2. Look for qualified equivalent modules. Reuse one directly or use its source,
   interfaces and evidence as a reference. An agent may author a new backing
   when appropriate; reuse, one language and original encoding are not mandatory.
   Record the selection rationale and dependencies. Similar names are leads,
   not compatibility evidence.
3. Determine whether the selected target can supply the backing and its resource,
   runtime, ISA/mode, ABI, state, control-flow and lifecycle obligations. Qualify
   only necessary adapters. A supported original/residual route can remain a
   baseline; unavailable capabilities require an explicit unsupported result.
4. Preserve logical semantic identity separately from immutable implementation,
   adapter, compiler/runtime, resource and selection identities. Retain source
   bindings, evidence and counterexamples in supported records or project notes;
   these instructions do not authorize adding fields to existing schemas.
5. Compare each source/model/implementation edge, then the composed operation.
   Exercise normal and failed actions, interruption, concurrency and time where
   relevant. Existing evidence is reusable only while its dependencies and
   qualification scope remain applicable. A scalar proof does not cover audio,
   scheduling or callbacks merely because its output values agree.

A finite set of matching observations supports bounded indistinguishability
for those cases. It does not prove equivalence for every input, environment or
execution. Preserve unknown compatibility as unknown. A counterexample rejects
the equivalence claim until resolved. A deliberately relaxed contract is a
separately disclosed and accepted variation, not an equivalent swede.

## Audio backends

For the illustrative UIL operation `play_sound("blah")`, OGG, MP3 or CD audio
may all be valid backings. The abstraction permits format/device freedom while
requiring the same observable sound experience and action behavior. Merely
playing some sound eventually is insufficient. Codec delay, audible artifacts,
CD seek latency, different duration, changed blocking or lost synchronization
can distinguish a candidate. Preloading or an adapter might solve a difference;
their composed behavior still needs qualification.

For an authored acceptance scenario, bind the same identified cue and original
reference trace to each candidate. Record action dispatch, audible onset/end,
return/completion, state/event order and synchronization with a visible event.
Compare repeated calls, looping/stop, interruption and unavailable-media/device
responses wherever the original exposes them. Retain the clock alignment,
measurement resolution and agreed comparison conditions. Measurement uncertainty
limits the evidence; it is not permission to relax the requirement. No game
audio, waveform or native playback is supplied or tested by this guide.

## Three authored JavaScript implementations of one block

This newly authored example illustrates implementation choice, not an existing
JavaScript UDC backend. The pure block accepts an integer `cell` in 0..8 and
returns its zero-based row in a 3×3 board. Invalid inputs are outside this
example's admitted domain; there is no state mutation or external effect.

```js
function rowArithmetic(cell) {
  return Math.floor(cell / 3);
}

function rowBranches(cell) {
  if (cell < 3) return 0;
  if (cell < 6) return 1;
  return 2;
}

function rowLookup(cell) {
  return [0, 0, 0, 1, 1, 1, 2, 2, 2][cell];
}
```

The required results for inputs 0..8 are `0,0,0,1,1,1,2,2,2`. All three
implementations satisfy that scalar projection. That is only one edge of the
qualification: a real game integration must also preserve the original action
response, state effects and observable timing. These functions alone establish
neither a board-game implementation nor timing parity. A bounded JS execution
can check the nine scalar inputs; it cannot establish original-game equivalence.

## Mixed-language hosting

A JavaScript sound player inside a Win32 output is a valid architectural choice
when orchestration can host or bridge it and preserve the operation contract.
JavaScript needs a compatible runtime/host; an ISA label does not make it native
machine code. Qualify the host and deployment dependencies, cue/resource mapping,
argument and return marshalling, ABI or message boundary, state ownership,
initialization and teardown. Include event-loop scheduling, callbacks, async
completion, cancellation, lifetime, reentrancy, errors and partial effects as
relevant. The composed player's timing and responses must remain indistinguishable.

If the selected target cannot provide that runtime or bridge, report the
capability gap and evaluate a supported backing. Do not execute embedded code
merely because a UIL document contains it. Existing execution authority and
consumer intake remain separate from the semantic document.

## Acceptance/specification cases

These are authored review scenarios for future implementations, not receipts
claiming current playback, hosting or general lowering support.

| Case | Required assessment |
| --- | --- |
| OGG, MP3 and CD render the identified cue | May qualify independently if the composed sound, actions and timing are indistinguishable under the agreed boundary; file equality is unnecessary unless observed. |
| Same cue starts late or blocks a formerly responsive action | Meaningful mismatch: reject equivalence even if final sound/message matches. |
| Stop/loop/completion/error behavior differs | Reject equivalence when exposed by the original; preserve evidence of partial effects before retrying. |
| Three JS row implementations | Check all nine scalar inputs and unchanged state; retain timing and composed-action qualification as separate obligations. |
| JS player hosted by Win32 | Qualify runtime, bridge, resource/control/lifecycle boundaries and composed observations; component success alone is insufficient. |
| Target lacks audio output or a viable JS host | Explicit unsupported capability or an admitted alternative backing; never successful silence or assumed native JS execution. |
| Timing or failure coverage is missing | Unknown compatibility; do not promote scalar agreement or one normal trace to full equivalence. |
| User accepts a later cue or simplified response | Record a deliberate contract variation and its acceptance separately from equivalent sweding. |
