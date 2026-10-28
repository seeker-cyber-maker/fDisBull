# Behavioral investigation reference

Use this reference when a plausible internal explanation disagrees with an
interaction, a probe fails, or an observation is being generalized. It adds no
new tool API and does not authorize actions beyond the user's task.

## Screen for and map interpreted control flow

Early, use a cheap, task-relevant check for a possible interpreter alongside
native execution and other explanations. Follow the outer game/input loop from
a qualified input or update boundary. Look for repeated consumption of a data
stream and changes in a candidate virtual program counter or VM state; a loop,
jump table or unusual bytes alone proves neither an interpreter nor its role.
Compare ordinary event dispatch, decompression, rendering and native code as
alternatives. If a bounded trace only repeats idle polling, move to a qualified
input or loop-exit boundary rather than repeatedly sampling the idle loop.
Execution can mix native routines, interpreted scripts and native callbacks;
dispatch can be direct, threaded or another form.
The interpreter execution cycle may carry the guest game's logic; input,
rendering and timing may be outer scheduling or host services. Establish their
actual boundaries rather than assuming either layer contains all game logic.

If warranted, use a bounded trace/watch at the suspected boundary to connect
fetch and operand consumption to dispatch, state changes and the next fetch.
Qualify the stream, virtual PC, operand lengths, dispatch mechanism and relevant
VM state from observed behavior, not only decoder guesses. For the question at
hand, trace guest branch conditions and destinations and their effects, including
calls out to native code and returns. Record native execution coordinates together
with guest script identity/version and guest PC/offset, the source of each
mapping, relevant input/state and observed versus inferred edges. Retain raw
bytes and trace timing (e.g., before-instruction), registers and relevant state
so the transition is interpretable. Preserve unknown paths; neither a single
handler nor one run proves the whole language.

For a game-backed action model, trace text commands or UI controls through their
respective input paths to the underlying guest/native behavior. Associate a
proposed action and its effects with qualified code provenance and distinguish
observed semantics from hypotheses. A reusable game-independent representation
may later express those semantics without requiring the original code at runtime;
evidence links do not themselves prove a faithful translation or full coverage.

Do not treat a filename, region label or executable extension as a code boundary:
code or scripts may share a resource container with graphics or live in an
external data file. Inspect relevant load/asset paths cheaply, rather than
scanning every file. Connect file identity and offset through load, decompression
or copy to the loaded address and runtime generation, then to native execution
or VM fetch. A byte match suggests identity but does not prove a file-read or
load edge; incidental decodability is not execution evidence. Distinguish a
traced file/handle read into RAM from content-derived offsets, and qualify links
across sessions. Keep missing links and permissions explicit.

A memory watch covers only the access paths it instruments. A non-hit does not
prove unchanged memory; compare before/after bytes and inspect relevant service
entry and return or other plausible write paths when the distinction matters.

Prefer execution-led discovery on relevant unresolved indirect targets over
assuming where code must be stored: observe natural targets first. Where useful
and authorized, a disposable checkpoint can support a bounded counterfactual
branch force; declare the changed condition, preconditions and possible side
effects, and keep forced reachability distinct from ordinary reachability.
Observed valid CPU execution establishes code use only for those bytes and that
context; attempted fetch, decoder acceptance or a corrupted forced pointer does
not. Track the byte generation through overlays or self-modification. For guest
scripts, establish interpreter fetch rather than expecting the CPU PC to enter
the script. Bound attempts and stop when they no longer distinguish the question.

Choose a discriminating probe and negative control: vary the relevant input or
condition while holding preparation comparable, and check both the predicted
guest branch/effect and an alternative explanation. A failed fetch, unmatched
trace, or unsupported observation is not proof of absence. Stop when the
requested causal claim is supported to its needed scope, when a bounded test
reasonably favors an alternative, or when cost/capability prevents a useful
next discriminator; report evidence, limits and the condition for reopening.

## Select evidence for the exact claim

