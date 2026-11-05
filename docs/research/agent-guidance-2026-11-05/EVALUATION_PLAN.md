# Evaluating guidance without confusing it with model capability

Status: proposed experiment and implementation backlog. No trials, timings,
causal improvements or model rankings are claimed. Read the [analysis](README.md)
and [candidate core](SKILL_CORE_PROPOSAL.md) first.

## 1. Keep the user's prompt short

The motivating request supplied three files and asked for the game's UIL
representation without naming GitLab. Preserve that task style. The product must
supply usable context; the benchmark should not repair guidance by handing one
arm a detailed walkthrough or the reviewer's recovered answers.

A one-shot user message is not automatically a cold context. Record the actual
system/host instructions, automatic continuation messages, available tools,
loaded skills, retained task state, retrieved references and model identifier
where exposed. Unknown backend identity remains unknown. Never infer model
vendor or capability from an alias or an unavailable score.

## 2. Controlled sequence

First use an authored, known-answer fixture. Then use an unfamiliar target with
appropriate rights/privacy handling. Keep evaluation-only checks separate from
training examples and do not tune the method solely to Dragonsphere.

| Arm | Model | Guidance | Interpretation |
| --- | --- | --- | --- |
| A | Iceman alias, or another explicitly identified unfamiliar model | Frozen current guidance | Baseline for this environment and task |
| B | Same model identifier/settings | Candidate guidance | Guidance contrast |
| C | Control model qualified on a small comparable task | Frozen current guidance | Model/environment diagnostic |
| D | Same control model/settings | Candidate guidance | Transfer of the guidance contrast |

Run fresh independent task state for every arm. Hold tool implementation, input
bytes, availability of references, filesystem permissions and resource budget
constant. Pin exact runtime and skill identities, not merely release labels.
Resolve incompatible advertised methods before comparing performance; otherwise
record the environment mismatch as a separate failure class.

Use multiple runs and targets when feasible. Randomize arm order and record run
date/provider identity, because a stable alias need not imply a frozen backend.
Report distributions and raw per-run outcomes, not a single best success. Treat
an assisted continuation as a separate condition, not retroactive cold success.

Test tool-level validation changes in a later comparison, with guidance and model
fixed. Do not simultaneously change the model, skill, tool and task and then
assign the improvement to one of them. This document specifies no numerical
improvement threshold before baseline measurement.

## 3. Acceptance prepared independently

The evaluator defines task-relevant success conditions before the worker runs.
The worker may author tests, but cannot be the sole author of its own acceptance.
A valid component preserves the selected operation's conditions, required state,
ordered effects and continuation and executes through its declared consumer.
A behavioral representation may be incomplete elsewhere without being mislabeled
as whole-game recovery.

Evaluate at least these boundaries using authored fixtures or qualified references:

| Case | Required observation |
| --- | --- |
| Known source/reference answer available | Agent reuses it and investigates only the unresolved binding or material conflict |
| Successful and rejected interaction | Both execute as specified; rejected path does not acquire success effects |
| Missing required operation | Consumer refuses or reports the local gap; no silent no-op |
| Duplicate records | One repeated plus one distinct record survives deduplication correctly |
| Lookalike identifiers | Coordinates, durations, handles and resource IDs are not conflated |
| Failed producer with previous outputs present | No new publication falsely claims the failed output; deliberate cache reuse names admitted identities |
| Interrupted task | Resume recovers the active goal and next dependency without restarting unrelated maintenance |
| Alternate backing | Same named operation can distinguish original-backed observations from model-only tests |

A source-backed implementation is an acceptable scoped milestone when original
execution is unavailable. Label that evidence edge; do not invent an independent
oracle. An original comparison checks only its stated cases and observed state.

## 4. Measurements

Measure elapsed time from the same declared start, tool calls, tokens when
available, and cost when actually exposed. Separate active work from external
waiting. Use receipt timestamps rather than interpreting transcript line count
or UI timer labels as a complete clock.

