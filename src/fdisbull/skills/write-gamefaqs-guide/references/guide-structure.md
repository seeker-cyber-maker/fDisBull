# Guide structure and delivery

## Contents

- [Choose a useful scope](#choose-a-useful-scope)
- [Build the reader's route through the document](#build-the-readers-route-through-the-document)
- [Write consequential steps](#write-consequential-steps)
- [Use interpretable tables and maps](#use-interpretable-tables-and-maps)
- [Render only the formats needed](#render-only-the-formats-needed)
- [Review the result](#review-the-result)

## Choose a useful scope

Write a human-readable account of established knowledge. The target can be a
single puzzle, a recovered subsystem, a partial game, or the entire supported
investigation. Match the title and section promises to that scope. A mechanics
reference and a walkthrough can coexist without implying equal coverage.

Adapt to the genre and evidence. An adventure benefits from puzzle dependencies,
parser/action vocabulary, inventory use, timed hazards and dead ends. A strategy
game benefits from unit/economy rules, scenario and faction distinctions, AI
conditions and timing assumptions. An RPG benefits from ability and equipment
tables, calculation order, status interactions and encounter exceptions. Include
those topics only when supported and relevant. Do not mandate a speedrun, sequel
history, copy-protection patch or a particular emulator for every game.

For a reversing-first review, include the material implementation discoveries
even when they do not advance the ordinary route. Unused handlers, defective
calculations, debug features and partially decoded media may be central findings.
Map known coverage and gaps across these areas instead of filling empty chapters
with guesses. Put actionable implications near the relevant player section and
link the detailed evidence/specification in the technical appendix.

## Build the reader's route through the document

Use this as an adaptable outline, not a required chapter count:

| Section | Reader's question |
| --- | --- |
| Title, scope and version | Which game/build is this about, what is supported, and what is still missing? |
| Contents and terminology | Where is the answer, and what do the names and notation mean? |
| Orientation and controls | How do I interpret locations, interaction verbs and important warnings? |
| Progression or strategy | What can I do next, under what conditions, and how will I recognize success? |
| Mechanics | Why does the behavior occur, and when do its rules change? |
| Random events | What is the chance of a named outcome, conditional on what state, and how can choices affect it? |
| Reference tables | Where can I look up a supported value, item, command or relationship? |
| Bugs, cheats, easter eggs and unused code | What was recovered, how can it be triggered, what happens, and which reachability or intent claims remain unresolved? |
| Alternate routes and speedrun techniques | What can be skipped or reordered, what state must be preserved, and which rules permit each technique? |
| Completion checklist | What can be obtained or experienced, what is missable or exclusive, and how many runs are needed under the stated goals? |
| File/media specifications | How are recovered bytes organized and interpreted, and what remains unknown about decoding or playback? |
| Engine/interpreter and related games | Which execution layer supplies the behavior, and which parts of the analysis transfer to a specified edition of another game? |
| Open questions | What remains uncertain, and which advice does that affect? |
| Sources, evidence and revision history | What supports this account, and what changed? |

Put material limits near the start, not solely in a long disclaimer at the end.
For example: `This review covers the extracted inventory and three decoded
puzzles in release R. Their effects are statically supported; no continuous
completion route has been executed.` Use the actual scope, not this invented
example's numbers.

Give sections short stable search codes such as `[SCOPE]`, `[ROUTE-02]` and
`[MECH-HARVEST]`, or stable Markdown anchors. Use a contents list and local
cross-references. Do not change identifiers on every revision. A short document
may need only a few headings; do not bury a useful answer under decorative
banners, an unrelated preface or repeated boilerplate.

Keep game-visible names consistent. Record aliases, localized names and engine
identifiers once in a small mapping when needed. Make it clear when a name is
an analyst's label. Exact parser commands should be distinct from prose. Explain
abbreviations before using them, and keep technical detail near the question it
answers or in a linked appendix.

State the spoiler scope. For a full knowledge review, gameplay and story spoilers
are normally inherent; identify them rather than promising spoiler-free content.
If the user requests progressive hints, separate hint levels from the explicit
solution and check that headings and tables do not reveal later answers early.

## Write consequential steps

Lead with an actionable instruction or a clear known outcome. For a significant
step, include the relevant parts of this compact pattern:

| Part | Meaning |
| --- | --- |
| Before | Location, inventory, flags, resources or earlier events required. |
| Action | Exact parser command, interaction, choice or sequence. |
| Success | What the player can observe and which state/resource changes are supported. |
| Hazard | Timing, irreversible cost, softlock, death or branch consequences, placed before the risky action. |
| Recovery | Supported retry/alternate route or the need for an earlier save. |
| Evidence | A short source ID and qualifier if the reader could otherwise mistake a prediction for an observation. |

Do not manufacture an input from a resource name. In a point-and-click game,
identify the actual interactable and readiness condition when known. In a parser
game, preserve accepted vocabulary and distinguish verified synonyms from guessed
ones. In a timed sequence, define the time basis or state the unresolved timing
limit; do not convert a counter to seconds from assumed frame rate.

Retain partial effects. An unsuccessful action may still spend money, consume a
turn, set a flag or trigger a delayed event. A displayed message need not mean
the effect committed. Describe the effect the evidence supports and its ordering.
Explain why an item must be kept or a warning matters when that relationship is
known; this makes the guide useful beyond blindly following a command list.

Separate required actions, optional score, alternate solutions and assisted
inspection. A final success screen does not by itself establish every scoring or
no-damage claim. A condensed route should link to prerequisites and warnings in
the detailed route. Label an abridgment so omitted details are not mistaken for
unnecessary steps. Let the route's real dependencies determine its length.

### Small illustrative excerpt

The following describes an invented test scenario, not an actual game:

> **Open the observatory.** The recovered handler requires the brass key and a
> lit lamp. Use the key on the north door. Its script clears the locked flag and
> consumes one turn [C12]. This effect is statically supported; the current
> evidence does not show that both prerequisites can be obtained together.

This is useful known behavior without claiming a playable completion route.
If a later target run establishes reachability and the visible result, revise
the same claim with that evidence instead of silently changing its status.

## Use interpretable tables and maps

For tables, name the quantity, units, version and conditions. Distinguish raw
storage values from displayed values; totals from deltas; counts from chances;
unknown from zero; and unavailable from not applicable. Preserve exceptions
near affected rows. Avoid false numerical precision and unexplained blank cells.

State what a catalogue contains and what is omitted. A selection of parser words
is a useful reference when named as a selection. A reported total from an earlier
guide does not make the displayed selection complete or freshly extracted.
Keep evidence coverage and presentation coverage separate.

Use linked inventories for discoveries and completion goals. A score total, all
endings, every collectible, all dialogue branches and all recovered resources
measure different things. Identify exclusive alternatives and inaccessible
entries before presenting a single-run checklist. A short route should name
what it skips and link to the optional content it bypasses. Use
[Routes and discoveries](routes-and-discoveries.md) for the coverage and route
contracts, and [Formats and engine reuse](formats-and-engine-reuse.md) for
implementable layout tables and qualified cross-game comparisons.

For maps or dependency diagrams, label known connections, directionality,
conditions and uncertain edges. A coordinate catalogue or screen adjacency graph
does not automatically establish a traversable route. Prefer a compact rendered
diagram or image when it materially helps; preserve readable textual names and
connections for an optional text edition. Do not invent geography to fill gaps.

## Render only the formats needed

Use Markdown by default for repository review: normal paragraphs, meaningful
headings, concise tables and links. This is a delivery choice, not a claim that
GameFAQs accepts Markdown directly. Keep one reviewed set of facts and derive
any other rendition from it.

For a requested legacy text edition, use an explicitly named export profile:

- Target 79 columns as a conservative local convention; check that no intended
  text line exceeds 80 columns. The source examples distinguish historical staff
  guidance from current verified submission requirements.
- Use spaces instead of tabs and inspect fixed-width tables in a monospace view.
  If ASCII-only output is requested, check encoding explicitly; a width check
  alone cannot detect Unicode punctuation or guarantee display width.
- Replace unsupported typography thoughtfully. Preserve spelling, localized
  names, mathematical meaning and search codes; provide an explicit alias where
  transliteration is necessary.
- Wrap prose; redesign wide tables instead of cutting values. Keep formulas
  legible and operator precedence unambiguous.
- Preserve resolvable source URLs. If a URL cannot fit the chosen profile, keep
  it intact in a declared reference exception or a companion source list; never
  split or invent a shortened URL and claim the text fully passes the profile.

Report the check actually run: line width, encoding, navigation or equivalent
facts. Do not call that `100% GameFAQs compliant` or promise acceptance. HTML
guides on GameFAQs have their own editor; a locally rendered HTML document is
not proof of compatibility with that editor. Refresh current submission guidance
only if publication is actually part of the task.

## Review the result

Check the full written artifact, not just its outline:

1. Match each consequential claim, heading and completeness label to evidence.
2. Ensure all material supported findings in scope appear somewhere useful;
   preserve exceptions, unknowns and conflicts.
3. Check the starting state, dependencies, hazards and observable result of
   consequential instructions. Do not smooth over disconnected route segments.
4. Reconcile prose, numerical tables, formulas, pseudocode and any compact route.
5. Verify contents entries, search codes, cross-references and terminology.
6. Compare alternate formats for lost warnings, source qualifiers or release
   limits. Declare intentional abridgments.
7. Check attribution, actual author facts, revision changes and the user's chosen
   distribution scope. Avoid copied personal or legal boilerplate.

Deliver the human-readable result even when some facts remain unknown. Explain
the material gap and its impact locally. A later research task can fill that
gap; the writing task does not require pretending it has already been solved.