| Claim | Evidence needed |
| --- | --- |
| A control is currently available | Fresh scene/context and visible, ready and enabled checks, plus a qualified real-input route for that context |
| Input was consumed | A target-side effect or acknowledged response at the selected boundary, not merely delivery acceptance or an empty adapter queue |
| An action committed | The relevant state transition or acknowledged output; pending state alone is insufficient |
| A value is displayed | An authentic current capture; do not infer it from a raw field or assume a frame refreshed |
| A result persists | The actual write and a fresh read through the target when claiming target reload behavior |
| A formula governs a reachable operation | The mechanism, its call conditions and a qualifying authorized ordinary-interface route |

There is no universal ranking in which screenshots always defeat memory or
memory always defeats screenshots. Observable behavior constrains the
interpretation, while the question determines which boundary is authoritative.
A backend selector can nominate a candidate scene without establishing that its
controls exist. A stale display can coexist with a successfully committed action.
Preserve both facts rather than inventing a contradiction or retrying blindly.

## Trace a complete action, not just an interesting field

For typed input, qualify parser readiness separately from queue acceptance. An
input accepted during a transition may be consumed before the intended prompt;
verify the ready context before attributing the resulting text to a command.

Write the smallest causal account needed for the question:

1. What context and input start the operation?
2. Which conditions select or reject its path?
3. What changes before commitment, and what commits or reverses it?
4. When does presentation update, and is completion waiting on it?
5. What survives exit, reload or restart, if persistence is part of the claim?

Use a watched write and bounded trace to locate the mechanism. Preserve the
authorized ordinary-interface route that reaches it. If an isolated probe
bypasses dispatch or uses edited state, label that boundary explicitly. Complete
disassembly is not a prerequisite for a verified routine contract, and one
verified routine is not proof of the complete application.

Observe before and after the relevant boundary. Unrelated background processing
can change totals during a wait. Distinguish an action's delta from that activity
using an appropriate control or a more precise stop. Prefer invariants such as
"pending quantity rose by one while committed quantity stayed unchanged" when
absolute totals may legitimately vary. Such relationships are experimental
assertions, not claims that every installed predicate API supports them.

## Triage a failed interaction

Before reporting a target or debugger defect, distinguish:

- Wrong address space, load context, byte version, mode or coordinate transform.
- Wrong object, hidden/disabled control, focus, occlusion or blocking modal.
- Incomplete setup, input not consumed yet, delayed presentation or a capture
  taken after unrelated processing resumed.
- A harness expectation, unsupported tool call, adapter limit or exhausted budget.
- An actual target behavior or reproducible tool fault.

Do not force a cause when evidence cannot discriminate. Change one assumption
per new probe. After repeated uninformative attempts, switch the observation
boundary or retain a bounded unresolved finding; do not merely lengthen sleeps.
A diagnostic record needs expected behavior, observed behavior, the minimal
route, target/runtime identities and what remains unproven. Do not assign an
unrelated image or old capture to a current run.

## Compare equivalent preparations

Specify what is restored: machine state, controls, code layers and external
files are separate. Also account for pending input, callbacks, timers and shared
random state where relevant. Never assume an emulator checkpoint rolls back
host-file writes. Preserve originals and reset only explicit disposable copies.

A visual wait that advances execution can consume random numbers or run other
callbacks. For matched trials, align the relevant causal boundaries, not merely
the initial seed or an approximate wall-clock delay. Preserve intermediate
observations and reject unequal or incomplete capture structures as evidence of
equality. A same-process repeat, fresh-process repeat and independent review
answer different questions.

## Preserve knowledge without preserving stale observations

Reuse established identities, geometry, routes and documented conditions.
Preserve one object identity when the same control remains the same object across
revisions or state-dependent availability and relative outcomes. Use a separate
action identity when the interaction itself has a genuinely different meaning.

Re-evaluate current presence, readiness and applicability after relevant changes.
Present, absent and unknown are different conclusions; absence needs an adequate
view and a qualified detector. Retain negative examples and conflicts with the
accepted definition rather than replacing them with a more permissive guess.

Keep each receipt proportional to its decision value. A short outcome with an
evidence reference can reuse qualified setup; it need not duplicate every trace
or rerun every unrelated suite. Broader checks are appropriate when shared
assumptions change. A handoff should distinguish settled facts, actual unknowns,
blocked work and untested integration, and name what would justify reopening them.
