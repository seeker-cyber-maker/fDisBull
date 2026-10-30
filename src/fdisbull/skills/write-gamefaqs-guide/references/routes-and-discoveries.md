# Routes, bugs and recovered discoveries

## Contents

- [Retain discoveries beyond the winning route](#retain-discoveries-beyond-the-winning-route)
- [Explain bugs, exploits and secret features](#explain-bugs-exploits-and-secret-features)
- [Define a minimal legal route](#define-a-minimal-legal-route)
- [Compare alternate paths and shortcuts](#compare-alternate-paths-and-shortcuts)
- [Account for completion across runs](#account-for-completion-across-runs)
- [Review the useful claim, not just the label](#review-the-useful-claim-not-just-the-label)

## Retain discoveries beyond the winning route

A reversing-first review includes recovered unused routines, disabled mechanics,
orphaned resources, alternate dialogue, hidden commands, debug facilities and
unfinished content. Explain what each finding reveals and whether a player can
encounter it. Link consequential discoveries from the relevant route or mechanic;
keep technical records in an appendix even when they do not help finish the game.

Reuse discovery IDs and source locators from the claim ledger. Record presence,
interpretation, reachability and developer intent separately. These questions
have different evidence requirements:

| Finding | Useful wording and qualification |
| --- | --- |
| Present bytes or resource | Identify the file/resource and decoded meaning, if established; a suggestive string alone does not establish a functioning feature. |
| Decoded routine with no known caller | Report the routine and examined reference paths. Unknown indirect dispatch or unexamined scripts can still call it. |
| Not observed during examined play | State the examined runs/states; this does not establish that the feature is globally unused. |
| Reachable under ordinary input | Give the supported prerequisites, input sequence and release, with static or observed qualification. |
| Conditional or alternate branch | State flags, difficulty, language, platform, date, RNG or other known gate; retain missing conditions. |
| Debug/cheat-only access | Identify the actual entry mechanism and assistance, including whether it ships enabled in this release. |
| Unreachable within an established domain | Name the entry points, state constraints and analysis coverage supporting that claim. |
| Reachability unresolved | Retain the interesting recovered behavior and the smallest missing connection; do not invent an acquisition route. |
| Absent from this build | Identify the inspected inventory or other bounded basis. A feature in another release is comparison evidence, not local presence. |

Do not flatten these into one "unused" label. Distinguish an executable routine
from data that merely disassembles plausibly, and a deliberately disabled branch
from code that a bounded traversal did not visit. A name such as `debug`, a
comment in a source port or an amusing message may suggest purpose; it does not
by itself prove the original developers' intent. Mark unfinished/cut-content
interpretations as interpretations unless their basis supports more.

Provide supported inspection or activation instructions when useful. Clearly
identify memory edits, patched scripts, forced room changes, extracted media
viewers and ordinary input. A successful debugger activation establishes the
effect under that intervention, not normal-play reachability or run eligibility.
Recovered-only content still belongs in the review and the technical inventory.

## Explain bugs, exploits and secret features

Distinguish programming defects, intentional cheat facilities, easter eggs and
unusual intended mechanics. Describe unknown intent without assigning it. A bug
need not benefit the player; a secret need not affect progression. Retain
potential exploits as candidates with their remaining input/state/reachability
gap.

For each material finding, give the reader the following information using the
existing claim record rather than creating an unrelated second ledger:

| Part | Information to preserve |
| --- | --- |
| Applicability | Exact release/interpreter/data version, configuration and relevant difference in compared releases. |
| Trigger | Starting state, accepted input, ordering, timing and any assistance. |
| Mechanism | Relevant condition, arithmetic, state transition or dispatch error; actual source locator and interpretation limits. |
| Observable result | What appears or changes, separately from predicted internal effects. |
| Continuing effects | Resource deltas, delayed events, save/reload persistence, repeatability, caps, crashes or softlocks where established. |
| Player use | Concrete advantage, disadvantage, shortcut or discovery; state any dependency on other unverified behavior. |
| Status | Recovered rule, native witness, derived possibility, external report or unresolved conflict. |
| Route eligibility | Allowed, disallowed or unresolved under the named route rules; keep this separate from whether the behavior exists. |

Reports of ignored intelligence and negative employees/items are investigation
questions until supported for an identified build.
For a reported ignored-stat bug, identify which calculation reads or bypasses
the field, which branches override it and which release contains that path.
Failure to use a stat in one formula does not establish that the stat is useless
everywhere. Explain the practical consequence only within the recovered scope.

For negative hiring or purchasing, preserve the path from input parsing to
validation, arithmetic and committed state. Important distinctions include a
negative value accepted by ordinary input versus injected through a debugger;
signed comparison versus unsigned storage; multiplication before a bounds
check; underflow/wrap versus a genuinely negative balance; and a changed display
versus a committed employee, inventory or money count. Name relevant widths and
rounding only when established. Check subsequent payroll, sale, capacity or save
behavior only to the extent needed for the claim, and mark the rest unresolved.

Do not infer an unlimited-money technique from one favorable arithmetic step.
Costs, later validation, one-shot flags, caps or persistent damage may prevent
repetition. Conversely, do not suppress a useful candidate simply because it
has not yet been executed. An honest entry can say: "The decoded transaction
path predicts a credit for this negative quantity; ordinary input acceptance
and the later inventory update remain unverified." This is an illustrative
statement, not a finding about a real game.

For secret commands or easter eggs, report exact supported vocabulary/inputs,
prerequisites, response, scope and reset/persistence behavior. Distinguish an
intentional exposed code from a disabled developer menu and an accidental state
transition. Preserve source credit and version differences for externally
reported discoveries; label locally confirmed behavior separately.

## Define a minimal legal route

Begin with the route's goal and allowed actions. "Legal" means compatible with
the stated rules, not a synonym for glitchless, intended or ordinary-input play.
A speedrun category, a personal challenge and a completionist route may permit
different techniques. Never infer acceptance from a technique being possible.

| Contract field | Required distinction when it affects the route |
| --- | --- |
| Objective | Reach a named ending/terminal state; minimum actions, shortest time, fewest resources or another explicit objective. |
| Category and authority | Named category/ruleset and exact rule source with consultation date; distinguish official category rules from personal assumptions. |
| Build and execution | Allowed game releases, language, platform, emulator/source port and settings. |
| Timing | Real time, in-game time or another clock; start/end events, loads, pauses, resets and save/load treatment. |
| Permitted actions | Glitches, sequence breaks, RNG manipulation, built-in cheats, debug inputs and any exclusions. |
| Assistance | Human execution, tool-assisted input, macros, savestates, memory edits or modified files, with relevant restrictions. |
| Initial state | New game, prepared save, seed, unlocks, difficulty and carried-over state. |
| Success and evidence | Terminal condition, connected route support, observed run or static justification, and remaining gaps. |

Refresh category rules when making a current eligibility claim. If no named
ruleset is available, state a provisional ordinary-input route contract and
its assumptions, list unresolved permissions and continue the useful analysis.
Do not label it leaderboard-legal without the relevant rules. A research
debugger or source analysis is different from an intervention during the run;
record what actually affected execution. fDisBull's physical/fair-play setting
alone does not certify a competition's rules or a route's correctness.

The shortest command sequence need not be fastest. Account for movement,
animations, dialogue, loads, waiting, timed gates and reset/retry cost under the
declared clock when supported. Distinguish a fast successful attempt from the
expected time to obtain success and from a reliable route. Explain the effects
of random conditions, rare drops, seeded starts or manipulation using the
qualified probabilities and RNG assumptions in the mechanics section.

Use "candidate", "supported route" or "best known within the examined routes"
according to the evidence. A global minimum/optimality claim needs its objective,
allowed action domain and an adequate search or lower-bound argument; one short
successful run is not such a proof. A local improvement can still be valuable.
State the baseline and supported improvement without claiming unexplored
alternatives cannot do better.

## Compare alternate paths and shortcuts

Present alternatives where they change player choice, not as an unordered list
of disconnected tricks. Use a compact branch table with entry prerequisites,
actions, exit state, cost/time basis, score/content tradeoff, hazards, eligibility
and evidence. Include different puzzle solutions, bypasses, sequence breaks,
early access and resource substitutions when recovered, even if they lose score
or omit story content.

Keep the state at branch joins explicit. Two paths reaching the same room may
leave different flags, inventory, time, NPC states or irreversible exclusions.
Show downstream consequences and any supported recovery. An available exit does
not prove the player can arrive with its required key, and a traversable segment
does not prove its compatibility with the rest of the route.

For a proposed shortcut, identify the skipped obligations and why the remaining
progression can still succeed. Separate a static prediction from a recorded
native execution; preserve partial effects and delayed failure. If only a local
segment is established, provide that segment with its starting state and missing
connection. Do not require an exhaustive new playthrough merely to explain it.

For time or probability comparisons, state comparable inputs, units and
conditions. Do not multiply independent-looking event rates when they share RNG
state or conditional triggers. Where the mechanics are incomplete, show the
conditional tradeoff and unresolved quantity instead of inventing a precise
route ranking. A robust fallback after a failed trick is useful when supported.

## Account for completion across runs

Define what "everything" includes for the selected game and release. A maximum
score, an achievement flag, all items and all reachable content are different
objectives. Include relevant endings, branches, optional puzzles, places,
dialogue, items, encounters, secrets, easter eggs and mechanic variants according
to the available inventory and the user's goal. Avoid a universal checklist that
pretends every game exposes the same completion measure.

Keep a compact coverage matrix. For each category or entry, record its stable
ID, inventory denominator, applicability, reachability, requirement, missable
window or exclusion, route/run assignment and evidence. Separate how much was
discovered, how much was examined and how much a player can obtain. If the
inventory itself is incomplete, say so instead of manufacturing a percentage.

Mark one-time opportunities, consumed unique items, irreversible choices and
point-of-no-return conditions before the relevant actions. Explain which
objectives conflict. Use alternate runs or save branches when allowed and
supported; do not concatenate mutually exclusive endings into a single claimed
playthrough. Label "seen across these runs" separately from "held simultaneously"
or "achieved in this save". State whether saving/reloading preserves or resets
the relevant completion state when known.

Keep obtainable content, debug-accessible content and recovered-only material
as separate totals. An unreachable item should not prevent an honestly scoped
ordinary-play collection from being complete, nor disappear from the recovered
resource catalogue. A secret whose reachability is unknown remains an explicit
open entry. Do not describe an inventory of unused assets as gameplay the player
can experience without modification.

## Review the useful claim, not just the label

Reconcile route and discovery summaries with their triggers, effects, evidence,
branch consequences, probability qualifications and version differences. Link
speedrun and completionist advice to relevant bugs, secrets and technical
appendices.

When evidence changes, revisit dependent routes, legality labels and completion
counts, keeping previous claims traceable. Resolve the smallest consequential
gap where authorized; otherwise deliver the supported portion and a precise
next question without promising a trick works, a run is legal or every feature
has been found.
