# Behavioral hypotheses and alternative entry points

Decision: 18 November 2026. Use an agent's programming knowledge to propose how
observed behavior could be implemented, then seek evidence that distinguishes
those explanations. Retain several qualified ways to reach a useful operation:
ordinary input for visible play, and deeper original-code or constructed-state
routes for isolated analysis where they remove repeated preparation work.

Status: design and operating guidance. This document adds no native invocation,
teleportation, hypothesis engine or live controller. Its records extend the
[transition-family model](EVENT_TRANSITIONS.md); the existing components below
are reuse references with narrower contracts, not newly ported DotBox features.

## Think like the programmer, then discriminate

Ask what small implementation would produce the observed behavior. Write a few
plausible sketches when they help predict code, data or execution evidence.
Treat each as a hypothesis with alternatives and a next discriminating probe.
Do not require a reconstruction of the whole program before using a working
control, or spend the foreground budget listing every possible implementation.

These are authored examples, not recovered code for a particular game:

| Possible implementation | Useful distinguishing prediction |
| --- | --- |
| A control calls `open_inventory()` directly | A direct call or control-associated callback target reaches the operation |
| A shared `handle_action(button_id)` selects behavior | The same dispatch site receives differing selector values; branches or table entries distinguish operations |
| A handler assigns `current_mode = next_mode` | A state write selects work in a later loop iteration; the click's immediate callee may return before the effect |
| A handler enters `run_inventory_mode()` | The routine owns input/rendering until an exit; normal return occurs after that interval |
| A handler tail-transfers to another context | Execution changes owner or continuation without the assumed near return |
| A handler enqueues `Load(slot)` | A request producer and later consumer are separated by a queue, callback, tick or phase |

A callback table, script interpreter or optimized branch sequence can implement
the same relationship as an authored sketch. Search for the predicted structure
and data flow, not the spelling or exact instruction order of hypothetical code.
Use observed arguments, callers, writes, indirect targets and continuation to
refine the explanation. Preserve unresolved branches and contradicting examples.

A useful hypothesis record contains the behavior being explained, the proposed
mechanism, relevant state/arguments, predicted distinguishing evidence, observed
support and contradictions, and the next question. A plausible implementation
does not become a recovered fact merely because the agent could write it.
Conversely, a recovered mechanism can immediately enable the sibling searches
and prerequisite-driven analyses in [the transition guide](EVENT_TRANSITIONS.md).

## Record transient paths across controls

Use the debugger as an experimental instrument. Arm a finite set of candidate
exits, branch destinations, calls or state-write sites before triggering an
event, so short-lived execution and selector values can be retained without
the agent interpreting each site while the game runs. Coverage is concurrent:
the same trial watches several alternatives. Recorded execution still has its
actual order; several buttons or branches need not run simultaneously.

A six-button screen can first yield a dispatch map: which observed control
reached which site, with which selector or destination, under which baseline.
Retain that useful relationship immediately. Explaining every handler, proving
the final game effect or qualifying a direct invocation can follow separately.
"Button B reached site X with selector 2" is already a useful future starting
point, even when X has no semantic name.

### Compare controls from a declared baseline

1. **Prepare the isolated trial.** Identify the controls, source/mapping and
   relevant context. Capture a qualified memory baseline with neutral input
   before adding experimental probes. Record relevant file/environment state,
   guest clocks and available RNG provenance. Establish the restore capability
   rather than assuming the existing DotBox interface already provides it.
2. **Arm the candidate set before input.** Cover the known exits or other useful
   observation sites of a declared function/region. Retain coverage gaps at
   indirect transfers, opaque calls or scan bounds. A shared return may require
   an earlier selector/branch or a later mode consumer to distinguish controls.
   Respect backend capacity; if batching is necessary, retain which sites were
   armed in each trial rather than claiming simultaneous whole-region coverage.
3. **Trigger one control and retain the transient evidence.** Use its qualified
   input route once and retain the actual delivery receipt. Hits before delivery
   remain baseline observations. Capture site identity, selected values and actual transfer
   targets where observable, with ordering and small relevant state windows.
   Bound guest execution, host time, events and retained bytes. Save records in
   the evidence store outside the guest checkpoint so rewind cannot erase them.
4. **Finish the declared observation window.** A first-hit stop establishes that
   hit and censors the remaining path. To collect later hits, use an explicitly
   supported bounded log/continue or trace mechanism; do not insert model
   reasoning at every stop. Preserve foreign stops, takeover, session exit and
   unexpected interruption. Remove only owned probes through known cleanup.
