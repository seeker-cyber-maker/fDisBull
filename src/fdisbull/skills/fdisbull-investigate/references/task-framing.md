# Expected result and investigation depth

Use this reference when a broad tool capability could distract from the requested
result, or when a control/string question needs a clear stopping point. It adds
decision guidance, not a required interview, new runtime API or approval cycle.
The user's request and existing project facts supply the task contract.

## Define enough before building

Keep a short brief in existing task notes; no extra ledger is required:

```text
Deliverable: the artifact or answered question, for this target and platform
Audience / report level: intended reader; overview, practical or technical
Human outcome: what the reader should understand, recognize or decide afterward
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

## Tell a human-readable story and use feedback

Choose the audience, report level and useful human outcome in the task brief.
Introduce the target and starting situation so someone who did not watch the
investigation can follow it. Use the user's
stated preference; for an unspecified human observer, start with `overview`.
These are authoring conventions, not new CLI flags or runtime schema fields.
Report level controls vocabulary, detail and evidence presentation. It does not
change investigation depth, completion criteria, claim strength or what evidence
must be preserved. Length is a separate choice: an overview can explain a complex
finding at length without requiring the reader to know assembly language.

| Report level | Reader's need | Content to show |
| --- | --- | --- |
| `overview` | Understand the purpose, result and next decision without specialist knowledge | Plain-language story, supported finding, observed effect when available, implication, uncertainty and next step; explain necessary terms |
| `practical` | Repeat the action or help test it | Overview plus entry conditions, named actions, expected result, recovery and relevant observations |
| `technical` | Inspect or extend the implementation and evidence | Story plus relevant call/component paths, fields, addresses, formats, reproducible inputs and decisive artifact references |

For mixed audiences, lead with the overview and provide an optional detail
section or existing evidence link. Derive both from the same findings. Keep the
agent handoff's complete facts and dependencies available by reference; do not
erase a difficult unknown to make the story simpler. The supplied TellStoryAI
pattern contributes what/where/role, but a human observer also needs purpose,
consequence and an understandable next decision. The local skill need not be
installed to apply this guidance.

A useful story answers, in connected prose:

1. What were we trying to learn or make possible?
2. What did we establish from files, code or runtime observations?
3. What does that support, and why is it useful?
4. What remains uncertain, and what is the next useful action or human input?

For example, this is an **illustrative partial result**, not a new test:

> We are trying to make loading a saved game work without navigating its menus.
> The game copied the edited money value from the save into memory, so we have
> found part of its loading process. The screen has not yet shown that value.
> The next step is to identify how loading finishes and refreshes the screen.

The technical view may identify the file reader, destination buffer and missing
continuation. Both views must preserve that full loading is still incomplete.
Avoid unexplained terms such as ABI, serialization or pointer in an overview;
use a short explanation when the concept matters to the decision.

Use screenshots when they make a finding easier to assess. A code screenshot
needs a caption naming the relevant operation, what the highlighted lines support
and what they leave unknown. Label inferred meanings. A code view supports a
code claim; it does not by itself show that an action ran or its effect committed.
For a visible-state claim, a relevant before/after view may be more useful. Reuse
existing captures and evidence; do not run the target again just to decorate a
report. Follow the existing privacy/publication rules for target-derived images.

Human feedback is another input to the investigation. At a meaningful finding,
ambiguity or change of direction, make the useful opening specific: a term the
reader can correct, behavior they recognize, a missing outcome, or a priority
they can choose. Do not require approval after every probe or make a human who
cannot read disassembly interpret a raw code dump. Reuse a supplied preference
instead of repeatedly asking for it.

| Feedback | How it changes the next work |
| --- | --- |
| A requested outcome or priority changes | Update the task/acceptance or queue priority within the user's authorization; preserve previous findings |
| A domain name or interpretation is corrected | Update the candidate label while retaining stable identities and its evidence history |
| The observer remembers a rule or reports behavior | Attribute it as human-reported evidence or a hypothesis; choose a cheap relevant probe if it changes the next decision |
| The report is too technical, too vague or too long | Adjust presentation using retained findings; no new experiment is needed solely to rephrase it |
| Feedback conflicts with a retained observation | Preserve both and find the smallest relevant discriminator; do not silently relabel either as independently verified |

Reuse the dossier and existing dependency queue for useful feedback and the next
question it unlocks. Include only a compact feedback/result note, not a second
ledger. If clarification is required for one branch, keep its dependents waiting
and continue independent ready work. If no decision is needed, deliver the story
without inventing a question. Feedback collection does not add a new UI, event
channel or automatic ingestion capability to the tool.

## Improve the skill from use

Prefer corrections that generalize across targets and keep detailed procedures
selectively discoverable. Judge a trial by completed required outputs, errors,
recovery and worker feedback alongside first useful result and end-to-end time.
Use matched old/new briefs and tooling when making comparisons; identify repair
time, assistance, carryover and incomplete runs. Record tokens only when actually
provided. A shorter report or a higher instruction-following score alone does
not establish faster correct work. Target-specific discoveries belong in the
dossier, not hidden answers baked into a general skill.