Primary outcomes:

- Time/effort to the first correct causal finding and first accepted behavioral
  component, plus the fraction of required milestone cases accepted.
- Correctness against independent evaluation cases, including false semantic
  promotion and unsupported behavior hidden by a success report.
- Avoidable work: rediscovery of an adequate retained answer, repeated operations
  without new information, packaging that adds no accepted behavior.
- Failure recovery and reporting: repair of the first failing stage, accurate
  separation of indexed/implemented/compared results, and a usable retained
  next task after interruption or budget exhaustion.

Failures and non-completions stay in the denominator. Report time-to-milestone as
not reached within budget rather than dropping the run. Count inventory coverage
separately from behavioral coverage. Do not optimize for low tool use at the cost
of the necessary observation or test. The objective is useful progress per cost.

Replay speed of an already-authored harness is not discovery/build speed. This
follows the distinction retained in
[MR !84](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/84),
not a new claim that its benchmark was completed.

## 5. Diagnostic interpretation

Success on a bounded task but failure on the open request suggests task selection,
context or sustained-execution problems. Failure even with explicit inputs,
semantics and checks suggests a capability/tool-use limitation, subject to
infrastructure checks. Neither observation proves a model-wide capability ranking.
Improvement in B over A supports this guidance change for the measured conditions;
replication in D and held-out targets strengthens transfer evidence.

Preserve the transcript's attribution boundary. Earlier Civilization work is not
Iceman data. Model identity speculation is unnecessary to run this experiment.
Check provider data-handling terms separately before submitting private material;
keeping files out of Git does not by itself keep excerpts out of model requests.
No current provider-policy claim is made by this document.

## 6. Implementation backlog and acceptance

These are proposed tasks, not implemented features or automatically created issues.
Reuse existing operation-goal/work-queue mechanisms from the relevant skill lane.

| Priority | Work item | Acceptance condition |
| --- | --- | --- |
| P0 | Task-specific installed discovery | Fresh agent receives exact tool identity, compatible available methods, relevant reference and consumer without repository history. Unsupported/draft-only methods are not advertised as installed. |
| P0 | Consumer-first entry core | A pinned candidate is retrievable from the installed package; one useful executable milestone and the full retained objective are explicit. Old guidance remains available for the controlled comparison. |
| P0 | Persistent active decision | Goal, known answer, gap, next action, acceptance and unlocked dependencies survive a fresh process; resume selects the same ready item. |
| P0 | Stage integrity and tiny regression cases | Known-positive extraction, typed-domain negative cases and failed-producer/stale-output cases are tested before broad packaging. |
| P1 | Original/model backing distinction | Identical named action exposes its backing and scope; a model-only result cannot be promoted to original observation. |
| P1 | EGM task packet and ownership | Worker gets one question, inputs, budget and required output; canonical publication remains lead-owned; one controller owns each live guest. |
| P1 | Cold-agent measurement harness | Identical inputs/tool identities, independent contexts, retained outcomes and evaluation-only acceptance support arms A-D. |

For EGM work, a minimal packet is a task record, not a new language: question,
relevant facts/references, permitted operations, expected output, budget,
acceptance and what it unlocks. Workers return patches/findings to the lead.
A blocked worker must not independently redefine the final schema or publish a
new canonical package. The lead may use ready independent work while the blocked
question is reassessed.

## 7. Review gates for a later implementation MR

The documentation review can land independently of runtime work. Before activating
a new skill, verify its local discoverability and compare it with the prior
revision on authored fixtures. Before claiming a speed or quality improvement,
run the controlled experiment and publish scoped, sanitized receipts. Before
claiming whole-game recovery, satisfy the broader user outcome rather than
extrapolating from the first successful component.

No new runtime API, registered UIL schema, service, automatic model routing,
mandatory per-probe approval, hosted benchmark or release is authorized merely
by merging this analysis.
