# Steering unfamiliar agents toward recovered behavior

Status: documentation-only analysis and proposal, 2026-11-05. No runtime,
active skill, CLI contract, UIL schema, release or installation is changed.

## Decision requested

Review a smaller, consumer-first investigation entrypoint, task-specific local
capability discovery, persistent decision items, and inexpensive checks on
intermediate outputs. Evaluate these changes without requiring the user to
supply repository history or write a longer prompt.

The product question is: can an unfamiliar agent take a normal request, discover
the relevant capabilities and guidance, and make sustained progress toward the
requested outcome without supervision?

The recommendation is to make the next unit of progress a recovered behavior,
not another representation of unfinished work. This is a proposed improvement,
not a demonstrated causal explanation of the observed run.

Companions:

- [Candidate skill core](SKILL_CORE_PROPOSAL.md): review text, not an activated skill.
- [Evaluation and rollout](EVALUATION_PLAN.md): controlled experiments and follow-up
  acceptance criteria, not completed benchmark results.

## 1. Basis, attribution and limits

The primary source is the owner-supplied private transcript, identified here as
**T1**, `Pasted text(3)(1).txt`, 133,906 lines, 19,157,006 bytes, SHA-256
`3e29eead2bc5b5429f9646f09f41933a9b4ca48e1d8548700a57d4205657271b`.
Line references below are original file lines, not search-result display lines.
T1 is not included in this contribution. Only sanitized analysis, short technical
examples and locators are published; no game bytes, game prose, private logs,
credentials or personal filesystem paths are included.

The user's follow-up explains that the Dragonsphere request was a one-shot test
of an unfamiliar agent, without mentioning GitLab. T1:117896-117906 corroborates
the short request, supplied files and visible investigation-skill selection.
It does not establish a fresh, isolated model context or the complete set of
host-injected instructions. The capture includes earlier work, repeated history,
compaction and collapsed tool output. Its size is not elapsed effort or a count
of independent experiments.

**Attribution correction:** T1:50-51 identifies an earlier DeepSeek session;
T1:117433 names `opencode-go/iceman-contributor-free`, with later interface labels
at T1:122790 and 130187. The Civilization findings are a separate earlier lane,
not evidence that Iceman made those mistakes. The alias alone establishes neither
the underlying model vendor nor its ability. This contribution makes no vendor,
parameter-count, benchmark-score or comparative-capability claim.

The user described the intended environment as local v0.33 with packages present.
The captured capability response at T1:118025-118029 instead reports runtime
`0.30.0` and distribution `0.9.0` for that invocation. These are distinct pieces
of evidence, not reconciled identities. They do not establish which release was
used throughout the run. A future trial must record the actual executable,
import path, package identity and loaded skill revision.

This review does not rerun Dragonsphere, validate the final private artifacts,
or assert that every observed defect survives in current repository code.
Recommendations are separated from observations. No model evaluation is run here.

### Evidence-to-recommendation map

| ID | Recorded observation | Scope and interpretation | Proposed response |
| --- | --- | --- | --- |
| F1 | The short request selects the investigation skill; the agent opens the quickstart and retrieves scene recovery. T1:117896-117916, 118482-118494. | Guidance discovery partly worked. Reading is not evidence of operational adoption. | Make the entry rules select a concrete consumer and next action; retrieve deeper references only when needed. |
| F2 | Source case numbers become interaction records; the final output counts 77 scenes, 1,536 actions and 58 conversations while a package is labeled non-executable. T1:125240-125267, 127775-127789, 133833-133856. | These are recorded artifact counts, not verified behavioral coverage. A source index can be useful without being executable UIL. | Keep inventories, semantic candidates, executable behavior and comparison results distinct. |
| F3 | A deduplication helper puts continue, set insertion and append in one conditional suite. T1:125397-125405; related variants at 125568-125576 and 125639-125648. | The shown helper cannot append as intended. Final artifact impact has not been independently audited. | Require a tiny known-positive fixture before broad application; rebuild affected outputs from retained inputs. |
| F4 | Coordinate and timing constants are extracted as room references. T1:125688-125710. | Name similarity and a matching integer do not establish a semantic type or transition. | Follow the value's producer and consumer; keep typed ID namespaces. |
| F5 | The transcript states that a scan failed before new writes, but its merge stage used existing files. T1:133698-133705. | This records stale-result reuse during development, not proof that every final output is stale. | Fail the dependent publication stage or explicitly identify admitted cached inputs. |
| F6 | Earlier Civ work acknowledges using binary investigation before available reconstructed source; that source resolves the handler interpretation. T1:2539-2543, 2605-2619. | Earlier lane only; useful methodology evidence, not an Iceman score. | Reuse an adequate documented/source answer before investigating the remaining discrepancy. |
| F7 | Earlier address reasoning mixes segment bases and function entries and contains arithmetic errors. T1:99996-100017. | Earlier lane only; no binary execution address is newly established by this review. | Centralize typed address conversion with round-trip tests; distinguish a coordinate mapping from observed runtime CS. |

