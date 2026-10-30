# Evidence and provenance

## Contents

- [Scope and source boundaries](#scope-and-source-boundaries)
- [Claim records](#claim-records)
- [Interpret evidence at its actual strength](#interpret-evidence-at-its-actual-strength)
- [Routes and coverage](#routes-and-coverage)
- [Earlier generated guides and source ports](#earlier-generated-guides-and-source-ports)
- [Conflicts and revisions](#conflicts-and-revisions)
- [Public evidence and authorship](#public-evidence-and-authorship)

## Scope and source boundaries

Start from the selected original files and existing investigation record. Record
platform, edition, region/language, patch/mod, difficulty and relevant engine or
emulator settings when they affect a claim. Name the actual artifact represented
by an existing digest; an unexplained hash is not a target definition. Preserve
distinctions between original executable, resource data, interpreter version and
source-port build. A familiar game title or similar filename is insufficient.

Separate the writing objective from the experiment's information policy:

| Task | How to handle external game facts |
| --- | --- |
| Review existing knowledge | Reuse available findings with their existing lineage; do not recast external findings as newly recovered facts. |
| Reference-guided investigation | Credit the source that suggested a hypothesis and the separate target evidence that checked it. |
| Files-only recovery experiment | Honor the permitted inputs. Use formatting exemplars for presentation only. Keep game-guide/source-port facts outside the recovery pass; record any later comparison separately. |
| Audit an earlier generated solution | Evaluate claims and the available provenance. Preserve useful presentation; do not trust or reject claims because of which model wrote them. |

Model familiarity is not an artifact. Do not claim a historically blind experiment
was uncontaminated merely because no citations were written down. If external
material was already consulted, state the boundary honestly and continue under
the user's current scope. Useful reference-guided work remains useful when
correctly described.

## Claim records

Use stable IDs for assertions that can change player decisions or the reader's
understanding: routes, prerequisites, numerical values, formulas, timing, failure
conditions, release differences, unused content and completeness claims. Reuse
the existing ledger where possible. Group a table under one evidence record only
when the provenance and applicability actually cover every grouped row.

| Field | Minimum useful content |
| --- | --- |
| ID and assertion | A precise claim, with its guide section and meaningful scope. |
| Applicability | Target identity, build/variant, settings, conditions and units. |
| Evidence kind | Recovered, observed, reference, derived, hypothesis or unknown; allow more than one. |
| Locator | Existing artifact/file ID plus offset/resource/function/trace event, or a pinned URL and section. |
| Method and lineage | What extraction, interpretation, test or calculation produced the finding; which external source suggested it. |
| Qualification | Why that evidence applies, what was checked, and what remains outside its coverage. |
| Conflict or next question | Competing account and the smallest observation or source span that would distinguish them. |

Keep provenance separate from verification. A source can be precisely cited and
still be wrong; a runtime trace can be authentic and cover only one input. Use
explicit states such as supported in stated scope, partial, unresolved,
contradicted in stated scope, or not examined. Avoid confidence percentages
without a calibrated interpretation.

For example, a hypothetical record might say: `C17: the bronze key sets flag 4
in the examined door handler; recovered from resource R8, branch B3; transition
guard decoded, reachability not yet checked.` The readable guide can say the
handler supports that interaction while withholding a claim that the player can
reach the door with the key. This example is invented to illustrate the record,
not a finding about any shipped game.

## Interpret evidence at its actual strength

| Evidence | What it may establish | What still needs qualification |
| --- | --- | --- |
| Extracted strings or resource inventory | The inspected input contains those bytes/entries. | Meaning, active use, reachability, localization and release correspondence. |
| Decoded table | The recorded values under a stated layout. | Field interpretation, units, scaling, callers and variant overrides. |
| Recovered control flow or script | Conditions and effects supported by the decoded path. | Unknown indirect calls, interpreter semantics, hidden dependencies and reachability. |
| Runtime witness | The observed action/outcome in the recorded starting state. | Other states, timing distributions, unobserved branches and effects after the capture. |
| External guide | What that author reports for the stated version. | Accuracy and correspondence to the current target. |
| Reimplementation source | What the pinned implementation and configuration define. | Original-game equivalence, fixes, enhancements, data-version effects and unimplemented paths. |
| Mathematical derivation | A consequence of stated premises under the recorded numeric model. | Whether those premises/model match the game. |

Do not treat a decoded text, visible animation, queued input, accepted click or
watchpoint stop label as proof of the final gameplay effect. Preserve immediate,
delayed, partial and persistent outcomes. Distinguish native game saves from
emulator checkpoints and authored model states. Record assistance, altered
memory, debug features and information unavailable to an ordinary player.

An unused or unreachable resource belongs in a qualified technical appendix,
not an instruction to collect an item. Absence from a bounded analysis is not
proof of absence from the game. A shared decoder, table or source port remains
one lineage even when several tools or agents repeat it.

## Routes and coverage

Define what a heading promises before calling it complete:

| Label | Required scope statement |
| --- | --- |
| Knowledge review | Material examined areas and limits at the investigation cutoff. |
| Strategy overview | Systems, scenarios or examples discussed; no implied executable action sequence. |
| Candidate/partial route | Supported transitions and explicit gaps, starting conditions and unverified portions. |
| Supported completion route | Start state, target release/settings, connected progression, relevant guards/resources, terminal success and how the route was qualified. |
| Full-score/no-damage route | Additional score, optional-action or damage obligations and evidence for them. |
| Optimal/shortest route | Objective, allowed actions, search domain and evidence of optimality, not only one successful short sequence. |
| Complete catalogue | Named inventory and denominator, inclusion criteria and accounted-for omissions. |

Execution is one way to qualify a route, not a prerequisite for writing a static
knowledge review. If a route is justified statically, say so and identify the
coverage of guards, interpreter behavior and reachable states. Do not call it
playtested. A claim of actual completion requires the corresponding recorded
result. Retain disconnected regions as disconnected rather than silently
joining them with plausible prose.

Describe coverage with meaningful denominators: examined scripts versus known
scripts, supported transitions versus route transitions, scenarios/houses/maps
covered, or displayed dictionary entries versus the inventoried vocabulary.
If the denominator itself is uncertain, preserve that uncertainty. An earlier
guide's asserted inventory size is a reported number until its extraction is
available; do not call it newly measured. Do not invent percentages from word
count, instruction count or the number of chapters written.

For runtime verification, retain a concise record: step ID, initial scene/state,
input, observed result, score/resource delta, save/checkpoint reference,
timing/settings and divergence. Separate failed attempts from successful ones.
Keep the ordinary player path distinct from a shortcut used to inspect later
content.

## Earlier generated guides and source ports

First use earlier guides as an inventory of claims and useful organization.
Inspect the evidence behind exact-looking facts instead of copying their tone.
Preserve factual material only at its supported level; a claim can remain an
attributed lead while its derivation is unavailable.

Classify code blocks accurately. A reconstructed C-like explanation is not
original source, a genuine decompiler result needs its tool/input/region, and
source-port identifiers may have been introduced by that project. Preserve
lineage even when an external claim is later confirmed in the target. Distinguish
learned from, suggested by, compared against and independently recovered.

For a source-port comparison, pin the commit and inspected functions/tables,
identify required game-data version and compatibility/enhancement settings, and
map the relevant behavior to the original target when evidence permits. Compare
raw versus displayed units and mod-specific overrides before resolving a
disagreement. Agreement supports correspondence within the compared scope; it
does not prove universal equivalence or independent discovery.

Similarity alone cannot establish copying, and missing public receipts cannot
establish that no private analysis occurred. Conversely, an agent's declaration
of originality is not a reproducible derivation. Report the comparison and its
limits without assigning motives.

## Conflicts and revisions

Preserve conflicting accounts with their scope and source IDs. Consider release
changes, alternate solutions, terminology, scaling, bugs and source errors as
alternatives; do not select whichever account makes the draft more complete.
When the available evidence cannot discriminate, keep the conflict local to the
affected instruction or table.

For an update, keep stable claim IDs where the proposition remains identifiable.
Record corrected/withdrawn claims, affected builds and sections, and the evidence
that changed the conclusion. Recheck dependent advice and alternate formats.
Do not erase a useful unresolved question merely because a newer draft sounds
more confident.

## Public evidence and authorship

Keep original game bytes, private deliveries, emulator states and byte-retaining
project databases out of public repositories. A public appendix can identify a
private evidence record and provide an authored sanitized summary; label whether
the reader can independently inspect it. Do not make a private scratch path the
only promised durable evidence locator.

Use original explanatory prose and concise attributed references. Preserve
actual authorship and user-selected licensing. A repository-wide license and a
guide-specific rights notice may conflict; flag the discrepancy instead of
copying either as settled legal boilerplate. Do not invent personal history,
prior play sessions or a source author's permission. Long manual passages,
dialogue dumps and third-party guide text are unnecessary for this review.
