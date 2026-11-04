# Expected result and investigation depth

Use this reference when a broad tool capability could distract from the requested
result, or when a control/string question needs a clear stopping point. It adds
decision guidance, not a required interview, new runtime API or approval cycle.
The user's request and existing project facts supply the task contract.

## Define enough before building

Keep a short brief in existing task notes; no extra ledger is required:

```text
Deliverable: the artifact or answered question, for this target and platform
Success: the observable result and required recovery, if an intervention is used
Scope: relevant constraints and the boundary beyond which work is deferred
Next: the cheapest useful action, its output and who can use it
```

Use already supplied answers. Ask a concise question only if two plausible
interpretations would materially change the output, cost or platform. When a
detail can safely remain open, state a bounded assumption and proceed. A broad
request may need two or three approaches with a recommended smallest useful
one; a clear small request needs no obligatory alternatives or design ceremony.

| Requested result | Sufficient next artifact | Stop or expand when |
| --- | --- | --- |
| Explain a value, string or control | Scoped finding and decisive evidence reference | The requested meaning is supported; trace further only for a missing required mechanism |
| Repeat operations in the original app/game | Named actions with inputs, entry conditions, effects and continuation | The required sequence works and can be reused; full semantics are unnecessary |
| Recover semantic behavior into UIL | State/operation definitions and component correspondences, with unresolved portions explicit | The requested semantic coverage is met; a target implementation is separate |
| Replace, port or swap a backing | Implementation on the requested platform plus its applicable comparison evidence | Follow the replacement acceptance procedure for those requested edges |

These are choices of deliverable, not four mandatory consecutive phases. Start
at the cheapest acquired capability. If an existing API already opens, edits and
saves a document, use it before reverse engineering mouse coordinates. Add only
the harness operations the next experiments need. Do not build a compiler,
emulator or rules engine to answer a question an available reader can settle.

For example, a Notepad harness may expose `open(path)`, `replace(text)` and
`save(path)` through the original program. Success is that the requested text
reopens correctly through those actions. Native-code recovery, a complete editor
model and another platform are separate tasks. The same principle applies to a
game: a reusable scene route can satisfy a harness request while its original
engine keeps running. The verb names here illustrate contracts, not shipped APIs.

Revisit the brief when a proposed new platform, dependency, backend or subsystem
changes the deliverable, or when repeated failures stop producing useful evidence.
Ask what this addition unlocks for the next required result. If it unlocks none,
defer it with one line. A useful local helper within scope needs no separate
permission ceremony. Do not defer a required unanswered question merely to make
a trial appear faster.

## Trace the exact control to the needed effect

Identify the exact control by scene/window, menu path, label, accessibility
identity or observed hit box. Similar labels in different menus do not establish
a shared action handler. Distinguish label construction from the callback that
executes the operation. Follow the nearest useful path first:

```text
specific control -> callback/dispatch -> relevant state guard -> requested effect
```

Use the existing resource/source/xref view or one bounded original call capture;
choose the cheapest route that answers the question. A resource string can seed
a candidate without proving execution. Expand outward only until the requested
boundary is explained or a concrete missing dependency is found. Do not recover
every menu and serializer to explain one button.

For repeated use, capture the learned control as a named Z action immediately.
Keep its semantic operation stable when replacing UI steps with native calls.
For Save/Load, distinguish selection/submission, per-component file I/O, live
state adoption, continuation and redraw. Return, file change, buffer transfer and
display refresh have different outputs. Use the existing operation-goal child
definitions and queue to expose missing components; see [common UIL](common-uil.md).

## Locate a string, then classify its role

Use a known string or visible value as an anchor, with the smallest relevant
resource, file or readable memory range. Batch compatible needles and encodings
over one snapshot. Report scan bounds and skipped regions for a no-hit result;
do not turn a bounded search into an absence claim.

Classify useful hits as shipped code/resource data, mapped file/cache, mutable
state, formatted display text, heap copy, or unrelated session/log content.
Keep file offset, module-relative address and live address distinct. Note the
containing text, region/module and a useful reference or writer/reader candidate.
The first matching copy is not automatically the origin or authoritative field.

For `Health: 234`, a formatted string is an immediate UI anchor. Search likely
numeric encodings of 234 in relevant state or saved files, then test candidate
fields with distinct valid values and one refresh. A corresponding display
change supports that scoped dependency; authoritative gameplay use or complete
provenance needs further tracing only when required. Preserve candidate names
and raw references when labels change. Reuse relevant qualified facts between
searches while discarding accidental filters or assumptions from unrelated ones.

Before live reads, confirm the requested target, current runtime owner and
address mapping at the affected boundary. For emulated games, distinguish guest
memory from the host emulator's process memory. A failed attach blocks its live
path while static inspection continues. Do not copy/re-sign apps, alter platform
security or install a debugger merely because a reference skill recommends it.

## Keep failures and parallel work proportional

For a failed operation, compare expected and observed results at the first
unresolved boundary: input delivery, scene readiness, handler entry, component
effect, continuation or display. State a hypothesis and choose the smallest probe
whose outcomes differ. Change one causal condition per discriminating probe;
compatible independently attributable HUD edits can still be batched.

Keep a linear task list for a linear route. Branch only for genuine alternatives
or independent ready questions. Rank work by useful output and dependencies
unlocked per cost; a cheap decisive check usually precedes a broad trace. Each
worker has a current bounded question; the investigation can have several ready
workers. One controller still owns each live guest.

Retain a rejected hypothesis with its decisive reference and what would reopen
it. Do not rerun it without changed evidence. A retry limit prompts reassessment,
not a claim that the entire architecture is wrong. Park only dependent work and
continue ready record/file tasks. Reconcile an uncertain side effect before retry.

Return a short account: what was requested, what happened, where the decisive
evidence is, the supported role/scope and the next required action. Include a
mismatch or blocker when material. Keep the raw artifacts by reference rather
than repeating scanner output or every rejected lead. See the
[methodology addendum](methodology.md) for deeper causal or replacement claims.

## Improve the skill from use

Prefer corrections that generalize across targets and keep detailed procedures
selectively discoverable. Judge a trial by completed required outputs, errors,
recovery and worker feedback alongside first useful result and end-to-end time.
Use matched old/new briefs and tooling when making comparisons; identify repair
time, assistance, carryover and incomplete runs. Record tokens only when actually
provided. A shorter report or a higher instruction-following score alone does
not establish faster correct work. Target-specific discoveries belong in the
dossier, not hidden answers baked into a general skill.
