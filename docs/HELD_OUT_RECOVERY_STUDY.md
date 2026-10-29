# Held-out recovery: parallel agents, play-driven discovery and draft scaffolds

Status: **proposed study and implementation requirements**, 29 October 2026.
No parallel-agent or held-out-game trial is reported here. This extends the
[measured export-order experiment](REPRESENTATION_EXPORT_ORDER_EXPERIMENT.md),
[minimum source acceptance](SCENE_RECOVERY_FAST_PATH.md), and
[HUD/context proposal #22](https://github.com/seeker-cyber-maker/fDisBull/pull/22).
It changes no core schema, runtime rule, scene permission or installed skill.

## What the existing findings do and do not establish

The retained Lost in Time experiment rebuilt seven already recovered branches
into six representations: 42 byte-identical artifacts across 126 successful
worker runs. In-memory joint/staged/hybrid medians to all exports and final
checks were 157.4/141.3/165.4 ms; the paired total-time intervals did not establish
a reliable winner, and the median ranking changed with serialized handoffs.
Joint reached its first successful Z smoke action earlier than staged. These
are prepared-artifact measurements, not agent discovery or whole-scene proofs.
The existing report retains the earlier timeout outside those successful runs.

Two additional findings inform this proposal. Public Z observations lost private
state needed to distinguish later behavior; first-description-wins merging also
hid a later, more precise field interpretation. Preserve the private typed
knowledge, refinements and evidence rather than rediscovering rules from prose.
These are retained results, not fresh tests performed for this document.

The open questions are whether independent agents shorten discovery, whether
normal gameplay supplies useful discriminating evidence, and whether a rough
code/guide scaffold reduces search enough to offset anchoring and rework.
All three are hypotheses to test, not established speedups.

## Compare work allocation, not just artifact names

| Arm | Allocation | Question it tests |
| --- | --- | --- |
| S: sequential representations | One investigator completes the agreed bounded scope in one representation, then reuses its private knowledge for the next | Does the broader picture repay the delay to other outputs? |
| V: vertical action slices | One investigator builds a compact overview, then completes one useful action across representations | Does focused discovery minimize time to useful, accepted behavior? |
| R: representation specialists | Separate agents own outline, UDL, UIL, Z, HUD/context and harness outputs, up to a declared concurrency cap | Does representation-specific reasoning outweigh dependency waits and coordination? |
| D: dependency-oriented workers | Workers claim independent unknowns such as inventory, dispatch, geometry or transition semantics; common exporters consume their results | Does dividing the actual discovery work beat dividing the outputs? |
| P: play-driven recovery | A normal-input player produces observations; investigator workers resolve blockers and annotate candidate fields | Does encountering real behavior prioritize the right questions? |

All arms use the same private fact/evidence interface and the same final
acceptance scope. R may publish provisional structures early; it need not wait
for an entire upstream representation. Unsupported semantics still cannot become
accepted effects. UDL/UIL share the current representation machinery: assigning
two agents to a role-metadata copy alone is not independent semantic work.
Use deterministic exporters where facts already determine the output. Record
any additional representation-specific discoveries separately.

First compare S and V at one worker, then R and D at the same declared worker
cap. Compare P with the otherwise identical best non-player arrangement, making
player compute and input access explicit. Test scaffold seeds separately before
combining winning factors. This staged pilot avoids an expensive all-factor
matrix; freeze a final configuration before the final held-out evaluation.
Keep intermediate pilot results distinct from final evaluation results.

## Shared evidence and scheduling contract

One private versioned knowledge graph is authoritative for recovered claims;
no representation owns a conflicting private copy of game truth. An immutable
claim revision records the target/resource and storage-bank identity, meaning,
types/units, domain, source spans, evidence, alternatives, dependencies and
remaining obligations. A numeric offset or a plausible name is not an identity.
Keep original annotations and later refinements, including disagreement.

Track evidence dimensions separately: external hypothesis, runtime observation,
source binding, conditional source qualification, ordinary reachability and
current input readiness. This is conceptual study metadata, not a new accepted
status enum. A confidence score, agreement between agents, repeated wording or
compilation success does not upgrade a hypothesis into qualified semantics.

Workers consume revisioned deltas rather than retransmitting every document.
Each output names the revisions it used and the claims it depends on. A changed
sentinel, guard, type or alias invalidates dependent outputs; independent work
survives. The next action must reconcile its own current dependencies before
execution. No consumer may silently use a superseded qualification because its
export task started earlier. Preserve committed outcomes if a later phase fails.

Claim a bounded question before starting work. Record one owner, expected input,
deliverable, budget, stop rule and dependents. A blocked worker reports the exact
missing claim once and either takes independent queued work or waits without
repeated model polling. On owner failure, expire/reassign the claim explicitly.
A cyclic dependency becomes a named joint question, not an indefinite wait.
A coordinator resolves incompatible publications using evidence, not majority
vote or last-writer-wins. Independent verification roles may remain blind to
candidate interpretations when the experiment calls for an independent check.

Measure readiness publication, consumption and dependent resumption separately.
The approximate lower bound is the larger of the dependency critical path and
useful work divided by available workers. Actual time additionally includes
coordination, queueing, tool contention, propagation and rework. This is a
planning model, not a measured prediction. Six consumers of one unresolved
inventory interpretation do not remove that interpretation from the critical
path. Multiple genuinely independent unknowns might.

## A player that discovers missing context during normal play

Give the player ordinary controls and record its current goal, perceived context,
input, consumption, visible response and outcome uncertainty. One controller
owns mutation of each live guest. Other workers use immutable source, retained
captures and read-only coordinated observations, not competing mouse/key input.
Parallel native experiments require isolated compatible saves, filesystems and
session identities; checkpoint creation/restore cost belongs in the comparison.
Direct state edits remain diagnostic interventions, never ordinary-play evidence.

The discovery loop is:

1. The player attempts a bounded useful action through normal input. Unknown
   outcomes are reconciled before retrying. Failure or waiting is retained.
2. Qualified before/after observations identify changed candidate values. The
   analyst keeps alternatives: a changing byte could be an item location, a
   selection index, animation state, elapsed time or an unrelated counter.
3. The investigator follows the relevant reads/writes and guards in code, or
   requests one discriminating ordinary action or unchanged-state control.
   A correlation suggests where to look; it does not establish field meaning.
4. When the existing source-acceptance requirements are satisfied, publish the
   scoped interpretation and regenerate affected outputs. A previously observed
   value is not automatically a fresh live value after that publication.
5. Resume useful play. At the agreed scene boundary, inspect the relevant
   branches omitted by that route instead of claiming the route covers them all.

Freeze two distinct player-information conditions. In the ordinary-information
condition, hypotheses and privileged memory are private to investigators. In
an assisted condition, the player may receive the requested HUD values and
explicitly labeled hypotheses. Assistance is allowed, but its availability and
cost must be matched between compared arms. Neither condition should silently
turn a guessed field name into a reported fact. Keep play used for discovery
separate from evaluation play on withheld actions/states.

A native harness may explore an unknown rule through a separately qualified
input mechanism while the original game owns the outcome. That does not license
a reconstructed runtime to invent the unknown rule. Exploration authorization,
physical input readiness and recovered semantic acceptance are different things.

## Guide and rough-code skeletons are useful candidate inputs

Compare four seeds within the same selected allocation: no prepared skeleton,
a guide-derived scene graph, a rough code draft, and both. A guide seed predicts
objects, exits, candidate actions, dependencies and expected outcomes. A draft
can propose function boundaries, state types, event order, branch alternatives
and output interfaces. Use the guide checklist already described in the
[fast-path contract](SCENE_RECOVERY_FAST_PATH.md).

Record exactly which sources each arm may inspect. A scheduling comparison
gets equal starting information. A comparison of extra guide access is a separate
information-access experiment. Skeleton construction and external reading time
must be counted, even when a prepared seed is supplied to a downstream agent.
Report supplied-seed-only latency as an additional metric, never as cold recovery.
A literal recovered source listing, decompiler output, hand-authored pseudocode
and a model-generated implementation are different evidence origins.

All guessed semantics start unverified. Preserve guide claims separately from
inferred prerequisite edges, object names and draft effects. Walkthrough order
is not necessarily a dependency; a successful route is not an exhaustive scene.
A copied guide, its paraphrase and a draft based on both are one evidence lineage,
not three confirmations. Include edition/platform/language and actual viewed
video ranges. Do not claim unseen frames from a transcript.

Scaffold admission rules:

- Structural stubs and candidate interfaces may exist before source binding.
  The source-backed runtime returns an explicit incomplete/unsupported outcome
  for an unqualified path, with no invented state changes or success narration.
- An optional executable conjecture model is a separate sandbox, plainly marked
  as predicted behavior. It may generate test questions; it must not control the
  native game or be used as its own expected-answer oracle.
- Keep the original skeleton and discrepancy history. Code evidence may split,
  rename, remove or contradict a predicted entity or effect; exporters consume
  the corrected claim revision, not the more fluent earlier draft.
- Promote only the supported claim/domain through the existing acceptance gate.
  A test generated from a draft and passed by that same draft is a consistency
  check, not independent source qualification. A passing source-free simulation
  remains a source-free simulation.

For example, an authored skeleton can propose an `apply(item, target)` action
and a question about whether the item is consumed. It must not default to
`consumed = true`, `false`, or a successful no-op before the source establishes
that behavior. Unknown is a useful investigation result, not a missing Boolean.

## Held-out design and fair comparisons

Use the user's unrevealed games without selecting or researching them in advance.
Lost in Time is a development case, not a fresh held-out discovery task. Split
at game level, grouping editions and near-duplicate content; include an
engine-family-held-out stratum when testing transfer beyond reusable decoders.
Record known tooling/engine knowledge rather than hiding it. "Held out" means
not used in this workflow's development; it cannot guarantee absence from a
model's pretraining.

Before a run, freeze game/resource fingerprints, starting save and input policy,
selected scene/action scope, model/version, tools/skills, source and guide access,
worker cap, hardware, token/tool/time budgets, seed identity, evidence rules and
acceptance checks. Evaluators keep the withheld tests and answers outside the
worker messages. Use private workspaces for game assets and source-bound data;
only sanitized authored study material belongs in the public repository.

Use fresh isolated contexts/workspaces for each arm. Do not give a later arm the
earlier arm's discoveries unless warm transfer is explicitly the variable under
test. Counterbalance assignments/order across matched tasks and repeat stochastic
runs. No agent may honestly claim to unlearn a game it has just analyzed.
Within a given arm, the shared graph remains reusable throughout its stages.

Run both cost-normalized and latency-normalized views: equal total token/tool
budget across workers for resource efficiency, and equal wall-time allowance
with declared concurrency for throughput. Report aggregate cost in both; a team
of six must not be compared with one agent as though it costs one. Separate
model/tool queue limits, emulator contention and coordinator overhead. Fixed
model identity is the baseline; heterogeneous specialist models are a later
factor, not an unrecorded advantage.

Set the correctness/coverage floor before timing. Count accepted action domains,
source-backed field meanings, relevant alternative/refusal branches, current
click bindings when claimed, and cross-representation consistency. A skeleton
or an artifact file is not a completed behavior. Mark field snapshots and draft
layouts separately from native captures and fully qualified harness actions.
Report failures, unsafe/unintended actions, correction count and unsupported
frontier, not only successful runs. Preserve a useful partial result on a budget
stop without relabeling the task complete.

For the ordinary-play arm, require a matched boundary audit so a fast walkthrough
is not compared with another arm's complete selected branch coverage. Withheld
checks should include plausible wrong item/guard, repetition, sentinel/type,
missing state, stale binding and transition alternatives where relevant. Use
separate authored perturbation fixtures to test whether the workflow can reject
a deliberately incorrect seed. Do not alter the original game or quietly turn
those fixtures into normal-game ground truth.

## Minimum instrumentation and decision rule

| Measure | Interpretation |
| --- | --- |
| Time to first accepted useful action | Includes acquisition/preparation and the acceptance needed for the stated claim; report smoke-test latency separately |
| Time and cost to equal accepted coverage | Prevents rewarding missing branches or weaker evidence |
| Useful analysis/export work by worker | Distinguishes independent discoveries from cheap deterministic serialization |
| Dependency-blocked worker time | Aggregate worker-seconds waiting for specified prerequisites, not elapsed run time |
| Publication-to-consumption latency | Measures propagation delay after a claim is actually available |
| Duplicate investigations, conflicts and stale-output rework | Measures the cost of fragmentation and revision handling |
| Coordination tokens/messages and active/idle tool time | Distinguishes communication from reasoning and external rate limits |
| Hypotheses confirmed, revised, rejected and unresolved | Measures skeleton value and anchoring cost, without equating confidence with proof |
| Post-handoff behavior and context reuse | Tests that another agent can resume from the private graph, with current action revalidation |

Events should identify run, worker, task, role, monotonic time, dependency
revisions and outcome. Account for worker intervals as useful work, coordination,
blocked-on-dependency, external queue/tool wait, idle or stopped, avoiding double
counting. Preserve raw local receipts and export bounded summaries. This is an
instrumentation requirement, not a newly implemented event schema or scheduler.

Use game/task-level paired comparisons with uncertainty, not thousands of tool
calls treated as independent games. Publish completion rates and quality first,
then wall time and total cost. Call a configuration faster only at comparable
accepted scope and permissions. A latency win with higher spend is a tradeoff,
not an efficiency win. Retain inconclusive results. Do not pick a winner from a
single fastest run or optimize on the final held-out games.

## Implementation requirements and prospective checks

| ID | Requirement | Acceptance scenario |
| --- | --- | --- |
| A01 | Persistent private facts, provenance and refinements | A generic field label cannot erase a later sentinel interpretation; conflicting interpretations remain reviewable |
| A02 | Revision/dependency-aware exports | A changed field type invalidates all affected Z/UIL/HUD/harness outputs and leaves unrelated exports valid |
| A03 | Claimed tasks and non-polling wait | Two workers need the same helper; one investigates it, the other receives its publication or takes independent work |
| A04 | Explicit source-free scaffold boundary | A compiling draft and self-generated passing tests cannot become accepted original behavior |
| A05 | One writer per live guest | Concurrent requests serialize or refuse; diagnostic clones have separate state/files and receipts |
| A06 | Correlation kept as a candidate | Pickup also changes a timer; the protocol retains alternatives until a discriminating observation/source binding resolves them |
| A07 | Separate information policies | Plain play receives no private hints; assisted play receives labeled selected context without silently changing the comparison |
| A08 | Unknown outcome reconciliation | A timed-out input is inspected before retry; confirmed partial effects survive a later export failure |
| A09 | Revisioned agent handoff | A replacement worker can identify stale claims, resume the useful question and revalidate actions without redoing settled analysis |
| A10 | Missing evidence and failures remain visible | Blocked dependencies, missing engine support and budget stops produce partial/incomplete results, not empty successful scenes |
| A11 | Equal-scope reproducibility | Swapping the schedule preserves semantic acceptance checks, source identities and output information policy |
| A12 | Recovery from a wrong seed | A contradicted prediction is retained as rejected; dependent outputs are rebuilt rather than forcing observations to fit it |

These twelve cases are prospective acceptance requirements, not executed tests.
Implement the smallest missing capability needed for the pilot; a new agent
framework, language or whole-game reconstruction is not a prerequisite. Existing
project, observation, scene and output boundaries remain in force.

Working hypothesis: a small shared overview, a normal-play evidence stream and
workers assigned to independent unresolved mechanisms may outperform permanent
one-agent-per-representation ownership. Simple export code should remain simple
export code. Test that hypothesis against representation specialists; do not
make it the conclusion before the held-out trials.