The transcript also preserves useful work: provenance, resource inventories,
attributed implementation references and explicit limitations. Those should be
retained. The proposed change is to turn them into executable behavioral progress,
not discard them or prohibit exploratory hypotheses.

## 2. Relationship to existing guidance

Repository context was inspected on 2026-11-05:

- [AGENTS.md at main 242e5343](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/242e5343f5aa55dec95af3a49668a71ae14982c6/AGENTS.md)
  already directs agents to the user's task, selective skill retrieval, one
  active question and scoped evidence.
- [MR !82](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/82)
  is an existing draft retained-workflow/operation-goal proposal. The inspected
  [skill at 2e7ec16](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/2e7ec16add6f1cacd459119c6a745598da45eeb9/src/fdisbull/skills/fdisbull-investigate/SKILL.md)
  already includes expected-result framing, reference reuse, named Z actions,
  operation goals, work queues, delegation and first-failed-boundary guidance.
- [MR !84](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/84)
  is closed at this inspection. Its retained description distinguishes already
  authored Castles II replay speed from a genuine cold-agent harness-building
  comparison. That distinction remains applicable; no benchmark result is imported
  as evidence for this proposal.

These references are repository context, not proof of exactly which skill bytes
Iceman consumed. The transcript records the reference request, but the complete
loaded instruction context is not established.

**Do not add a second planner or replace !82's functioning workflow wholesale.**
The proposed delta is prominence, discoverability from an installed package,
consumer-backed acceptance, robust stage boundaries and controlled evaluation.
Integrate any later changes through the existing operation-goal/work-queue system.
This documentation MR remains independent of the unmerged code in !82.

## 3. Proposed methodology

### 3.1 Orient locally, without requiring GitLab history

Use three levels of guidance:

| Level | Content | Role |
| --- | --- | --- |
| Entry skill | Outcome, three decision gates, completion criterion, discovery entry | Choose the method. |
| Task-specific context | Exact local tool identity, relevant capabilities, one applicable example, selected references | Make the next action concrete. |
| Deep reference | Format, engine or debugging detail | Resolve a particular gap. |

Extend existing discovery rather than inventing a parallel command surface.
A compact response should establish the requested outcome, actual available
backend, private workspace, likely first useful behavior, relevant consumer,
known gaps and the next command. It must not advertise draft-only methods as
installed functionality. GitLab is relevant when needed for missing source,
contradictions or authorized contribution, not a prerequisite for using the tool.

A roughly one-page entry core is a candidate design to test, not a proven optimal
length. Detailed material should remain retrievable. Do not remove essential
boundaries merely to achieve a line-count target.

### 3.2 Apply three decision gates

1. **Is the question necessary now?** Does its answer unblock the current milestone
   or the requested conclusion? Otherwise defer it.
2. **Is an adequate answer already available?** Reuse local findings, compatible
   documentation, source or reference implementation with attribution. Investigate
   only a material gap, conflict or required target-edition correspondence.
3. **What is the smallest discriminating action?** Choose an inspection, experiment
   or implementation test whose result can change the decision.

Documentation-first must not become exhaustive reading before any work. Static
source can support a source-backed component without a native run. Runtime
comparison is required when the claim requires it, not as a ritual on every fact.
An explicitly blind or independent-recovery arm must retain its declared limits.

At Gate 3 ask: if implementing this functionality, how would it be coded and what
would distinguish it while reversing? Record a hypothesis, expected evidence and
one discriminator. For a possible conversation handle, inspect its producer and
consumer rather than equating its number with a filename. The imagined
implementation is a search aid, not recovered semantics.

### 3.3 Choose reuse, recovery or capability repair

**Reuse:** adapt an appropriate existing implementation, preserving provenance and
checking the changed boundary. Do not reimplement a documented mechanism simply
to claim independence.

**Recovery:** identify a necessary unknown and resolve it through the cheapest
adequate source inspection or original-backed observation.

**Capability repair:** when behavior is understood but the tool lacks a reader,
representation or provider, implement the smallest reusable missing capability
within scope. Return to the behavioral task afterward. Missing support is a
local dependency, not permission to replace UIL with a title-specific catalog.

Identify where behavior actually lives: native code, interpreted scripts,
declarative data, reconstructed source, or a combination. Do not assume that
every resource type contains an executable script. T1:125225-125228 explicitly
recognizes room logic in reference C++ source; indexing its case labels does
not preserve that code's control flow.

### 3.4 Recover a complete useful behavior, not a toy substitute

Inventory broadly once, then close a useful dependency slice: inputs, guard,
state reads/writes, ordered effects, continuation or wait condition, and a named
consumer. The first slice should exercise machinery likely to be reused, such
as a branch, state access, a media reference and a continuation.