5. **Restore, verify and re-arm for the next control.** Rewind memory through
   the qualified owner, refresh branch/mapping/input bindings and validate the
   comparable starting predicates. Reconcile observer state and re-arm current
   probe IDs; an old live-owner token alone is not a restore-generation check.
   Retain every input as a distinct trial with its stop/coverage record.
6. **Keep the map and investigate selectively.** Compare rows, group supported
   common behavior and choose the next useful question. Add an idle contrast,
   repeat or contrasting input when it resolves an ambiguity. A first pass may
   map all visible controls without fully explaining any of their handlers.

Memory rewind leaves current disk files in place. If a trial changes a save or
configuration file, later trials no longer share that original environment just
because RAM was restored. Record the difference or use independently prepared
helper guests with their own fixture copies. Do not add filesystem rollback to
the player's rewind. Identical memory also does not guarantee identical input
timing or external events; retain these differences rather than requiring full
RNG recovery before any useful comparison. See [process experiments](BOOTSTRAP_AND_EVENT_LOOPS.md)
and [recovery](RECOVERY_AND_SAVES.md).

### Retain a dispatch map before a semantic explanation

The minimum useful record is the control/attempt, baseline and branch identity,
armed probe-set identity, ordered observed hits with relevant selector/target
values, the ending condition and coverage, and any separately observed effect.
Keep a code destination distinct from a game scene destination. Hitting an exit
instruction does not by itself observe its eventual indirect or return target.

These are authored illustrations, not measured game results:

| Trial observation | Useful retained deduction | Still unresolved |
| --- | --- | --- |
| A and B reach the same site with different selectors | Candidate shared dispatcher; keep both argument bindings | Meaning and effects of each selector |
| C reaches a distinct callee and returns | Observed route to a separate code region | Whether that region is the complete operation |
| D writes a pending value before the capture ends | Candidate producer boundary for later work | Which consumer runs, and when |
| E hits a common return and observation stops | The shared return was reached in this trial | Earlier distinctions and all later execution |
| F has no recorded candidate hit before timeout | No hit was observed within this trial's coverage | Uncovered paths, later effects or ignored input |

A hit matrix may use counts or ordered signatures. Distinguish an observed hit,
no hit within a fully observed declared window, an unobserved/truncated interval,
and a site that was not instrumented. A blank cell is not proof that a branch
was untaken. Shared helpers,
rendering loops and incidental timers can appear in several rows. Keep
site-plus-selector/context distinctions rather than subtracting every shared
site. The relationship can be many-to-many: one control can visit several sites,
and several controls can share one handler or exit.

This map feeds sibling discovery and later directed analysis. Static candidates,
observed routes, interpreted effects and callable-entry qualification retain
their separate evidence. An agent can now jump to the relevant code/evidence
without repeating the UI experiment solely to rediscover where the click went.
Run broad comparisons in bounded preparation or isolated helpers; keep existing
foreground budgets and ordinary visible play moving.

## One operation can have several entry routes

Bind alternative routes to the same operation when the relevant effects support
that relationship. Keep their actual starting conditions and execution paths.
Mouse and keyboard routes may converge; a direct call may enter after selection;
a loader and a scene-entry routine may initialize different portions of state.
These alternatives form a graph, not universal ordered layers that every game
must expose or a requirement to always choose the deepest available entry.

| Route or setup | What it can omit | What must remain represented |
| --- | --- | --- |
| Ordinary movement, key or mouse input | Nothing beyond normal control composition | Original traversal/event behavior, current input admission and outcome |
| Supported click/key delivery without pointer animation | Unnecessary host pointer travel | Actual input semantics, target/focus, hit testing where applicable and original event processing |
| UI event or dispatcher binding | Some physical-input decoding | Event payload/selector, applicable context and work normally supplied by the skipped prefix |
| Original handler or operation routine | Earlier selection/dispatch/navigation | Arguments, initialized state, invocation context and original continuation |
| Mode entry or continuation binding | An earlier route into a continuing operation | Current phase, ownership of subsequent execution, exit/completion conditions and remaining work |
| Controlled state construction | Traversal or progression needed to create a research starting state | Deliberate interventions and their provenance; the construction need not reproduce the skipped operation |

An observation hook identifies a useful place to inspect execution. A callable
route establishes how to enter and continue it. A breakpoint at a state write,
an instruction inside a handler, or a discovered address is not automatically
a callable function boundary. A mode loop, tail transfer or deferred callback
needs its own continuation contract; do not force it into a near-call helper.

For the main visualization, retain the original movement and event route.
Supported click delivery can omit visible pointer movement while the game still
processes the original interaction. Helpers can use deeper routes in their own
isolated guests to investigate quickly. Keep both recipes and their measured
scope; learning a shortcut does not silently replace the player's visible route.
All live actions retain the existing supported owner rather than adding a
second input executor.

