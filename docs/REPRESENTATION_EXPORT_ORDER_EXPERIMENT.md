# Joint versus staged representation export

Status: measured local experiment, 29 October 2026. Follow-up to
[scene recovery](SCENE_RECOVERY_FAST_PATH.md) and
[synthetic HUD/context proposal #22](https://github.com/seeker-cyber-maker/fDisBull/pull/22).
This document changes no runtime or acceptance policy.

## Question and scope

Compare exporting every representation for one recovered action before moving on
with completing each representation across the whole selected corpus and reusing
its results in subsequent stages. Include a hybrid: build the bounded outline
first, then complete action slices end-to-end.

The experiment uses seven previously recovered Lost in Time branches, linked to
eleven source action IDs. These are not seven complete scenes or a whole game.
Each branch produces six real artifacts: investigator outline, UDL, UIL,
executable partial Z package, model-state HUD/agent JSON, and source-derived
harness target bindings. UDL-to-UIL is the existing checked role-metadata change,
not a separate semantic compiler. All 42 outputs are byte-identical across
schedules and handoff modes, totaling 307,935 bytes per run.

This measures prepared-AST rebuild/export work. Prior extraction, decoding,
manual interpretation and mapper authoring are excluded. It does not measure
whether an investigator learns the game faster in one order.

## Matched procedure

- Joint: outline -> UDL -> UIL -> Z -> HUD -> harness for one action, then next.
- Staged: all outlines, all UDL, all UIL, all Z, all HUD, all harness.
- Hybrid: all bounded outlines, then the remaining outputs per action.

Every schedule uses the same source cache, lowerer, schemas, entry witnesses,
output writes and final checks. The bilge builder was factored for on-demand
branches; every resulting model is compared with the retained model. Neither
schedule is forced to repeat reverse engineering.

Twenty-one paired repetitions cover each of three schedules and two handoff
modes, for 126 successful fresh-worker runs. Deterministically randomized
schedule order reduces ordering bias; all strategies within a repetition use
the same randomized action order. OS page caches are not flushed. Memory mode
reuses stage objects; JSON mode reopens the same intermediate artifacts.
Interpreter/import costs are excluded from internal timing and included in
separately recorded process-wall timing. An earlier unlogged batch hit a tool
execution timeout and contributes no samples to these results.

## Results

In-process handoff, medians in milliseconds:

| Schedule | Complete bounded outline | First successful Z test action | All exports and final checks |
| --- | ---: | ---: | ---: |
| Joint | 59.0 | 18.0 | 157.4 |
| Staged | 13.0 | 31.7 | 141.3 |
| Hybrid | 14.0 | 21.6 | 165.4 |

First-Z means a schema-valid model-backed action smoke pass, not completion of
all final counter checks or a new native-game qualification.

The total-time interquartile ranges are 137.4–174.0, 131.2–161.1 and
140.8–176.3 ms respectively. Staged minus joint has a paired median difference
of -11.6 ms; a 10,000-resample percentile bootstrap interval for that paired
median is [-35.4, +2.1] ms. This does not establish a reliable total-speed winner.
Its first-Z difference is +14.4 ms, interval [+9.8, +20.2] ms: the staged schedule
consistently delays the first executable Z result in this corpus.

With JSON handoff, total medians are joint 157.0 ms, staged 163.0 ms and hybrid
169.7 ms. Total-time paired intervals again include zero. The ranking change is
another reason not to select policy from one fastest median.

All modes reuse the same source knowledge. The shared cache records 19 reads,
9 JSON parses and 12 hashes per worker; these counters exclude identical direct
reads inside the retained poster builder. JSON handoff adds 43 intermediate
reads totaling 384,788 bytes, without repeating semantic recovery. Exporter-phase
changes are 41 joint, 5 staged and 35 hybrid. These are scheduling counts, not
measured human or model cognitive-switching costs.

## What must be reused

A separate executed test supplies two valid typed poster-model witnesses with
counter values -2 and 2. Public Z observations are identical after removing the
opaque freshness token. The same action succeeds in both, then yields counters
-1 and 3: the first hides the object and the second keeps it visible. These are
isolated model witnesses, not ordinary original-game reachability claims.

Therefore public Z observations are not a lossless source for later rule
recovery. A private Z blueprint can serve that purpose when it retains the
necessary typed facts, guards, source bindings and evidence. Reuse that private
knowledge rather than reconstructing implementation semantics from narration.
Selected HUD observations likewise are not presumed complete game saves.

The retained source-packet merger also uses first-description-wins for an
equal-type field at an already-seen offset. A generic poster-state annotation
therefore masks a later, more precise counter/removal-sentinel annotation in the
merged field list. The executable poster model already has correct semantics;
this is an annotation-reuse issue, not a demonstrated model-execution bug.
The experiment's private catalog retains both descriptions and their provenance:
36 storage-field entries, 23 targets and 51 source action descriptions, including
eight fields annotated by both packets. Field identities remain pinned-profile
and storage-bank scoped, not universally identified by a numeric offset.

## Verification and limits

All 126 trials passed seven retained-model comparisons, seven actual Z-player
action invocations, seven HUD JSON round-trips, 256 poster counter cases and two
poster guard refusals. Additional audit exercised all 51 unresolved broad action
descriptions: all refused with no effects. Seven harness artifacts retained
unknown live readiness. The public-Z information-loss probe passed.

HUD values come from actual isolated UIL witness evaluation, not new native
captures. Harness artifacts carry retained source geometry, not newly qualified
clicks. No native replay, persistence qualification, whole-game proof or measured
analyst speedup is claimed. No full project pytest or new CI result is claimed
for this experiment. Private game bytes, text, addresses, saves and captures are
not included in this documentation change.

Runtime: Python 3.13.5 with the preserved fDisBull 0.22.0 offline package, plus
exact PR #18 Z-backend file at commit
`c107d1576d46d7dc353c8043cb81be5005e8926b`, Git blob
`9f349892065a6fd3e5ac026956899970d9fd3173`, loaded alongside that runtime.
This is a pinned test combination, not a new installed release.

The private reproducibility package contains the runner, audit, all 126 trial
receipts, canonical artifacts and implementation identities. Runner SHA-256:
`812128b6530ef542e81752a269b7b59632957a61c7d3f634f9fcfacae1cffe00`.
Audit SHA-256:
`9c676382b3e6706344b455056f614c2c6cf1952ad75824ae973cba5b6ec87220`.
Canonical sorted output-file/digest manifest SHA-256:
`85f67a08fe4861810877ec809e739e5ce934082f8f6717df847d7bc5743f63c3`.
These identities track the experiment; hashes alone are not semantic proof.

## Recommended next workflow and requirements

Use a compact shared overview for the next useful area, then complete one action
slice end-to-end and generate its supported representations. Do not block the
first useful action on completion of a whole-game representation. This hybrid
recommendation balances the two measured latency goals; its advantage to analyst
reasoning is still a hypothesis.

Support both scheduling orders from one private dependency graph. Persist source
facts and qualification across agent handoffs; do not maintain independent
copies of game truth in each exporter. Preserve contextual semantic refinements
instead of silently keeping the first label. Maintain public/private projections
and invalidate only dependent outputs after a source or interpretation change.

For a genuine discovery-speed comparison, use previously unseen matched scene
sets with isolated investigators, equal starting tools/knowledge and equal
acceptance scope. Counterbalance assignment. Count guide preparation, source
interpretation, corrections, tools/tokens, first useful action, completed scope,
failed actions and rework. Timing exports from this already-understood corpus
cannot answer that remaining part of the question.
