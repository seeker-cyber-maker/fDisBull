# Local skill review and integration

The user supplied nine OMP skill folders for comparison with the retained Z and
UIL workflow on 2026-11-04. They were reviewed as source material, not invoked as
instructions. In particular, their approval gates, tool preferences, debugger
workarounds and evaluation loops do not acquire authority through this review.
The maintained fDisBull skill remains self-contained and does not require these
skills to be installed or loaded together.

## Findings and decisions

| Supplied skill | Useful contribution | Integration and limits |
| --- | --- | --- |
| `brainstorming` | Understand purpose, constraints and success before choosing an implementation; decompose a large request; avoid unrelated features. | Add a short deliverable/success/scope/next-action brief at the skill entry. Reuse existing answers and clarify consequential ambiguity. Do not import mandatory design approval for every task, repeated interviews, companion servers or the required transition to `writing-plans`. |
| `debug-decision-tree-ai` | Define objective/deliverable/acceptance/next action; prefer cheap deterministic answers; retain rejected branches and their reopening conditions. | Use a task list for a linear route and branches for actual alternatives or independent ready work. One current question per worker, with multiple workers allowed. Do not import one globally active branch, mandatory colored reports, a second global ledger or a checkpoint after every minor milestone. |
| `debug-ready-ai` | Identify the actual runtime, architecture and mapping before live reads; retain debugger continuity; separate offline evidence from runtime proof. | Check the affected identity boundary on entry to live work and after a relevant change. Distinguish guest and host memory. Failed attach parks its live path. Do not import blanket attach prerequisites for static work, automatic app copies/re-signing, entitlement changes or test bypasses. |
| `explain-button-ai` | Separate label construction, exact control, callback, dispatch, state guards and the first useful effect. | Add a control-to-effect chain with a task-specific stop point. Similar labels do not prove shared handlers. Map discovered controls to named actions and semantic child operations. Do not automatically recover every related subsystem or generate relationship graphs. |
| `find-string-ai` | Classify a hit's region, source, owner and role; preserve offsets, containing text and use candidates. | Add bounded batched string/value searches and distinguish display text, mapped copies and authoritative state. Retain useful prior findings but discard accidental filters. Its LLDB helper is archived, not installed or presented as a fDisBull API; its 3 GiB scan default is not adopted. |
| OMP `skill-creator` | Evaluate real outputs, compare baselines, collect quality and timing, and revise from user/worker feedback. | Add evaluation criteria that preserve required questions, failures, assistance and timing origin. Keep generic guidance separate from target answers. Do not import Claude-specific commands, mandatory viewers, unbounded evaluation loops or assumptions that token/timing metadata is available. This differs from the Codex system skill-creator already archived. |
| `systematic-debugging` | Compare expected and actual behavior, locate the first differing boundary, form one causal hypothesis and make a discriminating change. | Clarify failure triage while retaining compatible HUD batches. Repeated failed probes cause reassessment; they do not prove the architecture is wrong. Do not require complete tracing, a new test for every discovery, a fixed ritual or unsupported performance percentages. |
| `tell-story-ai` | Explain what was found, where it comes from and what role the evidence supports in concise prose. | Extend the existing compact handoff with expected versus observed outcome when they differ. Keep raw results by reference and distinguish likely from observed. Do not duplicate the dossier or write unsupported causal stories. |
| `write-a-skill` | Use discriminating descriptions, progressive disclosure and deterministic helpers for repeated work. | Keep the new decision detail in a selectively retrieved reference, indexed by the CLI. Use an existing deterministic tool before adding another script. Do not adopt its contradictory fixed length thresholds, require interviews already answered by the conversation or create extra files merely to match a template. |

Complete supplied sources and included notices are retained under
[`research/local-skills/2026-11-04/omp/`](../research/local-skills/2026-11-04/omp/).
The [inventory](../research/local-skills/2026-11-04/manifest.json) distinguishes
these reviewed candidate inputs from the earlier tested skill variants and the
maintained bundled skills. Archival inclusion is not installation, endorsement
of every instruction, a new license grant or a tested performance claim.

## Maintained workflow changes

The investigation entrypoint now asks for the expected artifact before backend
selection and applies the Z harness to repeated program as well as game work.
The [task-framing reference](../src/fdisbull/skills/fdisbull-investigate/references/task-framing.md)
contains depth selection, exact-control tracing, string classification, bounded
failure triage and evaluation guidance. It is available through
`fdisbull agent-skill --reference references/task-framing.md` without opening an
analysis project. The quickstart and methodology addendum route to it.

The intended default sequence is:

1. State the requested result and an observable completion condition.
2. Reuse the cheapest relevant capability or acquire one small missing one.
3. Publish its usable output and the questions it unlocks.
4. Continue ready independent work; investigate a blocker at its first missing boundary.
5. Stop when the requested result is satisfied, with required unknowns explicit.

This supports the existing formal operation-goal syntax and work queue; it adds
no second goal format or new runtime automation. A task brief is a planning aid,
not executable syntax. A repeated operation can still be lowered into the
existing typed operation/component definitions when that is useful.

## Reasoning examples and validation scope

These are review cases, not newly executed game or application benchmarks:

- **Notepad harness:** open a document, replace text, save and reopen through the
  original app. Prefer an existing programmatic interface; named UI actions are
  a fallback. No replacement editor, console target or full engine extraction.
- **Displayed cash:** find candidate encodings, intervene reversibly, refresh
  once and report the scoped display dependency. Recovering the whole economy
  is additional work unless requested.
- **Load button:** identify the exact control and follow its requested effect.
  If the goal is UI-free native reload, continue through valid entry, component
  reads, adoption, continuation and refresh. A useful prefix read is a partial
  output, not a reason to declare the full reload complete.
- **Blocked tactical UI:** keep an immutable soldier/file census running while
  the owner resolves navigation. Record the missing native/save condition and
  give the next worker the relevant evidence subset.

One independent read-only agent compared the six debugging/story skills against
the existing workflow. Its main finding was that evidence discipline largely
already existed; explicit expected output and permitted depth were the largest
entrypoint gap. This pass was a document review, not a new cold runtime trial.
No supplied script, visual server, debugger bypass or benchmark loop was run.
Validation checks retrieval/discovery and document consistency; runtime speed
and cold-agent behavior after these edits remain unmeasured.

Fresh checks for this integration: the existing agent-skill gate, analysis-approach
and reconstruction-discovery tests passed (37 tests in 0.52s); the Codex skill
frontmatter validator passed; the new 8,444-byte reference was indexed and
selectively retrieved without a project. An initial duplicate local Markdown
link was caught by the existing gate and removed. Independent final document
review reported no actionable findings. These checks do not measure runtime
speed or prove the behavior of a future cold agent.