## Describe the entry contract needed by the task

Extend a concrete transition binding with the evidence needed to use its chosen
entry. A known ordinary key route need not wait for an internal ABI to be decoded.
Unknown outcome conditions do not prohibit an otherwise qualified attempt;
invocation readiness and the conditions determining success remain separate.

| Contract element | Meaning |
| --- | --- |
| Operation and entry identity | Semantic operation, source/edition, code/resource mapping and supported entry surface |
| Parameters | Established selector, target, slot, destination, buffer or other arguments, including unresolved roles |
| Starting context | Required mode, phase, selection, relevant state and initialized resources |
| Invocation mechanism | Actual API, calling convention or transfer rule; required register/stack/global context where relevant |
| Omitted prefix and setup | Work skipped by this entry and the relevant prerequisites or effects it normally establishes |
| Continuation | Observed return, mode exit, callback, caller initialization or later event needed for the claimed result |
| Witnesses and bounds | Relevant effect/presentation/readiness evidence, host/guest limits, interruption handling and retained partial results |
| Equivalence and use | Compared ordinary route, starting conditions, effects preserved, deliberate differences, intended research or visible use |

Recover the prerequisites needed by the selected consumer. Keep unsupported
parts explicit instead of filling the contract with assumed boilerplate or
requiring an exhaustive inventory of global state for every useful step.
In particular, restore the relevant setup performed by an omitted caller, or
choose an earlier qualified entry that still performs it.

A routine that legitimately remains active can be a pending operation with
meaningful exit conditions. A bounded capture ending before that exit is a
partial observation. Preserve the attempt and confirmed effects; use a qualified
continuation or reconcile the state before issuing another invocation. Do not
replay the outer click merely because a deeper operation has not redrawn yet.

## Compare the effects that matter

Qualify a shortcut against the retained ordinary route from compatible isolated
baselines. Compare the state, continuation and side effects relevant to its
consumer, and record which dimensions differ or remain unknown. Matching a
number or final image can support that observation without establishing equal
timing, queue state, initialization, file effects or later behavior.

For example, a direct load routine may transfer a file into a buffer while a
caller normally adopts it, rebuilds state and returns control to the game.
Retain the successful transfer and investigate the missing continuation. A
file-layout consumer can use transfer evidence; a usable-load claim needs the
relevant adoption and readiness witnesses. Existing [XCOM work](XCOM_REUSE.md)
records why those claims must be kept distinct.

Saving or loading through a deeper entry still has the original operation's
game/file effects. Restoring temporary registers, stack or code does not undo
those effects. Record them explicitly and keep them within the helper's isolated
mutable files during research. The player's [memory rewind](RECOVERY_AND_SAVES.md)
continues to preserve current disk files; it is a different operation from game
save/load or restoration of a helper's experimental baseline.

Equivalence is conditional on the relevant starting context and required result.
Reuse established common behavior, then investigate differences introduced by
the new entry. Preserve the ordinary route and counterexamples. A shortcut may
be useful for analysis without matching the presentation or elapsed game time
expected during visible play. Measure warm replay separately from discovery,
with host, guest and game clocks as defined in [process guidance](BOOTSTRAP_AND_EVENT_LOOPS.md).

## Movement supplies the same kind of progression

Follow [the movement capability progression](NAVIGATION.md): identify position,
confirm it through ordinary movement, qualify isolated same-room placement,
observe original room crossing, and recover the necessary transition/setup path.
Position readback, engine adoption, collision behavior and room initialization
are different questions. Prefer the original setter or transition mechanism
when it performs required work that a raw field edit would omit.

An isolated helper may construct a coherent starting state in a location that
normal story progression has not reached. Record its baseline, deliberate field
or entry changes, initialization path, applicable conditions and observed result.
That evidence can support conditional geometry, objects, controls or script
relationships. It does not prove normal reachability or advance the player.
Some unknown prerequisites can remain explicit while a narrower observation is
useful; a malformed construction cannot establish the missing game rule.

Adopt reusable knowledge from those experiments after checking its live
applicability. Do not copy the helper's constructed state into the player's
session as part of adopting a finding. Preserve branch-specific occurrences and
invalidate dynamic entry bindings after rewind, mapping, mode or entity-lifetime
changes make them stale.

## Existing source to reuse within its actual contract

The following inspected fDisBull modules are pinned to source
`ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd`. They demonstrate parts of this workflow;
they do not qualify arbitrary calls, arbitrary room entry or a DotBox port.