One interaction is a milestone within the full requested goal, not a silent
scope reduction. Continue to the next required group after its acceptance.
A limitation in one dependency should not block unrelated ready work.

Keep these dimensions independent in existing records; the following are
conceptual labels, not a newly registered UIL schema:

| Dimension | Example values |
| --- | --- |
| Representation | Inventory, behavioral definition, executable component |
| Basis | Documented, source-backed, binary-derived, runtime-observed |
| Comparison | Not run, passed for stated cases, diverged |

A partial executable with unresolved operations can still be useful if execution
cannot silently cross an unsupported required path. A qualified reference
implementation can support translation without proof of the whole game first.
A successful test of a self-authored guess does not establish original fidelity.

### 3.5 Separate behavior, media, state and host realization

Retain the established separation: behavior requests effects; media identifies
payloads; memory owns authoritative mutable state; a realization supplies the
host services. Zero-based IDs and filename aliases may resolve to the same
catalog entry, but rooms, coordinates, durations, media and memory slots retain
their types and namespaces. Numeric similarity is not a binding.

Do not duplicate authoritative state in independent flags and byte stores.
Preserve aliasing through typed views. Resolve and validate catalogs at admission,
then retain them for use. A representation can become higher-level UIL only when
the abstraction preserves the claimed behavior; mechanical translation and
intent recovery remain different achievements.

Named Z actions can have original-backed and reconstructed implementations.
The interface does not determine the evidence strength. An original-backed
text verb can acquire observations; an authored-only model cannot independently
validate itself. Keep the backend and assistance policy explicit.

## 4. Persistent decisions and EGM delegation

Use the existing task/dossier machinery. Each active item needs: goal, known
answer/reference, actual gap, next action, acceptance and what it unlocks.
Retain the full user outcome above those items. A board or graph is a projection
of that state, not a second hand-maintained document.

The lead owns priorities, canonical state and acceptance. A worker receives one
question, relevant inputs/references, allowed tools, budget, expected output and
integration boundary. Workers return findings or isolated patches, not concurrent
rewrites of the canonical package. One owner controls a live guest; workers may
use shared read-only snapshots or separate guests.

Resume means recover the active item and its dependencies, not infer new work
from the current directory's dirty files. After repeated non-informative attempts
(three is a candidate default), reassess the hypothesis, target identity,
readiness, tool or oracle. Do not stop the whole project because one method failed.
Do not manufacture housekeeping tasks just to obey an automatic continue nudge.

## 5. Mechanical checks belong in the toolchain

| Boundary | Small required check | Avoid |
| --- | --- | --- |
| Extractor | Known-positive input, relevant negative case and retained complete records | Treating an empty result as successful recovery without explanation |
| Typed binding | Producer/consumer evidence and domain checks | A regex name match promoted to an executable room transition |
| Stage publication | Successful current inputs or explicit validated cache identity | A failed decoder followed by a new package using unacknowledged stale files |
| Address conversion | Declared coordinate type, mapping parameters and round-trip fixture | Repeated hexadecimal arithmetic in prose or inferred runtime CS |
| Executable claim | Named consumer plus an execution assertion | A file named UIL with no implementation for its effects |
| Representation export | Full semantic data retained separately from summaries | Preview limits silently truncating the authoritative model |

The deduplication pattern in F3 is enough to motivate a small regression example:

```python
# Incorrect: all statements are inside the conditional suite.
if key in seen: continue; seen.add(key); output.append(item)

# Intended control flow:
if key in seen:
    continue
seen.add(key)
output.append(item)
```

A fixture with one repeated and one distinct value catches this without a full
game test. Arithmetic can likewise be checked directly: `0xA990 + 0x4C00` is
`0xF590`, and `0x0D12 * 16 + 0x4CDF` is `0x11DFF`. These calculations correct
only the stated mappings, not the unverified premise that a particular segment
was the executing CS in the earlier Civ investigation.

Never weaken acceptance to force success. Add regression cases for discovered
failures; correct a demonstrably wrong test with an explicit rationale. Run
focused checks at the changed boundary and the relevant integration gate, not
an unrelated full suite after every documentation change.

## 6. Acceptance and next work

This proposal is accepted as documentation when attribution and source locators
are correct, proposals are clearly marked, existing mechanisms are reused in the
plan, and no claim implies that the candidate guidance has been activated or
benchmarked. Implementation acceptance and the experimental controls are in the
[evaluation plan](EVALUATION_PLAN.md).

The first implementation priorities are: make local discovery concrete; test a
shorter consumer-first entry; persist the active decision using the existing
queue; prevent failed-stage/stale-result promotion; then measure cold-agent
behavior on fixed inputs. The intended outcome is a short user prompt, relevant
context supplied by fDisBull, guidance that changes decisions, and tools that
catch small mechanical errors before they become large semantic artifacts.