- [`z_native.py`](https://github.com/seeker-cyber-maker/fDisBull/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/z_native.py)
  invokes an identified flat32 near-return callee at a caller-qualified,
  non-reentrant boundary. The caller establishes compatible flat selectors and
  a temporary boundary window the callee will not execute. Byte, stack and
  segment checks support the bounded mechanism; they do not infer that contract.
  Temporary code, registers and a bounded stack window are restored while the
  callee's intended game/file effects remain. Failure preserves recovery state.
- [`z_call_contract.py`](https://github.com/seeker-cyber-maker/fDisBull/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/z_call_contract.py)
  captures an original flat32 `E8` near call, selected argument observations,
  return and optionally bounded continuation. Argument observations do not infer
  an ABI. Replay is a same-runtime CPU/stack reentry with matching code and
  segment context, an observed compatible return, and caller-selected compatible
  game state. Captured continuation can be checked for divergence. Callee
  global/file effects remain; fresh scene initialization or redraw is not inferred.
- [`assisted_travel.py`](https://github.com/seeker-cyber-maker/fDisBull/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/assisted_travel.py)
  applies qualified, bounded actor-field edits and observes the original guest
  after execution. Its room-jump route places the actor for an original portal
  input; it refuses writes to the observed room field and retains original room
  initialization. Partial writes/stops are recorded without an automatic rollback.
  Its execution uses fast-forward and needs lifecycle/timing adaptation for
  visible DotBox play. It is not a generic scene-loader or position-discovery tool.

Do not generalize these flat32 call helpers into real-mode AGI or modal/tail-call
support. A successful source audit also does not establish an executed Police
Quest teleportation or a supported original-Dot invocation interface.

### Existing multi-probe and trace components

At the same pinned fDisBull source:

- [`z_capture_watch.py`](https://github.com/seeker-cyber-maker/fDisBull/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/z_capture_watch.py)
  arms 1-16 explicit flat32 `E8` callsites together and retains the watch across
  separate UI requests. Status does not run the guest. Finish consumes a currently
  observed owned candidate, removes the owned probes and delegates to original
  call capture. This is a first-hit watch, not an all-hit recorder or automatic
  multi-button survey. It does not establish restore-generation compatibility.
- [`execution_trace.py`](https://github.com/seeker-cyber-maker/fDisBull/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/execution_trace.py)
  provides bounded predicate capture, including composed alternatives and an
  optional single queued input. Its live trace-until workflow is qualified for
  its stopped real-mode entry contract; it does not supply the same mechanism
  for arbitrary flat32 targets. A matching stopped boundary does not prove that
  its instruction executed; an initially true predicate can finish before input
  is queued. Retain the actual delivery, observation and interruption limits.
- [`event_search.py`](https://github.com/seeker-cyber-maker/fDisBull/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/event_search.py)
  retrospectively retains/excludes candidates from collected evidence, including
  site/register/value distinctions. It narrows a search without performing a
  live sweep or establishing the semantic effect of a matching site.

Their composition into a DotBox-owned survey still needs implementation and
qualification. Capture the clean baseline before arming and explicitly reconcile
probes around restore; do not assume these distinct helpers already share a
checkpoint lifecycle or a general record-and-continue operation.

The subsequent [Dune experiment](DUNE_BATCH_PROBE.md) exercised this composition
in an isolated real-mode guest using the retained native runtime. A fixed script
restored memory, armed several candidates, clicked each declared control,
recorded selected targets and exhausted an idle no-hit window. Its full
nine-trial batch took 18.080 seconds, with preparation reported separately.
The target-specific experimental runner is retained for reuse; qualification
through DotBox's current ownership protocol and visible player flow remains open.

## Bounded implementation and acceptance

First retain hypotheses and alternative entry contracts with the existing
family/binding/evidence records. Integrate one supported capture or invocation
adapter at a time, keeping normal controls usable. Package the required analysis
components with DotBox; ordinary players should not have to install fDisBull.

Future acceptance cases include direct versus selector dispatch, a deferred
consumer, a modal routine with a later exit, a data write that updates only a
display cache, same-room placement followed by original engine continuation,
room entry with required initialization, a successful callee with unfinished
caller work, scoped equivalence with different timing/presentation, retained file
effects, stale mappings after rewind, and helper construction that never becomes
player progression. No such new runtime acceptance was executed by this guide.

Survey acceptance should additionally cover six controls with shared exits and
different selectors, one control reaching several probes, first-hit truncation,
no-hit coverage, a transient value overwritten later, deferred work, trace/event
limits, a foreign stop and stale observer bindings after rewind. Preserve the
recordings across guest restore and distinguish changed disk/environment state
from a comparable memory baseline. These are future runtime checks.
